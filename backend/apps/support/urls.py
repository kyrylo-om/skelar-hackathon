from django.urls import path

from apps.accounts import views as accounts
from apps.support import views

urlpatterns = [
    path("auth/csrf/", accounts.csrf),
    path("auth/login/", accounts.LoginView.as_view()),
    path("auth/logout/", accounts.logout),
    path("me/", accounts.me),
    path("subscription/", views.subscription),
    path("conversations/", views.conversations),
    path("conversations/<uuid:conversation_id>/", views.conversation_detail),
    path("conversations/<uuid:conversation_id>/messages/", views.messages),
    path("actions/<uuid:action_id>/confirm/", views.confirm),
    path("operator/conversations/", views.operator_queue),
    path("operator/conversations/<uuid:conversation_id>/", views.operator_detail),
    path("operator/conversations/<uuid:conversation_id>/claim/", views.claim),
    path("operator/conversations/<uuid:conversation_id>/messages/", views.operator_messages),
    path("operator/conversations/<uuid:conversation_id>/resolve/", views.resolve),
]
