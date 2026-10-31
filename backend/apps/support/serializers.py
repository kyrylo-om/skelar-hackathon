from rest_framework import serializers

from .models import AuditLog, Chat, Message, ReviewItem, TraceStep


class MessageSerializer(serializers.ModelSerializer):
    at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = Message
        fields = ["id", "role", "text", "at"]


class TraceStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = TraceStep
        fields = ["agent", "verdict", "detail"]


class ReviewSerializer(serializers.ModelSerializer):
    decidedBy = serializers.CharField(source="decided_by.username", default=None)

    class Meta:
        model = ReviewItem
        fields = ["id", "action", "params", "risk", "reason", "status", "note", "decidedBy"]


class ChatListSerializer(serializers.ModelSerializer):
    customer = serializers.CharField(source="customer_name")
    updatedAt = serializers.DateTimeField(source="updated_at")

    class Meta:
        model = Chat
        fields = ["id", "customer", "subject", "status", "priority", "updatedAt", "summary"]


class ChatDetailSerializer(ChatListSerializer):
    messages = MessageSerializer(many=True)
    trace = TraceStepSerializer(many=True)
    review = serializers.SerializerMethodField()

    class Meta(ChatListSerializer.Meta):
        fields = [*ChatListSerializer.Meta.fields, "messages", "trace", "review"]

    def get_review(self, chat):
        # The cabinet shows one review per chat: the pending one, else the latest.
        reviews = list(chat.reviews.all())
        pending = [r for r in reviews if r.status == ReviewItem.Status.PENDING]
        chosen = pending[0] if pending else (reviews[-1] if reviews else None)
        return ReviewSerializer(chosen).data if chosen else None


class AuditSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.username", default=None)
    chat = serializers.PrimaryKeyRelatedField(read_only=True)
    at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = AuditLog
        fields = ["id", "actor", "event", "chat", "payload", "at"]


class ReplyInput(serializers.Serializer):
    text = serializers.CharField(max_length=2000, trim_whitespace=True)


class DecisionInput(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[ReviewItem.Status.APPROVED, ReviewItem.Status.REJECTED]
    )
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class LoginInput(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, trim_whitespace=False)
