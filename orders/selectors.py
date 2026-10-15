from orders.models import Order


def order_list():
    return (
        Order.objects.select_related("customer", "customer__user", "payment", "shipment")
        .prefetch_related("items", "items__product")
        .order_by("-placed_at")
    )
