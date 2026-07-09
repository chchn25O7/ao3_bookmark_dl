import json
import os
from datetime import datetime, timezone


class Manifest:
    """JSON-backed record of which (work_id, format) pairs have already been downloaded."""

    def __init__(self, path: str):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self):
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self.path)

    def has(self, work_id: int, fmt: str) -> bool:
        entry = self._data.get(str(work_id))
        return bool(entry and fmt in entry.get("formats", []))

    def record(self, work_id: int, title: str, fmt: str):
        key = str(work_id)
        entry = self._data.setdefault(key, {"title": title, "formats": []})
        entry["title"] = title
        if fmt not in entry["formats"]:
            entry["formats"].append(fmt)
        entry["downloaded_at"] = datetime.now(timezone.utc).isoformat()
        self._save()
