from datetime import date
from decimal import Decimal

import factory
from django.contrib.auth import get_user_model

from accounts.models import Customer
from catalog.models import Category, Product
from hr.models import Employee
from orders.models import Order, OrderItem

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = "Test"
    last_name = "User"


class StaffUserFactory(UserFactory):
    is_staff = True


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Customer

    user = factory.SubFactory(UserFactory)
    phone = "+15555550123"
    city = "Austin"
    tier = Customer.Tier.STANDARD


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    sku = factory.Sequence(lambda n: f"SKU-{n:04d}")
    name = factory.Sequence(lambda n: f"Product {n}")
    category = factory.SubFactory(CategoryFactory)
    price = Decimal("25.00")
    stock = 10


class EmployeeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Employee

    first_name = factory.Sequence(lambda n: f"Employee{n}")
    last_name = "Example"
    email = factory.Sequence(lambda n: f"employee{n}@example.com")
    title = "Developer"
    department = "Engineering"
    salary = Decimal("90000.00")
    hired_at = date(2022, 1, 1)


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    customer = factory.SubFactory(CustomerFactory)


class OrderItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = 1
    unit_price = Decimal("25.00")
