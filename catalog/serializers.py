from rest_framework import serializers

from catalog.models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent", "parent_name", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "sku",
            "name",
            "description",
            "category",
            "category_name",
            "price",
            "stock",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "stock": {
                "error_messages": {"min_value": "Stock cannot be negative."},
            },
        }

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value
