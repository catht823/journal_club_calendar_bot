import json
from pathlib import Path
from typing import Dict, Optional
import yaml
from .models import MessageEventMap

class StateStore:
    def __init__(self, base_dir: str) -> None:
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.processed_path = self.base / "processed.json"
        self.calendars_path = self.base / "calendars.json"
        self.settings_path = Path("config/settings.yml")
        if not self.processed_path.exists():
            self.processed_path.write_text("{}", encoding="utf-8")

    def is_processed(self, message_id: str) -> bool:
        data = json.loads(self.processed_path.read_text(encoding="utf-8"))
        return message_id in data

    def mark_processed(self, message_id: str, mapping: MessageEventMap) -> None:
        data = json.loads(self.processed_path.read_text(encoding="utf-8"))
        data[message_id] = mapping.category_to_event_ids
        self.processed_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_calendar_map(self) -> Optional[Dict[str, str]]:
        if not self.calendars_path.exists():
            return None
        return json.loads(self.calendars_path.read_text(encoding="utf-8"))

    def save_calendar_map(self, mapping: Dict[str, str]) -> None:
        self.calendars_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")

    def load_settings(self) -> dict:
        with open(self.settings_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}