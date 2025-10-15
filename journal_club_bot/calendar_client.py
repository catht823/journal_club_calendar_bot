import logging
from typing import Dict, List, Optional
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
    
    # Add attachment links to description
    if pe.attachments:
        attachment_info = []
        for att in pe.attachments:
            title = att.get("title", "Attachment")
            mime_type = att.get("mimeType", "")
            size = att.get("size", 0)
            
            # Format size nicely
            if size > 1024 * 1024:
                size_str = f"{size / (1024*1024):.1f} MB"
            elif size > 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} bytes" if size > 0 else ""
            
            file_url = att.get("fileUrl", "")
            if file_url:
                attachment_info.append(f"📎 {title} ({size_str}): {file_url}")
            else:
                attachment_info.append(f"📎 {title} ({size_str})")
        
        if attachment_info:
            description_parts.append("Attachments:\n" + "\n".join(attachment_info))
    
    # Add source information with Gmail link
    if msg_id:
        gmail_link = f"https://mail.google.com/mail/#all/{msg_id}"
        description_parts.append(f"📧 View original email: {gmail_link}")
        if pe.attachments:
            description_parts.append("(Attachments can be downloaded from the original email)")
    
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
    
    # Add attachments as event attachments (requires file URLs)
    if pe.attachments:
        calendar_attachments = []
        for att in pe.attachments:
            if att.get("fileUrl"):
                calendar_attachments.append({
                    "fileUrl": att["fileUrl"],
                    "title": att.get("title", "Attachment"),
                    "mimeType": att.get("mimeType", "application/octet-stream")
                })
        if calendar_attachments:
            body["attachments"] = calendar_attachments
    
    return body

def find_existing_event(calendar, cal_id: str, parsed_event: ParsedEvent, state: StateStore) -> Optional[str]:
    """
    Find an existing calendar event that matches the parsed event for updates.
    Uses multiple matching strategies with scoring to find the best match.
    """
    if not parsed_event.original_event_ref and not parsed_event.speaker and not parsed_event.title:
        logging.info("No identifying information for event matching")
        return None
    
    logging.info(f"Searching for existing event - ref: '{parsed_event.original_event_ref}', speaker: '{parsed_event.speaker}', title: '{parsed_event.title}'")
    
    # Search for events in the calendar
    try:
        # Get events from the past 60 days to future 60 days (wider range)
        from datetime import datetime, timedelta
        time_min = (datetime.now() - timedelta(days=60)).isoformat() + 'Z'
        time_max = (datetime.now() + timedelta(days=60)).isoformat() + 'Z'
        
        events_result = calendar.events().list(
            calendarId=cal_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        logging.info(f"Found {len(events)} existing events to check")
        
        # Score each event for matching
        matches = []
        
        for event in events:
            score = 0
            event_id = event['id']
            event_summary = event.get('summary', '')
            event_description = event.get('description', '')
            event_location = event.get('location', '')
            
            # Normalize for comparison
            event_summary_lower = event_summary.lower()
            event_description_lower = event_description.lower()
            ref_lower = (parsed_event.original_event_ref or '').lower()
            title_lower = (parsed_event.title or '').lower()
            speaker_lower = (parsed_event.speaker or '').lower()
            
            # Strategy 1: Exact or substring title match (highest priority)
            if parsed_event.original_event_ref:
                # Check if reference matches title
                if ref_lower in event_summary_lower or event_summary_lower in ref_lower:
                    score += 100
                    logging.debug(f"Event '{event_summary}' matches by original reference (score +100)")
                
                # Check if reference is in description
                if ref_lower in event_description_lower:
                    score += 80
                    logging.debug(f"Event '{event_summary}' has reference in description (score +80)")
            
            # Strategy 2: Current title similarity
            if parsed_event.title and parsed_event.title != "Journal Club":
                # Check for exact match
                if title_lower == event_summary_lower:
                    score += 90
                    logging.debug(f"Event '{event_summary}' exact title match (score +90)")
                # Check for substring match
                elif title_lower in event_summary_lower or event_summary_lower in title_lower:
                    score += 70
                    logging.debug(f"Event '{event_summary}' partial title match (score +70)")
                # Check for word overlap (fuzzy matching)
                elif len(title_lower) > 10:
                    title_words = set(title_lower.split())
                    summary_words = set(event_summary_lower.split())
                    common_words = title_words & summary_words
                    if len(common_words) >= 3:  # At least 3 common words
                        overlap_score = min(len(common_words) * 10, 50)
                        score += overlap_score
                        logging.debug(f"Event '{event_summary}' has {len(common_words)} common words (score +{overlap_score})")
            
            # Strategy 3: Speaker match
            if parsed_event.speaker:
                if speaker_lower in event_description_lower or speaker_lower in event_summary_lower:
                    score += 60
                    logging.debug(f"Event '{event_summary}' matches by speaker (score +60)")
            
            # Strategy 4: Date proximity
            if parsed_event.start:
                event_start = event.get('start', {}).get('dateTime')
                if event_start:
                    from dateutil import parser as date_parser
                    try:
                        event_datetime = date_parser.parse(event_start)
                        time_diff = abs((parsed_event.start - event_datetime).total_seconds())
                        
                        # Score based on how close the dates are
                        if time_diff <= 24 * 3600:  # Within 1 day
                            score += 40
                            logging.debug(f"Event '{event_summary}' within 1 day (score +40)")
                        elif time_diff <= 3 * 24 * 3600:  # Within 3 days
                            score += 30
                            logging.debug(f"Event '{event_summary}' within 3 days (score +30)")
                        elif time_diff <= 7 * 24 * 3600:  # Within 1 week
                            score += 20
                            logging.debug(f"Event '{event_summary}' within 1 week (score +20)")
                        elif time_diff <= 14 * 24 * 3600:  # Within 2 weeks
                            score += 10
                            logging.debug(f"Event '{event_summary}' within 2 weeks (score +10)")
                    except:
                        pass
            
            # Strategy 5: Location similarity (bonus)
            if parsed_event.location and event_location:
                loc_lower = parsed_event.location.lower()
                event_loc_lower = event_location.lower()
                if loc_lower in event_loc_lower or event_loc_lower in loc_lower:
                    score += 15
                    logging.debug(f"Event '{event_summary}' location match (score +15)")
            
            # Only consider events with score > threshold
            if score >= 50:  # Minimum threshold for matching
                matches.append((event_id, event_summary, score))
                logging.info(f"Potential match: '{event_summary}' with score {score}")
        
        # Select best match
        if matches:
            matches.sort(key=lambda x: -x[2])  # Sort by score descending
            best_id, best_summary, best_score = matches[0]
            logging.info(f"✅ Best match: '{best_summary}' (score={best_score})")
            
            if len(matches) > 1:
                logging.info(f"   Other matches: {[(m[1][:40], m[2]) for m in matches[1:3]]}")
            
            return best_id
        
        logging.info("No matching existing event found (no scores above threshold)")
        return None
        
    except Exception as e:
        logging.error(f"Error searching for existing event: {e}")
        return None

def handle_event_update(calendar, categories: Categories, parsed_event: ParsedEvent, msg_id: str, state: StateStore) -> MessageEventMap:
    """Handle updates to existing calendar events"""
    cfg = state.load_settings()
    prefix = cfg.get("calendar_prefix", "Journal Club – ")
    cal_map = state.load_calendar_map() or {}
    
    logging.info(f"Handling event update: {parsed_event.email_type}")
    logging.info(f"Original event reference: {parsed_event.original_event_ref}")
    
    # Determine which calendars to update based on the original event reference
    # For now, we'll update all calendars, but this could be made more sophisticated
    target_summaries = []
    for cat in categories.categories:
        target_summaries.append(_calendar_summary_for_category(prefix, cat.name))
    
    if categories.fallback_category:
        target_summaries.append(_calendar_summary_for_category(prefix, categories.fallback_category))
    
    mapping: Dict[str, str] = {}
    
    for summary in target_summaries:
        cal_id = cal_map.get(summary)
        if not cal_id:
            logging.warning(f"Calendar not found: {summary}")
            continue
        
        # Find the existing event
        existing_event_id = find_existing_event(calendar, cal_id, parsed_event, state)
        
        if existing_event_id:
            if parsed_event.email_type == "cancellation":
                # Delete the event
                try:
                    calendar.events().delete(calendarId=cal_id, eventId=existing_event_id).execute()
                    logging.info(f"Deleted cancelled event: {existing_event_id}")
                    mapping[summary] = existing_event_id  # Track the deleted event
                except Exception as e:
                    logging.error(f"Error deleting event: {e}")
            else:
                # Update the event
                try:
                    # Get the existing event
                    existing_event = calendar.events().get(calendarId=cal_id, eventId=existing_event_id).execute()
                    
                    # Update the event with new information
                    body = _build_event_body(parsed_event, msg_id)
                    
                    # Preserve some original information if not provided in update
                    if not parsed_event.title or parsed_event.title == "Journal Club":
                        body["summary"] = existing_event.get("summary", "Journal Club")
                    if not parsed_event.location:
                        body["location"] = existing_event.get("location", "")
                    
                    updated = calendar.events().update(
                        calendarId=cal_id, 
                        eventId=existing_event_id, 
                        body=body
                    ).execute()
                    
                    mapping[summary] = updated["id"]
                    logging.info(f"Updated existing event: {updated.get('htmlLink', 'no link')}")
                    
                except Exception as e:
                    logging.error(f"Error updating event: {e}")
        else:
            logging.info(f"No existing event found to update in calendar: {summary}")
    
    return MessageEventMap(message_id=msg_id, category_to_event_ids=mapping)

def upsert_event_to_calendars(calendar, categories: Categories, category_names: List[str], pe: ParsedEvent, msg_id: str, state: StateStore) -> MessageEventMap:
    cfg = state.load_settings()
    prefix = cfg.get("calendar_prefix", "Journal Club – ")
    cal_map = state.load_calendar_map() or {}
    mapping: Dict[str, str] = {}
    target_summaries = [_calendar_summary_for_category(prefix, c) for c in category_names]

    logging.info(f"Creating/updating event: '{pe.title}' for categories: {category_names}")
    logging.info(f"Event time: {pe.start} to {pe.end}")
    logging.info(f"Speaker: {pe.speaker}, Location: {pe.location}")
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

        # First check if this message already created an event
        q = calendar.events().list(calendarId=cal_id, privateExtendedProperty=f"source_msg_id={msg_id}", maxResults=1).execute()
        items = q.get("items", [])
        
        if items:
            # This exact message already created an event - update it
            ev_id = items[0]["id"]
            logging.info(f"Updating event from same message: {ev_id}")
            body = _build_event_body(pe, msg_id)
            updated = calendar.events().update(calendarId=cal_id, eventId=ev_id, body=body).execute()
            mapping[summary] = updated["id"]
            logging.info(f"Updated event: {updated.get('htmlLink', 'no link')}")
        else:
            # Check if this might be a duplicate of an existing event (even if email_type is "new")
            # This prevents duplicates when the same event is announced multiple times
            existing_event_id = find_existing_event(calendar, cal_id, pe, state)
            
            if existing_event_id:
                logging.info(f"Found potential duplicate event: {existing_event_id}")
                logging.info(f"Updating existing event instead of creating new one")
                
                # Get existing event to preserve some info
                existing_event = calendar.events().get(calendarId=cal_id, eventId=existing_event_id).execute()
                body = _build_event_body(pe, msg_id)
                
                # Update the event
                updated = calendar.events().update(calendarId=cal_id, eventId=existing_event_id, body=body).execute()
                mapping[summary] = updated["id"]
                logging.info(f"Updated existing event: {updated.get('htmlLink', 'no link')}")
            else:
                # Create new event
                logging.info(f"Creating new event in calendar: {summary}")
                body = _build_event_body(pe, msg_id)
                
                # Log event details
                start_time = body.get("start", {}).get("dateTime", "no time")
                end_time = body.get("end", {}).get("dateTime", "no time")
                logging.info(f"Event scheduled: {start_time} to {end_time}")
                
                created = calendar.events().insert(calendarId=cal_id, body=body).execute()
                mapping[summary] = created["id"]
                logging.info(f"Created new event: {created.get('htmlLink', 'no link')}")

    return MessageEventMap(message_id=msg_id, category_to_event_ids=mapping)

def delete_event_from_calendars(calendar, mapping: MessageEventMap) -> None:
    # No-op here; deletion would require storing calendar IDs alongside event IDs.
    pass