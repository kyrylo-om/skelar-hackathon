from django.urls import path

from . import views

urlpatterns = [
    path("chat/", views.chat, name="widget-chat"),
    path("chat/messages/", views.messages, name="widget-messages"),
    path("actions/<uuid:action_id>/confirm/", views.confirm, name="widget-confirm"),
]
