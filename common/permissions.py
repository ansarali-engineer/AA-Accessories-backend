from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_admin(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def is_staff(user):
    return bool(user and user.is_authenticated and user.is_staff)


def is_customer(user):
    return bool(user and user.is_authenticated and hasattr(user, "customer"))


class IsAdminOrStaffOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return is_staff(request.user)


class IsAdminOrStaff(BasePermission):
    def has_permission(self, request, view):
        return is_staff(request.user)


class IsAdminStaffOrCustomerOrderAccess(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if is_staff(request.user):
            return True
        return is_customer(request.user) and obj.customer_id == request.user.customer.id


class IsAdminStaffOrCustomerSelf(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if is_staff(request.user):
            return True
        if view.action == "create":
            return False
        return is_customer(request.user)

    def has_object_permission(self, request, view, obj):
        if is_staff(request.user):
            return True
        return is_customer(request.user) and obj.user_id == request.user.id


class IsAdminStaffOrCustomerSelf(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if is_staff(request.user):
            return True
        if view.action == "create":
            return False
        return is_customer(request.user)

    def has_object_permission(self, request, view, obj):
        if is_staff(request.user):
            return True
        return is_customer(request.user) and obj.user_id == request.user.id
