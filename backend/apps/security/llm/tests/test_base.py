import json
import logging
import sys
import types
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.security.llm import LLMError, LLMNetworkError, base, complete_json, message_budget

SCHEMA = {
    "required": ["verdict"],
    "properties": {
        "verdict": {"type": "string", "enum": ["a", "b"]},
        "n": {"type": "number"},
    },
}
DEFAULT = {"verdict": "b"}


def call(role="critic"):
    return complete_json("system", "user", SCHEMA, role, DEFAULT)


def provider(**kwargs):
    return mock.patch.object(base, "_provider_call", **kwargs)


class CompleteJsonTests(SimpleTestCase):
    def test_valid_json_is_returned_and_unknown_keys_are_dropped(self):
        with provider(return_value=json.dumps({"verdict": "a", "n": 1, "evil": "x"})):
            assert call() == {"verdict": "a", "n": 1}

    def test_broken_json_gives_the_default_after_one_retry(self):
        with provider(return_value="not json") as ask:
            result = call()
        assert result == {**DEFAULT, "_fallback": True}
        assert ask.call_count == 2

    def test_a_retry_can_recover(self):
        with provider(side_effect=["not json", '{"verdict": "a"}']) as ask:
            assert call() == {"verdict": "a"}
        assert ask.call_count == 2

    def test_schema_violations_give_the_default(self):
        bad = ['{"verdict": "zzz"}', '{"n": 1}', '{"verdict": "a", "n": true}', "[1]", "null"]
        for raw in bad:
            with provider(return_value=raw):
                assert call()["_fallback"] is True, raw

    def test_timeout_gives_the_default_after_one_retry(self):
        with provider(side_effect=LLMNetworkError("timeout")) as ask:
            result = call()
        assert result == {**DEFAULT, "_fallback": True}
        assert ask.call_count == 2

    def test_network_error_then_success(self):
        with provider(side_effect=[LLMNetworkError("x"), '{"verdict": "a"}']):
            assert call() == {"verdict": "a"}

    def test_provider_refusal_is_not_retried(self):
        with provider(side_effect=LLMError("AuthenticationError")) as ask:
            assert call()["_fallback"] is True
        assert ask.call_count == 1

    def test_the_default_is_never_mutated(self):
        with provider(return_value="not json"):
            call()["extra"] = 1
        assert DEFAULT == {"verdict": "b"}

    @override_settings(LLM_MAX_CALLS_PER_MESSAGE=2)
    def test_call_budget_per_message(self):
        with provider(return_value='{"verdict": "a"}') as ask, message_budget():
            assert call() == {"verdict": "a"}
            assert call() == {"verdict": "a"}
            assert call() == {**DEFAULT, "_fallback": True}
        assert ask.call_count == 2

    @override_settings(LLM_MAX_CALLS_PER_MESSAGE=2)
    def test_nested_budgets_share_one_counter(self):
        with provider(return_value='{"verdict": "a"}') as ask, message_budget():
            call()
            with message_budget():
                call()
                assert call()["_fallback"] is True
        assert ask.call_count == 2

    @override_settings(LLM_MAX_CALLS_PER_MESSAGE=1)
    def test_a_new_message_gets_a_fresh_budget(self):
        with provider(return_value='{"verdict": "a"}') as ask:
            for _ in range(3):
                with message_budget():
                    assert call() == {"verdict": "a"}
        assert ask.call_count == 3


def fake_openai(captured, create):
    class APIError(Exception):
        pass

    class APIConnectionError(APIError):
        pass

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))

    return types.SimpleNamespace(
        OpenAI=FakeClient, APIError=APIError, APIConnectionError=APIConnectionError
    )


def reply(content):
    message = types.SimpleNamespace(content=content)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


@override_settings(
    LLM_PROVIDER="deepseek",
    LLM_API_KEY="sk-test-secret",
    LLM_BASE_URL="https://api.deepseek.com",
    LLM_MODEL="deepseek-chat",
    LLM_TIMEOUT=7,
    LLM_MAX_OUTPUT_TOKENS=321,
)
class DeepSeekRequestTests(SimpleTestCase):
    def run_call(self, create, role="critic"):
        captured = {}
        fake = fake_openai(captured, create)
        with mock.patch.dict(sys.modules, {"openai": fake}):
            return call(role), captured, fake

    def test_request_is_json_mode_with_config_values(self):
        sent = {}

        def create(**kwargs):
            sent.update(kwargs)
            return reply('{"verdict": "a"}')

        result, captured, _ = self.run_call(create)
        assert result == {"verdict": "a"}
        assert captured["client"]["base_url"] == "https://api.deepseek.com"
        assert captured["client"]["timeout"] == 7
        assert captured["client"]["max_retries"] == 0
        assert sent["response_format"] == {"type": "json_object"}
        assert sent["model"] == "deepseek-chat"
        assert sent["max_tokens"] == 321
        assert sent["temperature"] == 0.0

    def test_responder_gets_a_little_temperature(self):
        sent = {}

        def create(**kwargs):
            sent.update(kwargs)
            return reply('{"verdict": "a"}')

        self.run_call(create, role="responder")
        assert sent["temperature"] == 0.3

    def test_connection_errors_are_retried_once_then_default(self):
        calls = []
        holder = {}

        def create(**kwargs):
            calls.append(1)
            raise holder["fake"].APIConnectionError("down")

        captured = {}
        fake = fake_openai(captured, create)
        holder["fake"] = fake
        with mock.patch.dict(sys.modules, {"openai": fake}):
            assert call()["_fallback"] is True
        assert len(calls) == 2

    def test_empty_content_gives_the_default(self):
        result, _, _ = self.run_call(lambda **kw: reply(None))
        assert result["_fallback"] is True

    def test_the_key_is_never_logged(self):
        with self.assertLogs("apps.security.llm", level=logging.INFO) as logs:
            self.run_call(lambda **kw: reply('{"verdict": "a"}'))
        text = "\n".join(logs.output)
        assert "sk-test-secret" not in text
        assert "role=critic" in text and "valid=True" in text

    @override_settings(LLM_API_KEY="")
    def test_missing_key_gives_the_default_without_a_request(self):
        sent = []
        result, captured, _ = self.run_call(lambda **kw: sent.append(1))
        assert result["_fallback"] is True
        assert not sent and "client" not in captured

    @override_settings(LLM_PROVIDER="mock")
    def test_mock_provider_never_touches_openai(self):
        with mock.patch.dict(sys.modules, {"openai": None}):
            result = complete_json(
                "s",
                "<customer_message>\nпривіт\n</customer_message>",
                {"required": ["attack"], "properties": {"attack": {"type": "boolean"}}},
                "guard",
                {"attack": True},
            )
        assert result == {"attack": False}
