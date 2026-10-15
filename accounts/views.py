from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import selectors
from accounts.models import Customer
from accounts.serializers import (
    CustomerRegistrationSerializer,
    CustomerSerializer,
    UserSummarySerializer,
)
from common.permissions import IsAdminStaffOrCustomerSelf, is_staff


class CurrentUserView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(UserSummarySerializer(request.user).data)


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.none()
    serializer_class = CustomerSerializer
    permission_classes = (IsAdminStaffOrCustomerSelf,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_fields = ("tier", "city")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    ordering_fields = ("created_at", "tier", "city")

    def get_queryset(self):
        queryset = selectors.customer_list()
        if is_staff(self.request.user):
            return queryset
        return queryset.filter(user=self.request.user)

    @extend_schema(
        request=CustomerRegistrationSerializer,
        responses={201: CustomerSerializer},
    )
    @action(
        detail=False,
        methods=("post",),
        permission_classes=(AllowAny,),
        authentication_classes=(),
        url_path="register",
    )
    def register(self, request):
        serializer = CustomerRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return Response(
            CustomerSerializer(customer, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        customer = request.user.customer
        if request.method == "PATCH":
            serializer = self.get_serializer(customer, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        serializer = self.get_serializer(customer)
        return Response(serializer.data)