from pathlib import Path
from typing import List, Tuple
import re
import logging
import yaml
from .models import Categories, CategoryConfig

# Synonym/abbreviation normalization
KEYWORD_ALIASES = {
    'scrna-seq': 'single-cell rna-seq',
    'scrna': 'single-cell rna',
    'wgs': 'whole genome sequencing',
    'wes': 'whole exome sequencing',
    'ip': 'immunoprecipitation',
    'co-ip': 'coimmunoprecipitation',
    'if': 'immunofluorescence',
    'ihc': 'immunohistochemistry',
    'kd': 'knockdown',
    'ko': 'knockout',
    'oe': 'overexpression',
    'emt': 'epithelial mesenchymal transition',
    'tme': 'tumor microenvironment',
    'tcr-seq': 't cell receptor sequencing',
    'bcr-seq': 'b cell receptor sequencing',
    'ptm': 'post-translational modification',
    'ipsc': 'induced pluripotent stem cell',
    'esc': 'embryonic stem cell',
    'pd-1': 'programmed death 1',
    'pd1': 'programmed death 1',
    'ctla-4': 'ctla4',
    'car-t': 'chimeric antigen receptor t cell',
}

# Stop-phrases to filter out (generic, non-specific)
STOP_PHRASES = [
    'introduction',
    'materials and methods',
    'supplementary figure',
    'grant',
    'conference',
    'perspective',
    'commentary',
    'acknowledgments',
    'funding',
]

def load_categories(path: Path) -> Categories:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cats = []
    for name, spec in (raw.get("categories") or {}).items():
        cats.append(CategoryConfig(
            name=name,
            keywords=[k.lower().strip() for k in spec.get("keywords", [])],
            color_id=str(spec.get("colorId", "1"))
        ))
    return Categories(
        categories=cats,
        fallback_category=raw.get("fallback_category"),
        fallback_color_id=str(raw.get("fallback_colorId", "1")),
    )

def _normalize_text(text: str) -> str:
    """Normalize text for better keyword matching"""
    if not text:
        return ""
    
    text = text.lower()
    
    # Apply alias substitutions for better matching
    for abbrev, full_form in KEYWORD_ALIASES.items():
        # Use word boundaries to avoid partial matches
        text = re.sub(r'\b' + re.escape(abbrev) + r'\b', full_form, text)
    
    # Remove common hyphen variations (e.g., "single-cell" vs "single cell")
    # Keep the original but add a version without hyphens for matching
    return text

def categorize_text(categories: Categories, text: str) -> List[str]:
    """
    Categorize text using multi-label classification with scoring.
    Returns list of category names, sorted by match confidence.
    """
    if not text:
        return []
    
    # Normalize text
    normalized_text = _normalize_text(text)
    
    # Check for stop-phrases (downweight generic content)
    has_stop_phrase = any(phrase in normalized_text for phrase in STOP_PHRASES)
    
    # Score each category
    category_scores: List[Tuple[str, int]] = []
    
    for cat in categories.categories:
        score = 0
        matched_keywords = []
        
        for keyword in cat.keywords:
            # Use word boundaries for better precision
            # But also check for substring matches (for compound terms)
            keyword_pattern = r'\b' + re.escape(keyword) + r'\b'
            
            if re.search(keyword_pattern, normalized_text):
                # Full word boundary match (highest confidence)
                score += 10
                matched_keywords.append(keyword)
            elif keyword in normalized_text and len(keyword) > 5:
                # Substring match for longer keywords (medium confidence)
                score += 5
                matched_keywords.append(keyword)
        
        # Penalize if mostly stop-phrases
        if has_stop_phrase and score < 20:
            score = score // 2
        
        # Log matches for debugging
        if matched_keywords:
            logging.info(f"Category '{cat.name}' matched {len(matched_keywords)} keywords (score={score})")
            logging.debug(f"  Matched: {matched_keywords[:5]}")  # Show first 5
        
        if score > 0:
            category_scores.append((cat.name, score))
    
    # Sort by score descending and take top categories
    category_scores.sort(key=lambda x: -x[1])
    
    # Return categories with score above threshold
    # Allow multi-label: take categories with score >= 10 or top 3
    threshold = 10
    matched = []
    for cat_name, score in category_scores:
        if score >= threshold or len(matched) < 3:
            matched.append(cat_name)
            if len(matched) >= 4:  # Cap at 4 categories
                break
    
    if matched:
        logging.info(f"Final categories: {matched}")
    
    return matched