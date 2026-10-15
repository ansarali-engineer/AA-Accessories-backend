from accounts.models import Customer


def customer_list():
    return Customer.objects.select_related("user").order_by("-created_at")


def customer_detail():
    return customer_list()
