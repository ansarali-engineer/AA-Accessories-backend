from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from catalog.models import Product
from orders.models import Order, OrderItem, Payment, Shipment


@dataclass(frozen=True)
class OrderLineInput:
    product_id: int
    quantity: int


@transaction.atomic
def place_order(*, customer, lines, payment_method=Order.PaymentMethod.CARD):
    product_ids = [line.product_id for line in lines]
    products = {
        product.id: product
        for product in Product.objects.select_for_update().filter(id__in=product_ids).order_by("id")
    }

    if len(products) != len(set(product_ids)):
        raise serializers.ValidationError({"items": "One or more products do not exist."})

    inactive = [product.name for product in products.values() if not product.is_active]
    if inactive:
        raise serializers.ValidationError({"items": f"Inactive products cannot be ordered: {', '.join(inactive)}."})

    for line in lines:
        product = products[line.product_id]
        if line.quantity > product.stock:
            raise serializers.ValidationError(
                {"items": f"Only {product.stock} units available for {product.name}."}
            )

    total = sum(products[line.product_id].price * Decimal(line.quantity) for line in lines)
    order = Order.objects.create(
        customer=customer,
        status=Order.Status.PLACED,
        payment_method=payment_method,
        total_amount=total,
    )

    order_items = [
        OrderItem(
            order=order,
            product=products[line.product_id],
            quantity=line.quantity,
            unit_price=products[line.product_id].price,
        )
        for line in lines
    ]
    OrderItem.objects.bulk_create(order_items)

    for line in lines:
        products[line.product_id].stock -= line.quantity
    Product.objects.bulk_update(products.values(), ["stock"])

    return order


@transaction.atomic
def cancel_order(*, order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PLACED:
        raise serializers.ValidationError(
            {"status": "Only placed orders can be cancelled."}
        )

    payment = Payment.objects.select_for_update().filter(order=order).first()
    if payment:
        from orders.payment_services import cancel_payment_intent

        cancel_payment_intent(payment=payment)

    items = list(order.items.order_by("product_id"))
    products = {
        product.id: product
        for product in Product.objects.select_for_update()
        .filter(id__in=[item.product_id for item in items])
        .order_by("id")
    }

    for item in items:
        products[item.product_id].stock += item.quantity
    Product.objects.bulk_update(products.values(), ["stock"])

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def ship_order(*, order_id, carrier, tracking_number):
    order = Order.objects.select_for_update().get(pk=order_id)
    can_ship_cod_order = (
        order.status == Order.Status.PLACED
        and order.payment_method == Order.PaymentMethod.CASH_ON_DELIVERY
    )
    if order.status != Order.Status.PAID and not can_ship_cod_order:
        raise serializers.ValidationError(
            {"status": "Only paid orders or cash-on-delivery orders can be shipped."}
        )
    if Shipment.objects.filter(order=order).exists():
        raise serializers.ValidationError({"shipment": "This order already has a shipment."})

    shipment = Shipment.objects.create(
        order=order,
        carrier=carrier,
        tracking_number=tracking_number,
    )
    order.status = Order.Status.SHIPPED
    order.save(update_fields=["status", "updated_at"])
    return shipment


@transaction.atomic
def mark_order_delivered(*, order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.SHIPPED:
        raise serializers.ValidationError({"status": "Only shipped orders can be marked delivered."})

    shipment = Shipment.objects.select_for_update().get(order=order)
    shipment.status = Shipment.Status.DELIVERED
    shipment.delivered_at = timezone.now()
    shipment.save(update_fields=["status", "delivered_at"])
    order.status = Order.Status.DELIVERED
    order.save(update_fields=["status", "updated_at"])
    return shipment
