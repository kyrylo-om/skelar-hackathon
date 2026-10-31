from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import ports, services
from .models import AuditLog, Chat, ReviewItem
from .permissions import IsCustomer, IsOperator
from .serializers import (
    AuditSerializer,
    ChatDetailSerializer,
    ChatListSerializer,
    CustomerChatSerializer,
    DecisionInput,
    ReplyInput,
)


class MyChatView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        chat = services.chat_for_customer(request.user)
        return Response(CustomerChatSerializer(chat).data)


class MyMessageView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        data = ReplyInput(data=request.data)
        data.is_valid(raise_exception=True)
        chat = services.chat_for_customer(request.user)
        services.receive_customer_message(chat, data.validated_data["text"])
        chat.refresh_from_db()
        return Response(CustomerChatSerializer(chat).data, status=status.HTTP_201_CREATED)


def _detail_queryset():
    return Chat.objects.prefetch_related("messages", "trace", "reviews__decided_by")


class ChatListView(generics.ListAPIView):
    permission_classes = [IsOperator]
    serializer_class = ChatListSerializer

    def get_queryset(self):
        queryset = Chat.objects.all()
        status_filter = self.request.query_params.get("status")
        if status_filter in Chat.Status.values:
            queryset = queryset.filter(status=status_filter)
        query = self.request.query_params.get("q", "").strip().casefold()
        if query:
            # SQLite's LIKE is case-insensitive for ASCII only, so match Cyrillic in Python.
            return [
                chat
                for chat in queryset
                if query in chat.customer_name.casefold() or query in chat.subject.casefold()
            ]
        return queryset


class ChatDetailView(generics.RetrieveAPIView):
    permission_classes = [IsOperator]
    serializer_class = ChatDetailSerializer

    def get_queryset(self):
        return _detail_queryset()


class ChatReplyView(APIView):
    permission_classes = [IsOperator]

    def post(self, request, pk):
        chat = get_object_or_404(Chat, pk=pk)
        data = ReplyInput(data=request.data)
        data.is_valid(raise_exception=True)
        services.reply_as_operator(chat, request.user, data.validated_data["text"])
        chat = get_object_or_404(_detail_queryset(), pk=pk)
        return Response(ChatDetailSerializer(chat).data, status=status.HTTP_201_CREATED)


class ReviewDecisionView(APIView):
    permission_classes = [IsOperator]

    def post(self, request, pk):
        review = get_object_or_404(ReviewItem, pk=pk)
        data = DecisionInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.decide_review(
                review.pk,
                request.user,
                data.validated_data["decision"],
                data.validated_data["note"],
            )
        except services.ReviewAlreadyDecided:
            return Response({"detail": "Рішення вже прийнято"}, status=status.HTTP_409_CONFLICT)
        except ports.ExecutionError as exc:
            return Response(
                {"detail": f"Дію не виконано: {exc}"}, status=status.HTTP_502_BAD_GATEWAY
            )
        chat = get_object_or_404(_detail_queryset(), pk=review.chat_id)
        return Response(ChatDetailSerializer(chat).data)


class AuditListView(generics.ListAPIView):
    permission_classes = [IsOperator]
    serializer_class = AuditSerializer

    def get_queryset(self):
        return AuditLog.objects.select_related("actor")[:100]
