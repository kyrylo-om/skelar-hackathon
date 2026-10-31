from rest_framework import serializers

from apps.subscriptions.models import Plan, Subscription
from apps.support.models import Action, Conversation, Message


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({field: "Unknown field." for field in unknown})
        return super().to_internal_value(data)


class MessageInput(StrictSerializer):
    text = serializers.CharField(max_length=4000)
    client_message_id = serializers.CharField(max_length=128)


class EmptyInput(StrictSerializer):
    pass


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "name", "storage_limit_gb"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer()

    class Meta:
        model = Subscription
        fields = ["id", "plan", "status", "period_end", "auto_renew", "version"]


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "sender", "text", "created_at"]


class ActionSerializer(serializers.ModelSerializer):
    description = serializers.SerializerMethodField()

    def get_description(self, obj):
        if obj.kind == "cancel_auto_renewal":
            return "Вимкнути автоподовження. Доступ збережеться до кінця оплаченого періоду."
        return "Застосувати оплачений план у демонстраційній базі."

    class Meta:
        model = Action
        fields = ["id", "kind", "status", "description", "expires_at"]


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True)
    pending_action = serializers.SerializerMethodField()

    def get_pending_action(self, obj):
        from django.utils import timezone
        action = obj.actions.filter(status="awaiting_confirmation", expires_at__gt=timezone.now()).order_by("-created_at").first() if obj.status == "ai" else None
        return ActionSerializer(action).data if action else None

    class Meta:
        model = Conversation
        fields = ["id", "status", "version", "summary", "messages", "pending_action"]
