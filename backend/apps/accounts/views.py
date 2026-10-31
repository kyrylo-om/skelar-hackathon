from django.contrib.auth import authenticate, login as session_login, logout as session_logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.support.serializers import EmptyInput, StrictSerializer


def user_data(user):
    return {"id": str(user.pk), "username": user.username, "is_staff": user.is_staff}


@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    return Response({"detail": "CSRF cookie set."})


class LoginInput(StrictSerializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = LoginInput(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(request, **data.validated_data)
        if user is None:
            raise PermissionDenied("Невірне ім’я користувача або пароль.")
        session_login(request, user)
        return Response(user_data(user))


@api_view(["POST"])
def logout(request):
    data = EmptyInput(data=request.data)
    data.is_valid(raise_exception=True)
    session_logout(request)
    return Response(status=204)


@api_view(["GET"])
def me(request):
    return Response(user_data(request.user))
