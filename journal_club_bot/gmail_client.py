import base64
from email.header import decode_header
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import os
import yaml

def _load_settings(settings_path: Path) -> dict:
    with open(settings_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if os.environ.get("JC_TIMEZONE"):
        cfg["timezone"] = os.environ["JC_TIMEZONE"]
    if os.environ.get("JC_SOURCE_LABEL"):
        cfg["source_label"] = os.environ["JC_SOURCE_LABEL"]
    if os.environ.get("JC_PROCESSED_LABEL"):
        cfg["processed_label"] = os.environ["JC_PROCESSED_LABEL"]
    if os.environ.get("JC_CAL_PREFIX"):
        cfg["calendar_prefix"] = os.environ["JC_CAL_PREFIX"]
    return cfg

def fetch_labeled_messages(gmail, settings_path: Path, state) -> List[Dict[str, Any]]:
    import logging
    cfg = _load_settings(settings_path)
    source_label = cfg.get("source_label", "buffer-label")
    lookback_days = int(cfg.get("lookback_days", 14))
    max_messages = int(cfg.get("max_messages", 50))
    
    if lookback_days > 0:
        query = f"label:{source_label} newer_than:{lookback_days}d"
    else:
        query = f"label:{source_label}"
    
    logging.info(f"Gmail query: {query}")
    logging.info(f"Searching for label: {source_label}, lookback_days: {lookback_days}")
    
    results = gmail.users().messages().list(userId="me", q=query, maxResults=max_messages).execute()
    messages = results.get("messages", [])
    logging.info(f"Found {len(messages)} messages")
    return messages

def _decode_subject(headers: List[Dict[str, str]]) -> str:
    subject_vals = [h["value"] for h in headers if h.get("name") == "Subject"]
    subject_raw = subject_vals[0] if subject_vals else ""
    decoded = decode_header(subject_raw)
    out = ""
    for text, enc in decoded:
        out += text.decode(enc or "utf-8", errors="replace") if isinstance(text, bytes) else text
    return out

def extract_message_payload(gmail, message_id: str) -> Tuple[str, str, Optional[str], List[Dict[str, str]]]:
    msg = gmail.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = msg["payload"].get("headers", [])
    subject = _decode_subject(headers)

    body_text = ""
    html = None
    attachments = []

    def walk_parts(part):
        nonlocal body_text, html, attachments
        mime = part.get("mimeType")
        data = part.get("body", {}).get("data")
        parts = part.get("parts")
        
        # Extract attachments
        if part.get("filename"):
            filename = part.get("filename")
            attachment_id = part.get("body", {}).get("attachmentId")
            if attachment_id:
                attachments.append({
                    "filename": filename,
                    "mimeType": mime,
                    "attachmentId": attachment_id,
                    "size": part.get("body", {}).get("size", 0)
                })
        
        if mime == "text/plain" and data:
            body_text += base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        elif mime == "text/html" and data:
            html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if parts:
            for p in parts:
                walk_parts(p)

    walk_parts(msg["payload"])
    return subject, body_text, html, attachments