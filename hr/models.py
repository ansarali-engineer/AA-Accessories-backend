from django.db import models


class Employee(models.Model):
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    email = models.EmailField(unique=True)
    title = models.CharField(max_length=120)
    department = models.CharField(max_length=80)
    salary = models.DecimalField(max_digits=12, decimal_places=2)
    manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )
    hired_at = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["department", "salary"], name="employee_dept_salary_idx"),
            models.Index(fields=["manager"], name="employee_manager_idx"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

# Create your models here.
