"""Persistence helpers for the enterprise-ready ABA Sign-In app."""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping


@dataclass
class PersonRecord:
    """Typed representation of a staff or client record."""

    id: str
    name: str
    site: str
    email: str = ""
    phone: str = ""
    contact_name: str = ""
    contact_phone: str = ""


@dataclass
class ScheduleRecord:
    """Typed representation of a schedule entry."""

    person_type: str
    person_id: str
    date: str
    start_time: str
    end_time: str
    site: str


@dataclass
class SignInRecord:
    """Persistent representation of a sign-in event."""

    person_type: str
    person_id: str
    name: str
    site: str
    timestamp: str
    action: str


def _normalize_row(row: MutableMapping[str, str]) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized_key = key.strip().lower()
        if not normalized_key:
            continue
        cleaned[normalized_key] = value.strip() if isinstance(value, str) else ""
    return cleaned


class CSVDataLoader:
    """Load staff, client, and schedule data from CSV sources."""

    REQUIRED_STAFF_COLUMNS = {"id", "name", "site"}
    REQUIRED_CLIENT_COLUMNS = {"id", "name", "site"}
    REQUIRED_SCHEDULE_COLUMNS = {"person_type", "id", "date", "start_time", "end_time", "site"}

    def __init__(self, data_store: MutableMapping[str, object]):
        self._data = data_store

    def load_people(self, file_path: str, category: str) -> None:
        if category not in {"staff", "clients"}:
            raise ValueError(f"Unsupported category: {category}")
        required = self.REQUIRED_STAFF_COLUMNS if category == "staff" else self.REQUIRED_CLIENT_COLUMNS
        records: Dict[str, Dict[str, str]] = {}
        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                cleaned = _normalize_row(row)
                if not required.issubset(cleaned):
                    # Skip incomplete rows; detailed validation is performed by
                    # higher layers once a real database is adopted.
                    continue
                key = cleaned["id"]
                records[key] = cleaned
        self._data[category] = records

    def load_schedule(self, file_path: str) -> None:
        schedule: List[Dict[str, str]] = []
        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                cleaned = _normalize_row(row)
                if not self.REQUIRED_SCHEDULE_COLUMNS.issubset(cleaned):
                    continue
                if not all(cleaned.get(field) for field in self.REQUIRED_SCHEDULE_COLUMNS):
                    continue
                person_type = cleaned.get("person_type", "")
                if person_type not in {"staff", "client"}:
                    continue
                if not self._is_valid_date(cleaned["date"]):
                    continue
                if not self._is_valid_time(cleaned["start_time"]):
                    continue
                if not self._is_valid_time(cleaned["end_time"]):
                    continue
                schedule.append(
                    {
                        "person_type": person_type,
                        "id": cleaned["id"],
                        "date": cleaned["date"],
                        "start_time": cleaned["start_time"],
                        "end_time": cleaned["end_time"],
                        "site": cleaned["site"],
                    }
                )
        self._data["schedule"] = schedule

    @staticmethod
    def _is_valid_date(value: str) -> bool:
        try:
            _dt.datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return False
        return True

    @staticmethod
    def _is_valid_time(value: str) -> bool:
        try:
            _dt.datetime.strptime(value, "%H:%M")
        except ValueError:
            return False
        return True


class RuntimeSnapshotStore:
    """Persist sign-in records to disk as JSON snapshots."""

    def __init__(self, runtime_dir: Path):
        self._runtime_dir = Path(runtime_dir)
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_path = self._runtime_dir / "signins.json"

    def save(self, records: Iterable[Dict[str, str]]) -> None:
        payload = [dict(record) for record in records]
        with open(self._snapshot_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def load(self) -> List[Dict[str, str]]:
        if not self._snapshot_path.exists():
            return []
        try:
            with open(self._snapshot_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, dict)]
        return []


class SettingsStore:
    """Persist runtime configuration outside of source control."""

    def __init__(self, runtime_dir: Path, filename: str = "settings.json") -> None:
        self._runtime_dir = Path(runtime_dir)
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._runtime_dir / filename

    def load(self) -> Dict[str, str]:
        if not self._path.exists():
            return {"teams_webhook_url": ""}
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"teams_webhook_url": ""}
        if not isinstance(data, dict):
            return {"teams_webhook_url": ""}
        result = {"teams_webhook_url": ""}
        webhook = data.get("teams_webhook_url")
        if isinstance(webhook, str):
            result["teams_webhook_url"] = webhook
        return result

    def save(self, settings: Dict[str, str]) -> None:
        payload = {"teams_webhook_url": settings.get("teams_webhook_url", "")}
        with open(self._path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)


class AuditLogger:
    """Append simple audit events for compliance readiness."""

    def __init__(self, runtime_dir: Path, filename: str = "audit-events.jsonl") -> None:
        self._path = Path(runtime_dir) / filename

    def record(self, event: Dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + os.linesep)
