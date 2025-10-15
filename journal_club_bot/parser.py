import re
import logging
from datetime import timedelta, datetime
from typing import Optional, Tuple, List, Dict, Any
import dateparser
from bs4 import BeautifulSoup
from pathlib import Path
import yaml
from .models import ParsedEvent

# Common academic/research keywords for scoring
ACADEMIC_KEYWORDS = [
    'mechanism', 'pathway', 'regulation', 'function', 'structure', 'dynamics',
    'interaction', 'signaling', 'cascade', 'network', 'system', 'process',
    'model', 'approach', 'method', 'technique', 'analysis', 'characterization',
    'identification', 'discovery', 'development', 'application', 'implication',
    'role', 'effect', 'impact', 'influence', 'contribution', 'advance',
    'progress', 'breakthrough', 'finding', 'result', 'outcome', 'neural',
    'brain', 'cognitive', 'molecular', 'cellular', 'genetic', 'protein',
    'cell', 'tissue', 'organ', 'disease', 'therapy', 'treatment', 'drug',
    'virus', 'bacteria', 'immune', 'cancer', 'tumor', 'metabolism', 'gene'
]

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

def _is_likely_title(text: str) -> bool:
    """Check if text is likely a title vs metadata"""
    if not text or len(text) < 5:
        return False
    
    # Reject if it's clearly not a title
    reject_patterns = [
        r'^\s*(?:from|to|date|subject|cc|bcc|sent|received)\\s*:',  # Email headers
        r'@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # Contains email
        r'^[A-Z][a-z]+,?\s+[A-Z][a-z]+$',  # Just a name
        r'^(?:dr|prof|professor)\\.?\\s+[a-z\s]+$',  # "Dr. Name"
        r'\\d{1,2}[:/]\\d{1,2}',  # Date/time patterns
        r'^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)',  # Day names
        r'^(?:january|february|march|april|may|june|july|august|september|october|november|december)',  # Month names
        r'^(?:location|room|building|hall|venue|place)\\s*:',  # Location fields
        r'^(?:when|where|time|date)\\s*:',  # Metadata fields
    ]
    
    for pattern in reject_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    
    return True

def _score_title_candidate(text: str) -> int:
    """Score a title candidate based on various heuristics"""
    score = 0
    words = text.split()
    word_count = len(words)
    
    # Ideal length: 4-15 words
    if 5 <= word_count <= 12:
        score += 30
    elif 4 <= word_count <= 15:
        score += 20
    elif 3 <= word_count <= 20:
        score += 10
    
    # Title case bonus
    if re.match(r'^[A-Z]', text):
        score += 15
    
    # Academic/research keywords
    text_lower = text.lower()
    keyword_count = sum(1 for kw in ACADEMIC_KEYWORDS if kw in text_lower)
    score += min(keyword_count * 10, 40)  # Cap at 40
    
    # Not a complete sentence (no verbs like "will", "please", "join")
    if not re.search(r'\\b(?:will|would|should|could|please|join|invite|we|you|us)\\b', text_lower):
        score += 10
    
    # Contains scientific/technical terms
    if re.search(r'\\b(?:via|through|during|using|based|novel|new|recent|current)\\b', text_lower):
        score += 5
    
    return score

def _extract_title(text: str, subject: str, html: Optional[str] = None) -> str:
    """
    Extract talk title using multi-strategy approach with intelligent scoring.
    Prioritizes: quotes, colons, bold/formatting, then contextual analysis.
    """
    candidates = []
    
    # Parse HTML for better structure detection
    soup = None
    if html:
        soup = BeautifulSoup(html, 'lxml')
    
    # === STRATEGY 1: Quoted Text (Score: 100) ===
    quote_patterns = [
        (r'"([^"]{8,300})"', 100),  # Double quotes
        (r"'([^']{8,300})'", 98),  # Single quotes
        (r'["""]([^"""]{8,300})["""]', 100),  # Smart double quotes
    ]
    
    for pattern, base_score in quote_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            title = match.group(1).strip()
            if _is_likely_title(title):
                score = base_score + _score_title_candidate(title)
                candidates.append((title, score, "quoted"))
    
    # === STRATEGY 2: Text After Colons (Score: 90-95) ===
    colon_patterns = [
        # "X will present a paper: TITLE"
        (r'(?:[A-Z][a-z]+\\s+[A-Z][a-z]+)\\s+(?:will present|presents|is presenting)\\s+(?:a\\s+)?(?:paper|talk|presentation)\\s*[:\\-]\\s*([^\\n]{8,300})', 95),
        # "will present: TITLE" or "presents: TITLE"
        (r'(?:will present|presents|presenting)\\s+(?:a\\s+)?(?:paper|talk|presentation|on)\\s*[:\\-]\\s*([^\\n]{8,300})', 94),
        # "Title: TITLE" or "Topic: TITLE"
        (r'(?:^|\\n)\\s*(?:title|topic|subject)\\s*[:\\-]\\s*([^\\n]{8,300})', 93),
        # "Talk/Seminar/Presentation Title: TITLE"
        (r'(?:talk|seminar|presentation|lecture)\\s+(?:title|topic)\\s*[:\\-]\\s*([^\\n]{8,300})', 92),
        # "entitled/titled: TITLE"
        (r'(?:entitled|titled)\\s*[:\\-]\\s*([^\\n]{8,300})', 91),
        # Generic "paper: TITLE", "talk: TITLE"
        (r'(?:paper|talk|presentation|seminar|lecture)\\s*[:\\-]\\s*([^\\n]{8,300})', 85),
    ]
    
    for pattern, base_score in colon_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            title = match.group(1).strip()
            # Remove leading articles
            title = re.sub(r'^(?:a|an|the)\\s+', '', title, flags=re.IGNORECASE)
            title = title.strip('.,;:')
            
            if _is_likely_title(title):
                score = base_score + _score_title_candidate(title)
                candidates.append((title, score, "colon"))
    
    # === STRATEGY 3: HTML Formatting (Score: 75-90) ===
    if soup:
        # Check for bold/strong tags
        for tag in soup.find_all(['b', 'strong']):
            title = tag.get_text(strip=True)
            if _is_likely_title(title) and len(title) >= 8:
                score = 85 + _score_title_candidate(title)
                candidates.append((title, score, "html_bold"))
        
        # Check for italic/em tags
        for tag in soup.find_all(['i', 'em']):
            title = tag.get_text(strip=True)
            if _is_likely_title(title) and len(title) >= 8:
                score = 80 + _score_title_candidate(title)
                candidates.append((title, score, "html_italic"))
        
        # Check for larger font sizes
        for tag in soup.find_all(style=re.compile(r'font-size\s*:\s*\d+p[tx]', re.IGNORECASE)):
            title = tag.get_text(strip=True)
            if _is_likely_title(title) and len(title) >= 8:
                score = 75 + _score_title_candidate(title)
                candidates.append((title, score, "html_font"))
    
    # === STRATEGY 4: Markdown Formatting (Score: 70-85) ===
    markdown_patterns = [
        (r'\\*\\*([^*]{8,300})\\*\\*', 85),  # **bold**
        (r'__([^_]{8,300})__', 85),  # __bold__
        (r'\\*([^*]{8,300})\\*', 80),  # *italic*
        (r'_([^_]{8,300})_', 80),  # _italic_
        (r'^#{1,3}\\s+(.{8,300})$', 90),  # # Header
    ]
    
    for pattern, base_score in markdown_patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            title = match.group(1).strip()
            if _is_likely_title(title):
                score = base_score + _score_title_candidate(title)
                candidates.append((title, score, "markdown"))
    
    # === STRATEGY 5: Line Analysis (Score: 40-70) ===
    lines = text.split('\\n')
    for i, line in enumerate(lines[:50]):  # Check first 50 lines
        line = line.strip()
        
        # Skip short lines and obvious non-titles
        if len(line) < 10 or len(line) > 300:
            continue
        
        # Skip header lines with colons (they're just field names)
        if re.match(r'^(?:title|speaker|location|time|date|when|where|abstract|summary)\\s*:', line, re.IGNORECASE):
            continue
        
        # Skip lines with common email patterns
        if re.search(r'(?:dear|hello|regards|sincerely|thank you|please join|you are invited)', line, re.IGNORECASE):
            continue
        
        if _is_likely_title(line):
            score = 50 + _score_title_candidate(line)
            
            # Bonus for position (earlier lines more likely)
            if i < 10:
                score += 10
            elif i < 20:
                score += 5
            
            candidates.append((line, score, "line_analysis"))
    
    # === STRATEGY 6: Subject Line (Score: 30-50) ===
    if subject and len(subject) > 5:
        clean_subject = subject
        # Remove common prefixes
        clean_subject = re.sub(r'^(?:re|fw|fwd|fyi)\\s*[:\\-]\\s*', '', clean_subject, flags=re.IGNORECASE)
        clean_subject = re.sub(r'^(?:journal club|seminar|talk|presentation|lecture|guest speaker|announcement)\\s*[:\\-]?\\s*', '', clean_subject, flags=re.IGNORECASE)
        # Remove date/time patterns
        clean_subject = re.sub(r'\\s*-\\s*\\d{1,2}/\\d{1,2}(/\\d{2,4})?', '', clean_subject)
        clean_subject = re.sub(r'\\s*\\d{1,2}/\\d{1,2}(/\\d{2,4})?\\s*-?\\s*', '', clean_subject)
        clean_subject = re.sub(r'\\s+', ' ', clean_subject).strip()
        
        if _is_likely_title(clean_subject) and len(clean_subject) > 5:
            score = 40 + _score_title_candidate(clean_subject)
            candidates.append((clean_subject, score, "subject"))
    
    # === FINAL SELECTION ===
    if candidates:
        # Remove duplicates (same text, different strategies)
        seen = {}
        for title, score, strategy in candidates:
            title_norm = re.sub(r'\\s+', ' ', title.lower().strip())
            if title_norm not in seen or seen[title_norm][1] < score:
                seen[title_norm] = (title, score, strategy)
        
        unique_candidates = list(seen.values())
        unique_candidates.sort(key=lambda x: (-x[1], -len(x[0])))
        
        best_title, best_score, best_strategy = unique_candidates[0]
        
        logging.info(f"✅ Selected title: '{best_title}' (score={best_score}, strategy={best_strategy})")
        if len(unique_candidates) > 1:
            logging.info(f"   Other candidates: {[(c[0][:40]+'...', c[1], c[2]) for c in unique_candidates[1:3]]}")
        
        return _clean_title_punctuation(best_title)
    
    # Ultimate fallback
    logging.warning("⚠️ No title found, using default")
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

def _extract_location(text: str) -> Optional[str]:
    """Extract location information with intelligent scoring and bracket handling"""
    
    # Collect all potential locations with scores
    candidates = []
    
    # Strategy 1: Look for explicit location fields (highest priority)
    explicit_locations = _extract_line(["Location", "Where", "Room", "Venue", "Place", "Address", "Building", "Hall", "Auditorium", "Conference Room", "Meeting Room"], text)
    if explicit_locations and len(explicit_locations) > 2:
        candidates.append((explicit_locations, 100))  # Highest score
    
    # Strategy 2: Look for location patterns throughout the entire text
    location_patterns = [
        r'(?:location|where|room|venue|place|address|building|hall|auditorium)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
        r'(?:at|in)\\s+(.+?)(?:\\s+(?:room|hall|building|auditorium|conference|meeting))',
        r'(?:room|hall|building|auditorium|conference|meeting)\\s+(?:number|#)?\\s*[:\\-]?\\s*(.+?)(?:\\n|$)',
        r'(?:zoom|meeting|webinar)\\s+(?:link|url|id)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',  # Virtual meetings
        r'(?:join|meeting)\\s+(?:us|the)\\s+(?:at|in)\\s+(.+?)(?:\\n|$)',
        r'(?:held|taking place|located)\\s+(?:at|in)\\s+(.+?)(?:\\n|$)',
    ]
    
    for pattern in location_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            location = match.strip()
            # Clean up the location
            location = re.sub(r'^(?:at|in)\\s+', '', location, flags=re.IGNORECASE)  # Remove leading prepositions
            location = location.strip('.,;:')  # Remove trailing punctuation
            
            # Handle brackets and abbreviations properly
            location = _clean_location_text(location)
            
            if len(location) > 2 and len(location) < 200:  # Reasonable location length
                score = 80
                if 'room' in pattern.lower() or 'building' in pattern.lower():
                    score += 10
                candidates.append((location, score))
    
    # Strategy 3: Look for common room/building patterns
    room_patterns = [
        r'(?:room|rm)\\s+(?:number|#)?\\s*[:\\-]?\\s*([a-z0-9\\-\\s]+?)(?:\\n|$)',  # Room 123, RM 456, etc.
        r'(?:building|bldg)\\s+(?:number|#)?\\s*[:\\-]?\\s*([a-z0-9\\-\\s]+?)(?:\\n|$)',  # Building A, Bldg 1, etc.
        r'(?:hall|auditorium)\\s+(?:number|#)?\\s*[:\\-]?\\s*([a-z0-9\\-\\s]+?)(?:\\n|$)',  # Hall 1, Auditorium A, etc.
        r'([a-z]+\\s+\\d+[a-z]?)(?:\\s+(?:room|hall|building|auditorium))?',  # Building names like "Price Center 123"
        r'(?:price center|student center|library|medical center|hospital)\\s+(?:room|hall|auditorium)?\\s*[:\\-]?\\s*([a-z0-9\\-\\s]+?)(?:\\n|$)',  # Common building names
    ]
    
    for pattern in room_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            location = match.strip()
            location = _clean_location_text(location)
            if len(location) > 1 and len(location) < 100:
                score = 70
                if any(word in location.lower() for word in ['room', 'hall', 'building', 'center', 'library']):
                    score += 15
                candidates.append((location, score))
    
    # Strategy 4: Look for virtual meeting indicators
    virtual_patterns = [
        r'(?:zoom|webex|teams|google meet|virtual)\\s+(?:meeting|link|url|id)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
        r'(?:meeting|webinar)\\s+(?:link|url|id)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
        r'(?:join|participate)\\s+(?:via|using)\\s+(?:zoom|webex|teams|google meet)\\s*[:\\-]\\s*(.+?)(?:\\n|$)',
    ]
    
    for pattern in virtual_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            location = match.strip()
            location = _clean_location_text(location)
            if len(location) > 5 and len(location) < 200:
                score = 60
                candidates.append((f"Virtual: {location}", score))
    
    # Strategy 5: Analyze all lines for location-like information
    lines = text.split('\n')
    for line in lines[:20]:  # Check first 20 lines
        line = line.strip()
        
        # Skip obvious non-location lines
        if (len(line) < 5 or len(line) > 150 or
            re.match(r'^(?:from|to|date|subject|cc|bcc|sent|received|message-id|x-|return-path)', line, re.IGNORECASE) or
            re.match(r'^\d{4}-\d{2}-\d{2}', line) or  # Skip date lines
            re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}', line) or  # Skip date lines
            re.search(r'\d{1,2}:\d{2}', line) or  # Skip lines with time patterns
            re.search(r'@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line) or  # Skip lines containing email addresses
            re.match(r'^(?:fwd|fw|re|fyi)', line, re.IGNORECASE)):  # Skip forwarding prefixes
            continue
            
        # Score this line as a potential location
        score = 0
        
        # Check for location keywords
        location_keywords = ['room', 'hall', 'building', 'auditorium', 'conference', 'meeting', 'center', 'library', 'hospital', 'medical', 'price', 'student', 'zoom', 'webex', 'teams', 'google meet', 'virtual']
        if any(word in line.lower() for word in location_keywords):
            score += 30
        
        # Check for room/building number patterns
        if re.search(r'(?:room|rm|hall|building|bldg)\\s*[#:]?\\s*\\d+', line, re.IGNORECASE):
            score += 25
        
        # Check for building name patterns
        if re.search(r'[a-z]+\\s+\\d+[a-z]?', line, re.IGNORECASE):
            score += 20
        
        # Check for virtual meeting patterns
        if re.search(r'(?:zoom|webex|teams|google meet|virtual)', line, re.IGNORECASE):
            score += 15
        
        if score > 20:  # Only consider if score is reasonable
            cleaned_line = _clean_location_text(line)
            if cleaned_line and len(cleaned_line) > 3:
                candidates.append((cleaned_line, score))
    
    # Final selection: Choose the highest scoring candidate
    if candidates:
        # Sort by score (highest first), then by length (prefer longer locations)
        candidates.sort(key=lambda x: (-x[1], -len(x[0])))
        best_location, best_score = candidates[0]
        
        logging.info(f"Selected location '{best_location}' with score {best_score} from {len(candidates)} candidates")
        if len(candidates) > 1:
            logging.info(f"Other candidates: {[(c[0][:50] + '...' if len(c[0]) > 50 else c[0], c[1]) for c in candidates[1:3]]}")
        
        return best_location
    
    return None

def _clean_location_text(location: str) -> str:
    """Clean location text by handling brackets, abbreviations, and common issues"""
    if not location:
        return location
    
    # Remove common prefixes
    location = re.sub(r'^(?:at|in|located at|held at)\\s+', '', location, flags=re.IGNORECASE)
    
    # Handle brackets and parentheses - extract content inside brackets
    # Pattern: "Building Name (Abbreviation)" -> "Building Name (Abbreviation)"
    # Pattern: "Room 123 [Building A]" -> "Room 123, Building A"
    # Pattern: "Price Center (PC)" -> "Price Center (PC)"
    
    # First, handle square brackets by converting to parentheses
    location = re.sub(r'\[([^\]]+)\]', r'(\1)', location)
    
    # Clean up multiple spaces and punctuation
    location = re.sub(r'\s+', ' ', location)  # Multiple spaces to single
    location = re.sub(r'\s*,\s*', ', ', location)  # Clean up commas
    location = re.sub(r'\s*\(\s*', ' (', location)  # Clean up opening parentheses
    location = re.sub(r'\s*\)\s*', ') ', location)  # Clean up closing parentheses
    
    # Remove trailing punctuation
    location = location.strip('.,;:')
    
    return location.strip()

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

def _detect_update_type(text: str) -> str:
    """Detect if this email is a new announcement, update, cancellation, or reminder"""
    text_lower = text.lower()
    
    # Check for cancellation patterns (HIGHEST PRIORITY)
    cancellation_patterns = [
        r'\b(?:cancelled|canceled)\b',
        r'\b(?:will not take place|will not occur|not happening)\b',
        r'\b(?:sorry|unfortunately).*\b(?:cancel|postpone)\b',
        r'\b(?:due to|because of).*\b(?:cancel|postpone)\b',
        r'\bhas been cancelled\b',
        r'\bcancellation of\b',
    ]
    
    for pattern in cancellation_patterns:
        if re.search(pattern, text_lower):
            logging.info(f"Detected cancellation via pattern: {pattern}")
            return "cancellation"
    
    # Check for update/change patterns (HIGH PRIORITY)
    update_patterns = [
        r'\b(?:update|updated|change|changed|modification|modified|correction|corrected)\b',
        r'\b(?:new time|new location|new date|new room|new venue)\b',
        r'\b(?:different time|different location|different date|different room)\b',
        r'\b(?:time change|location change|date change|schedule change|room change|venue change)\b',
        r'\b(?:please note|note that|important|urgent|attention).*\b(?:change|update|modification)\b',
        r'\b(?:moved to|changed to|rescheduled to|relocated to)\b',
        r'\b(?:now (?:at|in|on|scheduled for))\b',
        r'\b(?:has been moved|has been changed|has been rescheduled|has been relocated)\b',
        r'\b(?:instead of|rather than).*\b(?:originally|previously)\b',
        r'\b(?:the (?:location|time|date|room|venue) has)\b',
    ]
    
    for pattern in update_patterns:
        if re.search(pattern, text_lower):
            logging.info(f"Detected update via pattern: {pattern}")
            return "update"
    
    # Check for postponement (treat as update if new date given, else cancellation)
    if re.search(r'\b(?:postponed|postpone|postponement)\b', text_lower):
        # Check if new date is mentioned
        if re.search(r'\b(?:new date|rescheduled to|moved to).*\b(?:january|february|march|april|may|june|july|august|september|october|november|december|\d{1,2}[/-]\d{1,2})\b', text_lower):
            logging.info("Detected postponement with new date - treating as update")
            return "update"
        else:
            logging.info("Detected postponement without new date - treating as cancellation")
            return "cancellation"
    
    # Check for reminder patterns (LOWER PRIORITY)
    reminder_patterns = [
        r'\b(?:reminder|remind|don\'t forget|don\'t miss)\b',
        r'\b(?:just a reminder|friendly reminder|quick reminder)\b',
        r'\b(?:coming up|approaching|tomorrow|today).*\b(?:seminar|talk|presentation)\b',
        r'\b(?:as a reminder)\b',
    ]
    
    for pattern in reminder_patterns:
        if re.search(pattern, text_lower):
            logging.info(f"Detected reminder via pattern: {pattern}")
            return "reminder"
    
    # Check for new announcement patterns
    new_patterns = [
        r'\b(?:announce|announcing|announcement)\b',
        r'\b(?:invitation|invite|invited)\b',
        r'\b(?:join us|please join)\b',
        r'\b(?:we are pleased|pleased to announce)\b',
        r'\b(?:upcoming|next).*\b(?:seminar|talk|presentation)\b',
        r'\b(?:seminar|talk|presentation).*\b(?:will be|is scheduled)\b',
    ]
    
    for pattern in new_patterns:
        if re.search(pattern, text_lower):
            return "new"
    
    # Default to new if no specific pattern matches
    return "new"

def _extract_original_event_identifier(text: str) -> Optional[str]:
    """
    Extract information that can help identify the original event for updates.
    Returns a combination of title + speaker + date to uniquely identify events.
    """
    identifiers = []
    
    # Strategy 1: Extract title from the update email
    # Look for "regarding X", "about X", "for the X talk"
    reference_patterns = [
        r'(?:regarding|about|concerning|for|update on).*?(?:seminar|talk|presentation|journal club).*?["\']([^"\']{10,200})["\']',  # Quoted reference
        r'(?:regarding|about|concerning|for|update on).*?(?:seminar|talk|presentation|journal club).*?(?:titled|entitled|on|about)\\s+([^\\n]{10,200})(?:\\n|$)',
        r'(?:the|our)\\s+(?:seminar|talk|presentation|journal club).*?(?:titled|entitled|on|about)\\s+([^\\n]{10,200})(?:\\n|$)',
        r'(?:originally|previously)\\s+(?:scheduled|announced).*?(?:titled|entitled|on|about)\\s+([^\\n]{10,200})(?:\\n|$)',
    ]
    
    for pattern in reference_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
        if matches:
            for match in matches:
                ref = match.strip() if isinstance(match, str) else match[0].strip()
                # Clean up
                ref = ref.strip('.,;:')
                if len(ref) > 8 and len(ref) < 200 and _is_likely_title(ref):
                    identifiers.append(("title", ref))
                    logging.info(f"Found original event title reference: '{ref}'")
                    break
        if identifiers:
            break
    
    # Strategy 2: Look for speaker as identifier
    speaker_patterns = [
        r'(?:originally presented by|previously presented by|by)\\s+([A-Z][a-z]+\\s+[A-Z][a-z]+)',
        r'(?:speaker|presenter)\\s*:?\\s*([A-Z][a-z]+\\s+[A-Z][a-z]+)',
        r'(?:dr\.|prof\.|professor)\\s+([A-Z][a-z]+(?:\\s+[A-Z][a-z]+)?)',
    ]
    
    for pattern in speaker_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            speaker = matches[0].strip() if isinstance(matches[0], str) else matches[0][0].strip()
            identifiers.append(("speaker", speaker))
            logging.info(f"Found original event speaker reference: '{speaker}'")
            break
    
    # Strategy 3: Look for original date reference
    original_date_patterns = [
        r'(?:originally scheduled for|previously scheduled for|was scheduled for)\\s+([^\\n]{10,100})',
        r'(?:original date|previous date)\\s*:?\\s*([^\\n]{10,100})',
    ]
    
    for pattern in original_date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            date_ref = matches[0].strip()
            identifiers.append(("date", date_ref))
            logging.info(f"Found original event date reference: '{date_ref}'")
            break
    
    # Build combined identifier
    if identifiers:
        # Prefer title-based identification, then speaker, then date
        for id_type, id_value in identifiers:
            if id_type == "title":
                return id_value
        
        # If no title, combine speaker + date
        id_parts = []
        for id_type, id_value in identifiers:
            id_parts.append(id_value)
        
        combined = " | ".join(id_parts)
        logging.info(f"Combined event identifier: '{combined}'")
        return combined
    
    logging.info("No original event identifier found")
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

    # Detect the type of email (new, update, cancellation, reminder)
    email_type = _detect_update_type(combined)
    cancelled = (email_type == "cancellation")
    
    # Extract original event identifier for updates
    original_event_ref = None
    if email_type in ["update", "cancellation", "reminder"]:
        original_event_ref = _extract_original_event_identifier(combined)

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
        
        # Fallback: Try to extract numeric dates only (no relative dates)
        fallback_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # MM/DD/YYYY or MM-DD-YYYY
            r'\d{1,2}[/-]\d{1,2}',  # Just MM/DD (will infer year)
        ]
        
        for pattern in fallback_patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            if matches:
                try:
                    fallback_date = dateparser.parse(matches[0], settings={
                        "TIMEZONE": tz,
                        "RETURN_AS_TIMEZONE_AWARE": True,
                        "PREFER_DATES_FROM": "future"  # Assume future dates
                    })
                    if fallback_date:
                        # Set to a reasonable default time (e.g., 2 PM)
                        start = fallback_date.replace(hour=14, minute=0, second=0, microsecond=0)
                        logging.info(f"Fallback numeric date found: {matches[0]} -> {start}")
                        break
                except:
                    continue
    
    if not start:
        logging.error("Failed to extract any date/time information")
        return None

    # Set end time
    end = start + timedelta(minutes=default_minutes)

    # Extract fields using enhanced methods - pass HTML for better formatting detection
    title = _extract_title(combined, subject, html)
    speaker = _extract_speaker(combined)
    location = _extract_location(combined)  # Use enhanced location extraction
    url = _extract_url(combined)
    abstract = _extract_abstract(combined)
    
    # Process attachments - include attachment metadata for calendar description
    processed_attachments = []
    if attachments:
        for att in attachments:
            processed_attachments.append({
                'title': att.get('filename', 'Attachment'),
                'mimeType': att.get('mimeType', 'application/octet-stream'),
                'size': att.get('size', 0),
                # Note: Gmail attachments can be viewed in the original email
                # To add to calendar, we'd need to upload to Drive which requires additional setup
                'fileUrl': ''  # Leave empty for now - will show in description as "view in Gmail"
            })
        logging.info(f"Found {len(processed_attachments)} attachments")

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
        attachments=processed_attachments if processed_attachments else None,
        email_type=email_type,
        original_event_ref=original_event_ref,
    )