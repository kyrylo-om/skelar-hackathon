from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.core.errors import Conflict
from apps.support import services
from apps.support.models import Conversation, Message
from apps.support.serializers import (
    ActionSerializer, ConversationSerializer, EmptyInput, MessageInput,
    MessageSerializer, SubscriptionSerializer,
)


def validate(serializer, request):
    data = serializer(data=request.data)
    data.is_valid(raise_exception=True)
    return data.validated_data


@api_view(["GET"])
def subscription(request):
    return Response(services.get_subscription(request.user))


@api_view(["POST"])
def conversations(request):
    validate(EmptyInput, request)
    conversation = Conversation.objects.create(user=request.user)
    return Response(ConversationSerializer(conversation).data, status=201)


@api_view(["GET"])
def conversation_detail(request, conversation_id):
    conversation = services.owned_conversation(request.user, conversation_id)
    return Response(ConversationSerializer(conversation).data)


@api_view(["POST"])
def messages(request, conversation_id):
    data = validate(MessageInput, request)
    conversation, message, token = services.begin_turn(request.user, conversation_id, **data)
    if message.response is not None:
        # Return current status on retry, including handoff/claim since first response.
        result = dict(message.response)
        result["conversation_status"] = conversation.status
        if conversation.status != "ai":
            result["pending_action"] = None
        return Response(result)
    if token:
        # Explicit unavailable-provider fallback. The AI developer replaces this
        # boundary with bounded orchestration outside a DB transaction.
        services.handoff_to_operator(
            request.user, conversation_id,
            "AI provider is not connected. Customer request requires human review.",
            token=token, version=conversation.version,
        )
    with transaction.atomic():
        conversation = services.owned_conversation(request.user, conversation_id, lock=True)
        result = {"conversation_id": str(conversation.pk), "conversation_status": conversation.status,
                  "reply": None, "pending_action": None, "subscription_changed": False}
        message.response = result
        message.save(update_fields=["response"])
    return Response(result)


@api_view(["POST"])
def confirm(request, action_id):
    validate(EmptyInput, request)
    action, sub, changed = services.confirm_cancellation(request.user, action_id)
    return Response({"action": ActionSerializer(action).data,
                     "subscription": SubscriptionSerializer(sub).data,
                     "subscription_changed": changed})


@api_view(["GET"])
@permission_classes([IsAdminUser])
def operator_queue(request):
    query = Conversation.objects.filter(status__in=["waiting_operator", "operator"]).order_by("created_at")
    return Response({"results": list(query.values("id", "status", "summary", "version", "assigned_operator_id", "created_at"))})


@api_view(["GET"])
@permission_classes([IsAdminUser])
def operator_detail(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id, status__in=["waiting_operator", "operator", "resolved"])
    if conversation.assigned_operator_id and conversation.assigned_operator_id != request.user.pk:
        raise PermissionDenied("Conversation is assigned to another operator.")
    return Response(ConversationSerializer(conversation).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
@transaction.atomic
def claim(request, conversation_id):
    validate(EmptyInput, request)
    conversation = get_object_or_404(Conversation.objects.select_for_update(), pk=conversation_id)
    if conversation.status == "operator" and conversation.assigned_operator_id == request.user.pk:
        return Response(ConversationSerializer(conversation).data)
    if conversation.status != "waiting_operator" or conversation.assigned_operator_id:
        raise Conflict("Conversation cannot be claimed.")
    conversation.assigned_operator = request.user
    conversation.status = "operator"
    conversation.version += 1
    conversation.in_flight_token = None
    conversation.in_flight_at = None
    conversation.save()
    return Response(ConversationSerializer(conversation).data)


def assigned_conversation(user, conversation_id):
    conversation = get_object_or_404(Conversation.objects.select_for_update(), pk=conversation_id)
    if conversation.assigned_operator_id != user.pk:
        raise PermissionDenied("Only the assigned operator can act.")
    return conversation


@api_view(["POST"])
@permission_classes([IsAdminUser])
@transaction.atomic
def operator_messages(request, conversation_id):
    data = validate(MessageInput, request)
    conversation = assigned_conversation(request.user, conversation_id)
    existing = conversation.messages.filter(sender="operator", client_message_id=data["client_message_id"]).first()
    if existing:
        if existing.text != data["text"]:
            raise Conflict("client_message_id already belongs to another message.")
        return Response(MessageSerializer(existing).data)
    if conversation.status != "operator":
        raise Conflict("Conversation is not open for operator replies.")
    message = Message.objects.create(conversation=conversation, sender="operator", sender_user=request.user, **data)
    conversation.version += 1
    conversation.save(update_fields=["version"])
    return Response(MessageSerializer(message).data, status=201)


@api_view(["POST"])
@permission_classes([IsAdminUser])
@transaction.atomic
def resolve(request, conversation_id):
    validate(EmptyInput, request)
    conversation = assigned_conversation(request.user, conversation_id)
    if conversation.status not in ("operator", "resolved"):
        raise Conflict("Conversation cannot be resolved.")
    if conversation.status != "resolved":
        conversation.status = "resolved"
        conversation.version += 1
        conversation.save()
    return Response(ConversationSerializer(conversation).data)
