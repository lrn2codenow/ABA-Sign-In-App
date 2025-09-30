"""Domain services for the enterprise-ready ABA Sign-In app."""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Dict, List, MutableMapping, Optional, Tuple
import urllib.error
import urllib.request

from .config import AppConfig
from .persistence import AuditLogger, RuntimeSnapshotStore

LOGGER = logging.getLogger("aba.enterprise.services")


def _utcnow_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SignInService:
    """Encapsulate sign-in/out rules and auditing."""

    def __init__(
        self,
        data_store: MutableMapping[str, object],
        snapshot_store: RuntimeSnapshotStore,
        audit_logger: AuditLogger,
        config: AppConfig,
    ) -> None:
        self._data = data_store
        self._snapshot_store = snapshot_store
        self._audit_logger = audit_logger
        self._config = config

    def record_action(self, *, person_type: str, person_id: str, action: str, site: str) -> Dict[str, str]:
        if person_type not in {"staff", "client"}:
            raise ValueError("Unsupported person type")
        if action not in {"sign_in", "sign_out"}:
            raise ValueError("Unsupported action")

        person = self._data["staff" if person_type == "staff" else "clients"].get(person_id)
        if not person:
            raise KeyError(f"Unknown {person_type} identifier: {person_id}")

        timestamp = _utcnow_iso()
        entry = {
            "person_type": person_type,
            "id": person_id,
            "name": person.get("name", person_id),
            "site": site or person.get("site", ""),
            "timestamp": timestamp,
            "action": action,
        }
        self._data.setdefault("signins", []).append(entry)
        self._snapshot_store.save(self._data["signins"])
        if self._config.audit_log_enabled:
            self._audit_logger.record(
                {
                    "event": "sign_action",
                    "person_type": person_type,
                    "person_id": person_id,
                    "action": action,
                    "site": entry["site"],
                    "timestamp": timestamp,
                }
            )
        LOGGER.info(
            "Recorded %s event for %s %s",
            action,
            person_type,
            person.get("name", person_id),
            extra={"component": "SignInService", "site": entry["site"]},
        )
        return entry


class ReportingService:
    """Compute schedule adherence and emergency roll-call data."""

    def __init__(self, data_store: MutableMapping[str, object]):
        self._data = data_store

    def last_actions(self) -> Dict[Tuple[str, str], Dict[str, str]]:
        actions: Dict[Tuple[str, str], Dict[str, str]] = {}
        for record in self._data.get("signins", []):
            key = (record.get("person_type"), record.get("id"))
            actions[key] = record
        return actions

    def build_schedule_matrix(self, date: Optional[str] = None) -> List[Dict[str, str]]:
        today = date or _dt.date.today().isoformat()
        actions = self.last_actions()
        rows: List[Dict[str, str]] = []
        for schedule in self._data.get("schedule", []):
            if schedule.get("date") != today:
                continue
            key = (schedule.get("person_type"), schedule.get("id"))
            person_store = self._data["staff" if schedule.get("person_type") == "staff" else "clients"]
            person = person_store.get(schedule.get("id"), {})
            entry = {
                "person_type": schedule.get("person_type", "").title(),
                "name": person.get("name", schedule.get("id", "")),
                "start_time": schedule.get("start_time", ""),
                "end_time": schedule.get("end_time", ""),
                "site": schedule.get("site", ""),
                "status": "Absent",
                "sign_time": "",
            }
            action = actions.get(key)
            if action and action.get("action") == "sign_in":
                entry["status"] = "Present"
                entry["sign_time"] = action.get("timestamp", "")
            rows.append(entry)
        return rows

    def build_emergency_status(self, date: Optional[str] = None) -> Dict[str, object]:
        today = date or _dt.date.today().isoformat()
        actions = self.last_actions()
        present = []
        missing = []
        for schedule in self._data.get("schedule", []):
            if schedule.get("date") != today:
                continue
            key = (schedule.get("person_type"), schedule.get("id"))
            person_store = self._data["staff" if schedule.get("person_type") == "staff" else "clients"]
            person = person_store.get(schedule.get("id"), {})
            name = person.get("name", schedule.get("id", ""))
            site = schedule.get("site", "")
            contact_name = person.get("contact_name", "")
            contact_phone = person.get("contact_phone", "")
            action = actions.get(key)
            if action and action.get("action") == "sign_in":
                present.append(
                    (
                        schedule.get("person_type", "").title(),
                        name,
                        action.get("site", site),
                        action.get("timestamp", ""),
                    )
                )
            else:
                missing.append(
                    (
                        schedule.get("person_type", "").title(),
                        name,
                        site,
                        contact_name,
                        contact_phone,
                    )
                )
        return {"date": today, "present": present, "missing": missing}


class EmergencyNotificationService:
    """Dispatch formatted emergency roll-call summaries."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def send(self, webhook: str, markdown: str) -> Tuple[bool, str]:
        if not webhook:
            return False, "No Microsoft Teams webhook configured."
        payload = json.dumps({"text": markdown}).encode("utf-8")
        request = urllib.request.Request(
            webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._config.webhook_timeout) as response:
                if response.status >= 400:
                    return False, f"Teams webhook responded with HTTP {response.status} ({response.reason})."
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            LOGGER.warning("Webhook dispatch failed", exc_info=exc)
            return False, f"Failed to send notification: {exc}"
        return True, "Notification sent to Microsoft Teams."
