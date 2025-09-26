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
    # Build description with better formatting
    description_parts = []
    
    if pe.abstract:
        description_parts.append(pe.abstract)
    
    if pe.speaker:
        description_parts.append(f"Speaker: {pe.speaker}")
    
    if pe.location:
        description_parts.append(f"Location: {pe.location}")
    
    if pe.url:
        description_parts.append(f"Meeting Link: {pe.url}")
    
    # Add attachment information
    if pe.attachments:
        attachment_info = []
        for att in pe.attachments:
            filename = att.get("filename", "Unknown")
            size = att.get("size", 0)
            size_str = f"({size} bytes)" if size > 0 else ""
            attachment_info.append(f"📎 {filename} {size_str}")
        
        if attachment_info:
            description_parts.append("Attachments:\n" + "\n".join(attachment_info))
    
    # Add source information
    if msg_id:
        description_parts.append(f"Source: Gmail message {msg_id}")
    
    description = "\n\n".join(description_parts) if description_parts else ""
    
    body = {
        "summary": pe.title,
        "description": description,
        "start": {"dateTime": pe.start.isoformat(), "timeZone": pe.timezone},
        "end": {"dateTime": pe.end.isoformat(), "timeZone": pe.timezone},
        "extendedProperties": {"private": {"source_msg_id": msg_id}},
    }
    
    # Add location to the event location field (separate from description)
    if pe.location:
        body["location"] = pe.location
    
    return body

def upsert_event_to_calendars(calendar, categories: Categories, category_names: List[str], pe: ParsedEvent, msg_id: str, state: StateStore) -> MessageEventMap:
    cfg = state.load_settings()
    prefix = cfg.get("calendar_prefix", "Journal Club – ")
    cal_map = state.load_calendar_map() or {}
    mapping: Dict[str, str] = {}
    target_summaries = [_calendar_summary_for_category(prefix, c) for c in category_names]

    logging.info(f"Creating/updating event: '{pe.title}' for categories: {category_names}")
    logging.info(f"Event time: {pe.start} to {pe.end}")
    logging.info(f"Target calendars: {target_summaries}")

    for summary in target_summaries:
        cal_id = cal_map.get(summary)
        if not cal_id:
            logging.info(f"Calendar not found in map, ensuring it exists: {summary}")
            ensure_category_calendars(calendar, categories, state)
            cal_map = state.load_calendar_map() or {}
            cal_id = cal_map.get(summary)
            if not cal_id:
                logging.warning("Missing calendar for %s", summary)
                continue

        logging.info(f"Using calendar: {summary} (ID: {cal_id})")

        q = calendar.events().list(calendarId=cal_id, privateExtendedProperty=f"source_msg_id={msg_id}", maxResults=1).execute()
        items = q.get("items", [])
        body = _build_event_body(pe, msg_id)
        
        # Log event details
        start_time = body.get("start", {}).get("dateTime", "no time")
        end_time = body.get("end", {}).get("dateTime", "no time")
        logging.info(f"Event scheduled: {start_time} to {end_time}")
        
        if items:
            ev_id = items[0]["id"]
            logging.info(f"Updating existing event: {ev_id}")
            updated = calendar.events().update(calendarId=cal_id, eventId=ev_id, body=body).execute()
            mapping[summary] = updated["id"]
            logging.info(f"Updated event: {updated.get('htmlLink', 'no link')}")
        else:
            logging.info(f"Creating new event in calendar: {summary}")
            created = calendar.events().insert(calendarId=cal_id, body=body).execute()
            mapping[summary] = created["id"]
            logging.info(f"Created new event: {created.get('htmlLink', 'no link')}")

    return MessageEventMap(message_id=msg_id, category_to_event_ids=mapping)

def delete_event_from_calendars(calendar, mapping: MessageEventMap) -> None:
    # No-op here; deletion would require storing calendar IDs alongside event IDs.
    pass