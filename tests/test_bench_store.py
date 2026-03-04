import random
from datetime import datetime, timedelta, timezone

import pytest

from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore


def _make_events(n: int) -> list[Event]:
    now = datetime.now(tz=timezone.utc)
    out: list[Event] = []
    for i in range(n):
        out.append(
            Event(
                id=f"e{i}",
                title=f"Event {i}",
                source_id="github",
                source_type=SourceType.GITHUB,
                occurred_at=now - timedelta(minutes=i),
                summary="",
                url="",
                metadata={"i": i},
                created_at=now,
            )
        )
    return out


def _make_action_items(n: int) -> list[ActionItem]:
    now = datetime.now(tz=timezone.utc)
    out: list[ActionItem] = []
    for i in range(n):
        out.append(
            ActionItem(
                id=f"a{i}",
                title=f"Action {i}",
                source_id="github",
                source_type=SourceType.GITHUB,
                priority=random.choice(list(Priority)),
                due_at=now + timedelta(days=(i % 7)),
                url="",
                completed=(i % 3 == 0),
                notes="",
                metadata={"i": i},
                created_at=now,
            )
        )
    return out


@pytest.fixture()
def store(tmp_path):
    s = BeaconStore(tmp_path / "bench.db")
    s.upsert_events(_make_events(2000))
    s.upsert_action_items(_make_action_items(2000))
    return s


@pytest.mark.benchmark(group="store")
def test_benchmark_query_events_first_page(benchmark, store):
    def run():
        res = store.query_events(limit=100, sort="occurred_at_desc")
        assert len(res) == 100

    benchmark(run)


@pytest.mark.benchmark(group="store")
def test_benchmark_query_events_second_page_by_cursor(benchmark, store):
    first = store.query_events(limit=100, sort="occurred_at_desc")
    last = first[-1]
    cursor = store.encode_event_cursor(last, sort="occurred_at_desc")

    def run():
        res = store.query_events(limit=100, sort="occurred_at_desc", cursor=cursor)
        assert len(res) == 100

    benchmark(run)


@pytest.mark.benchmark(group="store")
def test_benchmark_query_action_items_default_sort(benchmark, store):
    def run():
        res = store.query_action_items(limit=100, sort="default")
        assert len(res) == 100

    benchmark(run)
