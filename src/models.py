"""Core data models for Beacon."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SourceType(Enum):
    GITHUB = "github"
    CALENDAR = "calendar"
    EMAIL = "email"
    WEATHER = "weather"
    NEWS = "news"
    HACKER_NEWS = "hacker_news"
    CUSTOM = "custom"


class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class SyncStatus(Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    OK = "ok"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class User:
    """Represents the Beacon user/owner."""

    name: str
    email: str
    timezone: str = "UTC"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __repr__(self) -> str:
        return f"User(name={self.name!r}, email={self.email!r})"


@dataclass
class Source:
    """A connected data source (connector instance)."""

    name: str
    source_type: SourceType
    enabled: bool = True
    sync_status: SyncStatus = SyncStatus.PENDING
    last_synced_at: datetime | None = None
    error_message: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    def mark_synced(self) -> None:
        """Mark this source as successfully synced."""
        self.sync_status = SyncStatus.OK
        self.last_synced_at = datetime.utcnow()
        self.error_message = None

    def mark_error(self, message: str) -> None:
        """Mark this source as errored."""
        self.sync_status = SyncStatus.ERROR
        self.error_message = message

    def is_healthy(self) -> bool:
        return self.enabled and self.sync_status in (SyncStatus.OK, SyncStatus.PENDING)

    def __repr__(self) -> str:
        return f"Source(name={self.name!r}, type={self.source_type.value!r}, status={self.sync_status.value!r})"


@dataclass
class Event:
    """A discrete event pulled from a source (meeting, notification, email, etc.)."""

    title: str
    source_id: str
    source_type: SourceType
    occurred_at: datetime
    summary: str = ""
    url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __repr__(self) -> str:
        return f"Event(title={self.title!r}, source={self.source_type.value!r})"


@dataclass
class ActionItem:
    """A task or action that requires attention."""

    title: str
    source_id: str
    source_type: SourceType
    priority: Priority = Priority.MEDIUM
    due_at: datetime | None = None
    url: str = ""
    completed: bool = False
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)

    def complete(self) -> None:
        """Mark this action item as completed."""
        self.completed = True

    def is_overdue(self) -> bool:
        if self.due_at is None or self.completed:
            return False
        return datetime.utcnow() > self.due_at

    def __repr__(self) -> str:
        return f"ActionItem(title={self.title!r}, priority={self.priority.value!r}, completed={self.completed!r})"


@dataclass
class Briefing:
    """A daily briefing aggregating events and action items."""

    date: datetime
    sources_synced: list[str] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    summary: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def add_event(self, event: Event) -> None:
        self.events.append(event)

    def add_action_item(self, item: ActionItem) -> None:
        self.action_items.append(item)

    def pending_actions(self) -> list[ActionItem]:
        return [a for a in self.action_items if not a.completed]

    def urgent_actions(self) -> list[ActionItem]:
        return [a for a in self.action_items if not a.completed and a.priority == Priority.URGENT]

    def __repr__(self) -> str:
        return (
            f"Briefing(date={self.date.date()!r}, "
            f"events={len(self.events)}, "
            f"action_items={len(self.action_items)})"
        )
