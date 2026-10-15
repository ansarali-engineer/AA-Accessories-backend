import pytest

from catalog.serializers import ProductSerializer
from tests.factories import CategoryFactory


@pytest.mark.django_db
def test_product_serializer_rejects_negative_stock():
    category = CategoryFactory()
    serializer = ProductSerializer(
        data={
            "sku": "NEGATIVE-STOCK",
            "name": "Invalid Product",
            "category": category.id,
            "price": "10.00",
            "stock": -1,
        }
    )

    assert not serializer.is_valid()
    assert serializer.errors["stock"] == ["Stock cannot be negative."]
