from hr.serializers import EmployeeSerializer


def create_employee(*, data):
    serializer = EmployeeSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()
