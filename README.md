# AA Accessories

AA Accessories online store API and backend.

## Roadmap

1. Phase 1: project setup, PostgreSQL-ready settings, models, migrations, seed data, first CRUD endpoints.
2. Phase 2: JWT flows, role-based permissions, nested serializers, custom validation, order stock deduction.
3. Phase 3: filtering/search/ordering, pagination variants, throttling, custom errors, OpenAPI polish.
4. Phase 4: complex ORM and SQL endpoints, including window functions, CTEs, N+1 fixes, and EXPLAIN.
5. Phase 5: Redis caching, Celery jobs, data-structure-backed features, coverage hardening.

## Folder Structure

```text
accounts/   Customer profiles and auth-facing APIs
catalog/    Categories and products
orders/     Orders and order items
analytics/  Reporting endpoints in later phases
hr/         Employees and manager hierarchy
common/     Shared pagination, permissions, exceptions
tests/      Pytest API tests and factories
```

## Local Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
docker compose up -d db redis
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Pytest uses SQLite by default for fast local feedback. Set `USE_POSTGRES_FOR_TESTS=True` when you specifically want pytest to create a PostgreSQL test database.

Customers can create an account without authentication at `POST /api/customers/register/`. Submit `username`, `email`, and `password`; `first_name`, `last_name`, `phone`, and `city` are optional. Passwords are checked using Django's configured password validators. The endpoint always creates a standard customer account; staff privileges cannot be assigned through registration.

Authenticated clients can retrieve their account identity and staff flag from `GET /api/auth/me/`. This endpoint also supports staff accounts that do not have a customer profile.

## Payments and Fulfillment

Configure `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in `.env`, and set `STRIPE_CURRENCY` to the order currency (defaults to `usd`). Apply migrations before starting the app. Configure the Stripe webhook endpoint as `/api/payments/stripe/webhook/` and subscribe it to `payment_intent.succeeded`, `payment_intent.payment_failed`, `payment_intent.canceled`, `charge.refunded`, and `refund.updated`.

Customers create an order with `payment_method` set to `card` (the default) or `cash_on_delivery`. Card orders call `POST /api/orders/{id}/pay/` to receive a Stripe PaymentIntent client secret for Stripe.js confirmation; the order becomes paid only after the signed Stripe webhook is received. Cash-on-delivery orders can be shipped without a card payment. Staff can update lifecycle-managed order status with `POST /api/orders/{id}/status/` and a `status` value of `cancelled` (placed orders) or `delivered` (shipped orders); payment and shipping states must use their dedicated workflows. Staff can issue a full refund for paid card orders with `POST /api/orders/{id}/refund/`, record carrier/tracking details with `POST /api/orders/{id}/ship/`, and mark delivery with `POST /api/orders/{id}/deliver/`. Order responses include `payment_method`, `payment_status`, and a nested `shipment` object when one exists. Refund completion is reconciled from Stripe webhooks. Shipping is manually managed; no carrier API, address collection, shipping quotes, or tax calculation is included.

## Sample Requests

```powershell
curl http://localhost:8000/api/products/
curl http://localhost:8000/api/categories/?search=lap
curl -X POST http://localhost:8000/api/auth/token/ -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin12345\"}"
curl -X POST http://localhost:8000/api/products/ -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d "{\"sku\":\"ACC-KEY-01\",\"name\":\"Mechanical Keyboard\",\"category\":2,\"price\":\"129.00\",\"stock\":25}"
curl -X POST http://localhost:8000/api/orders/ -H "Authorization: Bearer <customer-token>" -H "Content-Type: application/json" -d "{\"items\":[{\"product\":1,\"quantity\":2}]}"
curl http://localhost:8000/api/customers/me/ -H "Authorization: Bearer <customer-token>"
```

## Phase 1 Notes

Views are thin because they only choose serializer, permissions, and selector-backed querysets. Selectors make ORM tuning easier later. Services are included early so business workflows have a stable home as complexity grows.

`select_related` is used in list selectors where the API returns related names or emails. That keeps Phase 1 from introducing avoidable N+1 queries.

Order creation uses `transaction.atomic`, `select_for_update`, and `bulk_create`. Time complexity is O(n) in the number of submitted items; space complexity is O(n) for the locked product map and pending `OrderItem` list.

## Phase 1 Interview Questions

1. Why keep query construction in selectors instead of directly inside each ViewSet?
2. What does `select_related` prevent in the product and order list endpoints?
3. Why is `select_for_update` paired with `transaction.atomic` during order creation?

## Phase 2 Notes

Permissions are now explicit:

- Catalog is public-read and staff-write.
- Employees are staff-only.
- Customers can see and patch their own profile through `/api/customers/me/`.
- Customers can create orders for themselves and only list their own orders.
- Staff can create orders for any customer by passing `customer`.

Order creation now uses `OrderCreateSerializer` for request validation and `OrderReadSerializer` for nested response output. The service layer owns stock deduction because stock is a business invariant, not just an API formatting concern.

The stock algorithm locks all requested products, validates active status and inventory, creates items with `bulk_create`, then updates product stock with `bulk_update`. Time complexity is O(n), where n is the number of order lines. Space complexity is O(n) for DTOs and the product lookup dictionary.

Tests verify that negative product stock is rejected and that customers cannot override their own identity when placing orders.

Orders are created in the `placed` state; clients cannot assign payment or shipping states. Generic order updates and deletes are disabled to protect inventory accounting. Customers can cancel their own placed orders at `POST /api/orders/{id}/cancel/`, which atomically restores inventory. Payment, refund, and shipping workflows are not integrated.

## Phase 2 Interview Questions

1. Why should stock deduction happen inside `transaction.atomic` instead of after `Order.objects.create()` returns?
2. Why split order serializers into create/read variants instead of using one serializer for everything?
3. What can go wrong if two requests check product stock without `select_for_update`?
