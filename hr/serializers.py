from rest_framework import serializers

from hr.models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            "id",
            "first_name",
            "last_name",
            "email",
            "title",
            "department",
            "salary",
            "manager",
            "manager_name",
            "hired_at",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def get_manager_name(self, obj):
        return str(obj.manager) if obj.manager_id else None
