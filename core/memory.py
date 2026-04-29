"""Conversation memory for maintaining context across multi-agent interactions."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MemoryEntry:
    role: str          # "user", "agent", "system", "tool"
    agent_name: str    # which agent produced this
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


class ConversationMemory:
    """Thread-safe memory store for complaint processing context."""

    def __init__(self, max_entries: int = 100):
        self._entries: dict[str, list[MemoryEntry]] = defaultdict(list)
        self.max_entries = max_entries

    def add(self, conversation_id: str, role: str, agent_name: str,
            content: str, metadata: dict | None = None):
        entry = MemoryEntry(role=role, agent_name=agent_name, content=content,
                            metadata=metadata or {})
        self._entries[conversation_id].append(entry)
        if len(self._entries[conversation_id]) > self.max_entries:
            self._entries[conversation_id] = self._entries[conversation_id][-self.max_entries:]

    def get_context(self, conversation_id: str, limit: int = 20) -> list[MemoryEntry]:
        return self._entries[conversation_id][-limit:]

    def get_agent_output(self, conversation_id: str, agent_name: str) -> str | None:
        """Get the last output from a specific agent."""
        for entry in reversed(self._entries[conversation_id]):
            if entry.role == "agent" and entry.agent_name == agent_name:
                return entry.content
        return None

    def get_all_evidence(self, conversation_id: str) -> list[dict]:
        """Collect all evidence from tool calls."""
        evidence = []
        for entry in self._entries[conversation_id]:
            if entry.role == "tool" and entry.metadata.get("type") == "evidence":
                evidence.append(entry.metadata)
        return evidence

    def clear(self, conversation_id: str):
        self._entries.pop(conversation_id, None)

    def summary(self, conversation_id: str) -> str:
        """Return a compact summary of the conversation flow."""
        entries = self._entries[conversation_id]
        if not entries:
            return "(无对话记录)"
        lines = []
        for e in entries:
            role_tag = {"user": "用户", "agent": "Agent", "system": "系统", "tool": "工具"}.get(e.role, e.role)
            lines.append(f"[{role_tag}:{e.agent_name}] {e.content[:120]}{'...' if len(e.content) > 120 else ''}")
        return "\n".join(lines)
