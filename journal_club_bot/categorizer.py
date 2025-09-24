from pathlib import Path
from typing import List
import yaml
from .models import Categories, CategoryConfig

def load_categories(path: Path) -> Categories:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cats = []
    for name, spec in (raw.get("categories") or {}).items():
        cats.append(CategoryConfig(
            name=name,
            keywords=[k.lower() for k in spec.get("keywords", [])],
            color_id=str(spec.get("colorId", "1"))
        ))
    return Categories(
        categories=cats,
        fallback_category=raw.get("fallback_category"),
        fallback_color_id=str(raw.get("fallback_colorId", "1")),
    )

def categorize_text(categories: Categories, text: str) -> List[str]:
    if not text:
        return []
    t = text.lower()
    matched = []
    for cat in categories.categories:
        if any(k in t for k in cat.keywords):
            matched.append(cat.name)
    return matched