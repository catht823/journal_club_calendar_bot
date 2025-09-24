from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime

@dataclass
class ParsedEvent:
    title: str
    start: datetime
    end: datetime
    timezone: str
    speaker: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    abstract: Optional[str] = None
    cancelled: bool = False

@dataclass
class Services:
    gmail: any
    calendar: any

@dataclass
class CategoryConfig:
    name: str
    keywords: List[str]
    color_id: str

@dataclass
class Categories:
    categories: List[CategoryConfig]
    fallback_category: Optional[str]
    fallback_color_id: Optional[str]

@dataclass
class MessageEventMap:
    message_id: str
    category_to_event_ids: Dict[str, str]