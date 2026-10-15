from catalog.serializers import CategorySerializer, ProductSerializer


def create_category(*, data):
    serializer = CategorySerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def create_product(*, data):
    serializer = ProductSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()
