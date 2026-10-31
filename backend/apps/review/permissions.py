from rest_framework.permissions import BasePermission

OPERATOR_GROUP = "operators"


def is_operator(user) -> bool:
    if not user.is_authenticated:
        return False
    return user.is_staff or user.groups.filter(name=OPERATOR_GROUP).exists()


class IsOperator(BasePermission):
    def has_permission(self, request, view):
        return is_operator(request.user)


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and not is_operator(request.user)
