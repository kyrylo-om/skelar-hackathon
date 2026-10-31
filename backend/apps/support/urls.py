from django.urls import path

from . import views

urlpatterns = [
    path("auth/login/", views.login_view, name="login"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("auth/me/", views.me_view, name="me"),
    path("chats/", views.ChatListView.as_view(), name="chat-list"),
    path("chats/<int:pk>/", views.ChatDetailView.as_view(), name="chat-detail"),
    path("chats/<int:pk>/reply/", views.ChatReplyView.as_view(), name="chat-reply"),
    path("reviews/<int:pk>/decision/", views.ReviewDecisionView.as_view(), name="review-decision"),
    path("audit/", views.AuditListView.as_view(), name="audit"),
]
