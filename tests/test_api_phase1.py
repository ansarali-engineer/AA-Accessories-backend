import pytest
from rest_framework.test import APIClient

from orders.models import Order
from tests.factories import CategoryFactory, CustomerFactory, EmployeeFactory, ProductFactory, StaffUserFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def staff_client():
    api_client = APIClient()
    user = StaffUserFactory(username="staff")
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def customer_client():
    api_client = APIClient()
    customer = CustomerFactory(user__username="customer")
    api_client.force_authenticate(user=customer.user)
    api_client.customer = customer
    return api_client


@pytest.mark.django_db
def test_cors_allows_local_frontend_origin(api_client):
    response = api_client.get("/api/products/", HTTP_ORIGIN="http://localhost:5173")

    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_cors_handles_preflight_request(api_client):
    response = api_client.options(
        "/api/products/",
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "GET" in response["Access-Control-Allow-Methods"]


@pytest.mark.django_db
def test_category_crud(staff_client):
    response = staff_client.post("/api/categories/", {"name": "Electronics", "slug": "electronics"}, format="json")

    assert response.status_code == 201
    category_id = response.data["id"]

    list_response = staff_client.get("/api/categories/?search=elect")
    assert list_response.status_code == 200
    assert list_response.data["count"] == 1

    patch_response = staff_client.patch(f"/api/categories/{category_id}/", {"is_active": False}, format="json")
    assert patch_response.status_code == 200
    assert patch_response.data["is_active"] is False


@pytest.mark.django_db
def test_product_crud_and_validation(staff_client):
    category = CategoryFactory()
    response = staff_client.post(
        "/api/products/",
        {
            "sku": "SKU-100",
            "name": "Desk Lamp",
            "category": category.id,
            "price": "40.00",
            "stock": 20,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["category_name"] == category.name

    invalid = staff_client.post(
        "/api/products/",
        {"sku": "SKU-101", "name": "Bad Price", "category": category.id, "price": "0.00", "stock": 1},
        format="json",
    )
    assert invalid.status_code == 400
    assert invalid.data["success"] is False


@pytest.mark.django_db
def test_customer_crud(staff_client):
    response = staff_client.post(
        "/api/customers/",
        {
            "username": "newcustomer",
            "email": "newcustomer@example.com",
            "first_name": "New",
            "last_name": "Customer",
            "city": "Denver",
            "tier": "silver",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["user"]["email"] == "newcustomer@example.com"
    assert staff_client.get("/api/customers/?tier=silver").data["count"] == 1


@pytest.mark.django_db
def test_public_customer_registration_can_sign_in_and_place_order(api_client):
    registration = api_client.post(
        "/api/customers/register/",
        {
            "username": "newbuyer",
            "email": "newbuyer@example.com",
            "password": "A-strong-customer-password-42!",
            "first_name": "New",
            "last_name": "Buyer",
            "phone": "+15555550123",
            "city": "Austin",
        },
        format="json",
    )

    assert registration.status_code == 201
    assert registration.data["user"]["username"] == "newbuyer"

    token_response = api_client.post(
        "/api/auth/token/",
        {"username": "newbuyer", "password": "A-strong-customer-password-42!"},
        format="json",
    )
    assert token_response.status_code == 200
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}")

    product = ProductFactory(stock=3)
    order_response = api_client.post(
        "/api/orders/",
        {"items": [{"product": product.pk, "quantity": 1}]},
        format="json",
    )

    assert order_response.status_code == 201
    assert order_response.data["customer"] == registration.data["id"]


@pytest.mark.django_db
def test_public_customer_registration_validates_password(api_client):
    response = api_client.post(
        "/api/customers/register/",
        {
            "username": "weakpasswordbuyer",
            "email": "weakpasswordbuyer@example.com",
            "password": "password",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "password" in response.data["error"]["message"]


@pytest.mark.django_db
def test_staff_can_retrieve_current_user_without_customer_profile(api_client):
    staff_user = StaffUserFactory(username="staff-without-customer")
    api_client.force_authenticate(user=staff_user)

    response = api_client.get("/api/auth/me/")

    assert response.status_code == 200
    assert response.data["id"] == staff_user.id
    assert response.data["is_staff"] is True


def test_current_user_requires_authentication(api_client):
    response = api_client.get("/api/auth/me/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_employee_crud(staff_client):
    manager = EmployeeFactory(first_name="Manager", email="manager@example.com")
    response = staff_client.post(
        "/api/employees/",
        {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "title": "Analyst",
            "department": "Finance",
            "salary": "85000.00",
            "manager": manager.id,
            "hired_at": "2023-02-01",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["manager_name"] == str(manager)


@pytest.mark.django_db
def test_order_create_with_nested_items(staff_client):
    customer = CustomerFactory()
    product = ProductFactory(price="99.99")
    response = staff_client.post(
        "/api/orders/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": 2}],
        },
        format="json",
    )

    assert response.status_code == 201
    order = Order.objects.get(id=response.data["id"])
    assert order.items.count() == 1
    assert str(order.total_amount) == "199.98"


@pytest.mark.django_db
def test_customer_places_own_order_and_stock_is_deducted(customer_client):
    other_customer = CustomerFactory()
    product = ProductFactory(price="50.00", stock=3)

    response = customer_client.post(
        "/api/orders/",
        {
            "customer": other_customer.id,
            "items": [{"product": product.id, "quantity": 2}],
        },
        format="json",
    )

    product.refresh_from_db()
    assert response.status_code == 201
    assert response.data["customer"] == customer_client.customer.id
    assert response.data["status"] == "placed"
    assert product.stock == 1


@pytest.mark.django_db
def test_customer_cancels_own_order_and_stock_is_restored(customer_client):
    product = ProductFactory(stock=3)
    create_response = customer_client.post(
        "/api/orders/",
        {"items": [{"product": product.id, "quantity": 2}]},
        format="json",
    )
    product.refresh_from_db()
    assert product.stock == 1

    response = customer_client.post(f"/api/orders/{create_response.data['id']}/cancel/")

    product.refresh_from_db()
    assert response.status_code == 200
    assert response.data["status"] == Order.Status.CANCELLED
    assert product.stock == 3


@pytest.mark.django_db
def test_cancelled_order_cannot_be_cancelled_twice(customer_client):
    product = ProductFactory(stock=3)
    create_response = customer_client.post(
        "/api/orders/",
        {"items": [{"product": product.id, "quantity": 2}]},
        format="json",
    )
    order_id = create_response.data["id"]
    customer_client.post(f"/api/orders/{order_id}/cancel/")

    response = customer_client.post(f"/api/orders/{order_id}/cancel/")

    product.refresh_from_db()
    assert response.status_code == 400
    assert product.stock == 3


@pytest.mark.django_db
def test_paid_order_cannot_be_cancelled_without_refund_flow(customer_client):
    product = ProductFactory(stock=3)
    create_response = customer_client.post(
        "/api/orders/",
        {"items": [{"product": product.id, "quantity": 2}]},
        format="json",
    )
    order = Order.objects.get(id=create_response.data["id"])
    order.status = Order.Status.PAID
    order.save(update_fields=["status"])

    response = customer_client.post(f"/api/orders/{order.id}/cancel/")

    product.refresh_from_db()
    assert response.status_code == 400
    assert product.stock == 1


@pytest.mark.django_db
def test_order_status_cannot_be_set_when_creating_order(customer_client):
    product = ProductFactory(stock=3)

    response = customer_client.post(
        "/api/orders/",
        {"status": "paid", "items": [{"product": product.id, "quantity": 1}]},
        format="json",
    )

    product.refresh_from_db()
    assert response.status_code == 400
    assert product.stock == 3


@pytest.mark.django_db
def test_generic_order_update_and_delete_are_disabled(customer_client):
    product = ProductFactory()
    create_response = customer_client.post(
        "/api/orders/",
        {"items": [{"product": product.id, "quantity": 1}]},
        format="json",
    )
    order_url = f"/api/orders/{create_response.data['id']}/"

    assert customer_client.patch(order_url, {"status": "cancelled"}, format="json").status_code == 405
    assert customer_client.delete(order_url).status_code == 405


@pytest.mark.django_db
def test_order_rejects_quantity_above_available_stock(customer_client):
    product = ProductFactory(stock=1)

    response = customer_client.post(
        "/api/orders/",
        {"items": [{"product": product.id, "quantity": 2}]},
        format="json",
    )

    product.refresh_from_db()
    assert response.status_code == 400
    assert product.stock == 1


@pytest.mark.django_db
def test_customer_only_sees_own_orders(customer_client, staff_client):
    own_product = ProductFactory(sku="OWN-1")
    other_product = ProductFactory(sku="OTHER-1")
    own_response = customer_client.post(
        "/api/orders/",
        {"items": [{"product": own_product.id, "quantity": 1}]},
        format="json",
    )
    other_customer = CustomerFactory()
    staff_client.post(
        "/api/orders/",
        {"customer": other_customer.id, "items": [{"product": other_product.id, "quantity": 1}]},
        format="json",
    )

    list_response = customer_client.get("/api/orders/")

    assert list_response.status_code == 200
    assert list_response.data["count"] == 1
    assert list_response.data["results"][0]["id"] == own_response.data["id"]


@pytest.mark.django_db
def test_customer_me_endpoint(customer_client):
    response = customer_client.patch("/api/customers/me/", {"city": "Seattle"}, format="json")

    assert response.status_code == 200
    assert response.data["city"] == "Seattle"


@pytest.mark.django_db
def test_anonymous_users_can_read_but_not_write(api_client):
    ProductFactory()

    assert api_client.get("/api/products/").status_code == 200
    assert api_client.post("/api/products/", {}, format="json").status_code == 401
