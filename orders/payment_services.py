import logging

import stripe
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import APIException, ValidationError

from orders.models import Order, Payment

logger = logging.getLogger(__name__)

ZERO_DECIMAL_CURRENCIES = {
    "bif", "clp", "djf", "gnf", "isk", "jpy", "kmf", "krw", "mga", "pyg",
    "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
}
THREE_DECIMAL_CURRENCIES = {"bhd", "iqd", "jod", "kwd", "lyd", "omr", "tnd"}


class PaymentProviderError(APIException):
    status_code = 502
    default_detail = "The payment provider could not complete the request."
    default_code = "payment_provider_error"


class PaymentNotConfigured(APIException):
    status_code = 503
    default_detail = "Stripe payments are not configured."
    default_code = "payment_not_configured"


def _stripe_client():
    if not settings.STRIPE_SECRET_KEY:
        raise PaymentNotConfigured()
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


def _create_stripe_payment_intent(*, amount, currency, order):
    return _stripe_client().v1.payment_intents.create(
        {
            "amount": amount,
            "currency": currency,
            "automatic_payment_methods": {"enabled": True},
            "metadata": {"order_id": str(order.pk)},
        },
        options={"idempotency_key": f"order-{order.pk}-payment-intent"},
    )


def _retrieve_stripe_payment_intent(payment_intent_id):
    return _stripe_client().v1.payment_intents.retrieve(payment_intent_id)


def _cancel_stripe_payment_intent(payment_intent_id):
    return _stripe_client().v1.payment_intents.cancel(payment_intent_id)


def _create_stripe_refund(*, payment_intent_id, order_id):
    return _stripe_client().v1.refunds.create(
        {"payment_intent": payment_intent_id},
        options={"idempotency_key": f"order-{order_id}-full-refund"},
    )


def _provider_call(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except stripe.StripeError as exc:
        logger.exception("Stripe request failed")
        raise PaymentProviderError() from exc


@transaction.atomic
def create_payment_intent(*, order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.payment_method != Order.PaymentMethod.CARD:
        raise ValidationError({"payment_method": "Stripe payment is only available for card orders."})
    if order.status != Order.Status.PLACED:
        raise ValidationError({"status": "Payment can only be initiated for a placed order."})

    payment = Payment.objects.filter(order=order).first()
    if payment and payment.status == Payment.Status.CANCELLED:
        raise ValidationError({"payment": "The payment for this order was cancelled."})

    if payment and payment.stripe_payment_intent_id:
        intent = _provider_call(_retrieve_stripe_payment_intent, payment.stripe_payment_intent_id)
    else:
        currency = settings.STRIPE_CURRENCY
        if len(currency) != 3 or not currency.isalpha():
            raise PaymentNotConfigured("STRIPE_CURRENCY must be a three-letter currency code.")
        if currency in ZERO_DECIMAL_CURRENCIES:
            if order.total_amount != order.total_amount.to_integral_value():
                raise ValidationError(
                    {"amount": "This currency does not support fractional-unit order totals."}
                )
            multiplier = 1
        elif currency in THREE_DECIMAL_CURRENCIES:
            multiplier = 1000
        else:
            multiplier = 100
        amount = int(order.total_amount * multiplier)
        intent = _provider_call(
            _create_stripe_payment_intent,
            amount=amount,
            currency=currency,
            order=order,
        )
        payment = Payment.objects.create(
            order=order,
            stripe_payment_intent_id=intent["id"],
            amount=amount,
            currency=currency,
        )

    return {
        "payment_intent_id": intent["id"],
        "client_secret": intent["client_secret"],
        "amount": payment.amount,
        "currency": payment.currency,
    }


@transaction.atomic
def cancel_payment_intent(*, payment):
    if payment.stripe_payment_intent_id and payment.status in (
        Payment.Status.PENDING,
        Payment.Status.FAILED,
    ):
        _provider_call(_cancel_stripe_payment_intent, payment.stripe_payment_intent_id)
        payment.status = Payment.Status.CANCELLED
        payment.save(update_fields=["status", "updated_at"])


def _restore_inventory(order):
    from catalog.models import Product
    from orders.models import OrderItem

    items = list(OrderItem.objects.filter(order=order).order_by("product_id"))
    products = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=[item.product_id for item in items])
        .order_by("pk")
    }
    for item in items:
        products[item.product_id].stock += item.quantity
    Product.objects.bulk_update(products.values(), ["stock"])


def _finalize_refund(payment):
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if payment.status == Payment.Status.REFUNDED and order.status == Order.Status.CANCELLED:
        return
    if order.status in (
        Order.Status.PLACED,
        Order.Status.PAID,
        Order.Status.REFUND_PENDING,
    ):
        _restore_inventory(order)
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    payment.status = Payment.Status.REFUNDED
    payment.save(update_fields=["status", "updated_at"])


@transaction.atomic
def refund_order(*, order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PAID:
        raise ValidationError({"status": "Only paid, unshipped orders can be refunded."})

    payment = Payment.objects.select_for_update().filter(order=order).first()
    if payment is None or payment.status != Payment.Status.SUCCEEDED:
        raise ValidationError({"payment": "A successful payment is required for a refund."})

    refund = _provider_call(
        _create_stripe_refund,
        payment_intent_id=payment.stripe_payment_intent_id,
        order_id=order.pk,
    )
    payment.stripe_refund_id = refund["id"]

    if refund["status"] == "succeeded":
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["stripe_refund_id", "status", "updated_at"])
        _finalize_refund(payment)
    elif refund["status"] == "pending":
        payment.status = Payment.Status.REFUND_PENDING
        payment.save(update_fields=["stripe_refund_id", "status", "updated_at"])
        order.status = Order.Status.REFUND_PENDING
        order.save(update_fields=["status", "updated_at"])
    else:
        raise PaymentProviderError("Stripe did not confirm the refund.")
    return payment


@transaction.atomic
def handle_stripe_event(event):
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type.startswith("payment_intent."):
        payment = (
            Payment.objects
            .filter(stripe_payment_intent_id=data["id"])
            .first()
        )
        if payment is None:
            logger.warning("Received Stripe event for an unknown PaymentIntent")
            return

        order = Order.objects.select_for_update().get(pk=payment.order_id)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if event_type == "payment_intent.succeeded":
            if order.status == Order.Status.CANCELLED:
                refund = _provider_call(
                    _create_stripe_refund,
                    payment_intent_id=payment.stripe_payment_intent_id,
                    order_id=order.pk,
                )
                if refund["status"] not in ("succeeded", "pending"):
                    raise PaymentProviderError("Stripe could not refund a late payment.")
                payment.stripe_refund_id = refund["id"]
                payment.status = (
                    Payment.Status.REFUNDED
                    if refund["status"] == "succeeded"
                    else Payment.Status.REFUND_PENDING
                )
                payment.save(update_fields=["stripe_refund_id", "status", "updated_at"])
                return
            if order.status == Order.Status.PLACED:
                payment.status = Payment.Status.SUCCEEDED
                order.status = Order.Status.PAID
                payment.save(update_fields=["status", "updated_at"])
                order.save(update_fields=["status", "updated_at"])
        elif event_type == "payment_intent.payment_failed":
            if payment.status == Payment.Status.PENDING:
                payment.status = Payment.Status.FAILED
                payment.save(update_fields=["status", "updated_at"])
        elif event_type == "payment_intent.canceled":
            if payment.status in (Payment.Status.PENDING, Payment.Status.FAILED):
                payment.status = Payment.Status.CANCELLED
                payment.save(update_fields=["status", "updated_at"])
        return

    if event_type in ("charge.refunded", "refund.updated"):
        payment_intent_id = data.get("payment_intent")
        payment = (
            Payment.objects
            .filter(stripe_payment_intent_id=payment_intent_id)
            .first()
        )
        if payment is None:
            logger.warning("Received Stripe refund event for an unknown PaymentIntent")
            return

        Order.objects.select_for_update().get(pk=payment.order_id)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        full_refund = (
            data.get("status") == "succeeded" and data.get("amount") == payment.amount
            if event_type == "refund.updated"
            else data.get("amount_refunded") == payment.amount
        )
        if full_refund:
            _finalize_refund(payment)
