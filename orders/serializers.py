from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from accounts.models import Customer
from orders.models import Order, OrderItem, Payment, Shipment
from orders.services import OrderLineInput, place_order


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "product", "product_name", "quantity", "unit_price", "line_total")
        read_only_fields = ("id", "unit_price", "line_total")


class ShipmentReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = ("carrier", "tracking_number", "status", "shipped_at", "delivered_at")
        read_only_fields = fields


class OrderReadSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer_email = serializers.EmailField(source="customer.user.email", read_only=True)
    payment_status = serializers.SerializerMethodField()
    shipment = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "customer",
            "customer_email",
            "status",
            "total_amount",
            "payment_method",
            "payment_status",
            "shipment",
            "items",
            "placed_at",
            "updated_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_payment_status(self, obj):
        try:
            return obj.payment.status
        except Payment.DoesNotExist:
            return None

    @extend_schema_field(ShipmentReadSerializer(allow_null=True))
    def get_shipment(self, obj):
        try:
            shipment = obj.shipment
        except Shipment.DoesNotExist:
            return None
        return ShipmentReadSerializer(shipment).data


class ShipmentCreateSerializer(serializers.Serializer):
    carrier = serializers.CharField(max_length=80, trim_whitespace=True)
    tracking_number = serializers.CharField(max_length=120, trim_whitespace=True)


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)


class OrderCreateItemSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False)
    payment_method = serializers.ChoiceField(
        choices=Order.PaymentMethod.choices,
        required=False,
        default=Order.PaymentMethod.CARD,
    )
    items = OrderCreateItemSerializer(many=True)

    def validate(self, attrs):
        if "status" in self.initial_data:
            raise serializers.ValidationError(
                {"status": "Order status is managed by the order lifecycle."}
            )

        request = self.context["request"]
        if request.user.is_staff:
            if "customer" not in attrs:
                raise serializers.ValidationError({"customer": "Staff users must choose a customer."})
            return attrs

        if not hasattr(request.user, "customer"):
            raise serializers.ValidationError({"customer": "Only customer accounts can place orders."})
        attrs["customer"] = request.user.customer
        return attrs

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one order item is required.")
        product_ids = [item["product"] for item in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("Duplicate products are not allowed in one order.")
        return value

    def create(self, validated_data):
        lines = [
            OrderLineInput(product_id=item["product"], quantity=item["quantity"])
            for item in validated_data["items"]
        ]
        return place_order(
            customer=validated_data["customer"],
            payment_method=validated_data["payment_method"],
            lines=lines,
        )


OrderSerializer = OrderReadSerializer
