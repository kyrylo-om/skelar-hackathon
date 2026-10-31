from django.urls import path

from . import views

urlpatterns = [
    path("my/chat/", views.MyChatView.as_view(), name="my-chat"),
    path("my/chat/messages/", views.MyMessageView.as_view(), name="my-message"),
    path("chats/", views.ChatListView.as_view(), name="chat-list"),
    path("chats/<int:pk>/", views.ChatDetailView.as_view(), name="chat-detail"),
    path("chats/<int:pk>/reply/", views.ChatReplyView.as_view(), name="chat-reply"),
    path("reviews/<int:pk>/decision/", views.ReviewDecisionView.as_view(), name="review-decision"),
    path("audit/", views.AuditListView.as_view(), name="audit"),
]
