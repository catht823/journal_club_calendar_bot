import re
import logging
from datetime import timedelta, datetime
from typing import Optional, Tuple, List, Dict
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
    """Enhanced field extraction with multiple patterns"""
    for p in prefixes:
        # Try different patterns for field extraction
        patterns = [
            rf"{re.escape(p)}\\s*[:\\-]\\s*(.+?)(?:\\n|$)",  # Field: Value
            rf"{re.escape(p)}\\s*[:\\-]\\s*(.+?)(?=\\n[A-Z]|$)",  # Field: Value (until next field)
            rf"{re.escape(p)}\\s*[:\\-]\\s*(.+?)(?=\\n\\n|$)",  # Field: Value (until double newline)
            rf"{re.escape(p)}\\s*[:\\-]\\s*(.+?)(?=\\n(?:Title|Speaker|Location|Date|Time|Abstract|Summary|Description)|$)",  # Until next known field
            rf"{re.escape(p)}\\s*[:\\-]\\s*(.+?)(?=\\n\\d|$)",  # Until next line starting with number
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if m:
                value = m.group(1).strip()
                # Clean up the value
                value = re.sub(r'\\s+', ' ', value)  # Normalize whitespace
                value = value.strip('.,;:')  # Remove trailing punctuation
                if value and len(value) > 2:  # Avoid very short matches
                    return value
    return None

def _clean_title_punctuation(title: str) -> str:
    """Remove punctuation marks from the start and end of a title"""
    if not title:
        return title
    
    # Define punctuation marks to remove from start and end (including whitespace)
    punctuation_chars = set('*"\'`~!@#$%^&()_+={}[]|\\:;"<>?,./- \t\n\r')
    
    # Remove punctuation from start (including quotes)
    while title and title[0] in punctuation_chars:
        title = title[1:]
    
    # Remove punctuation from end (including quotes)
    while title and title[-1] in punctuation_chars:
        title = title[:-1]
    
    # Remove leading/trailing whitespace
    title = title.strip()
    
    logging.info(f"Final cleaned title: '{title}'")
    return title

def _extract_title(text: str, subject: str) -> str:
    """Extract talk title with multiple strategies, prioritizing actual talk titles over email subjects"""
    
    # Strategy 1: Look for explicit title fields (highest priority)
    title = _extract_line(["Title", "Topic", "Subject", "Talk", "Presentation", "Seminar", "Talk Title", "Presentation Title"], text)
    if title and len(title) > 5:
        logging.info(f"Found explicit title field: '{title}'")
        return title

    # Strategy 2: Look for talk/presentation patterns
    talk_patterns = [
        r'(?:title|topic|subject|talk|presentation|seminar)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
        r'(?:talk|presentation|seminar)\\s+(?:title|about)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
        r'(?:presented by|by)\\s+(.+?)(?:\\n|$)',
        r'(?:speaker|presenter)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
        r'(?:will present|presents|will give|gives)\\s+(?:a talk on|a presentation on|about)\\s+(.+?)(?:\\n|$)',
        r'(?:discussing|covering|about)\\s+(.+?)(?:\\n|$)',
        # Look for seminar series titles (often in caps)
        r'(?:seminar series|guest|speaker)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
        r'(?:igc|igm|igem)\\s+(?:seminar|series)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
    ]

    for pattern in talk_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        if matches:
            title = matches[0].strip()
            # Clean up the title
            title = re.sub(r'^(?:a|an|the)\\s+', '', title, flags=re.IGNORECASE)  # Remove articles
            title = title.strip('.,;:')  # Remove trailing punctuation
            if len(title) > 5 and len(title) < 200:  # Reasonable title length
                logging.info(f"Found talk pattern title: '{title}'")
                return title

    # Strategy 3: Look for quoted titles or titles in quotes (but avoid speaker names and email addresses)
    quoted_patterns = [
        r'["\']([^"\']{15,200})["\']',  # Text in quotes (longer to avoid names)
        r'"(.*?)"',  # Text in double quotes
        r"'(.*?)'",  # Text in single quotes
    ]
    
    for pattern in quoted_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            match = match.strip()
            # Skip if it looks like a speaker name, email address, or metadata
            if (len(match) > 15 and len(match) < 200 and 
                not re.match(r'^[A-Z][a-z]+,\s*[A-Z][a-z]+$', match) and  # "Last, First" pattern
                not re.match(r'^(?:dr|prof|professor)\s+[a-z\s]+$', match, re.IGNORECASE) and  # "Dr. Name" pattern
                not re.match(r'^[a-z\s]+$', match) and  # All lowercase (likely a name)
                not re.search(r'(?:speaker|presenter|presented by)', match, re.IGNORECASE) and  # Contains speaker keywords
                not re.search(r'@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', match) and  # Contains email addresses
                not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', match) and  # Is an email address
                not re.search(r'(?:via|from|to|cc|bcc|sent|received)', match, re.IGNORECASE) and  # Contains email headers
                not re.search(r'<[^>]*@[^>]*>', match) and  # Contains email in angle brackets
                not re.match(r'^[a-zA-Z0-9@._-]+$', match)):  # Just metadata characters
                
                # Clean up the title by removing header prefixes and punctuation
                cleaned_title = match
                # Remove patterns like "*Title:*", "*Seminar Title:*", "*Topic:*", etc.
                cleaned_title = re.sub(r'^\*?(?:title|topic|subject|talk|presentation|seminar\s+title)\s*[:*]\s*', '', cleaned_title, flags=re.IGNORECASE)
                # Remove quotes if they wrap the entire title or are at the start/end
                cleaned_title = re.sub(r'^["\'](.+)["\']$', r'\1', cleaned_title)  # Full wrapping quotes
                cleaned_title = re.sub(r'^["\']', '', cleaned_title)  # Leading quotes
                cleaned_title = re.sub(r'["\']$', '', cleaned_title)  # Trailing quotes
                # Apply generalized punctuation cleaning
                cleaned_title = _clean_title_punctuation(cleaned_title)
                
                if cleaned_title and len(cleaned_title) > 5:
                    logging.info(f"Found quoted title: '{cleaned_title}'")
                    return cleaned_title

    # Strategy 4: Look for lines that look like talk titles (often in caps or specific format)
    lines = text.split('\n')
    for i, line in enumerate(lines[:20]):  # Check first 20 lines
        line = line.strip()
        
        # Skip email headers and common non-title patterns
        if (len(line) > 15 and len(line) < 200 and 
            not re.match(r'^(?:from|to|date|subject|cc|bcc|sent|received|message-id|x-|return-path|reply-to)', line, re.IGNORECASE) and
            not re.match(r'^\d{4}-\d{2}-\d{2}', line) and  # Skip date lines
            not re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}', line) and  # Skip date lines
            not re.match(r'^\d{1,2}-\d{1,2}-\d{2,4}', line) and  # Skip date lines with dashes
            not '-----Original Message-----' in line and
            not 'Begin forwarded message' in line and
            not 'On .* wrote:' in line and
            not re.match(r'^(?:dear|hello|hi|greetings)', line, re.IGNORECASE) and  # Skip greetings
            not re.match(r'^(?:thank you|thanks|regards|best)', line, re.IGNORECASE) and  # Skip closings
            not re.match(r'^(?:please join|join us|you are invited|invitation|seminar announcement)', line, re.IGNORECASE) and  # Skip invitations
            not re.match(r'^(?:upcoming|this week|next week|reminder)', line, re.IGNORECASE) and  # Skip announcements
            not re.match(r'^(?:the school of|department of|center for)', line, re.IGNORECASE) and  # Skip institutional names
            not re.match(r'^(?:we are pleased|it is our pleasure|we invite)', line, re.IGNORECASE) and  # Skip formal invitations
            not re.match(r'^(?:date|time|when|where|location)', line, re.IGNORECASE) and  # Skip date/time headers
            not re.match(r'^\*?(?:location|where|venue|place)\s*[:*]', line, re.IGNORECASE) and  # Skip location lines (with or without asterisk)
            not re.match(r'^\*?(?:speaker|presenter|presented by|by)\s*[:*]', line, re.IGNORECASE) and  # Skip speaker lines
            not re.match(r'^\*?(?:title|topic|subject|talk|presentation|seminar)\s*[:*]', line, re.IGNORECASE) and  # Skip title header lines
            not re.match(r'^\*?(?:date|time|when|schedule)\s*[:*]', line, re.IGNORECASE) and  # Skip date/time header lines
            not re.match(r'^\*?(?:abstract|summary|description)\s*[:*]', line, re.IGNORECASE) and  # Skip abstract header lines
            not re.match(r'^\*?(?:contact|email|phone|website|url)\s*[:*]', line, re.IGNORECASE) and  # Skip contact header lines
            not re.match(r'^\*?(?:host|organizer|coordinator)\s*[:*]', line, re.IGNORECASE) and  # Skip host header lines
            not re.match(r'^\*?(?:zoom|meeting|link|join)\s*[:*]', line, re.IGNORECASE) and  # Skip meeting link lines
            not re.search(r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)', line, re.IGNORECASE) and  # Skip lines with day names
            not re.search(r'(?:january|february|march|april|may|june|july|august|september|october|november|december)', line, re.IGNORECASE) and  # Skip lines with month names
            not re.search(r'\d{1,2}:\d{2}', line) and  # Skip lines with time patterns
            not re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', line) and  # Skip lines with date patterns
            not re.search(r'\d{4}-\d{2}-\d{2}', line) and  # Skip lines with ISO date patterns
            not re.match(r'^[A-Z][a-z]+,\s*[A-Z][a-z]+$', line) and  # Skip "Last, First" names
            not re.match(r'^(?:dr|prof|professor)\s+[a-z\s]+$', line, re.IGNORECASE) and  # Skip "Dr. Name" patterns
            not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', line) and  # Skip email addresses
            not re.match(r'^[a-zA-Z0-9@._-]+$', line) and  # Skip lines that are just metadata characters
            not re.search(r'@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line) and  # Skip lines containing email addresses
            not re.match(r'^(?:fwd|fw|re|fyi)', line, re.IGNORECASE)):  # Skip forwarding prefixes
            
            # Prioritize lines that look like actual talk titles
            if (re.match(r'^[A-Z][^.!?]*[A-Z]', line) or  # Title case pattern (starts with capital, has another capital)
                re.search(r'(?:seminar|talk|presentation|guest|lecture)', line, re.IGNORECASE) or  # Contains seminar keywords
                (len(line.split()) >= 4 and len(line.split()) <= 15 and  # Multi-word but not too long
                 not re.search(r'(?:will|would|should|could|can|may|might|please|join|invite)', line, re.IGNORECASE) and  # Not a sentence with modal verbs
                 not re.search(r'(?:the school|department|center|university)', line, re.IGNORECASE))):  # Not institutional text
                
                       # Check if this might be a multi-line title by looking at the next line
                       potential_title = line
                       if i + 1 < len(lines):
                           next_line = lines[i + 1].strip()
                           # If next line looks like a continuation (starts with lowercase, no punctuation ending, etc.)
                           if (next_line and len(next_line) > 5 and len(next_line) < 100 and
                               not re.search(r'^\d+:\d+', next_line) and  # Not a time
                               not re.search(r'^\d{1,2}/\d{1,2}/\d{2,4}', next_line) and  # Not a date
                               not re.match(r'^[A-Z][a-z]+,\s*[A-Z][a-z]+$', next_line) and  # Not a name
                               not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', next_line) and  # Not an email
                               not re.search(r'@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', next_line) and  # Not containing email
                               not re.match(r'^(?:fwd|fw|re|fyi)', next_line, re.IGNORECASE) and  # Not forwarding
                               (next_line[0].islower() or  # Starts with lowercase (continuation)
                                re.match(r'^[A-Z][a-z]+', next_line))):  # Or starts with proper case
                               potential_title = line + " " + next_line
                               logging.info(f"Combined multi-line title: '{potential_title}'")
                       
                       # Clean up the title by removing header prefixes and punctuation
                       cleaned_title = potential_title
                       # Remove patterns like "*Title:*", "*Seminar Title:*", "*Topic:*", etc.
                       cleaned_title = re.sub(r'^\*?(?:title|topic|subject|talk|presentation|seminar\s+title)\s*[:*]\s*', '', cleaned_title, flags=re.IGNORECASE)
                       # Remove quotes if they wrap the entire title or are at the start/end
                       cleaned_title = re.sub(r'^["\'](.+)["\']$', r'\1', cleaned_title)  # Full wrapping quotes
                       cleaned_title = re.sub(r'^["\']', '', cleaned_title)  # Leading quotes
                       cleaned_title = re.sub(r'["\']$', '', cleaned_title)  # Trailing quotes
                       # Apply generalized punctuation cleaning
                       logging.info(f"Before punctuation cleaning: '{cleaned_title}'")
                       cleaned_title = _clean_title_punctuation(cleaned_title)
                       logging.info(f"After punctuation cleaning: '{cleaned_title}'")
                       logging.info(f"Final cleaned title length: {len(cleaned_title)}")
                       
                       if cleaned_title and len(cleaned_title) > 5:
                           logging.info(f"Found substantial line title: '{cleaned_title}'")
                           return cleaned_title

    # Strategy 5: Use subject line as fallback (but clean it up)
    if subject and len(subject) > 5 and len(subject) < 200:
        # Clean up subject - remove common email prefixes
        clean_subject = re.sub(r'^(?:re|fw|fwd|fyi)\\s*[:\\-]\\s*', '', subject, flags=re.IGNORECASE)
        clean_subject = re.sub(r'^(?:journal club|seminar|talk)\\s*[:\\-]\\s*', '', clean_subject, flags=re.IGNORECASE)
        # Apply generalized punctuation cleaning
        clean_subject = _clean_title_punctuation(clean_subject)
        if len(clean_subject) > 5:
            logging.info(f"Using cleaned subject as title: '{clean_subject}'")
            return clean_subject

    # Strategy 6: Default fallback
    logging.info("No title found, using default")
    return "Journal Club"

def _extract_speaker(text: str) -> Optional[str]:
    """Extract speaker with multiple strategies"""
    # Strategy 1: Look for explicit speaker fields
    speaker = _extract_line(["Speaker", "Presenter", "Presented by", "By", "Presented", "Given by"], text)
    if speaker:
        return speaker
    
    # Strategy 2: Look for patterns
    patterns = [
        r'(?:speaker|presenter|presented by|by)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
        r'(?:dr\\.?|prof\\.?|professor)\\s+([a-z\\s]+?)(?:\\n|$)',  # Dr. Name or Prof. Name
        r'([a-z\\s]+?)\\s+(?:will present|presents|will give|gives)',  # Name will present
        r'(?:presented by|given by)\\s+([a-z\\s]+?)(?:\\n|$)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        if matches:
            speaker = matches[0].strip()
            if len(speaker) > 2 and len(speaker) < 100:
                return speaker
    
    return None

def _extract_date(text: str, tz: str) -> Optional[datetime]:
    """Extract date information only (no time) from text"""
    
    # Split text into lines and focus on content lines (not email headers)
    lines = text.split('\n')
    content_lines = []
    
    for line in lines:
        line = line.strip()
        # Skip lines that look like email headers/metadata
        if (not line or 
            re.match(r'^(from|to|cc|bcc|subject|date|sent|received|message-id|x-|return-path)', line, re.IGNORECASE) or
            re.match(r'^\d{4}-\d{2}-\d{2}', line) or  # ISO date lines
            re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}', line) or  # Date lines
            '-----Original Message-----' in line or
            'Begin forwarded message' in line or
            'On .* wrote:' in line):
            continue
        content_lines.append(line)
    
    # Focus on the actual content
    content_text = '\n'.join(content_lines)
    
    # Date-only patterns (no time) - ordered by specificity
    date_patterns = [
        # Pattern for "*Date: *Wednesday, September 24, 2025 10:00 AM" format (with asterisks, includes time)
        r'\*date:\s*\*((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)[,\s]*(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?[,\s]+\d{4}\s+\d{1,2}:\d{2}(?:\s*[AP]M)?)',
        
        # Pattern for "*Date: *Wednesday, September 24, 2025" format (with asterisks, no time)
        r'\*date:\s*\*((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)[,\s]*(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?[,\s]+\d{4})',
        
        # Month + day + year patterns (no weekday, no time)
        r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?[,\s]+\d{4}',
        
        # Pattern for "September 24th" format (no year, no time)
        r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?',
        
        # Patterns for specific date formats found in emails - exact matches (no time)
        r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)[,\s]+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?[,\s]+\d{4}',
        r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?[,\s]+\d{4}',
        
        # Patterns for the exact formats found in the emails (no time)
        r'(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)[,\s]+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?',
        r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?',
        
        # Numeric date patterns (without time)
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})',
        
        # Relative dates (only as last resort)
        r'(?:today|tomorrow|next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))',
        r'(?:this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))',
    ]
    
    # Try each date pattern
    for i, pattern in enumerate(date_patterns):
        matches = re.findall(pattern, content_text, re.IGNORECASE)
        if matches:
            logging.info(f"Date pattern {i+1} matched: {matches}")
        else:
            logging.debug(f"Date pattern {i+1} no match: {pattern[:50]}...")
        
        if matches:
            try:
                # Handle different match formats
                if isinstance(matches[0], tuple):
                    date_str = matches[0][0] if matches[0][0] else matches[0]
                else:
                    date_str = matches[0]
                
                parsed = dateparser.parse(date_str, settings={"TIMEZONE": tz, "RETURN_AS_TIMEZONE_AWARE": True})
                if parsed:
                    logging.info(f"Date pattern {i+1} matched: '{date_str}' -> {parsed}")
                    return parsed
            except Exception as e:
                logging.debug(f"Date pattern {i+1} failed to parse '{date_str}': {e}")
                continue
    
    return None

def _extract_time(text: str, tz: str) -> Optional[datetime]:
    """Extract time information only (no date) from text"""
    
    # Split text into lines and focus on content lines (not email headers)
    lines = text.split('\n')
    content_lines = []
    
    for line in lines:
        line = line.strip()
        # Skip lines that look like email headers/metadata
        if (not line or 
            re.match(r'^(from|to|cc|bcc|subject|date|sent|received|message-id|x-|return-path)', line, re.IGNORECASE) or
            re.match(r'^\d{4}-\d{2}-\d{2}', line) or  # ISO date lines
            re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}', line) or  # Date lines
            '-----Original Message-----' in line or
            'Begin forwarded message' in line or
            'On .* wrote:' in line):
            continue
        content_lines.append(line)
    
    # Focus on the actual content
    content_text = '\n'.join(content_lines)
    
    # Time-only patterns - ordered by specificity
    time_patterns = [
        # Time patterns with AM/PM
        r'(\d{1,2}:\d{2}(?:\s*[AP]M))',
        r'(\d{1,2}(?:\s*[AP]M))',
        
        # 24-hour time patterns
        r'(\d{1,2}:\d{2})',
        
        # Time with context words
        r'(?:at\s+)(\d{1,2}:\d{2}(?:\s*[AP]M)?)',
        r'(?:time:\s*)(\d{1,2}:\d{2}(?:\s*[AP]M)?)',
    ]
    
    # Try each time pattern
    for i, pattern in enumerate(time_patterns):
        matches = re.findall(pattern, content_text, re.IGNORECASE)
        if matches:
            logging.info(f"Time pattern {i+1} matched: {matches}")
        else:
            logging.debug(f"Time pattern {i+1} no match: {pattern[:50]}...")
        
        if matches:
            try:
                # Handle different match formats
                if isinstance(matches[0], tuple):
                    time_str = matches[0][0] if matches[0][0] else matches[0]
                else:
                    time_str = matches[0]
                
                # Parse time and set to today's date
                parsed = dateparser.parse(time_str, settings={"TIMEZONE": tz, "RETURN_AS_TIMEZONE_AWARE": True})
                if parsed:
                    logging.info(f"Time pattern {i+1} matched: '{time_str}' -> {parsed}")
                    return parsed
            except Exception as e:
                logging.debug(f"Time pattern {i+1} failed to parse '{time_str}': {e}")
                continue
    
    return None

def _extract_datetime(text: str, tz: str) -> Optional[datetime]:
    """Extract datetime by combining separate date and time extraction processes"""
    
    # Log the content for debugging
    logging.info(f"Content text for datetime parsing (first 500 chars): {text[:500]}")
    logging.info(f"Content text length: {len(text)}")
    
    # Run date and time extraction in parallel (separate processes)
    date_result = _extract_date(text, tz)
    time_result = _extract_time(text, tz)
    
    logging.info(f"Date extraction result: {date_result}")
    logging.info(f"Time extraction result: {time_result}")
    
    # Combine results
    if date_result and time_result:
        # Both date and time found - combine them
        combined = date_result.replace(hour=time_result.hour, minute=time_result.minute, second=time_result.second, microsecond=time_result.microsecond)
        logging.info(f"Combined date and time: {combined}")
        return combined
    elif date_result:
        # Only date found - use default time (2 PM)
        default_time = date_result.replace(hour=14, minute=0, second=0, microsecond=0)
        logging.info(f"Date only found, using default time: {default_time}")
        return default_time
    elif time_result:
        # Only time found - use today's date
        logging.info(f"Time only found, using today's date: {time_result}")
        return time_result
    else:
        # Neither found
        logging.info("No date or time found")
        return None

def _clean_email_content(text: str) -> str:
    """Remove email forwarding headers and metadata to focus on actual content"""
    
    # Split into lines for more precise cleaning
    lines = text.split('\n')
    cleaned_lines = []
    
    # Skip lines that look like email headers/metadata
    skip_patterns = [
        r'^(from|to|cc|bcc|subject|date|sent|received|message-id|x-|return-path|reply-to|mime-version|content-type|content-transfer-encoding)',
        r'^\s*(from|to|cc|bcc|subject|date|sent|received|message-id|x-|return-path|reply-to|mime-version|content-type|content-transfer-encoding)',
        r'^\d{4}-\d{2}-\d{2}',  # ISO date lines
        r'^\d{1,2}/\d{1,2}/\d{2,4}',  # Date lines
        r'^\d{1,2}-\d{1,2}-\d{2,4}',  # Date lines with dashes
        r'^\s*\d{4}-\d{2}-\d{2}',  # ISO date lines with whitespace
        r'^\s*\d{1,2}/\d{1,2}/\d{2,4}',  # Date lines with whitespace
        r'^\s*\d{1,2}-\d{1,2}-\d{2,4}',  # Date lines with dashes and whitespace
        r'-----Original Message-----',
        r'Begin forwarded message',
        r'On .* wrote:',
        r'From:',
        r'To:',
        r'Subject:',
        r'Date:',
        r'Sent:',
        r'Received:',
        r'Message-ID:',
        r'In-Reply-To:',
        r'References:',
        r'X-',
        r'Return-Path:',
        r'Reply-To:',
        r'MIME-Version:',
        r'Content-Type:',
        r'Content-Transfer-Encoding:',
        r'---------- Forwarded message ---------',  # Forwarded message header
        r'---------- Forwarded message ----------',  # Forwarded message header with extra dash
        r'---------- Forwarded Message ---------',  # Forwarded message header capitalized
        r'---------- Forwarded Message ----------',  # Forwarded message header capitalized with extra dash
        r'---------- Forwarded message',  # Partial forwarded message header
        r'---------- Forwarded Message',  # Partial forwarded message header capitalized
        r'^----------.*----------$',  # Any line that starts and ends with dashes
        r'^----------.*$',  # Any line that starts with dashes
        r'^.*----------$',  # Any line that ends with dashes
    ]
    
    # Also skip lines that are just email addresses
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
            
        # Skip lines matching email header patterns
        skip_line = False
        for pattern in skip_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                skip_line = True
                break
        
        # Skip lines that are just email addresses
        if not skip_line and re.match(email_pattern, line):
            skip_line = True
            
        # Skip lines that are very short and look like metadata
        if not skip_line and len(line) < 5 and re.match(r'^[a-zA-Z0-9@._-]+$', line):
            skip_line = True
            
        # Skip lines that are mostly dashes or special characters
        if not skip_line and re.match(r'^[-=_*#]+$', line):
            skip_line = True
            
        if not skip_line:
            cleaned_lines.append(line)
    
    # Join lines and clean up whitespace
    cleaned = '\n'.join(cleaned_lines)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)  # Multiple newlines to double
    cleaned = re.sub(r'^\s+', '', cleaned, flags=re.MULTILINE)  # Leading whitespace
    
    return cleaned.strip()

def parse_event_from_text(subject: str, body_text: str, html: Optional[str], settings_path: Path, attachments: Optional[List[Dict[str, str]]] = None) -> Optional[ParsedEvent]:
    cfg = _load_settings(settings_path)
    tz = cfg.get("timezone", "America/Los_Angeles")
    default_minutes = int(cfg.get("default_duration_minutes", 60))

    # Clean the email content to remove forwarding headers
    raw_content = "\n".join([subject, body_text or "", _html_to_text(html) or ""]).strip()
    combined = _clean_email_content(raw_content)
    
    if not combined:
        return None

    logging.info(f"Parsing email: '{subject[:50]}...'")
    logging.info(f"Raw content length: {len(raw_content)}, Cleaned: {len(combined)}")

    cancelled = bool(re.search(r"cancelled|canceled|postponed", combined, flags=re.IGNORECASE))

    # Use enhanced datetime extraction
    start = _extract_datetime(combined, tz)
    
    # If no datetime found, try fallback methods
    if not start:
        try:
            start = dateparser.parse(combined, settings={"TIMEZONE": tz, "RETURN_AS_TIMEZONE_AWARE": True})
            if start:
                logging.info(f"Fallback dateparser found: {start}")
        except (RecursionError, Exception) as e:
            logging.warning(f"Dateparser failed on text (length: {len(combined)}): {str(e)[:100]}...")
            start = None
    
    if not start:
        logging.warning("No date/time found in email, trying fallback strategies")
        
        # Fallback: Try to extract just a date and use a default time
        fallback_patterns = [
            r'(?:today|tomorrow)',
            r'(?:next\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))',
            r'(?:this\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))',
            r'\\d{1,2}[/-]\\d{1,2}',  # Just month/day
        ]
        
        for pattern in fallback_patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            if matches:
                try:
                    fallback_date = dateparser.parse(matches[0], settings={"TIMEZONE": tz, "RETURN_AS_TIMEZONE_AWARE": True})
                    if fallback_date:
                        # Set to a reasonable default time (e.g., 2 PM)
                        start = fallback_date.replace(hour=14, minute=0, second=0, microsecond=0)
                        logging.info(f"Fallback date found: {matches[0]} -> {start}")
                        break
                except:
                    continue
        
        # If still no date, create a placeholder event for today
        if not start:
            from datetime import datetime
            start = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
            logging.warning(f"No date found, using placeholder: {start}")
    
    if not start:
        logging.error("Failed to extract any date/time information")
        return None

    # Set end time
    end = start + timedelta(minutes=default_minutes)

    # Extract fields using enhanced methods
    title = _extract_title(combined, subject)
    speaker = _extract_speaker(combined)
    location = _extract_line(["Location", "Where", "Room", "Venue", "Place", "Address"], combined)
    url = _extract_line(["Zoom", "Link", "Meeting", "URL", "Join", "Webinar", "Webex", "Teams"], combined)
    abstract = _extract_line(["Abstract", "Summary", "Description", "Overview"], combined)

    logging.info(f"Final extracted fields:")
    logging.info(f"  Title: '{title}'")
    logging.info(f"  Speaker: '{speaker}'")
    logging.info(f"  Location: '{location}'")
    logging.info(f"  URL: '{url}'")
    logging.info(f"  Abstract: '{abstract[:100] if abstract else 'None'}...'")

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
        attachments=attachments,
    )