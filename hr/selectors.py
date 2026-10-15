from hr.models import Employee


def employee_list():
    return Employee.objects.select_related("manager").order_by("department", "last_name")
