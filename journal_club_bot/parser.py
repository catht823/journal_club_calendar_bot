import re
from datetime import timedelta
from typing import Optional
import dateparser
from bs4 import BeautifulSoup
from pathlib import Path
import yaml
from .models import ParsedEvent

def _load_settings(settings_path: Path) -> dict:
    with open(settings_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _html_to_text(html: Optional[str]) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text("\n", strip=True)

def _extract_line(prefixes, text: str) -> Optional[str]:
    import re
    for p in prefixes:
        m = re.search(rf"{re.escape(p)}\\s*[:\\-]\\s*(.+)", text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None

def parse_event_from_text(subject: str, body_text: str, html: Optional[str], settings_path: Path) -> Optional[ParsedEvent]:
    cfg = _load_settings(settings_path)
    tz = cfg.get("timezone", "America/Los_Angeles")
    default_minutes = int(cfg.get("default_duration_minutes", 60))

    combined = "\n".join([subject, body_text or "", _html_to_text(html) or ""]).strip()
    if not combined:
        return None

    cancelled = bool(re.search(r"cancelled|canceled|postponed", combined, flags=re.IGNORECASE))

    dt = dateparser.search.search_dates(combined, settings={"TIMEZONE": tz, "RETURN_AS_TIMEZONE_AWARE": True})
    start = None
    end = None
    if dt:
        start = dt[0][1]
        later = [d for t, d in dt[1:] if d > start]
        if later:
            end = later[0]
    if start and not end:
        end = start + timedelta(minutes=default_minutes)
    if not start or not end:
        return None

    title = _extract_line(["Title"], combined) or subject.strip()
    speaker = _extract_line(["Speaker", "Presenter"], combined)
    location = _extract_line(["Location", "Where"], combined)
    url = _extract_line(["Zoom", "Link", "Meeting", "URL"], combined)
    abstract = _extract_line(["Abstract"], combined)

    return ParsedEvent(
        title=title or "Journal Club",
        start=start,
        end=end,
        timezone=tz,
        speaker=speaker,
        location=location,
        url=url,
        abstract=abstract,
        cancelled=cancelled,
    )