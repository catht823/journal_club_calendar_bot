import logging
from typing import Dict, List
from .models import ParsedEvent, Categories, MessageEventMap
from .storage import StateStore

def _calendar_summary_for_category(prefix: str, name: str) -> str:
    return f"{prefix}{name}"

def ensure_category_calendars(calendar, categories: Categories, state: StateStore) -> None:
    cal_map = state.load_calendar_map()
    cfg = state.load_settings()
    prefix = cfg.get("calendar_prefix", "Journal Club – ")
    if not cfg.get("auto_create_calendars", True):
        return

    existing = {}
    page_token = None
    while True:
        resp = calendar.calendarList().list(pageToken=page_token).execute()
        for item in resp.get("items", []):
            existing[item["summary"]] = item["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    changed = False
    for cat in categories.categories:
        summary = _calendar_summary_for_category(prefix, cat.name)
        if summary not in existing:
            body = {"summary": summary, "timeZone": cfg.get("timezone", "America/Los_Angeles")}
            created = calendar.calendars().insert(body=body).execute()
            existing[summary] = created["id"]
            changed = True

    if categories.fallback_category:
        summary = _calendar_summary_for_category(prefix, categories.fallback_category)
        if summary not in existing:
            body = {"summary": summary, "timeZone": cfg.get("timezone", "America/Los_Angeles")}
            created = calendar.calendars().insert(body=body).execute()
            existing[summary] = created["id"]
            changed = True

    if changed or not cal_map:
        state.save_calendar_map(existing)

def _build_event_body(pe: ParsedEvent, msg_id: str) -> dict:
    body = {
        "summary": pe.title,
        "description": (pe.abstract or "") + (f"\n\nSpeaker: {pe.speaker}" if pe.speaker else "") + (f"\n\nSource: Gmail msg {msg_id}" if msg_id else ""),
        "start": {"dateTime": pe.start.isoformat(), "timeZone": pe.timezone},
        "end": {"dateTime": pe.end.isoformat(), "timeZone": pe.timezone},
        "extendedProperties": {"private": {"source_msg_id": msg_id}},
    }
    if pe.location:
        body["location"] = pe.location
    if pe.url:
        body["description"] += f"\n\nLink: {pe.url}"
    return body

def upsert_event_to_calendars(calendar, categories: Categories, category_names: List[str], pe: ParsedEvent, msg_id: str, state: StateStore) -> MessageEventMap:
    cfg = state.load_settings()
    prefix = cfg.get("calendar_prefix", "Journal Club – ")
    cal_map = state.load_calendar_map() or {}
    mapping: Dict[str, str] = {}
    target_summaries = [_calendar_summary_for_category(prefix, c) for c in category_names]

    for summary in target_summaries:
        cal_id = cal_map.get(summary)
        if not cal_id:
            ensure_category_calendars(calendar, categories, state)
            cal_map = state.load_calendar_map() or {}
            cal_id = cal_map.get(summary)
            if not cal_id:
                logging.warning("Missing calendar for %s", summary)
                continue

        q = calendar.events().list(calendarId=cal_id, privateExtendedProperty=f"source_msg_id={msg_id}", maxResults=1).execute()
        items = q.get("items", [])
        body = _build_event_body(pe, msg_id)
        if items:
            ev_id = items[0]["id"]
            updated = calendar.events().update(calendarId=cal_id, eventId=ev_id, body=body).execute()
            mapping[summary] = updated["id"]
        else:
            created = calendar.events().insert(calendarId=cal_id, body=body).execute()
            mapping[summary] = created["id"]

    return MessageEventMap(message_id=msg_id, category_to_event_ids=mapping)

def delete_event_from_calendars(calendar, mapping: MessageEventMap) -> None:
    # No-op here; deletion would require storing calendar IDs alongside event IDs.
    pass