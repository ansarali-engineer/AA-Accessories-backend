from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from catalog import selectors
from catalog.models import Category, Product
from catalog.serializers import CategorySerializer, ProductSerializer
from common.permissions import IsAdminOrStaffOrReadOnly


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.none()
    serializer_class = CategorySerializer
    permission_classes = (IsAdminOrStaffOrReadOnly,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_fields = ("parent", "is_active")
    search_fields = ("name", "slug")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        return selectors.category_list()


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.none()
    serializer_class = ProductSerializer
    permission_classes = (IsAdminOrStaffOrReadOnly,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_fields = ("category", "is_active")
    search_fields = ("sku", "name", "description")
    ordering_fields = ("name", "price", "stock", "created_at")

    def get_queryset(self):
        return selectors.product_list()

# Create your views here.
