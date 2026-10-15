from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from common.permissions import IsAdminStaffOrCustomerOrderAccess, is_staff
from orders import selectors
from orders.models import Order
from orders.payment_services import create_payment_intent, refund_order
from orders.serializers import (
    OrderCreateSerializer,
    OrderReadSerializer,
    OrderStatusUpdateSerializer,
    ShipmentCreateSerializer,
)
from orders.services import cancel_order, mark_order_delivered, ship_order


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.none()
    http_method_names = ("get", "post", "head", "options")
    permission_classes = (IsAdminStaffOrCustomerOrderAccess,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_fields = ("customer", "status")
    search_fields = ("customer__user__email", "items__product__name")
    ordering_fields = ("placed_at", "total_amount", "status")

    def get_queryset(self):
        queryset = selectors.order_list()
        if is_staff(self.request.user):
            return queryset
        return queryset.filter(customer__user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        output = OrderReadSerializer(order, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None):
        order = self.get_object()
        order = cancel_order(order_id=order.pk)
        serializer = OrderReadSerializer(order, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(detail=True, methods=("post",))
    def pay(self, request, pk=None):
        order = self.get_object()
        return Response(create_payment_intent(order_id=order.pk))

    @action(detail=True, methods=("post",))
    def refund(self, request, pk=None):
        if not is_staff(request.user):
            raise PermissionDenied("Only staff can issue refunds.")
        order = self.get_object()
        payment = refund_order(order_id=order.pk)
        return Response(
            {
                "payment_status": payment.status,
                "order_status": payment.order.status,
            }
        )

    @action(detail=True, methods=("post",))
    def ship(self, request, pk=None):
        if not is_staff(request.user):
            raise PermissionDenied("Only staff can create shipments.")
        order = self.get_object()
        serializer = ShipmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ship_order(order_id=order.pk, **serializer.validated_data)
        order.refresh_from_db()
        output = OrderReadSerializer(order, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=("post",))
    def deliver(self, request, pk=None):
        if not is_staff(request.user):
            raise PermissionDenied("Only staff can mark shipments delivered.")
        order = self.get_object()
        mark_order_delivered(order_id=order.pk)
        order.refresh_from_db()
        output = OrderReadSerializer(order, context=self.get_serializer_context())
        return Response(output.data)

    @action(detail=True, methods=("post",), url_path="status")
    def update_status(self, request, pk=None):
        if not is_staff(request.user):
            raise PermissionDenied("Only staff can update order status.")

        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = self.get_object()
        target_status = serializer.validated_data["status"]

        if target_status == Order.Status.CANCELLED:
            order = cancel_order(order_id=order.pk)
        elif target_status == Order.Status.DELIVERED:
            order = mark_order_delivered(order_id=order.pk).order
        else:
            raise ValidationError(
                {
                    "status": (
                        "Status is controlled by the order lifecycle. Use the payment, "
                        "shipment, or refund action for this transition."
                    )
                }
            )

        order.refresh_from_db()
        output = OrderReadSerializer(order, context=self.get_serializer_context())
        return Response(output.data)
