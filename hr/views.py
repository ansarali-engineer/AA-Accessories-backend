from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from common.permissions import IsAdminOrStaff
from hr import selectors
from hr.models import Employee
from hr.serializers import EmployeeSerializer


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.none()
    serializer_class = EmployeeSerializer
    permission_classes = (IsAdminOrStaff,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_fields = ("department", "manager")
    search_fields = ("first_name", "last_name", "email", "title")
    ordering_fields = ("last_name", "department", "salary", "hired_at")

    def get_queryset(self):
        return selectors.employee_list()

