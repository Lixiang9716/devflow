"""LLM Client — calls DeepSeek API via Anthropic-compatible endpoint.

Handles:
- Tool calling (function calling)
- Retry with exponential backoff
- Circuit breaker integration
- Token tracking via T4
- Structured logging
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional, Any

import requests

from devflow.core.config import get_config, LLMConfig
from devflow.core.circuit_breaker import CircuitBreaker, CircuitState
from devflow.core.result import Result, ok, retryable, permanent, need_human, is_ok
from devflow.core.correlation import CorrelationId


@dataclass
class ToolDefinition:
    """JSON Schema definition for a tool that the LLM can call."""

    name: str
    description: str
    parameters: dict  # JSON Schema
    required: list[str] = field(default_factory=list)


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    duration_ms: float = 0.0


@dataclass
class ToolResult:
    """Result of executing a tool call, to send back to the LLM."""

    tool_call_id: str
    name: str
    content: str  # JSON string
    is_error: bool = False


class LLMClient:
    """Client for calling LLM APIs with tool support.

    Uses the Anthropic Messages API format via the DeepSeek endpoint.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or get_config().llm
        self.breaker = CircuitBreaker(
            name="cb_llm_api",
            failure_threshold=5,
            timeout_seconds=30.0,
        )
        self._session = requests.Session()

    # ── Public API ──────────────────────────────────────────────

    def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: Optional[list[ToolDefinition]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        correlation: Optional[CorrelationId] = None,
    ) -> Result[LLMResponse]:
        """Send a chat completion request to the LLM.

        Args:
            system_prompt: System-level instruction
            messages: Conversation history as [{"role": "...", "content": "..."}]
            tools: Optional tool definitions for function calling
            model: Model override (defaults to config)
            temperature: Temperature override
            max_tokens: Max tokens override
            correlation: Correlation ID for tracing

        Returns:
            Result[LLMResponse] with content and optional tool calls
        """
        model = model or self.config.default_model
        temperature = temperature if temperature is not None else self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        # Build Anthropic-format request body
        body = self._build_request(system_prompt, messages, tools, model, temperature, max_tokens)
        headers = self._build_headers()

        # Execute with retry
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                if not self.breaker.is_allowed():
                    return retryable("llm_client", "X", "Circuit breaker OPEN — LLM API unavailable")

                start_time = time.time()
                resp = self._session.post(
                    f"{self.config.base_url}/v1/messages",
                    json=body,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                duration_ms = (time.time() - start_time) * 1000

                if resp.status_code == 200:
                    self.breaker.record_success()
                    return ok(self._parse_response(resp.json(), model, duration_ms))

                elif resp.status_code == 429:
                    # Rate limit — retry with backoff
                    self.breaker.record_failure()
                    wait = min(2 ** attempt, 30)
                    time.sleep(wait)
                    last_error = f"Rate limited (429), attempt {attempt + 1}"

                elif resp.status_code >= 500:
                    self.breaker.record_failure()
                    wait = min(2 ** attempt, 10)
                    time.sleep(wait)
                    last_error = f"Server error ({resp.status_code}): {resp.text[:200]}"

                else:
                    # 4xx (non-429) — don't retry
                    return permanent("llm_client", "X",
                                     f"Client error ({resp.status_code}): {resp.text[:300]}")

            except requests.Timeout:
                self.breaker.record_failure()
                last_error = f"Request timeout after {self.config.timeout_seconds}s"
                if attempt < self.config.max_retries - 1:
                    time.sleep(1)

            except requests.ConnectionError as e:
                self.breaker.record_failure()
                last_error = f"Connection error: {e}"
                if attempt < self.config.max_retries - 1:
                    time.sleep(2)

        # All retries exhausted
        return retryable("llm_client", "X", last_error or "Unknown error after all retries")

    def chat_with_tools_loop(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[ToolDefinition],
        tool_handler: callable,
        model: Optional[str] = None,
        correlation: Optional[CorrelationId] = None,
        max_tool_rounds: int = 5,
    ) -> Result[LLMResponse]:
        """Run a chat loop with tool calling.

        The LLM may request tool calls. When it does, we execute them
        and feed results back until the LLM produces a final text response.

        Args:
            system_prompt: System instruction for the agent
            user_message: The user's task description
            tools: Available tool definitions
            tool_handler: Function(tool_call: ToolCall) -> ToolResult
            model: Model override
            correlation: Correlation ID
            max_tool_rounds: Maximum tool-calling iterations

        Returns:
            Final LLMResponse (content is the agent's final answer)
        """
        messages = [{"role": "user", "content": user_message}]

        for round_num in range(max_tool_rounds):
            result = self.chat(
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                model=model,
                correlation=correlation,
            )

            if not is_ok(result):
                return result

            response = result.data

            # If no tool calls, this is the final response
            if not response.tool_calls:
                return ok(response)

            # Add assistant message with tool calls
            assistant_content = [{"type": "text", "text": response.content}]
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute all tool calls
            tool_results = []
            for tc in response.tool_calls:
                tr = tool_handler(tc)
                tool_results.append(tr)

            # Add tool results as a SINGLE user message (Anthropic requirement)
            tool_result_blocks = []
            for tr in tool_results:
                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tr.tool_call_id,
                    "content": tr.content,
                    "is_error": tr.is_error,
                })
            messages.append({
                "role": "user",
                "content": tool_result_blocks,
            })

        # Max rounds exceeded
        return need_human("agent_loop", "X",
                          f"Agent exceeded {max_tool_rounds} tool-calling rounds without final answer")

    # ── Internal helpers ────────────────────────────────────────

    def _build_request(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: Optional[list[ToolDefinition]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Build the Anthropic Messages API request body."""
        # Convert messages to Anthropic format
        anthropic_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                anthropic_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                anthropic_messages.append({"role": role, "content": content})
            else:
                anthropic_messages.append({"role": role, "content": str(content)})

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": anthropic_messages,
        }

        if tools:
            body["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": {
                        "type": "object",
                        "properties": t.parameters,
                        "required": t.required,
                    },
                }
                for t in tools
            ]

        return body

    def _build_headers(self) -> dict:
        """Build HTTP headers for the API request."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "anthropic-version": "2023-06-01",
        }

    def _parse_response(
        self, data: dict, model: str, duration_ms: float
    ) -> LLMResponse:
        """Parse Anthropic-format response into LLMResponse."""
        content_text = ""
        tool_calls = []

        # Anthropic format: content is an array of blocks
        for block in data.get("content", []):
            if block["type"] == "text":
                content_text += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block.get("input", {}),
                ))

        usage = data.get("usage", {})
        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            finish_reason=data.get("stop_reason", "stop"),
            duration_ms=duration_ms,
        )


# Global client instance
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def reset_llm_client():
    """Reset the LLM client (for testing)."""
    global _client
    _client = None
