"""The embeddable widget's API: the customer's chat, and a message whose answer streams as SSE.

Only the widget token authenticates here (no session, so no cookies and no CSRF). Streamed events:
`status` {stage}, `message` (a MessageSerializer item), `done` {status}, `error` {code, message}.
A `confirm: customer` action (pendingConfirmation in the chat) runs only through `confirm`.
Replies are sent whole: the pipeline checks a reply before anyone may see it.
"""

import json
import logging

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from apps.review import services
from apps.review.models import Message
from apps.review.permissions import IsCustomer
from apps.review.serializers import CustomerChatSerializer, MessageSerializer, ReplyInput

from .auth import WidgetTokenAuthentication

logger = logging.getLogger("apps.widget")


def event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@api_view(["GET"])
@authentication_classes([WidgetTokenAuthentication])
@permission_classes([IsCustomer])
def chat(request):
    return Response(CustomerChatSerializer(services.chat_for_customer(request.user)).data)


@api_view(["POST"])
@authentication_classes([WidgetTokenAuthentication])
@permission_classes([IsCustomer])
def messages(request):
    data = ReplyInput(data=request.data)
    data.is_valid(raise_exception=True)
    chat = services.chat_for_customer(request.user)

    def stream():
        yield event("status", {"stage": "working"})
        try:
            message = services.receive_customer_message(chat, data.validated_data["text"])
        except Exception:
            logger.exception("widget message failed in chat %s", chat.pk)
            yield event("error", {"code": "failed", "message": "Не вдалося обробити повідомлення."})
            return
        chat.refresh_from_db()
        for new in chat.messages.filter(pk__gte=message.pk):
            yield event("message", MessageSerializer(new).data)
        yield event("done", {"status": chat.status})

    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # let proxies pass events through as they come
    return response


@api_view(["POST"])
@authentication_classes([WidgetTokenAuthentication])
@permission_classes([IsCustomer])
def confirm(request, action_id):
    """The customer's own confirm button: the only way a `confirm: customer` action runs.

    Widget customers live in an external product, so this is always the MCP gateway's confirm,
    with all its checks (owner, expiry, once only, not after a hand-off).
    """
    from apps.orchestrator.mcp_gateway import confirm as confirm_product_action

    result = confirm_product_action(request.user, action_id)
    chat = services.chat_for_customer(request.user)
    done = f"Підтверджено: {result['action']['description']}"
    services.add_message(chat, Message.Role.SYSTEM, done)  # the chat keeps a record of it
    return Response(result)
