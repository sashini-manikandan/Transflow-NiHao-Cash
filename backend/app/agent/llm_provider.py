"""The only module in the codebase that imports the OpenAI SDK.

Uses the Chat Completions API with tool calling so the same code path works
for official OpenAI keys and OpenRouter (`sk-or-…`) keys. The API key is read
from backend settings and never returned, logged, or included in any response.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings

logger = logging.getLogger("billwise.llm")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LLMUnavailable(RuntimeError):
    """Raised when the model cannot be reached or refuses the request.

    The message is safe to show a user: it never contains credentials or raw
    provider payloads.
    """


@dataclass
class LLMToolCall:
    call_id: str
    name: str
    arguments_json: str

    def parsed_arguments(self) -> dict[str, Any]:
        if not self.arguments_json.strip():
            return {}
        try:
            value = json.loads(self.arguments_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"arguments were not valid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("arguments must be a JSON object")
        return value


@dataclass
class LLMTurn:
    text: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    # Assistant message in chat format, ready to append to the conversation.
    assistant_message: dict = field(default_factory=dict)
    # Kept for older test fixtures; unused by the chat-completions loop.
    raw_output: list[dict] = field(default_factory=list)


class LLMProvider:
    """Thin wrapper over Chat Completions with tool calling."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = None

    @property
    def available(self) -> bool:
        return self._settings.llm_enabled

    @property
    def model(self) -> str:
        name = self._settings.openai_model.strip()
        # OpenRouter expects vendor-prefixed ids; bare OpenAI names still work
        # if we add the openai/ prefix for that gateway.
        if self._settings.is_openrouter and "/" not in name:
            return f"openai/{name}"
        return name

    @property
    def provider_label(self) -> str:
        return "openrouter" if self._settings.is_openrouter else "openai"

    def _get_client(self):
        if self._client is None:
            if not self.available:
                raise LLMUnavailable("No model credentials are configured on the server.")
            from openai import OpenAI

            kwargs: dict[str, Any] = {
                "api_key": self._settings.openai_api_key,
                "timeout": self._settings.openai_timeout_seconds,
                "max_retries": 1,
            }
            base = self._settings.resolved_openai_base_url
            if base:
                kwargs["base_url"] = base
            self._client = OpenAI(**kwargs)
        return self._client

    def respond(
        self,
        *,
        instructions: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMTurn:
        """One model turn. Returns text and/or requested tool calls."""
        client = self._get_client()
        chat_messages = [{"role": "system", "content": instructions}, *messages]
        chat_tools = _to_chat_tools(tools) if tools else None

        request: dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": 0.2,
        }
        if chat_tools:
            request["tools"] = chat_tools
            request["tool_choice"] = "auto"

        try:
            response = client.chat.completions.create(**request)
        except Exception as exc:  # noqa: BLE001 - normalised below
            raise _translate_error(exc) from exc

        return _parse_chat_response(response)


def _to_chat_tools(tools: list[dict]) -> list[dict]:
    """Accept either Responses-style or Chat Completions-style tool schemas."""
    converted: list[dict] = []
    for tool in tools:
        if "function" in tool:
            converted.append(tool)
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return converted


def _parse_chat_response(response: Any) -> LLMTurn:
    choice = (response.choices or [None])[0]
    if choice is None or choice.message is None:
        return LLMTurn(text="")

    message = choice.message
    text = (message.content or "").strip()
    tool_calls: list[LLMToolCall] = []
    raw_tool_calls: list[dict] = []

    for call in message.tool_calls or []:
        call_id = getattr(call, "id", "") or ""
        function = getattr(call, "function", None)
        name = getattr(function, "name", "") if function else ""
        arguments = getattr(function, "arguments", "") if function else ""
        tool_calls.append(
            LLMToolCall(call_id=call_id, name=name, arguments_json=arguments or "")
        )
        raw_tool_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments or ""},
            }
        )

    assistant_message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if raw_tool_calls:
        assistant_message["tool_calls"] = raw_tool_calls
        # Some providers reject null content when tool_calls are present.
        if assistant_message["content"] is None:
            assistant_message["content"] = ""

    return LLMTurn(text=text, tool_calls=tool_calls, assistant_message=assistant_message)


def _translate_error(exc: Exception) -> LLMUnavailable:
    """Map provider exceptions to safe, user-facing messages."""
    name = type(exc).__name__
    mapping = {
        "APITimeoutError": "The assistant timed out before the model replied.",
        "APIConnectionError": "The assistant could not reach the model provider.",
        "RateLimitError": "The model provider is rate limiting this key right now.",
        "AuthenticationError": "The server's model credentials were rejected.",
        "PermissionDeniedError": "The configured model is not available to this key.",
        "NotFoundError": "The configured model name does not exist.",
        "BadRequestError": "The model rejected the request as malformed.",
    }
    message = mapping.get(name, "The assistant could not complete the request.")
    logger.error("llm_error type=%s", name)
    return LLMUnavailable(message)
