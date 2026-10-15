from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Customer
from catalog.models import Category, Product
from hr.models import Employee
from orders.models import Order, OrderItem

User = get_user_model()


class Command(BaseCommand):
    help = "Seed a small AA Accessories dataset for local practice."

    def handle(self, *args, **options):
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com", "is_staff": True, "is_superuser": True},
        )
        admin.set_password("admin12345")
        admin.save()

        alice_user, _ = User.objects.get_or_create(
            username="alice",
            defaults={"email": "alice@example.com", "first_name": "Alice", "last_name": "Ng"},
        )
        alice_user.set_password("customer12345")
        alice_user.save()
        alice, _ = Customer.objects.get_or_create(
            user=alice_user,
            defaults={"phone": "+1555000100", "city": "Austin", "tier": Customer.Tier.GOLD},
        )

        electronics, _ = Category.objects.get_or_create(
            slug="electronics",
            defaults={"name": "Electronics"},
        )
        laptops, _ = Category.objects.get_or_create(
            slug="laptops",
            defaults={"name": "Laptops", "parent": electronics},
        )
        accessories, _ = Category.objects.get_or_create(
            slug="accessories",
            defaults={"name": "Accessories", "parent": electronics},
        )

        products = [
            ("LAP-ULTRA-14", "Ultrabook 14", laptops, Decimal("1299.00"), 15),
            ("LAP-PRO-16", "Workstation Laptop 16", laptops, Decimal("2299.00"), 8),
            ("ACC-MOUSE-01", "Wireless Mouse", accessories, Decimal("49.99"), 100),
        ]
        product_objects = []
        for sku, name, category, price, stock in products:
            product, _ = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": category,
                    "price": price,
                    "stock": stock,
                    "description": f"Demo product: {name}",
                },
            )
            product_objects.append(product)

        ceo, _ = Employee.objects.get_or_create(
            email="maya.ceo@example.com",
            defaults={
                "first_name": "Maya",
                "last_name": "Patel",
                "title": "CEO",
                "department": "Executive",
                "salary": Decimal("250000.00"),
                "hired_at": date(2018, 1, 8),
            },
        )
        Employee.objects.get_or_create(
            email="sam.ops@example.com",
            defaults={
                "first_name": "Sam",
                "last_name": "Rivera",
                "title": "Operations Manager",
                "department": "Operations",
                "salary": Decimal("130000.00"),
                "manager": ceo,
                "hired_at": date(2020, 5, 11),
            },
        )

        order, created = Order.objects.get_or_create(customer=alice, defaults={"total_amount": Decimal("1348.99")})
        if created:
            OrderItem.objects.bulk_create(
                [
                    OrderItem(order=order, product=product_objects[0], quantity=1, unit_price=product_objects[0].price),
                    OrderItem(order=order, product=product_objects[2], quantity=1, unit_price=product_objects[2].price),
                ]
            )

        self.stdout.write(self.style.SUCCESS("Seeded AA Accessories demo data. Admin login: admin/admin12345"))
