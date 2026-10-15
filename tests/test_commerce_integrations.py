from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from orders.models import Order, Payment
from tests.factories import CustomerFactory, ProductFactory, StaffUserFactory


@pytest.fixture
def commerce_clients():
    customer = CustomerFactory()
    customer_client = APIClient()
    customer_client.force_authenticate(user=customer.user)

    staff_client = APIClient()
    staff_client.force_authenticate(user=StaffUserFactory())
    return customer, customer_client, staff_client


def create_order(client, product, payment_method="card"):
    response = client.post(
        "/api/orders/",
        {
            "payment_method": payment_method,
            "items": [{"product": product.pk, "quantity": 2}],
        },
        format="json",
    )
    assert response.status_code == 201
    return Order.objects.get(pk=response.data["id"])


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_configured")
def test_customer_can_create_and_retrieve_payment_intent(commerce_clients):
    _, customer_client, _ = commerce_clients
    product = ProductFactory(price="12.50", stock=4)
    order = create_order(customer_client, product)
    intent = {"id": "pi_test_1", "client_secret": "pi_test_1_secret"}

    with (
        patch("orders.payment_services._create_stripe_payment_intent", return_value=intent),
        patch("orders.payment_services._retrieve_stripe_payment_intent", return_value=intent),
    ):
        first = customer_client.post(f"/api/orders/{order.pk}/pay/")
        second = customer_client.post(f"/api/orders/{order.pk}/pay/")

    assert first.status_code == 200
    assert first.data == {
        "payment_intent_id": "pi_test_1",
        "client_secret": "pi_test_1_secret",
        "amount": 2500,
        "currency": "usd",
    }
    assert second.data["client_secret"] == first.data["client_secret"]
    assert Payment.objects.get(order=order).stripe_payment_intent_id == "pi_test_1"


@pytest.mark.django_db
def test_payment_endpoint_reports_missing_stripe_configuration(commerce_clients):
    _, customer_client, _ = commerce_clients
    order = create_order(customer_client, ProductFactory(stock=4))

    with override_settings(STRIPE_SECRET_KEY=""):
        response = customer_client.post(f"/api/orders/{order.pk}/pay/")

    assert response.status_code == 503


@pytest.mark.django_db
@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
def test_signed_payment_success_webhook_marks_order_paid(commerce_clients):
    _, customer_client, _ = commerce_clients
    product = ProductFactory(stock=4)
    order = create_order(customer_client, product)
    Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_test_paid",
        amount=2000,
        currency="usd",
    )
    event = {
        "id": "evt_payment_succeeded",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_test_paid"}},
    }

    with patch("orders.webhooks.stripe.Webhook.construct_event", return_value=event):
        response = APIClient().post(
            "/api/payments/stripe/webhook/",
            data=b'{"type":"payment_intent.succeeded"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid-signature",
        )

    order.refresh_from_db()
    payment = Payment.objects.get(order=order)
    assert response.status_code == 200
    assert order.status == Order.Status.PAID
    assert payment.status == Payment.Status.SUCCEEDED


@pytest.mark.django_db
@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
def test_invalid_stripe_webhook_is_rejected():
    with patch("orders.webhooks.stripe.Webhook.construct_event", side_effect=ValueError):
        response = APIClient().post(
            "/api/payments/stripe/webhook/",
            data=b"invalid",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="invalid-signature",
        )

    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_configured")
def test_staff_refund_restores_inventory(commerce_clients):
    _, customer_client, staff_client = commerce_clients
    product = ProductFactory(price="10.00", stock=4)
    order = create_order(customer_client, product)
    order.status = Order.Status.PAID
    order.save(update_fields=["status"])
    payment = Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_test_refund",
        amount=2000,
        currency="usd",
        status=Payment.Status.SUCCEEDED,
    )
    refund = {"id": "re_test_1", "status": "succeeded"}

    with patch("orders.payment_services._create_stripe_refund", return_value=refund):
        response = staff_client.post(f"/api/orders/{order.pk}/refund/")

    product.refresh_from_db()
    order.refresh_from_db()
    payment.refresh_from_db()
    assert response.status_code == 200
    assert order.status == Order.Status.CANCELLED
    assert payment.status == Payment.Status.REFUNDED
    assert product.stock == 4


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_configured")
@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
def test_pending_refund_is_completed_by_stripe_webhook(commerce_clients):
    _, customer_client, staff_client = commerce_clients
    product = ProductFactory(price="10.00", stock=4)
    order = create_order(customer_client, product)
    order.status = Order.Status.PAID
    order.save(update_fields=["status"])
    payment = Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_test_pending_refund",
        amount=2000,
        currency="usd",
        status=Payment.Status.SUCCEEDED,
    )

    with patch(
        "orders.payment_services._create_stripe_refund",
        return_value={"id": "re_test_pending", "status": "pending"},
    ):
        response = staff_client.post(f"/api/orders/{order.pk}/refund/")
    assert response.status_code == 200
    product.refresh_from_db()
    assert product.stock == 2

    event = {
        "id": "evt_refund_succeeded",
        "type": "refund.updated",
        "data": {
            "object": {
                "id": "re_test_pending",
                "payment_intent": "pi_test_pending_refund",
                "amount": 2000,
                "status": "succeeded",
            }
        },
    }
    with patch("orders.webhooks.stripe.Webhook.construct_event", return_value=event):
        webhook_response = APIClient().post(
            "/api/payments/stripe/webhook/",
            data=b'{"type":"refund.updated"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid-signature",
        )

    order.refresh_from_db()
    payment.refresh_from_db()
    product.refresh_from_db()
    assert webhook_response.status_code == 200
    assert order.status == Order.Status.CANCELLED
    assert payment.status == Payment.Status.REFUNDED
    assert product.stock == 4


@pytest.mark.django_db
def test_staff_can_record_shipment_and_delivery(commerce_clients):
    _, customer_client, staff_client = commerce_clients
    product = ProductFactory(stock=4)
    order = create_order(customer_client, product)
    order.status = Order.Status.PAID
    order.save(update_fields=["status"])
    Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_test_shipment",
        amount=2000,
        currency="usd",
        status=Payment.Status.SUCCEEDED,
    )

    ship_response = staff_client.post(
        f"/api/orders/{order.pk}/ship/",
        {"carrier": "Example Carrier", "tracking_number": "TRACK-123"},
        format="json",
    )
    assert ship_response.status_code == 200
    assert ship_response.data["status"] == Order.Status.SHIPPED
    assert ship_response.data["shipment"]["tracking_number"] == "TRACK-123"

    deliver_response = staff_client.post(f"/api/orders/{order.pk}/deliver/")

    order.refresh_from_db()
    assert deliver_response.status_code == 200
    assert order.status == Order.Status.DELIVERED
    assert deliver_response.data["shipment"]["status"] == "delivered"
    assert deliver_response.data["shipment"]["delivered_at"] is not None


@pytest.mark.django_db
def test_cash_on_delivery_order_can_be_created_shipped_and_delivered(commerce_clients):
    _, customer_client, staff_client = commerce_clients
    product = ProductFactory(stock=4)
    order = create_order(customer_client, product, payment_method="cash_on_delivery")

    assert order.payment_method == Order.PaymentMethod.CASH_ON_DELIVERY

    pay_response = customer_client.post(f"/api/orders/{order.pk}/pay/")
    assert pay_response.status_code == 400

    ship_response = staff_client.post(
        f"/api/orders/{order.pk}/ship/",
        {"carrier": "Example Carrier", "tracking_number": "COD-123"},
        format="json",
    )
    assert ship_response.status_code == 200
    assert ship_response.data["payment_method"] == Order.PaymentMethod.CASH_ON_DELIVERY
    assert ship_response.data["shipment"]["tracking_number"] == "COD-123"

    deliver_response = staff_client.post(f"/api/orders/{order.pk}/deliver/")
    order.refresh_from_db()
    assert deliver_response.status_code == 200
    assert order.status == Order.Status.DELIVERED


@pytest.mark.django_db
def test_order_rejects_unknown_payment_method(commerce_clients):
    _, customer_client, _ = commerce_clients
    product = ProductFactory(stock=4)

    response = customer_client.post(
        "/api/orders/",
        {
            "payment_method": "wire_transfer",
            "items": [{"product": product.pk, "quantity": 1}],
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.status_code == 400


@pytest.mark.django_db
def test_staff_can_update_order_status_through_lifecycle_action(commerce_clients):
    _, customer_client, staff_client = commerce_clients
    product = ProductFactory(stock=4)
    order = create_order(customer_client, product)

    cancel_response = staff_client.post(
        f"/api/orders/{order.pk}/status/",
        {"status": Order.Status.CANCELLED},
        format="json",
    )

    product.refresh_from_db()
    order.refresh_from_db()
    assert cancel_response.status_code == 200
    assert order.status == Order.Status.CANCELLED
    assert product.stock == 4

    paid_order = create_order(customer_client, product)
    paid_order.status = Order.Status.PAID
    paid_order.save(update_fields=["status"])
    Payment.objects.create(
        order=paid_order,
        stripe_payment_intent_id="pi_test_status",
        amount=2000,
        currency="usd",
        status=Payment.Status.SUCCEEDED,
    )
    staff_client.post(
        f"/api/orders/{paid_order.pk}/ship/",
        {"carrier": "Example Carrier", "tracking_number": "STATUS-123"},
        format="json",
    )
    deliver_response = staff_client.post(
        f"/api/orders/{paid_order.pk}/status/",
        {"status": Order.Status.DELIVERED},
        format="json",
    )
    paid_order.refresh_from_db()

    assert deliver_response.status_code == 200
    assert paid_order.status == Order.Status.DELIVERED
    assert deliver_response.data["shipment"]["delivered_at"] is not None


@pytest.mark.django_db
def test_customers_cannot_update_order_status_and_managed_states_are_rejected(commerce_clients):
    _, customer_client, staff_client = commerce_clients
    order = create_order(customer_client, ProductFactory(stock=4))

    forbidden = customer_client.post(
        f"/api/orders/{order.pk}/status/",
        {"status": Order.Status.CANCELLED},
        format="json",
    )
    unmanaged = staff_client.post(
        f"/api/orders/{order.pk}/status/",
        {"status": Order.Status.PAID},
        format="json",
    )

    order.refresh_from_db()
    assert forbidden.status_code == 403
    assert unmanaged.status_code == 400
    assert order.status == Order.Status.PLACED


@pytest.mark.django_db
def test_customer_cannot_issue_refund_or_create_shipment(commerce_clients):
    _, customer_client, staff_client = commerce_clients
    product = ProductFactory(stock=4)
    order = create_order(customer_client, product)
    order.status = Order.Status.PAID
    order.save(update_fields=["status"])
    Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_test_forbidden",
        amount=2000,
        currency="usd",
        status=Payment.Status.SUCCEEDED,
    )

    refund_response = customer_client.post(f"/api/orders/{order.pk}/refund/")
    shipment_response = customer_client.post(
        f"/api/orders/{order.pk}/ship/",
        {"carrier": "Example Carrier", "tracking_number": "TRACK-456"},
        format="json",
    )

    assert refund_response.status_code == 403
    assert shipment_response.status_code == 403


@pytest.mark.django_db
@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
def test_refund_after_delivery_does_not_add_stock_back(commerce_clients):
    _, customer_client, staff_client = commerce_clients
    product = ProductFactory(stock=4)
    order = create_order(customer_client, product)
    order.status = Order.Status.PAID
    order.save(update_fields=["status"])
    Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_test_delivered_refund",
        amount=2000,
        currency="usd",
        status=Payment.Status.SUCCEEDED,
    )
    staff_client.post(
        f"/api/orders/{order.pk}/ship/",
        {"carrier": "Example Carrier", "tracking_number": "TRACK-789"},
        format="json",
    )
    staff_client.post(f"/api/orders/{order.pk}/deliver/")
    event = {
        "id": "evt_external_refund",
        "type": "charge.refunded",
        "data": {
            "object": {
                "payment_intent": "pi_test_delivered_refund",
                "amount_refunded": 2000,
            }
        },
    }

    with patch("orders.webhooks.stripe.Webhook.construct_event", return_value=event):
        response = APIClient().post(
            "/api/payments/stripe/webhook/",
            data=b'{"type":"charge.refunded"}',
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid-signature",
        )

    product.refresh_from_db()
    assert response.status_code == 200
    assert product.stock == 2
