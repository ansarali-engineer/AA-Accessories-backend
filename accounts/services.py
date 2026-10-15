from accounts.serializers import CustomerSerializer


def create_customer(*, data):
    serializer = CustomerSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()
