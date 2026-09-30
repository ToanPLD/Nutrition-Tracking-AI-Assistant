import re
import unicodedata
from typing import List, Optional, Tuple


def normalize_vietnamese(text: str) -> str:
    """Normalize text by stripping combining diacritics and converting đ/Đ to d."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d").replace("Đ", "D")
    return text.lower().strip()


# Common Vietnamese dishes & keywords to preserve
VN_DISH_KEYWORDS = (
    "pho", "bun", "banh", "com tam", "com ga", "com suon", "goi cuon",
    "cha gio", "nem ran", "nem cuon", "mi quang", "hu tieu", "bun bo",
    "bun cha", "bun rieu", "bun mam", "bun thit", "bun dau",
    "banh xeo", "banh cuon", "banh canh", "banh mi", "banh khot",
    "che ", "xoi ", "xeo ", "bo kho", "ca kho", "thit kho", "canh chua",
    "lau ", "nuoc cham", "nuoc mam", "tom kho", "ga kho", "muc nhoi",
    "ca thu", "ca hoi", "uc ga", "sua chua", "dau hu", "dau phu"
)

# Filler patterns to strip away when looking for the core food/dish entity
QUESTION_FILLER_RE = re.compile(
    r"\b("
    r"cho toi hoi|cho minh hoi|cho hoi|hoi ti|ban oi|calai oi|xin chao|chao ban|"
    r"cho toi biet|cho minh biet|hay cho biet|cho xem|hay tinh|tinh giup|tinh dum|"
    r"toi muon an|minh muon an|muon an|thich an|toi muon|minh muon|"
    r"bao nhieu|nhieu khong|co bao nhieu|co chua|chua bao nhieu|la bao nhieu|"
    r"calo|calories?|kcal|protein|dam|chat dam|carb|carbs|carbonhydrate|fat|chat beo|"
    r"chat xo|fiber|dinh duong|nutrition|nang luong|energy|"
    r"trong mot|trong 1|trong|mot|1|to|bat|dia|chen|phan|ly|coc|khau phan|gam|gram|g|"
    r"co khoang|khoang tam|uoc tinh|tam khoang|uoc luong|chua khoang|khoang|"
    r"co tot khong|co nen an khong|co beo khong|co map khong|co giam can khong|co tang can khong|"
    r"an vao bua nao|an co sao khong|nhu the nao|the nao|ra sao|"
    r"giup toi|giup minh|nhe|nha|vay a|vay ha|the thi|vay thi"
    r")\b",
    re.IGNORECASE
)

FOLLOW_UP_ANAPHORA = (
    "mon nay", "mon do", "mon do a", "cai nay", "cai do",
    "to nay", "bat nay", "dia nay", "ly nay", "coc nay",
    "no", "nay", "do", "it", "this", "that"
)


class EntityExtractor:
    """Extracts isolated food, dish, and beverage entities from conversational queries

    to prevent vector drift during semantic retrieval.
    """

    @staticmethod
    def is_follow_up_reference(query: str) -> bool:
        normalized = normalize_vietnamese(query)
        if len(normalized.split()) <= 4:
            return any(ref in normalized for ref in FOLLOW_UP_ANAPHORA)
        tokens = normalized.split()
        return any(ref in " ".join(tokens[:3]) for ref in FOLLOW_UP_ANAPHORA)

    @staticmethod
    def extract_recent_entity_from_history(conversation_context: str) -> Optional[str]:
        """Scans conversation history in reverse to locate the last mentioned food item,
        prioritizing user turns first.
        """
        if not conversation_context:
            return None
        lines = [line.strip() for line in str(conversation_context).splitlines() if line.strip()]
        # First pass: check User turns in reverse
        for line in reversed(lines):
            if re.match(r"^User:\s*", line, flags=re.IGNORECASE):
                cleaned = re.sub(r"^User:\s*", "", line, flags=re.IGNORECASE)
                entity = EntityExtractor.extract_food_entity(cleaned)
                if entity and len(entity) >= 3 and not EntityExtractor.is_follow_up_reference(entity):
                    return entity
        # Second pass: check Assistant lines
        for line in reversed(lines):
            cleaned = re.sub(r"^(User|Assistant|System|Human|AI):\s*", "", line, flags=re.IGNORECASE)
            entity = EntityExtractor.extract_food_entity(cleaned)
            if entity and len(entity) >= 3 and not EntityExtractor.is_follow_up_reference(entity):
                return entity
        return None

    @staticmethod
    def extract_food_entity(query: str, conversation_context: str = None) -> str:
        """Extracts the isolated food or dish entity from a user query,

        resolving anaphora from history if necessary.
        """
        raw_query = str(query or "").strip()
        # Drop conversation history prefix if it was stitched into query upstream
        anchor_match = re.search(r"cau hoi hien tai\s*:\s*(.+)$", raw_query, re.IGNORECASE | re.DOTALL)
        if anchor_match:
            raw_query = anchor_match.group(1).strip()

        # If user asks a pronoun/follow-up question ("món này có béo không?"), resolve from history
        if conversation_context and EntityExtractor.is_follow_up_reference(raw_query):
            resolved = EntityExtractor.extract_recent_entity_from_history(conversation_context)
            if resolved:
                return resolved

        # Strip punctuation and numbers
        cleaned = re.sub(r"[?!.,;:_\"'()\[\]]+", " ", raw_query)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Check for English Title Case proper nouns (e.g. "Broiled Salmon Steaks")
        title_matches = re.findall(
            r"\b([A-Z][a-zA-Z]+(?:\s+(?:[A-Z][a-zA-Z]+|and|with|of|in|the|a))+)\b",
            cleaned
        )
        if title_matches:
            return max(title_matches, key=lambda m: (m.count(" "), len(m))).strip()

        # Normalized clean
        normalized = normalize_vietnamese(cleaned)
        filtered = QUESTION_FILLER_RE.sub(" ", normalized)
        filtered = re.sub(r"\b\d+\b", " ", filtered)
        filtered = re.sub(r"\s+", " ", filtered).strip()

        # Fallback if over-cleans
        if not filtered:
            return cleaned[:60]

        return filtered[:80]

    @staticmethod
    def extract_comparison_entities(query: str) -> List[str]:
        """Splits comparison queries into discrete candidate food terms."""
        normalized = normalize_vietnamese(query)
        # Strip comparison preambles
        segment = re.sub(
            r"^(?:so sanh|compare|khac nhau giua|phan biet giua|giua)\s+",
            "",
            normalized
        )
        segment = QUESTION_FILLER_RE.sub(" ", segment)
        segment = re.sub(r"\b(?:va|voi|and|vs|versus)\b|[,/]+", "|", segment)
        parts = [part.strip() for part in segment.split("|") if len(part.strip()) >= 2]
        return parts[:4]
