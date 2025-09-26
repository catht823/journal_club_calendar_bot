import argparse
import logging
import os
from pathlib import Path

from journal_club_bot.auth import get_authorized_services
from journal_club_bot.gmail_client import fetch_labeled_messages, extract_message_payload
from journal_club_bot.parser import parse_event_from_text
from journal_club_bot.categorizer import load_categories, categorize_text
from journal_club_bot.calendar_client import (
    ensure_category_calendars,
    upsert_event_to_calendars,
    delete_event_from_calendars,
)
from journal_club_bot.storage import StateStore, MessageEventMap

def setup_logging() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

def run_once() -> None:
    setup_logging()
    Path("tokens").mkdir(parents=True, exist_ok=True)
    Path("state").mkdir(parents=True, exist_ok=True)
    Path("config").mkdir(parents=True, exist_ok=True)

    settings_path = Path("config/settings.yml")
    categories_path = Path("config/categories.yml")

    services = get_authorized_services()
    gmail = services.gmail
    calendar = services.calendar

    categories = load_categories(categories_path)
    state = StateStore("state")

    ensure_category_calendars(calendar, categories, state)

    messages = fetch_labeled_messages(gmail, settings_path, state)
    if not messages:
        logging.info("No new messages to process.")
        return

    for msg in messages:
        msg_id = msg["id"]
        if state.is_processed(msg_id):
            continue
        subject, body_text, html, attachments = extract_message_payload(gmail, msg_id)
        parsed = parse_event_from_text(subject, body_text, html, settings_path, attachments)
        if not parsed:
            state.mark_processed(msg_id, MessageEventMap(message_id=msg_id, category_to_event_ids={}))
            continue

        combined_text = f"{subject}\n\n{parsed.title}\n\n{parsed.abstract or ''}"
        category_names = categorize_text(categories, combined_text)
        if not category_names and categories.fallback_category:
            category_names = [categories.fallback_category]

        mapping = upsert_event_to_calendars(calendar, categories, category_names, parsed, msg_id, state)
        state.mark_processed(msg_id, mapping)

        if parsed.cancelled:
            delete_event_from_calendars(calendar, mapping)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--poll", action="store_true", help="Run once (for scheduler)")
    _ = parser.parse_args()
    run_once()

if __name__ == "__main__":
    main()