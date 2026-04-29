"""Base agent class with Anthropic SDK integration."""

import json
import time
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore

from config import config
from core.memory import ConversationMemory


class BaseAgent(ABC):
    """Base class for all agents in the complaint arbitration system."""

    agent_name: str = "base"
    system_prompt: str = ""

    def __init__(self, memory: ConversationMemory, model: str | None = None):
        self.memory = memory
        self.model = model or config.default_model
        self._client: Optional[anthropic.Anthropic] = None

    @property
    def client(self):
        if anthropic is None:
            raise ImportError("anthropic package required for LLM calls")
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        return self._client

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """Return the tool definitions available to this agent."""

    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call. Override in subclasses that have tools."""
        raise NotImplementedError(f"Agent {self.agent_name} has no tool {tool_name}")

    def run(self, conversation_id: str, user_message: str,
            extra_context: str = "") -> str:
        """Run the agent: send prompt to LLM, handle tool calls, return result."""
        start = time.perf_counter()

        messages = self._build_messages(conversation_id, user_message, extra_context)
        system = self.get_system_prompt()
        tools = self.get_tools()

        self.memory.add(conversation_id, "system", self.agent_name,
                        f"Agent启动, system_prompt长度={len(system)}")

        try:
            response = self._call_llm(messages, system, tools)
        except Exception as e:
            error_msg = f"LLM调用失败: {e}"
            self.memory.add(conversation_id, "agent", self.agent_name, error_msg)
            return error_msg

        # Handle tool calls loop
        max_tool_rounds = 5
        for _ in range(max_tool_rounds):
            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._handle_tool(conversation_id, block)
                        tool_results.append(result)

                # Append assistant + tool results to messages
                messages.append({
                    "role": "assistant",
                    "content": [b.to_dict() for b in response.content],
                })
                messages.append({
                    "role": "user",
                    "content": tool_results,
                })
                try:
                    response = self._call_llm(messages, system, tools)
                except Exception as e:
                    return f"LLM tool-use round failed: {e}"

        elapsed = time.perf_counter() - start
        output = self._extract_text(response)
        self.memory.add(conversation_id, "agent", self.agent_name, output,
                        {"elapsed_ms": elapsed * 1000})
        return output

    def _build_messages(self, conversation_id: str, user_message: str,
                        extra_context: str = "") -> list[dict]:
        """Build message list from conversation memory + current message."""
        messages = []
        for entry in self.memory.get_context(conversation_id, limit=10):
            role = "assistant" if entry.role == "agent" else "user"
            messages.append({"role": role, "content": entry.content})

        prompt = user_message
        if extra_context:
            prompt = f"{extra_context}\n\n---\n用户消息:\n{user_message}"
        messages.append({"role": "user", "content": prompt})
        return messages

    def _call_llm(self, messages: list[dict], system: str,
                  tools: list[dict]) -> Any:
        kwargs = dict(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools
        return self.client.messages.create(**kwargs)

    def _handle_tool(self, conversation_id: str, tool_block) -> dict:
        """Execute a tool and record the result."""
        tool_name = tool_block.name
        tool_input = tool_block.input if isinstance(tool_block.input, dict) else json.loads(tool_block.input)
        self.memory.add(conversation_id, "tool", self.agent_name,
                        f"调用工具: {tool_name}({tool_input})")
        try:
            result = self.execute_tool(tool_name, tool_input)
        except Exception as e:
            result = f"工具执行错误: {e}"
        self.memory.add(conversation_id, "tool", self.agent_name,
                        f"工具结果: {str(result)[:500]}")
        return {
            "type": "tool_result",
            "tool_use_id": tool_block.id,
            "content": str(result),
        }

    @staticmethod
    def _extract_text(response) -> str:
        """Extract text content from an API response."""
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Try to extract JSON from LLM output."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON block
        for pattern in [r'```json\s*([\s\S]*?)\s*```', r'\{[\s\S]*\}']:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group(1) if '```' in pattern else match.group(0))
                except json.JSONDecodeError:
                    continue
        return None
