from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from src.web.server import create_app


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("BEACON_DB", raising=False)


def test_store_meta_returns_missing_when_db_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_DB", str(tmp_path / "missing.db"))
    client = TestClient(create_app())
    resp = client.get("/api/store/meta")
    assert resp.status_code == 200
    data = resp.json()
    assert data["backend"] == "missing"
    assert data["db_exists"] is False


def test_store_events_404_when_db_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_DB", str(tmp_path / "missing.db"))
    client = TestClient(create_app())
    resp = client.get("/api/store/events")
    assert resp.status_code == 404


def test_store_limit_validation(tmp_path, monkeypatch):
    # create db file
    db_path = tmp_path / "beacon.db"
    from src.store import BeaconStore

    BeaconStore(db_path=db_path).init_db()

    monkeypatch.setenv("BEACON_DB", str(db_path))
    client = TestClient(create_app())
    resp = client.get("/api/store/events?limit=0")
    assert resp.status_code == 400


def test_store_invalid_datetime_400(tmp_path, monkeypatch):
    db_path = tmp_path / "beacon.db"
    from src.store import BeaconStore

    BeaconStore(db_path=db_path).init_db()

    monkeypatch.setenv("BEACON_DB", str(db_path))
    client = TestClient(create_app())
    resp = client.get("/api/store/events?since=not-a-date")
    assert resp.status_code == 400
