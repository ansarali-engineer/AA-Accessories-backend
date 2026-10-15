from django.db import models


class Order(models.Model):
    class PaymentMethod(models.TextChoices):
        CARD = "card", "Card"
        CASH_ON_DELIVERY = "cash_on_delivery", "Cash on delivery"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PLACED = "placed", "Placed"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        REFUND_PENDING = "refund_pending", "Refund pending"
        CANCELLED = "cancelled", "Cancelled"

    customer = models.ForeignKey("accounts.Customer", on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CARD,
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "-placed_at"], name="order_customer_date_idx"),
            models.Index(fields=["status", "-placed_at"], name="order_status_date_idx"),
        ]

    def __str__(self):
        return f"Order #{self.pk} - {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="unique_product_per_order"),
        ]
        indexes = [
            models.Index(fields=["product", "order"], name="order_item_product_order_idx"),
        ]
        
    @property
    def line_total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.quantity} x {self.product_id}"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REFUND_PENDING = "refund_pending", "Refund pending"
        REFUNDED = "refunded", "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="payment")
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    stripe_refund_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    amount = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for order #{self.order_id} - {self.status}"


class Shipment(models.Model):
    class Status(models.TextChoices):
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="shipment")
    carrier = models.CharField(max_length=80)
    tracking_number = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SHIPPED)
    shipped_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-shipped_at",)

    def __str__(self):
        return f"Shipment for order #{self.order_id} - {self.status}"
