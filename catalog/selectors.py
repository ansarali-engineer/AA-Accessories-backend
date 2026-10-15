from catalog.models import Category, Product


def category_list():
    return Category.objects.select_related("parent").order_by("name")


def product_list():
    return Product.objects.select_related("category").order_by("name")


def active_product_list():
    return product_list().filter(is_active=True)
