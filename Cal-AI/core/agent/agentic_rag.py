import hashlib
import json
import re
import threading
import unicodedata
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from config.settings import settings
from core.agent.entity_extractor import EntityExtractor
from core.embedding.text_embedding_service import TextEmbeddingService
from core.services.cache.redis_cache import RedisCache
from core.services.llm.llm_service import LLMService
from core.services.rag.recipe_image_rag_service import RecipeImageRAGService
from core.services.retrieval.qdrant_service import QdrantService
from core.services.retrieval.rerank_service import FlashRankService


# Shared executor: per-collection Qdrant searches are I/O bound HTTP calls and
# fan out across ~20 collections per query, so running them sequentially is the
# dominant latency cost. A separate, smaller pool drives meal-planning sub-seeds
# so they can't starve the search pool when both layers fan out at once.
_QDRANT_SEARCH_EXECUTOR = ThreadPoolExecutor(
    max_workers=32, thread_name_prefix="qdrant-search"
)
_AGENT_FANOUT_EXECUTOR = ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="agent-fanout"
)


class AgenticTrace:
    def __init__(self):
        self.steps = []
        self._lock = threading.Lock()

    def add(self, title, text, status="done", evidence=None, detail=None):
        with self._lock:
            self.steps.append({
                "step": len(self.steps) + 1,
                "title": title,
                "text": text,
                "status": status,
                "evidence": evidence or [],
                "detail": detail
            })


TOPIC_REGISTRY = {
    "beverage": {
        "phrases": (
            "do uong", "thuc uong", "nuoc uong", "nuoc giai khat",
            "thuc uong giai khat", "loai nuoc", "cac loai nuoc",
            "drink", "drinks", "beverage", "beverages",
            "smoothie", "smoothies", "juice", "juices",
            "tra", "cafe", "coffee", "tea", "soda", "milk",
            "sua tuoi", "sua dau", "sua hat", "nuoc ep",
        ),
        "keywords": ("drink", "beverage", "tea", "coffee", "juice", "milk", "smoothie"),
        "collections": ("beverage_text_vectors_768", "beverage_vectors_768"),
        "exclusive": True,
    },
    "exercise": {
        "phrases": (
            "bai tap", "bai the duc", "tap luyen", "the duc", "the thao",
            "van dong", "hoat dong the chat", "tap gym", "tap aerobic",
            "tap yoga", "chay bo", "boi loi", "dap xe", "nang ta",
            "exercise", "exercises", "workout", "workouts", "training",
            "fitness", "gym", "sport", "sports", "physical activity",
            "cardio", "yoga", "running", "swimming", "cycling",
            "weightlifting", "strength training",
        ),
        "keywords": (
            "exercise", "workout", "training", "fitness", "gym",
            "sport", "activity", "cardio", "running", "yoga",
        ),
        "collections": (
            "exercise_text_vectors_768",
            "exercise_vectors_768",
            "exercise_gym_vectors_768",
        ),
        "exclusive": True,
    },
    "obesity_lifestyle": {
        "phrases": (
            "loi song", "thoi quen sinh hoat", "thoi quen an uong",
            "beo phi", "thua can", "obesity", "overweight",
            "lifestyle", "habit", "habits", "smoking",
            "alcohol", "screen time", "sedentary",
        ),
        "keywords": (
            "lifestyle", "habit", "obesity", "overweight",
            "smoking", "alcohol", "sedentary",
        ),
        "collections": ("lifestyle_obesity_vectors_768", "lifestyle_vectors_768"),
        "exclusive": True,
    },
    "diet_disease": {
        "phrases": (
            "che do an cho", "che do dinh duong cho", "an cho nguoi",
            "tieu duong", "huyet ap cao", "huyet ap thap", "tim mach",
            "ung thu", "benh nhan", "benh ly",
            "diabetes", "diabetic", "hypertension", "heart disease",
            "kidney disease", "cholesterol", "dietary recommendation",
            "dietary advice", "patient diet",
        ),
        "keywords": (
            "diet", "diabetes", "hypertension", "heart disease",
            "kidney", "cholesterol", "patient", "recommendation",
        ),
        "collections": ("diet_recommendations_vectors",),
        "exclusive": False,
    },
    "fruit": {
        "phrases": (
            "trai cay", "hoa qua", "fruit", "fruits",
        ),
        "keywords": ("fruit", "apple", "banana", "orange", "guava", "mango"),
        "collections": ("food_fruit_vectors_768",),
        "exclusive": False,
    },
}

BEVERAGE_PHRASES = TOPIC_REGISTRY["beverage"]["phrases"]


# Macro field aliases shared across collections. _numeric_metric also falls back
# to a nested `nutrition` dict so Nutrition5k payloads (e.g. nutrition.protein_g)
# resolve through the same key list.
MACRO_CALORIE_KEYS = (
    "Caloric Value", "calories", "Calories", "kcal",
    "Energ_Kcal", "energy", "energy_kcal",
    "energy-kcal_100g", "energy_100g",
)
MACRO_PROTEIN_KEYS = (
    "protein", "Protein", "Protein_(g)", "proteins_100g",
    "protein_g", "protein_grams",
)
MACRO_CARBS_KEYS = (
    "carbohydrate", "carbs", "Carbohydrates", "Carbohydrt_(g)",
    "carbohydrates_100g", "carbs_g", "carb", "carbs_grams",
)
MACRO_FAT_KEYS = (
    "fat", "Fat", "total_fat", "Lipid_Tot_(g)", "fat_100g",
    "fat_g", "fat_grams",
)
MACRO_SERVING_KEYS = (
    "serving_size", "GmWt_Desc1", "GmWt_1", "portion",
    "mass_g", "mass", "weight_g", "weight",
)


def _normalize_for_topic(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    return text


def _topic_phrase_matches(normalized, phrases):
    return any(
        re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", normalized)
        for phrase in phrases
    )


def matched_topics(query):
    normalized = _normalize_for_topic(query)
    return [
        topic for topic, spec in TOPIC_REGISTRY.items()
        if _topic_phrase_matches(normalized, spec["phrases"])
    ]


class AgentRouter:
    def _normalize(self, text):
        text = unicodedata.normalize("NFKD", str(text or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.replace("đ", "d").replace("Đ", "D")
        return text.lower()

    def _has_phrase(self, text, phrases):
        for phrase in phrases:
            pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
            if re.search(pattern, text):
                return True
        return False

    # Off-topic signals — programming, geography/general knowledge, chitchat.
    # Detected BEFORE nutrition-style routes so that "Thủ đô Pháp?" doesn't
    # end up in meal_planning, and "viết hàm fibonacci" doesn't pull a
    # food-table CONTEXT into the prompt.
    _OFF_TOPIC_PHRASES = (
        # programming
        "fibonacci", "python", "javascript", "typescript", "java ", "c++",
        "lap trinh", "viet ham", "viet code", "thuat toan", "algorithm",
        "function", "regex", "sql", "leetcode", "quicksort", "merge sort",
        # general knowledge / geography
        "thu do", "capital of", "tong thong", "president", "thu tuong",
        "dien tich", "dan so", "lich su", "history of", "nam nao",
        # math (non-nutrition)
        "phuong trinh", "tich phan", "dao ham", "hinh hoc",
        # chitchat
        "xin chao", "chao ban", "hello", "hi ", "how are you", "ban khoe",
        "ban la ai", "ten ban", "who are you",
        # weather / sport / entertainment
        "thoi tiet", "weather", "du bao", "nhiet do",
        "world cup", "bong da", "champions league", "premier league",
        "nba", "phim", "movie", "ca si", "bai hat",
        # politics
        "bau cu", "election", "chinh tri", "politics", "dang phai",
    )

    # Phrases that should be refused outright (harm / illegal / sensitive)
    # before retrieval, so RAG can't pivot "bomb" into "bombe dessert".
    _HARM_PHRASES = (
        "make a bomb", "che tao bom", "lam bom", "che bom",
        "weapon", "vu khi", "sung dan", "thuoc no",
        "kill ", "giet ", "self harm", "suicide", "tu sat",
        "ma tuy", "drug recipe", "heroin", "meth",
    )

    # Personal-preference patterns user-side. If query asks "what do I usually
    # eat / favorite foods" WITHOUT a real user_profile, refuse deterministically
    # to avoid the LLM fabricating preferences from random RAG hits.
    _PROFILE_LOOKUP_PHRASES = (
        "toi hay an", "minh hay an", "toi thuong an", "minh thuong an",
        "mon toi hay", "mon minh hay", "mon hay an cua toi",
        "mon yeu thich cua toi", "mon yeu thich cua minh",
        "toi thich an gi", "minh thich an gi",
        "toi hay an mon gi", "minh hay an mon gi",
        "toi an mon gi nhat", "minh an mon gi nhat",
        "lich su an uong cua toi", "lich su an uong cua minh",
        "ho so cua toi", "ho so cua minh", "profile cua toi",
        "my favorite food", "what do i usually eat", "what i eat",
        "my eating history", "my profile",
    )

    # Compiled once: nutrition signal that would override the off-topic
    # classifier. Word-boundaried so "ban" doesn't trigger "an", etc.
    _FOOD_SIGNAL_RE = re.compile(
        r"\b("
        r"calo|kcal|calories?|protein|carb|fat|"
        r"dinh duong|nutrition|thuc pham|mon|bua an|"
        r"giam can|tang can|tang co|muscle|"
        r"minh an|toi an|i ate|i am eating|vua an|dang an|"
        r"pho|bun|banh|com tam|com ga|goi cuon|cha gio|"
        r"nem ran|bo kho|ca kho|thit kho|canh chua"
        r")\b"
    )

    def _looks_off_topic(self, q):
        # Require at least one off-topic phrase AND no nutrition keyword,
        # so "tính giúp mình calo trong python rolls" isn't misrouted.
        if self._FOOD_SIGNAL_RE.search(q):
            return False
        return any(phrase in q for phrase in self._OFF_TOPIC_PHRASES)

    def looks_harmful(self, query):
        q = self._normalize(query)
        return any(phrase in q for phrase in self._HARM_PHRASES)

    def looks_profile_lookup(self, query):
        q = self._normalize(query)
        return any(phrase in q for phrase in self._PROFILE_LOOKUP_PHRASES)

    def classify(self, query, forced_intent=None):
        if forced_intent:
            return forced_intent

        q = self._normalize(query)

        if any(phrase in q for phrase in self._HARM_PHRASES):
            return "refuse_harm"

        if self._looks_off_topic(q):
            return "off_topic"

        if self._has_phrase(q, [
            "tang bao nhieu kg", "giam bao nhieu kg", "tang can bao nhieu",
            "giam can bao nhieu", "se tang bao nhieu", "se giam bao nhieu",
            "tang bao nhieu can", "giam bao nhieu can",
            "len bao nhieu can", "xuong bao nhieu can",
            "len bao nhieu kg", "xuong bao nhieu kg",
            "tang bao nhieu", "giam bao nhieu",
            "can nang hien tai", "tdee", "bmr", "surplus", "deficit",
            "thang du calo", "thieu hut calo", "calorie surplus",
            "calorie deficit", "energy balance", "kg fat", "kg mo",
            "gain weight", "lose weight", "how much weight",
            "weight gain", "weight loss"
        ]):
            return "weight_projection"

        if (
            self._has_phrase(q, ["trong", "sau", "voi", "neu", "if", "in", "after", "with"])
            and self._has_phrase(q, [
                "ngay", "tuan", "thang", "tuần", "tháng",
                "day", "days", "week", "weeks", "month", "months"
            ])
            and self._has_phrase(q, ["can", "kg", "weight", "ta", "mo", "fat"])
        ):
            return "weight_projection"

        if self._has_phrase(q, [
            "so sanh", "compare", "comparison", "vs", "versus",
            "khac nhau", "nguyen lieu nao", "bang so sanh"
        ]):
            return "ingredient_comparison"

        if self._has_phrase(q, [
            "bien tau", "goi y bien", "thay the", "substitute",
            "multi hop", "ket hop", "extract ingredients", "lay nguyen lieu"
        ]):
            return "multi_hop"

        if self._has_phrase(q, [
            "tim anh", "hinh anh", "anh mon", "image", "photo", "picture"
        ]):
            return "image_retrieval"

        topics = matched_topics(query)
        if topics and any(TOPIC_REGISTRY[topic].get("exclusive") for topic in topics):
            return "nutrition_qa"

        if self._has_phrase(q, [
            "plan my lunch", "plan lunch", "plan my dinner", "plan dinner",
            "plan breakfast", "meal plan", "lunch plan", "dinner plan",
            "breakfast plan", "lap thuc don", "len thuc don", "thuc don",
            "lap ke hoach", "len ke hoach", "ke hoach bua an",
            "ke hoach an uong", "bua an hom nay", "hom nay an gi",
            "an gi hom nay", "daily meal plan", "plan my meals",
            "bua trua", "bua toi", "bua sang", "an trua", "an toi",
            "an sang", "menu", "meal prep"
        ]):
            return "meal_planning"

        if (
            self._has_phrase(q, ["liet ke", "danh sach", "goi y", "de xuat", "suggest", "recommend"])
            and self._has_phrase(q, ["mon", "bua", "bua trua", "bua toi", "bua sang", "lunch", "dinner", "breakfast", "giau protein", "high protein"])
        ):
            return "meal_planning"

        plan_anchor_vi = self._has_phrase(q, ["ke hoach", "thuc don", "lo trinh", "lap ra", "len ra"])
        plan_anchor_en = self._has_phrase(q, ["plan", "schedule", "meal plan", "menu"])
        food_or_horizon = self._has_phrase(q, [
            "thuc pham", "do an", "bua an", "an uong", "mon an", "mon",
            "bua sang", "bua trua", "bua toi", "an sang", "an trua", "an toi",
            "ngay", "tuan", "thang", "tuần", "tháng",
            "meal", "meals", "food", "foods", "diet", "menu",
            "breakfast", "lunch", "dinner", "snack",
            "day", "days", "week", "weeks", "month", "months",
            "dinh duong", "nutrition",
        ])
        if (plan_anchor_vi or plan_anchor_en) and food_or_horizon:
            return "meal_planning"

        if topics:
            return "nutrition_qa"

        if self._has_phrase(q, [
            "calo", "kcal", "calorie", "macro", "protein", "carb", "fat",
            "dinh duong", "nutrition", "giam can", "tang can", "diet",
            "fitness", "tap luyen", "how many calories", "calories in",
            "bao nhieu calo", "bao nhieu kcal", "toi an", "minh an",
            "vua an", "dang an", "i ate", "i am eating"
        ]):
            return "nutrition_qa"

        if self._has_phrase(q, [
            "cong thuc", "recipe", "cach lam", "instructions",
            "nguyen lieu", "mon nay nau", "nau mon", "liet ke",
            "danh sach", "bang", "table", "bieu do", "chart", "so lieu"
        ]):
            return "recipe_reasoning"

        return "general_rag"


class CitationBuilder:
    TITLE_FIELDS = (
        "title", "Title", "recipe_title", "Recipe_Title",
        "recipe_name", "Recipe_Name", "Recipe Name", "recipeName",
        "name", "Name",
        "dish_name", "Dish_Name", "dish",
        "food_name", "Food_Name", "Food", "Food_Item", "food",
        "product_name", "Product_Name", "product",
        "ingredient_name",  # nutrition5k row-level
        "drink", "Drink", "Drink_Name", "beverage_name", "Beverage",
        "exercise_name", "Exercise", "Activity", "activity_name",
        "Disease", "disease_name", "Habit", "habit_name",
        "Fruit", "Vegetable",
        "Shrt_Desc", "shrt_desc", "Long_Desc",
    )

    @staticmethod
    def from_payload(payload):
        payload = payload or {}
        explicit = payload.get("citation")
        if isinstance(explicit, dict):
            return explicit

        dataset = payload.get("source_dataset") or payload.get("domain")
        title = None
        for field in CitationBuilder.TITLE_FIELDS:
            value = payload.get(field)
            if value not in (None, ""):
                title = value
                break

        return {
            "dataset": dataset,
            "collection": payload.get("source_collection"),
            "row": payload.get("source_row") or payload.get("ref_id"),
            "title": title,
            "image_name": payload.get("image_name"),
            "image_file": payload.get("image_file")
        }

    @staticmethod
    def display_label(payload, fallback=None):
        citation = CitationBuilder.from_payload(payload)
        title = citation.get("title")
        if title not in (None, ""):
            text = str(title).strip()
            if text:
                return text[:80]
        collection = citation.get("collection") or citation.get("dataset")
        row = citation.get("row")
        if collection and row not in (None, ""):
            return f"{collection}#{row}"
        if collection:
            return str(collection)
        return "" if fallback is None else str(fallback)

    @staticmethod
    def dedupe(citations):
        unique = OrderedDict()
        for citation in citations:
            if not citation:
                continue
            key = (
                citation.get("dataset"),
                citation.get("collection"),
                citation.get("row"),
                citation.get("title"),
                citation.get("image_name"),
            )
            unique[key] = citation
        return list(unique.values())


class AgenticResponseGenerator:
    def __init__(self, llm=None):
        self.llm = llm or LLMService()

    def _model_unavailable_answer(self):
        return (
            "Xin lỗi bạn, mình đang gặp trục trặc khi xử lý câu hỏi này. "
            "Bạn thử gửi lại nhé, hoặc bổ sung thêm chi tiết "
            "(ví dụ: tên món cụ thể, khẩu phần, mục tiêu dinh dưỡng) "
            "để mình hỗ trợ tốt hơn!"
        )

    def _no_context_answer(self, query):
        return (
            f"Mình chưa tìm thấy dữ liệu phù hợp trong kho thông tin cho câu hỏi của bạn. "
            "Bạn có thể thử:\n"
            "- Mô tả cụ thể hơn tên món ăn hoặc thực phẩm bạn muốn tra cứu\n"
            "- Dùng tên tiếng Anh nếu là món quốc tế (ví dụ: chicken breast, salmon)\n"
            "- Hỏi về một loại thực phẩm cụ thể thay vì câu hỏi chung\n\n"
            "Mình sẵn sàng giúp bạn ngay khi có thêm thông tin!"
        )

    async def generate(self, query, intent, context, citations, trace, conversation_context=None, user_profile_text=None):
        if not context and intent not in ("weight_projection", "off_topic"):
            return self._no_context_answer(query)

        try:
            answer = await self.llm.answer_agentic(
                query=query,
                intent=intent,
                context=context,
                citations=citations,
                conversation_context=conversation_context,
                user_profile_text=user_profile_text
            )
        except Exception:
            return self._model_unavailable_answer()

        return answer or self._model_unavailable_answer()

    async def generate_stream(self, query, intent, context, citations, conversation_context=None, user_profile_text=None):
        if not context and intent not in ("weight_projection", "off_topic"):
            yield self._no_context_answer(query)
            return

        try:
            async for chunk in self.llm.answer_agentic_stream(
                query=query,
                intent=intent,
                context=context,
                citations=citations,
                conversation_context=conversation_context,
                user_profile_text=user_profile_text
            ):
                yield chunk
        except Exception as exc:
            yield f"[Lỗi: {exc}]"


class GenericRAGAgent:
    FOOD_SYNONYMS = {
        "tao": "apple",
        "qua tao": "apple",
        "chuoi": "banana",
        "cam": "orange",
        "com": "rice",
        "gao": "rice",
        "uc ga": "chicken breast",
        "thit ga": "chicken",
        "thit bo": "beef",
        "ca hoi": "salmon",
        "trung": "egg",
        "sua chua": "yogurt",
        "khoai lang": "sweet potato",
        "banh mi": "bread sandwich",
        "pizza": "pizza",
        "salad": "salad",
        "pasta": "pasta",
        "pho": "pho beef noodle soup",
        "bun bo": "beef noodle soup",
        "mi": "noodle",
        "yen mach": "oats",
        "dau phu": "tofu",
    }

    # Keywords (accent-stripped, lowercase) that signal a Vietnamese-cuisine query.
    # When matched, the vn_food_* Qdrant collection gets a rerank boost so
    # multilingual embeddings don't drag Pad Thai / bun cha into "phở" answers.
    VN_FOOD_KEYWORDS = (
        "pho", "bun", "banh", "com tam", "com ga", "com suon", "goi cuon",
        "cha gio", "nem ran", "nem cuon", "mi quang", "hu tieu", "bun bo",
        "bun cha", "bun rieu", "bun mam", "bun thit", "bun dau",
        "banh xeo", "banh cuon", "banh canh", "banh mi", "banh khot",
        "che ", "xoi ", "xeo ", "bo kho", "ca kho", "thit kho", "canh chua",
        "lau ", "nuoc cham", "nuoc mam", "tom kho", "ga kho",
    )
    VN_FOOD_COLLECTION = "vn_food_vectors_768"

    def __init__(self, qdrant=None, text_embed=None):
        self.qdrant = qdrant or QdrantService()
        self.text_embed = text_embed or TextEmbeddingService()
        self._compatible_collections = None

    def _text_collections(self):
        if self._compatible_collections is not None:
            return self._compatible_collections

        available = self.qdrant.available_collections()

        configured = [
            collection for collection in settings.TEXT_COLLECTIONS
            if collection in available
        ]
        discovered = []
        for collection in available:
            if collection in configured:
                continue
            try:
                info = self.qdrant.client.get_collection(collection)
                vectors = info.config.params.vectors
                if isinstance(vectors, dict):
                    continue
                if getattr(vectors, "size", None) == settings.TEXT_VECTOR_DIM:
                    discovered.append(collection)
            except Exception:
                continue

        merged = []
        for collection in [*configured, *sorted(discovered)]:
            if collection not in merged:
                merged.append(collection)

        if not merged:
            print("⚠️ No compatible Qdrant collections found. Available:", available or "none")

        self._compatible_collections = merged or settings.TEXT_COLLECTIONS
        return self._compatible_collections

    def _nutrition_collections(self):
        existing = set(self._text_collections())
        preferred = [
            "food_fruit_vectors_768",
            "food_common_vectors_768",
            "food_nutrition_vectors_768",
            "nutrition5k_vectors_768",
            "food_nutrition_dev_vectors_768",
            "food_global_10k_vectors_768",
            "food_text_vectors_768",
            "food_vectors_768",
            "beverage_text_vectors_768",
            "beverage_vectors_768",
        ]
        selected = [collection for collection in preferred if collection in existing]
        return selected or self._text_collections()

    def _focused_nutrition_collections(self, query):
        existing = set(self._text_collections())
        keywords = set(self._query_keywords(query))
        topics = matched_topics(query)
        normalized_query = self._normalize_query(query)
        
        # When querying Vietnamese food, focus specifically on vn_food and key nutrition collections
        if self._is_vn_food_query(normalized_query) and self.VN_FOOD_COLLECTION in existing:
            vn_focused = [
                self.VN_FOOD_COLLECTION,
                "food_nutrition_vectors_768",
                "food_common_vectors_768"
            ]
            return [c for c in vn_focused if c in existing]

        vn_food_first = (
            [self.VN_FOOD_COLLECTION]
            if self._is_vn_food_query(normalized_query)
            and self.VN_FOOD_COLLECTION in existing
            else []
        )

        topic_collections = []
        any_exclusive = False
        for topic in topics:
            spec = TOPIC_REGISTRY[topic]
            topic_collections.extend(spec["collections"])
            if spec.get("exclusive"):
                any_exclusive = True

        if topic_collections:
            preferred = list(topic_collections)
            if not any_exclusive:
                preferred += [
                    "food_nutrition_vectors_768",
                    "nutrition5k_vectors_768",
                    "food_common_vectors_768",
                ]
            preferred = vn_food_first + [c for c in preferred if c != self.VN_FOOD_COLLECTION]
            selected = [c for c in preferred if c in existing]
            return list(dict.fromkeys(selected)) or self._nutrition_collections()

        fruit_keywords = {"apple", "banana", "orange"}
        beverage_keywords = {"milk", "coffee", "tea", "juice", "smoothie"}
        if keywords & beverage_keywords:
            preferred = [
                "beverage_text_vectors_768",
                "beverage_vectors_768",
                "food_nutrition_vectors_768",
                "food_common_vectors_768",
            ]
        elif keywords & fruit_keywords:
            preferred = [
                "food_fruit_vectors_768",
                "food_common_vectors_768",
                "food_nutrition_vectors_768",
            ]
        elif keywords:
            preferred = [
                "food_common_vectors_768",
                "food_nutrition_vectors_768",
                "nutrition5k_vectors_768",
                "food_nutrition_dev_vectors_768",
                "food_global_10k_vectors_768",
                "food_vectors_768",
                "food_text_vectors_768",
                "recipes_64k_vectors_768",
                "food_recipe_images_text_768",
            ]
        else:
            # No keyword/topic match — fall back to the curated nutrition list,
            # but still float vn_food to the top when the query mentions a
            # Vietnamese dish (so "Bò kho có giàu protein không?" still
            # surfaces curated VN macros instead of going generic).
            base = self._nutrition_collections()
            merged = vn_food_first + [c for c in base if c != self.VN_FOOD_COLLECTION]
            return merged

        merged_preferred = vn_food_first + [c for c in preferred if c != self.VN_FOOD_COLLECTION]
        selected = [collection for collection in merged_preferred if collection in existing]
        return selected or self._nutrition_collections()

    def _expand_query(self, query):
        keywords = self._query_keywords(query)
        if not keywords:
            return query

        return f"{query}\nEnglish retrieval keywords: {', '.join(dict.fromkeys(keywords))}"

    def _query_keywords(self, query):
        normalized = unicodedata.normalize("NFKD", str(query or ""))
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.replace("đ", "d").lower()

        keywords = []
        for source, target in self.FOOD_SYNONYMS.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(source) + r"(?![a-z0-9])", normalized):
                keywords.append(target)
        for target in sorted(set(self.FOOD_SYNONYMS.values()), key=len, reverse=True):
            if re.search(r"(?<![a-z0-9])" + re.escape(target.lower()) + r"(?![a-z0-9])", normalized):
                keywords.append(target)

        for topic in matched_topics(query):
            keywords.extend(TOPIC_REGISTRY[topic]["keywords"])

        return list(dict.fromkeys(keywords))

    def _comparison_terms(self, query):
        normalized = unicodedata.normalize("NFKD", str(query or ""))
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.replace("đ", "d").replace("Đ", "D").lower()

        match = re.search(
            r"(?:so sanh|compare|comparison|khac nhau giua|khac nhau)\s+(.+)",
            normalized
        )
        segment = match.group(1) if match else normalized
        segment = re.sub(
            r"\b(?:duoi dang|dang)?\s*(?:bang|table|bieu do|chart)\b.*",
            " ",
            segment
        )
        segment = re.sub(
            r"\b(?:cho nguoi|cho|minh|toi|de|phu hop voi|dang)?\s*(?:giam can|tang can|diet|eat clean)\b.*",
            " ",
            segment
        )
        segment = re.sub(
            r"\b(?:dinh duong|nutrition|nutrient|macro|macros|calo|calorie|calories|"
            r"kcal|protein|carb|fat|fiber|chat beo|chat xo|nguyen lieu|thuc pham|"
            r"mon an|mon|food|ingredient|cac|loai|giua|nao|hon|tot hon|nen an|"
            r"doi tuong|bat ki|bat ky|bat cu|any|random|giau|bo duong)\b",
            " ",
            segment
        )
        segment = re.sub(r"\b\d+\b", " ", segment)
        segment = re.sub(r"\s+", " ", segment).strip()

        parts = re.split(r"\s+(?:va|voi|and|vs|versus)\s+|[,/]+", segment)
        terms = []
        for part in parts:
            term = re.sub(r"\s+", " ", part).strip(" .:;!?-")
            if len(term) < 2:
                continue
            if term not in terms:
                terms.append(term[:80])
        return terms[:4]

    def _display_name(self, payload):
        return str(
            payload.get("title")
            or payload.get("Name")
            or payload.get("recipe_name")
            or payload.get("name")
            or payload.get("dish_name")
            or payload.get("food_name")
            or payload.get("product_name")
            or payload.get("food")
            or payload.get("ingredient_name")
            or payload.get("Fruit")
            or payload.get("Shrt_Desc")
            or ""
        )

    def _is_vn_food_query(self, normalized_query):
        if not normalized_query:
            return False
        return any(kw in normalized_query for kw in self.VN_FOOD_KEYWORDS)

    # Filler tokens that bury the dish phrase when embedding a full
    # Vietnamese sentence — stripping them before the vn_food search keeps
    # the vector aligned with curated dish-name entries. Includes
    # conversation-history scaffolding ("user", "assistant", "ngu canh"...)
    # that appears in expanded retrieval queries on follow-up turns.
    _VN_FOOD_FILLER_RE = re.compile(
        r"\b(co|bao nhieu|la gi|gi|nhu the nao|nhu vay|so sanh|so sanh voi|"
        r"cua|cho|toi|minh|ban|nguoi|user|assistant|"
        r"ngu canh|hoi thoai|gan day|gan|day|cau hoi|hien tai|"
        r"trong|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi|"
        r"to|bat|dia|chen|phan|khau phan|mieng|"
        r"calo|calories?|kcal|protein|carb|carbs|fat|chat beo|chat xo|chat dam|"
        r"dinh duong|nguyen lieu|thanh phan|"
        r"nhieu|it|hon|khong|co the|nen|an|uong|"
        r"hay|giup|tu van|hoi|hen|xin|vui long|"
        r"chua|kcal/100g|g/100g|tuy nhien|"
        r"va|voi|hoac|quay lai|lai|chuyen|luc nay|luc nao|"
        r"giau|nhieu|it|muon|tang co|tang can|giam can|giam beo|tang|giam|"
        r"phu hop|hop voi|kieng|an kieng|che do|"
        r"dau mo|chat dam|chat beo|chat xo|"
        r"cai nao|cai gi|cai do|thi sao|nhu the nao|"
        r"\d+)\b",
        re.IGNORECASE
    )

    def _vn_dish_phrase(self, query, normalized_query=None):
        """Pull the Vietnamese dish phrase out of a noisy question.

        Returns None when no VN food keyword is detected; otherwise returns
        a short phrase (accent-stripped) suitable for a targeted
        vn_food_vectors_768 search. Embedding the full sentence
        ("Phở bò có bao nhiêu calo trong một tô?") drifts the vector off
        the curated dish entries — embedding "pho bo" alone surfaces the
        right row. For follow-up queries with conversation history baked
        in, we anchor on the CURRENT question only (after "Câu hỏi hiện
        tại:" / "Cau hoi hien tai:") so the phrase doesn't grab a dish
        from an earlier turn ("banh mi thit" from history when current
        question is about "bo kho").
        """
        nq = normalized_query if normalized_query is not None else self._normalize_query(query)
        if not self._is_vn_food_query(nq):
            return None
        # When the upstream stitched conversation history in front of the
        # current question (see _retrieval_query), drop everything before
        # the explicit anchor so the dish phrase reflects what user just
        # asked, not what they asked five turns ago.
        anchor_match = re.search(r"cau hoi hien tai\s*:\s*(.+)$", nq, re.DOTALL)
        scope = anchor_match.group(1) if anchor_match else nq
        cleaned = self._VN_FOOD_FILLER_RE.sub(" ", scope)
        cleaned = re.sub(r"[?!.,;:\n]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return None

        tokens = cleaned.split()
        # Strip artifacts like "/100g" and leading single-char fragments.
        tokens = [t for t in tokens if not re.match(r"^[/\-\d].*$", t) and len(t) >= 2]
        if not tokens:
            return None

        # Take the first VN-keyword anchor and the next ~3 tokens. Dedupe
        # consecutive repeats so noisy expansions ("pho bo pho bo pho bo...")
        # collapse to a clean phrase suitable for embedding.
        anchor_idx = next(
            (i for i, _ in enumerate(tokens)
             if any(kw in " ".join(tokens[i: i + 2]) for kw in self.VN_FOOD_KEYWORDS)),
            None,
        )
        if anchor_idx is None:
            return None
        window = tokens[anchor_idx: anchor_idx + 4]

        deduped = []
        for tok in window:
            if not deduped or deduped[-1] != tok:
                deduped.append(tok)
        return " ".join(deduped)[:80]

    def _vn_dish_phrases(self, query, normalized_query=None, max_phrases=3):
        """Return up to `max_phrases` distinct dish phrases for queries that
        compare multiple Vietnamese dishes ("Chả giò và bánh xèo, cái nào
        nhiều dầu mỡ hơn?"). The single-phrase _vn_dish_phrase only embeds
        ~4 tokens around the FIRST keyword, so the second dish would never
        surface in vn_food. Splitting on conjunctions and re-running the
        extractor on each segment gives every dish its own search vector.
        """
        nq = normalized_query if normalized_query is not None else self._normalize_query(query)
        if not self._is_vn_food_query(nq):
            return []
        anchor_match = re.search(r"cau hoi hien tai\s*:\s*(.+)$", nq, re.DOTALL)
        scope = anchor_match.group(1) if anchor_match else nq
        # Split on common Vietnamese coordination conjunctions plus
        # comparison glue. Each segment is a candidate dish chunk.
        segments = re.split(
            r"\b(?:va|voi|hoac|hay|vs|versus|so sanh)\b|[,/]+|\bthi cai nao\b|\bcai nao\b",
            scope,
        )
        phrases = []
        seen = set()
        for seg in segments:
            ph = self._vn_dish_phrase(seg, normalized_query=seg.strip())
            if ph and ph not in seen:
                seen.add(ph)
                phrases.append(ph)
                if len(phrases) >= max_phrases:
                    break
        # Fallback: if splitting yielded nothing useful, fall back to single.
        if not phrases:
            single = self._vn_dish_phrase(query, normalized_query=nq)
            if single:
                phrases.append(single)
        return phrases

    def _rerank_score(self, hit, keywords, normalized_query=""):
        score = float(getattr(hit, "score", 0) or 0)
        payload = hit.payload or {}

        name = unicodedata.normalize("NFKD", self._display_name(payload))
        name = "".join(ch for ch in name if not unicodedata.combining(ch))
        name = name.replace("đ", "d").lower().strip()

        bonus = 0
        # Title appearing literally inside the user query (e.g. user typed
        # "thông tin về Broiled Salmon Steaks") — strong signal that this
        # specific dish is what they want, not just a salmon recipe.
        if name and len(name) >= 5 and normalized_query and name in normalized_query:
            bonus += 0.30

        collection = str(payload.get("source_collection") or "")

        # Vietnamese-cuisine query → prefer the curated vn_food collection
        # over multilingual matches in recipes_64k that drift to Pad Thai etc.
        if collection == self.VN_FOOD_COLLECTION and self._is_vn_food_query(normalized_query):
            bonus += 0.40

        if keywords:
            for keyword in keywords:
                keyword = keyword.lower()
                if name == keyword:
                    bonus += 0.35
                elif re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", name):
                    bonus += 0.12
            if collection == "food_fruit_vectors_768":
                bonus += 0.08

        return score + bonus

    def _normalize_query(self, query):
        text = unicodedata.normalize("NFKD", str(query or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return text.replace("đ", "d").lower()

    def _proper_noun_phrase(self, query):
        # Sequences of ≥2 Title-Cased ASCII words look like English dish/recipe
        # names (e.g. "Broiled Salmon Steaks"). When the user wraps such a name
        # in Vietnamese filler ("Cho mình thông tin về Broiled Salmon Steaks"),
        # embedding the full sentence drifts the vector off-target; pulling the
        # proper-noun phrase gives a precise retrieval anchor.
        matches = re.findall(
            r"\b([A-Z][a-zA-Z]+(?:\s+(?:[A-Z][a-zA-Z]+|and|with|of|in|the|a))+)\b",
            str(query or "")
        )
        if not matches:
            return None
        return max(matches, key=lambda m: (m.count(" "), len(m)))

    def _search_hits(self, query, top_k, collections=None, per_collection=None):
        isolated_entity = EntityExtractor.extract_food_entity(query)
        expanded_query = self._expand_query(query)
        keywords = self._query_keywords(query)
        normalized_query = self._normalize_query(query)
        proper_noun = self._proper_noun_phrase(query)

        # Priority: proper noun phrase > isolated food entity > expanded query
        embed_target = proper_noun or (isolated_entity if isolated_entity and len(isolated_entity) >= 3 else None) or expanded_query
        vector = self.text_embed.embed(embed_target)
        if vector is None:
            return []

        collections = collections or self._focused_nutrition_collections(query)
        # Floor of 6 so a specific-dish query has enough candidates per
        # collection for the title-match rerank to surface the exact match,
        # rather than competing with same-keyword neighbors at top_k=3.
        per_collection = per_collection or max(2, min(8, max(top_k, 6)))

        def _search_one(collection):
            results = []
            for hit in self.qdrant.search(
                collection_name=collection,
                vector=vector,
                top_k=per_collection
            ):
                payload = dict(hit.payload or {})
                payload.setdefault("source_collection", collection)
                hit.payload = payload
                results.append(hit)
            return results

        futures = [
            _QDRANT_SEARCH_EXECUTOR.submit(_search_one, collection)
            for collection in collections
        ]
        hits = []
        for future in futures:
            try:
                hits.extend(future.result())
            except Exception as exc:
                print("❌ Parallel collection search error:", exc)

        # Targeted secondary search against vn_food using only the dish
        # phrase(s) — the full-sentence embedding above misses curated VN
        # rows. Splitting on conjunctions surfaces every dish in compare
        # queries ("Chả giò và bánh xèo, cái nào nhiều dầu mỡ hơn?").
        vn_phrases = self._vn_dish_phrases(query, normalized_query=normalized_query)
        if vn_phrases and self.VN_FOOD_COLLECTION in collections:
            seen_ids = {(hit.id, str(hit.payload.get("source_collection") or "")) for hit in hits}
            for phrase in vn_phrases:
                vn_vector = self.text_embed.embed(phrase)
                if vn_vector is None:
                    continue
                try:
                    vn_hits = self.qdrant.search(
                        collection_name=self.VN_FOOD_COLLECTION,
                        vector=vn_vector,
                        top_k=per_collection,
                    )
                except Exception as exc:
                    print(f"❌ vn_food focused search error for {phrase!r}:", exc)
                    continue
                for hit in vn_hits:
                    payload = dict(hit.payload or {})
                    payload.setdefault("source_collection", self.VN_FOOD_COLLECTION)
                    hit.payload = payload
                    key = (hit.id, self.VN_FOOD_COLLECTION)
                    if key not in seen_ids:
                        seen_ids.add(key)
                        hits.append(hit)

        if not hits:
            return []

        # Neural Cross-Encoder Rerank with FlashRank
        reranker = FlashRankService.get_instance()
        reranked = reranker.rerank_hits(query=query, hits=hits, top_k=top_k)
        if reranked:
            return reranked

        # Fallback to score sort if reranker unavailable
        hits.sort(
            key=lambda hit: getattr(hit, "score", 0.0) or 0.0,
            reverse=True
        )
        return hits[:top_k]

    def run(self, query, top_k, trace, collections=None, per_collection=None):
        trace.add(
            "Generic RAG retrieval",
            "Embed query và tìm trong các collection text/nutrition/lifestyle hiện có.",
            detail="Bỏ qua collection không tồn tại trong Qdrant để giảm lỗi 404."
        )
        expanded_query = self._expand_query(query)
        keywords = self._query_keywords(query)
        if expanded_query != query:
            trace.add(
                "Query expansion",
                "Mở rộng query tiếng Việt sang keyword tiếng Anh để khớp dataset Qdrant.",
                evidence=keywords[:8]
            )

        selected = self._search_hits(query, top_k, collections=collections, per_collection=per_collection)
        if not selected:
            trace.add("Embedding failed", "Không tạo được vector query hoặc không có kết quả.", status="warning")
            return []

        collections = collections or self._text_collections()
        trace.add(
            "Generic RAG selected context",
            f"Chọn {len(selected)} context tốt nhất từ {len(collections)} collection khả dụng.",
            evidence=[CitationBuilder.display_label(hit.payload, fallback=hit.id) for hit in selected[:5]]
        )
        return [
            {
                "score": hit.score,
                "payload": hit.payload or {},
                "citation": CitationBuilder.from_payload(hit.payload or {})
            }
            for hit in selected
        ]

    def ingredient_comparison(self, query, top_k, trace):
        terms = self._comparison_terms(query)
        trace.add(
            "Ingredient comparison retrieval",
            "Tách từng thực phẩm/nguyên liệu rồi truy vấn các collection dinh dưỡng và text 768 chiều.",
            evidence=terms
        )

        if not terms:
            trace.add(
                "Open-ended comparison detected",
                "Không có thực phẩm cụ thể để truy vấn Qdrant; response generator sẽ hỏi rõ đối tượng hoặc nêu giả định thay vì semantic search nhiễu.",
                status="skipped"
            )
            return []

        buckets = []
        per_term = max(3, min(5, top_k))
        for term in terms:
            expanded_term = self._expand_query(term)
            trace.add(
                "Comparison sub-query",
                f"Tìm dữ liệu dinh dưỡng gần nhất cho `{term}`.",
                evidence=[expanded_term]
            )
            collections = self._focused_nutrition_collections(term)
            bucket = []
            for hit in self._search_hits(
                term,
                per_term,
                collections=collections,
                per_collection=2
            ):
                payload = dict(hit.payload or {})
                payload["comparison_term"] = term
                bucket.append({
                    "score": hit.score,
                    "payload": payload,
                    "comparison_term": term,
                    "citation": CitationBuilder.from_payload(payload)
                })
            buckets.append(bucket)

        merged = OrderedDict()
        cursor = 0
        while len(merged) < top_k and any(cursor < len(bucket) for bucket in buckets):
            for bucket in buckets:
                if cursor >= len(bucket):
                    continue
                item = bucket[cursor]
                payload = item.get("payload") or {}
                key = (
                    item.get("comparison_term"),
                    payload.get("source_collection"),
                    payload.get("source_row"),
                    payload.get("Name") or payload.get("name") or payload.get("title")
                )
                if key not in merged:
                    merged[key] = item
                if len(merged) >= top_k:
                    break
            cursor += 1

        results = list(merged.values())
        trace.add(
            "Comparison context prepared",
            f"Chuẩn hóa {len(results)} dòng dữ liệu để response generator tạo bảng so sánh.",
            evidence=[
                str((item.get("payload") or {}).get("Name") or (item.get("payload") or {}).get("name") or item.get("comparison_term"))
                for item in results[:5]
            ]
        )
        return results


class RecipeAgent:
    def __init__(self, recipe_rag=None):
        self.rag = recipe_rag or RecipeImageRAGService()

    def _food_keywords(self, query):
        normalized = unicodedata.normalize("NFKD", str(query or ""))
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.replace("đ", "d").replace("Đ", "D").lower()
        keywords = []
        for source, target in GenericRAGAgent.FOOD_SYNONYMS.items():
            if re.search(r"(?<![a-z0-9])" + re.escape(source) + r"(?![a-z0-9])", normalized):
                keywords.append(target)
        for target in sorted(set(GenericRAGAgent.FOOD_SYNONYMS.values()), key=len, reverse=True):
            if re.search(r"(?<![a-z0-9])" + re.escape(target.lower()) + r"(?![a-z0-9])", normalized):
                keywords.append(target)
        return list(dict.fromkeys(keywords))

    def _ingredient_hint(self, query):
        normalized = unicodedata.normalize("NFKD", str(query or ""))
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.replace("đ", "d").replace("Đ", "D")
        normalized = normalized.lower()
        keywords = self._food_keywords(query)
        if len(keywords) == 1:
            return keywords[0]
        if len(keywords) > 1:
            return None

        match = re.search(r"(?:co|voi|with|ingredient)\s+([a-z0-9\-\s]+)", normalized)
        if not match:
            return None
        hint = re.split(
            r",|\\. |\\?|\\b(?:goi y|bien tau|cong thuc|recipe|de|for|please)\\b",
            match.group(1)
        )[0]
        return hint.strip()[:80] or None

    def _recipe_search_query(self, query):
        normalized = unicodedata.normalize("NFKD", str(query or ""))
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.replace("đ", "d").replace("Đ", "D")
        normalized = normalized.lower()
        normalized = re.sub(
            r"\\b(?:cho toi|hay|please|toi muon|can|tim|cong thuc|recipe|"
            r"cach lam|instructions|nau|mon|món|giup toi|cho minh)\\b",
            " ",
            normalized
        )
        normalized = re.sub(r"\\s+", " ", normalized).strip(" .:;!?-")
        if not normalized:
            return query
        keywords = self._food_keywords(query)
        keyword_text = f"\nEnglish ingredient keywords: {', '.join(keywords)}" if keywords else ""
        return f"recipe {normalized}{keyword_text}"

    def _recipe_match_score(self, hit, keywords):
        score = float(getattr(hit, "score", 0) or 0)
        if not keywords:
            return score

        payload = hit.payload or {}
        text = " ".join([
            str(payload.get("title") or ""),
            str(payload.get("recipe_name") or ""),
            str(payload.get("ingredients_search") or ""),
            str(payload.get("cleaned_ingredients") or ""),
            str(payload.get("ingredients") or ""),
            str(payload.get("directions") or ""),
            str(payload.get("image_caption") or ""),
        ]).lower()

        bonus = 0
        for keyword in keywords:
            keyword = keyword.lower()
            if re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text):
                bonus += 0.18
            elif keyword in text:
                bonus += 0.08
        return score + bonus

    def _comparison_terms(self, query):
        normalized = unicodedata.normalize("NFKD", str(query or ""))
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.replace("đ", "d").replace("Đ", "D")
        normalized = normalized.lower()

        match = re.search(
            r"(?:so sanh|compare|comparison|khac nhau giua)\s+(.+)",
            normalized
        )
        segment = match.group(1) if match else normalized
        segment = re.sub(
            r"\b(mon|cac mon|món|dish|food|nguyen lieu|thuc pham|giua|loai)\b",
            " ",
            segment
        )
        parts = re.split(r"\s+(?:va|voi|and|vs|versus)\s+|[,/]+", segment)

        terms = []
        for part in parts:
            term = re.sub(r"\s+", " ", part).strip(" .:;!?-")
            if len(term) < 2:
                continue
            if term not in terms:
                terms.append(term[:80])
        return terms[:4]

    RECIPE_TEXT_COLLECTIONS = (
        "recipes_vectors_768",
        "food_recipes_vectors_768",
        "recipes_64k_vectors_768",
        "food_recipe_images_text_768",
    )

    def _parse_ingredient_list(self, value):
        if isinstance(value, list):
            return value
        if not value:
            return []
        text = str(value)
        try:
            import ast
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [part.strip() for part in re.split(r",\s*", text) if part.strip()]

    def _search_recipe_text_collections(self, query, top_k):
        vector = self.rag.text_embed.embed(query)
        if vector is None:
            return []

        def _search_one(collection):
            results = []
            try:
                response = self.rag.client.search(
                    collection_name=collection,
                    query_vector=vector,
                    limit=top_k,
                    with_payload=True
                )
            except Exception as exc:
                print(f"❌ Recipe text search error ({collection}):", exc)
                return results
            for hit in response:
                payload = dict(hit.payload or {})
                payload.setdefault("source_collection", collection)
                hit.payload = payload
                results.append(hit)
            return results

        futures = [
            _QDRANT_SEARCH_EXECUTOR.submit(_search_one, collection)
            for collection in self.RECIPE_TEXT_COLLECTIONS
        ]
        hits = []
        for future in futures:
            hits.extend(future.result())
        return hits

    def _format_text_recipe_hits(self, hits):
        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append({
                "score": hit.score,
                "title": payload.get("recipe_name") or payload.get("title"),
                "ingredients": self._parse_ingredient_list(
                    payload.get("cleaned_ingredients_list") or payload.get("ingredients")
                ),
                "instructions": payload.get("directions") or payload.get("instructions"),
                "image_name": payload.get("image_name"),
                "image_file": payload.get("image_file"),
                "image_path": payload.get("image_path"),
                "image_caption": payload.get("image_caption"),
                "citation": CitationBuilder.from_payload(payload),
                "payload": payload
            })
        return results

    def recipe_reasoning(self, query, top_k, trace):
        ingredient = self._ingredient_hint(query)
        search_query = self._recipe_search_query(query)
        keywords = self._food_keywords(query)
        trace.add(
            "Recipe reasoning retrieval",
            "Tìm công thức bằng vector text 768 chiều trên multimodal + recipe text collections.",
            evidence=[f"search_query={search_query}"] + ([f"ingredient_filter={ingredient}"] if ingredient else [])
        )

        over_fetch = max(top_k, top_k * 4 if keywords else top_k)
        primary_hits = list(self.rag.search_text(
            query=search_query,
            top_k=over_fetch,
            ingredient=ingredient
        ))
        text_hits = self._search_recipe_text_collections(search_query, over_fetch)

        combined = primary_hits + text_hits
        combined.sort(
            key=lambda hit: self._recipe_match_score(hit, keywords),
            reverse=True
        )
        combined = combined[:top_k]

        results = []
        for hit in combined:
            collection = (hit.payload or {}).get("source_collection")
            if collection in self.RECIPE_TEXT_COLLECTIONS:
                results.extend(self._format_text_recipe_hits([hit]))
            else:
                results.extend(self.rag.format_hits([hit]))
        trace.add(
            "Recipe context selected",
            f"Chọn {len(results)} công thức liên quan để đưa vào response generator.",
            evidence=[item.get("title") for item in results[:5] if item.get("title")],
            detail="Rerank ưu tiên công thức chứa nguyên liệu chính đã nhận diện trong câu hỏi."
        )
        return results

    def image_retrieval(self, query, top_k, trace):
        ingredient = self._ingredient_hint(query)
        trace.add(
            "Image retrieval",
            "Tìm ảnh công thức bằng named vector `image` 512 chiều và metadata filter nếu có.",
            evidence=[f"ingredient_filter={ingredient}"] if ingredient else []
        )
        hits = self.rag.search_images(
            query=query,
            top_k=top_k,
            ingredient=ingredient
        )
        results = self.rag.format_hits(hits)
        trace.add(
            "Image candidates selected",
            f"Chọn {len(results)} ảnh/công thức phù hợp nhất.",
            evidence=[item.get("image_file") or item.get("image_name") for item in results[:5]]
        )
        return results

    def ingredient_comparison(self, query, top_k, trace):
        terms = self._comparison_terms(query)
        trace.add(
            "Ingredient comparison retrieval",
            "Tách từng đối tượng cần so sánh rồi tìm context riêng bằng text vector.",
            evidence=terms
        )

        if not terms:
            results = self.recipe_reasoning(query, top_k, trace)
        else:
            buckets = []
            per_term = max(2, min(4, top_k))
            for term in terms:
                trace.add(
                    "Comparison sub-query",
                    f"Tìm dữ liệu liên quan đến `{term}`.",
                    evidence=[term]
                )
                hits = self.rag.search_text(query=term, top_k=per_term)
                bucket = []
                for item in self.rag.format_hits(hits):
                    item["comparison_term"] = term
                    bucket.append(item)
                buckets.append(bucket)

            merged = OrderedDict()
            cursor = 0
            while len(merged) < top_k and any(cursor < len(bucket) for bucket in buckets):
                for bucket in buckets:
                    if cursor >= len(bucket):
                        continue
                    item = bucket[cursor]
                    payload = item.get("payload") or {}
                    key = payload.get("source_row") or item.get("title") or f"{item.get('comparison_term')}:{len(merged)}"
                    if key not in merged:
                        merged[key] = item
                    if len(merged) >= top_k:
                        break
                cursor += 1
            results = list(merged.values())

        trace.add(
            "Comparison context prepared",
            "Chuẩn hóa danh sách nguyên liệu để response generator tạo bảng so sánh.",
            evidence=[item.get("title") for item in results[:5] if item.get("title")]
        )
        return results

    def multi_hop(self, query, top_k, trace):
        trace.add(
            "Multi-hop step 1",
            "Tìm ảnh/recipe candidates trước để lấy món và citation gốc."
        )
        image_results = self.image_retrieval(query, max(2, top_k // 2), trace)

        ingredient_terms = []
        for item in image_results:
            ingredients = item.get("ingredients") or []
            if isinstance(ingredients, list):
                ingredient_terms.extend(ingredients[:4])

        enriched_query = " ".join([
            query,
            " ".join(ingredient_terms[:12])
        ]).strip()
        trace.add(
            "Multi-hop step 2",
            "Extract nguyên liệu từ kết quả bước 1 và mở rộng query để tìm công thức/biến tấu.",
            evidence=ingredient_terms[:8]
        )

        recipe_hits = self.rag.search_text(
            query=enriched_query,
            top_k=top_k,
        )
        recipe_results = self.rag.format_hits(recipe_hits)

        merged = OrderedDict()
        for item in image_results + recipe_results:
            key = item.get("payload", {}).get("source_row") or item.get("title")
            merged[key] = item

        results = list(merged.values())[:top_k]
        trace.add(
            "Multi-hop context merged",
            f"Gộp {len(results)} kết quả từ image retrieval và recipe reasoning.",
            evidence=[item.get("title") for item in results[:5] if item.get("title")]
        )
        return results


class AgenticRAG:
    def __init__(self):
        self.router = AgentRouter()
        self.recipe_agent = RecipeAgent()
        self.generic_agent = None
        self.response_generator = AgenticResponseGenerator()
        self.cache = RedisCache()

    def _generic_agent(self):
        if self.generic_agent is None:
            self.generic_agent = GenericRAGAgent()
        return self.generic_agent

    def _context_from_results(self, results):
        context = []
        for result in results:
            payload = dict(result.get("payload") or result)
            if result.get("comparison_term"):
                payload["comparison_term"] = result["comparison_term"]
            if payload:
                context.append(payload)
        return context

    def _is_pure_affirmation(self, query):
        normalized = self.router._normalize(query).strip()
        if not normalized or len(normalized) > 12:
            return False
        affirmations = {
            "co", "yes", "ya", "yeah", "yep", "ok", "okay", "okie",
            "u", "um", "uhm", "vang", "da", "duoc", "duoc nha",
            "duoc roi", "co nhe", "yes please", "lam di", "go", "go ahead",
        }
        return normalized in affirmations

    def _is_vague_followup(self, query, is_follow_up, conversation_context):
        if not conversation_context or not is_follow_up:
            return False
        normalized = self.router._normalize(query)
        if len(normalized) > 60:
            return False

        suggest_phrases = [
            "goi y", "de xuat", "co the goi y", "co the de xuat",
            "suggest", "recommend", "co the cho", "cho toi them",
            "noi them", "noi ro hon", "them thong tin", "co the noi",
            "gi khac", "khac khong", "co gi khac", "tuong tu",
            "lam thu", "thu xem", "lam giup", "lam cho toi",
            "thu cho toi", "hay lam thu", "hay lam", "lam di",
            "try it", "show me", "do it", "give me one",
        ]
        has_suggest = any(phrase in normalized for phrase in suggest_phrases)
        if not has_suggest:
            return False

        topic_terms = list(GenericRAGAgent.FOOD_SYNONYMS.keys()) + [
            "calo", "kcal", "calorie", "macro", "protein", "carb", "fat",
            "fiber", "chat xo", "tdee", "bmr", "bua trua", "bua toi",
            "bua sang", "lunch", "dinner", "breakfast", "thuc don",
            "meal plan", "diet",
        ]
        has_topic = any(
            re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", normalized)
            for term in topic_terms
        )
        return not has_topic

    def _last_assistant_question(self, conversation_context):
        """Pull the final assistant turn's question from conversation context.
        Used to anchor short affirmations like 'có' on what the assistant just asked."""
        if not conversation_context:
            return None
        text = str(conversation_context)
        last_assistant = None
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("Assistant:"):
                last_assistant = stripped[len("Assistant:"):].strip()
        if not last_assistant:
            return None
        # Take the last sentence that ends with `?`
        sentences = re.split(r"(?<=[.?!])\s+", last_assistant)
        for sentence in reversed(sentences):
            if "?" in sentence:
                return sentence.strip()
        return last_assistant[-220:]

    def _extract_recent_topic(self, conversation_context):
        if not conversation_context:
            return None
        text = str(conversation_context)
        last_user = None
        last_assistant = None
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("User:"):
                last_user = stripped[len("User:"):].strip()
            elif stripped.startswith("Assistant:"):
                last_assistant = stripped[len("Assistant:"):].strip()
        return last_user or last_assistant

    def _retrieval_query(self, query, conversation_context=None, is_follow_up=None):
        if not conversation_context:
            return query

        resolved_entity = EntityExtractor.extract_food_entity(query, conversation_context=conversation_context)
        if resolved_entity and resolved_entity.lower() not in query.lower():
            return f"{query} (Món tham chiếu: {resolved_entity})"

        return query

    def _cache_key(
        self,
        query,
        top_k,
        intent,
        session_id=None,
        conversation_context=None,
        user_profile_text=None,
    ):
        context_digest = hashlib.sha1(
            str(conversation_context or "")[-1600:].encode("utf-8")
        ).hexdigest()[:12]
        # Profile drives personalization (allergies, goals, kcal target). Two
        # users asking the same query must NOT share an answer if their
        # profiles differ — fold the profile into the key.
        profile_digest = hashlib.sha1(
            str(user_profile_text or "").encode("utf-8")
        ).hexdigest()[:12]
        raw = "|".join([
            str(session_id or "global"),
            self.router._normalize(query),
            str(top_k),
            str(intent or ""),
            context_digest,
            profile_digest,
        ])
        return "agentic_rag:v9:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_get(self, key):
        cached = self.cache.get(key)
        if not cached:
            return None
        try:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            return json.loads(cached)
        except Exception:
            return None

    def _cache_set(self, key, response):
        compact = {
            "type": response.get("type"),
            "intent": response.get("intent"),
            "answer": response.get("answer"),
            "citations": response.get("citations", [])[:6],
            "context_used": response.get("context_used", [])[:2],
            "trace": response.get("trace", [])[:8],
            "session_id": response.get("session_id"),
        }
        self.cache.set(
            key,
            json.dumps(compact, ensure_ascii=False),
            ttl=settings.AGENTIC_CACHE_TTL
        )

    MEAL_TYPE_PATTERNS = {
        "breakfast": ("bua sang", "an sang", "buoi sang", "breakfast", "morning meal"),
        "lunch": ("bua trua", "an trua", "buoi trua", "lunch", "midday meal"),
        "dinner": ("bua toi", "an toi", "buoi toi", "dinner", "supper", "evening meal"),
    }

    MEAL_TYPE_SEEDS = {
        "breakfast": (
            "breakfast morning meal oats oatmeal porridge eggs scrambled boiled omelet "
            "Greek yogurt yogurt cottage cheese fruit berries banana apple "
            "whole grain toast pancakes waffles granola muesli milk smoothie protein"
        ),
        "lunch": (
            "lunch midday meal salad sandwich wrap rice bowl quinoa bowl "
            "chicken breast tuna salmon turkey vegetables soup beans lentils "
            "brown rice whole grain pasta protein"
        ),
        "dinner": (
            "dinner evening meal chicken breast salmon lean beef tofu fish shrimp "
            "vegetables broccoli spinach rice quinoa pasta soup stew steamed grilled protein"
        ),
    }

    GENERIC_MEAL_SEED = (
        "meal plan high protein low carb calories protein carbohydrates fat serving "
        "chicken breast egg tuna salmon shrimp lean beef tofu Greek yogurt cottage cheese vegetables salad"
    )

    BEVERAGE_SLOT_SEED = (
        "beverage drink water tea green tea unsweetened tea coffee black coffee milk skim milk "
        "soy milk almond milk oat milk smoothie protein shake fruit juice orange juice"
    )

    SLOT_SUBSEEDS = {
        "breakfast": [
            "oatmeal porridge whole grain cereal granola muesli",
            "scrambled eggs omelet boiled egg poached egg",
            "Greek yogurt cottage cheese plain yogurt parfait",
            "whole grain toast bread bagel sandwich avocado",
            "fresh fruit berries banana apple orange",
            "smoothie protein shake milk soy almond oat",
            "pancakes waffles french toast crepes",
        ],
        "lunch": [
            "grilled chicken breast turkey lean meat",
            "tuna salmon fish shrimp seafood",
            "rice bowl quinoa brown rice farro",
            "salad greens spinach kale romaine arugula",
            "soup stew lentil bean broth minestrone",
            "sandwich wrap tortilla pita falafel",
            "tofu tempeh beans legumes chickpeas",
        ],
        "dinner": [
            "grilled chicken breast lean white meat",
            "salmon fish baked steamed cod tilapia",
            "lean beef sirloin steak ground beef",
            "tofu paneer plant based protein",
            "vegetables broccoli cauliflower zucchini bell pepper",
            "rice quinoa whole grain barley",
            "pasta spaghetti penne whole wheat",
            "soup stew low sodium broth chowder",
        ],
        "beverage": [
            "water sparkling mineral lemon water",
            "green tea black tea herbal tea unsweetened",
            "coffee black americano espresso latte",
            "milk skim low fat soy almond oat",
            "smoothie fruit smoothie protein shake",
            "fresh juice orange apple beet vegetable",
        ],
    }

    HORIZON_NUMBER_PATTERNS = (
        (r"(\d+)\s*ngay", 1),
        (r"(\d+)\s*day", 1),
        (r"(\d+)\s*tuan", 7),
        (r"(\d+)\s*week", 7),
        (r"(\d+)\s*thang", 30),
        (r"(\d+)\s*month", 30),
    )

    HORIZON_WORD_PATTERNS = (
        (r"(?<![a-z0-9])(?:mot|one|ca|whole|nguyen)\s*thang(?![a-z0-9])", 30),
        (r"(?<![a-z0-9])(?:mot|one|ca|whole|nguyen)\s*month(?![a-z0-9])", 30),
        (r"(?<![a-z0-9])(?:mot|one|ca|whole|nguyen)\s*tuan(?![a-z0-9])", 7),
        (r"(?<![a-z0-9])(?:mot|one|ca|whole|nguyen)\s*week(?![a-z0-9])", 7),
    )

    def _meal_type(self, query):
        normalized = _normalize_for_topic(query)
        for meal_type, phrases in self.MEAL_TYPE_PATTERNS.items():
            if _topic_phrase_matches(normalized, phrases):
                return meal_type
        return None

    def _plan_horizon_days(self, query):
        normalized = _normalize_for_topic(query)
        max_days = 1
        for pattern, multiplier in self.HORIZON_NUMBER_PATTERNS:
            for match in re.finditer(pattern, normalized):
                try:
                    days = int(match.group(1)) * multiplier
                except ValueError:
                    continue
                if days > max_days:
                    max_days = days
        if max_days == 1:
            for pattern, days in self.HORIZON_WORD_PATTERNS:
                if re.search(pattern, normalized):
                    if days > max_days:
                        max_days = days
        return min(max_days, 90)

    def _numeric_metric(self, payload, keys):
        """Look up first numeric value among `keys` in payload.

        Tries top-level fields first, then falls back to nested `nutrition` dict
        (used by Nutrition5k payloads where macros live under `nutrition.protein_g`).
        Accepts both numeric values and embedded numbers in strings (e.g. "12.4g").
        """
        if not payload:
            return None
        nested = payload.get("nutrition") if isinstance(payload, dict) else None
        if not isinstance(nested, dict):
            nested = None

        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                if nested is not None:
                    value = nested.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, (int, float)):
                return float(value)
            match = re.search(r"-?\d+(?:\.\d+)?", str(value))
            if match:
                return float(match.group())
        return None

    def _meal_planning_results(self, results, top_k, trace, strict=True):
        blocked_terms = [
            "babyfood", "baby food", "dressing", "drsng", "sauce",
            "not included", "dry mix", "meal kits"
        ]
        ranked = []
        for item in results:
            payload = item.get("payload") or {}
            name = str(
                payload.get("food")
                or payload.get("name")
                or payload.get("Shrt_Desc")
                or payload.get("title")
                or payload.get("recipe_name")
                or payload.get("ingredient_name")
                or ""
            )
            normalized_name = self.router._normalize(name)
            if any(term in normalized_name for term in blocked_terms):
                continue

            protein = self._numeric_metric(payload, MACRO_PROTEIN_KEYS)
            carbs = self._numeric_metric(payload, MACRO_CARBS_KEYS)
            fat = self._numeric_metric(payload, MACRO_FAT_KEYS)
            calories = self._numeric_metric(payload, MACRO_CALORIE_KEYS)
            if strict:
                if protein is None or carbs is None or calories is None:
                    continue
            else:
                macro_count = sum(1 for value in (protein, carbs, fat) if value is not None)
                if calories is None and macro_count == 0:
                    continue

            nutrition_score = (protein or 0) - ((carbs or 0) * 0.35) - ((fat or 0) * 0.1)
            retrieval_score = float(item.get("score") or 0)
            ranked.append((nutrition_score + retrieval_score, item))

        ranked.sort(key=lambda value: value[0], reverse=True)
        selected = [item for _, item in ranked[:top_k]]
        if selected:
            trace.add(
                "Meal planning context filtered",
                "Lọc context theo protein, carb và loại bỏ payload nhiễu trước khi sinh câu trả lời.",
                evidence=[
                    str((item.get("payload") or {}).get("food") or (item.get("payload") or {}).get("name") or (item.get("payload") or {}).get("Shrt_Desc"))
                    for item in selected[:5]
                ]
            )
            return selected

        trace.add(
            "Meal planning context filtered",
            "Không có ứng viên đủ dữ liệu macro sau khi lọc; giữ context retrieval ban đầu để model hỏi thêm.",
            status="warning"
        )
        return results[:top_k]

    def _build_food_confidence(self, results):
        """Compute per-item confidence (high/medium/low) for the front-end badge.
        Score = macro completeness (kcal + P + C + F) + retrieval score + dataset reputation."""
        if not results:
            return []

        macro_keys = {
            "calories": MACRO_CALORIE_KEYS,
            "protein": MACRO_PROTEIN_KEYS,
            "carbs": MACRO_CARBS_KEYS,
            "fat": MACRO_FAT_KEYS,
        }
        trusted_collections = {
            "food_nutrition_vectors_768",
            "food_common_vectors_768",
            "food_fruit_vectors_768",
            "nutrition5k_vectors_768",
            "food_nutrition_dev_vectors_768",
            "food_global_10k_vectors_768",
        }

        confidences = []
        for result in results:
            payload = result.get("payload") or {}
            name = (
                payload.get("name")
                or payload.get("food")
                or payload.get("Shrt_Desc")
                or payload.get("title")
                or payload.get("recipe_name")
                or payload.get("food_name")
                or payload.get("ingredient_name")  # nutrition5k
                or payload.get("dish_name")
            )
            if not name:
                continue

            macro_present = sum(
                1
                for keys in macro_keys.values()
                if self._numeric_metric(payload, keys) is not None
            )
            retrieval_score = float(result.get("score") or 0)
            collection = str(payload.get("source_collection") or "")
            trusted = collection in trusted_collections

            score = macro_present  # 0..4
            if retrieval_score >= 0.55:
                score += 1
            if trusted:
                score += 1

            if score >= 5:
                level = "high"
            elif score >= 3:
                level = "medium"
            else:
                level = "low"

            reasons = []
            reasons.append(f"{macro_present}/4 macros có dữ liệu")
            if retrieval_score:
                reasons.append(f"retrieval score {retrieval_score:.2f}")
            if trusted:
                reasons.append("nguồn được xếp hạng cao")
            elif collection:
                reasons.append(f"nguồn {collection}")

            confidences.append({
                "name": str(name).strip(),
                "level": level,
                "macros_present": macro_present,
                "retrieval_score": round(retrieval_score, 3),
                "source_collection": collection or None,
                "reasons": reasons,
            })

        return confidences

    def _format_user_profile(self, user_profile):
        if not user_profile or not isinstance(user_profile, dict):
            return None
        parts = []
        field_map = [
            ("gender", "Giới tính"),
            ("age", "Tuổi"),
            ("height", "Chiều cao (cm)"),
            ("weight", "Cân nặng (kg)"),
            ("activityLevel", "Mức vận động"),
            ("dailyCalories", "Mục tiêu kcal/ngày"),
            ("targetWeight", "Cân nặng mục tiêu (kg)"),
            ("goal", "Mục tiêu"),
        ]
        for key, label in field_map:
            value = user_profile.get(key)
            if value is not None and value != "":
                parts.append(f"{label}: {value}")

        prefs = user_profile.get("foodPreferences") or []
        if isinstance(prefs, list) and prefs:
            buckets = {"favorite": [], "avoided": [], "disliked": [], "allergy": []}
            for pref in prefs:
                if not isinstance(pref, dict):
                    continue
                ptype = pref.get("type")
                name = (pref.get("foodName") or "").strip()
                if not name or ptype not in buckets:
                    continue
                if len(buckets[ptype]) < 8:
                    buckets[ptype].append(name)
            label_map = [
                ("favorite", "Món hay ăn"),
                ("avoided", "Né"),
                ("disliked", "Không thích"),
                ("allergy", "Dị ứng (TUYỆT ĐỐI không gợi ý)"),
            ]
            for key, label in label_map:
                if buckets[key]:
                    parts.append(f"{label}: {', '.join(buckets[key])}")
        return "\n".join(parts) if parts else None

    async def run(
        self,
        query,
        top_k=6,
        intent=None,
        session_id=None,
        conversation_context=None,
        is_follow_up=None,
        user_profile=None
    ):
        trace = AgenticTrace()

        # Pre-classify guards — refuse / clarify before retrieval so we don't
        # leak RAG context into harmful or empty queries, and don't fabricate
        # personal data from random vector hits.
        stripped_query = (query or "").strip()
        if len(re.sub(r"[\s\.,;:!?\"'`()\[\]{}\-—_]+", "", stripped_query)) < 3:
            trace.add(
                "Reject empty/too-short query",
                "Câu hỏi không đủ nội dung để truy xuất hoặc trả lời.",
                evidence=[query],
                status="warning"
            )
            return {
                "type": "agentic_rag",
                "intent": "clarify",
                "answer": (
                    "Mình chưa nhận được câu hỏi rõ ràng. Bạn nhập tên món ăn, "
                    "câu hỏi về dinh dưỡng, hoặc mục tiêu (giảm cân/tăng cơ...) "
                    "để mình hỗ trợ chính xác hơn nhé."
                ),
                "results": [], "citations": [], "context_used": [],
                "trace": trace.steps, "session_id": session_id, "cache_hit": False
            }

        if self.router.looks_harmful(query):
            trace.add(
                "Refuse harmful request",
                "Câu hỏi chứa từ khóa có hại / phi pháp — từ chối thẳng, không retrieve.",
                evidence=[query],
                status="warning"
            )
            return {
                "type": "agentic_rag",
                "intent": "refuse_harm",
                "answer": (
                    "Mình không thể hỗ trợ yêu cầu này. CalAI chỉ tư vấn về "
                    "dinh dưỡng, thực phẩm và sức khỏe. Nếu bạn đang gặp khó "
                    "khăn về sức khỏe tinh thần, hãy liên hệ đường dây hỗ trợ "
                    "tâm lý uy tín ở địa phương."
                ),
                "results": [], "citations": [], "context_used": [],
                "trace": trace.steps, "session_id": session_id, "cache_hit": False
            }

        # Profile lookup without real profile → refuse deterministically.
        # Avoids the LLM saying "you usually eat fried chicken and Gerolsteiner"
        # when no preferences are loaded.
        has_real_profile = bool(
            user_profile and isinstance(user_profile, dict) and (
                user_profile.get("foodPreferences")
                or user_profile.get("dailyCalories")
                or user_profile.get("goal")
            )
        )
        if self.router.looks_profile_lookup(query) and not has_real_profile:
            trace.add(
                "Profile lookup without profile",
                "User hỏi về sở thích/lịch sử ăn uống nhưng hệ thống chưa có hồ sơ — không bịa.",
                evidence=[query],
                status="warning"
            )
            return {
                "type": "agentic_rag",
                "intent": "profile_missing",
                "answer": (
                    "Mình chưa có hồ sơ ăn uống của bạn nên không thể liệt kê "
                    "các món bạn hay ăn. Bạn có thể:\n"
                    "- Cập nhật mục **Diet Goals** và **Profile Setup** trong app "
                    "để mình ghi nhận sở thích, mục tiêu và dị ứng.\n"
                    "- Hoặc nói trực tiếp một vài món bạn hay ăn để mình tư vấn "
                    "ngay trong cuộc trò chuyện này."
                ),
                "results": [], "citations": [], "context_used": [],
                "trace": trace.steps, "session_id": session_id, "cache_hit": False
            }

        routed_intent = self.router.classify(query, forced_intent=intent)
        trace.add(
            "Agent Router",
            f"Phân loại query thành intent `{routed_intent}`.",
            evidence=[query]
        )

        profile_text = self._format_user_profile(user_profile)
        if profile_text:
            trace.add(
                "User profile",
                "Đã nhận thông tin cá nhân từ hồ sơ user để cá nhân hóa câu trả lời.",
                evidence=profile_text.split("\n")[:6]
            )

        # Cache key digests session_id + normalized query + intent + a hash of
        # the last 1.6 KB of conversation context (see _cache_key), so it is
        # safe to cache per-session and per-follow-up. We only opt out when the
        # user is clearly mid-conversation about a freshly mutating profile.
        use_cache = bool(settings.AGENTIC_CACHE_ENABLED)
        cache_key = self._cache_key(
            query=query,
            top_k=top_k,
            intent=routed_intent,
            session_id=session_id,
            conversation_context=conversation_context,
            user_profile_text=profile_text,
        )
        cached = self._cache_get(cache_key) if use_cache else None
        if cached:
            cached_trace = [
                {
                    "step": 1,
                    "title": "Agent Router",
                    "text": f"Phân loại query thành intent `{routed_intent}`.",
                    "status": "done",
                    "evidence": [query],
                    "detail": None
                },
                {
                    "step": 2,
                    "title": "Redis agentic cache",
                    "text": "Trả kết quả từ cache theo session/query/context digest.",
                    "status": "done",
                    "evidence": [f"session_id={session_id}"] if session_id else [],
                    "detail": "Cache chỉ dùng cho truy vấn lặp lại cùng ngữ cảnh để tiết kiệm Redis và giảm độ trễ."
                }
            ]
            cached["trace"] = cached_trace
            cached["cache_hit"] = True
            cached.setdefault("results", [])
            return cached

        if conversation_context and self._is_pure_affirmation(query):
            anchor = self._last_assistant_question(conversation_context)
            if anchor:
                trace.add(
                    "Affirmation detected",
                    "Câu trả lời ngắn dạng đồng ý — gắn vào câu hỏi cuối của assistant để retrieval có ngữ cảnh.",
                    evidence=[query, f"anchor={anchor[:120]}"],
                    detail="Tránh trường hợp model bỏ context khi user chỉ trả lời 'có'."
                )
                query = f"{anchor.rstrip('?').strip()} - user xác nhận đồng ý ({query})"

        if self._is_vague_followup(query, is_follow_up, conversation_context):
            recent_topic = self._extract_recent_topic(conversation_context)
            topic_hint = recent_topic[:160] if recent_topic else "chủ đề vừa rồi"
            trace.add(
                "Vague follow-up detected",
                "Câu hỏi quá ngắn/chung để truy xuất chính xác nên agent xin user nói rõ thay vì gợi ý món ngẫu nhiên.",
                evidence=[query, f"topic_hint={topic_hint}"],
                detail="Tránh hallucination khi follow-up không nêu món/chủ đề cụ thể."
            )
            clarification = (
                f"Bạn muốn mình gợi ý cụ thể về điều gì liên quan đến \"{topic_hint}\"?\n\n"
                "Ví dụ:\n"
                "- Các thực phẩm tương tự (dinh dưỡng/calorie gần giống)\n"
                "- Cách kết hợp vào bữa ăn (sáng/trưa/tối)\n"
                "- Khẩu phần phù hợp với mục tiêu (giảm cân, tăng cơ...)\n\n"
                "Bạn cho mình biết hướng nào để mình tra số liệu chính xác nhé."
            )
            return {
                "type": "agentic_rag",
                "intent": routed_intent,
                "answer": clarification,
                "results": [],
                "citations": [],
                "context_used": [],
                "trace": trace.steps,
                "session_id": session_id,
                "cache_hit": False
            }

        retrieval_query = self._retrieval_query(
            query,
            conversation_context=conversation_context,
            is_follow_up=is_follow_up
        )
        if conversation_context:
            trace.add(
                "Conversation memory",
                "Đã nhận ngữ cảnh hội thoại từ backend và chỉ dùng để hiểu câu hỏi nối tiếp.",
                evidence=[f"session_id={session_id}"] if session_id else [],
                detail="Retrieval query được mở rộng bằng history khi câu hỏi hiện tại là follow-up."
            )

        if routed_intent == "image_retrieval":
            results = self.recipe_agent.image_retrieval(retrieval_query, top_k, trace)
        elif routed_intent == "recipe_reasoning":
            results = self.recipe_agent.recipe_reasoning(retrieval_query, top_k, trace)
        elif routed_intent == "ingredient_comparison":
            results = self._generic_agent().ingredient_comparison(retrieval_query, top_k, trace)
        elif routed_intent == "multi_hop":
            results = self.recipe_agent.multi_hop(retrieval_query, top_k, trace)
        elif routed_intent == "meal_planning":
            meal_type = self._meal_type(query)
            horizon_days = self._plan_horizon_days(query)
            multi_day = horizon_days >= 2

            if meal_type:
                slots = [meal_type]
            elif multi_day:
                slots = ["breakfast", "lunch", "dinner", "beverage"]
            else:
                slots = ["breakfast", "lunch", "dinner", "beverage"]

            full_day_plan = not meal_type
            trace.add(
                "Meal planning intent",
                f"Lập kế hoạch bữa ăn (horizon ≈ {horizon_days} ngày, slots = {slots}). Agent truy xuất dữ liệu dinh dưỡng cho từng bữa trước khi sinh câu trả lời.",
                evidence=[f"meal_type={meal_type or 'unspecified'}", f"horizon_days={horizon_days}"],
                detail=(
                    "Đa-bữa: với mỗi slot chạy nhiều sub-seed (oats/eggs/yogurt/...) để lấy món đa dạng thay vì cluster theo 1 vector."
                    if multi_day else
                    ("Đơn-ngày full combo: chạy retrieval riêng cho 4 slot (sáng/trưa/tối/đồ uống) để LLM có ≥3 món/bữa thay vì 1."
                     if full_day_plan else "Đơn-bữa: 1 sub-query với seed của bữa được hỏi.")
                )
            )

            generic_agent = self._generic_agent()
            collections = generic_agent._nutrition_collections()

            aggregated = []
            seen_keys = set()

            def _record(item, slot_label):
                payload = dict(item.get("payload") or {})
                name = (
                    payload.get("name")
                    or payload.get("food")
                    or payload.get("Shrt_Desc")
                    or payload.get("title")
                    or payload.get("recipe_name")
                    or payload.get("ingredient_name")
                )
                key = (
                    payload.get("source_collection"),
                    payload.get("source_row"),
                    str(name).strip().lower() if name else None,
                )
                if key in seen_keys:
                    return
                seen_keys.add(key)
                payload.setdefault("meal_slot", slot_label or "general")
                new_item = dict(item)
                new_item["payload"] = payload
                aggregated.append(new_item)

            if multi_day or full_day_plan:
                per_subseed_top_k = 4
                per_collection_for_subseed = 2
                sub_seeds_per_slot = 3 if multi_day else 2
                sub_seed_jobs = []
                for slot in slots:
                    sub_seeds = self.SLOT_SUBSEEDS.get(slot, [])[:sub_seeds_per_slot]
                    if not sub_seeds:
                        sub_seeds = [
                            self.BEVERAGE_SLOT_SEED if slot == "beverage"
                            else self.MEAL_TYPE_SEEDS.get(slot, self.GENERIC_MEAL_SEED)
                        ]
                    for sub_seed in sub_seeds:
                        sub_seed_jobs.append(
                            (slot, f"{retrieval_query}\n{sub_seed}")
                        )

                # Fan out sub-seeds via the agent pool; each job further fans
                # collection searches out via the search pool, so the two
                # layers don't deadlock on a single executor.
                sub_futures = [
                    _AGENT_FANOUT_EXECUTOR.submit(
                        generic_agent.run,
                        sub_query,
                        per_subseed_top_k,
                        trace,
                        collections=collections,
                        per_collection=per_collection_for_subseed,
                    )
                    for _, sub_query in sub_seed_jobs
                ]
                for (slot, _), future in zip(sub_seed_jobs, sub_futures):
                    try:
                        sub_results = future.result()
                    except Exception as exc:
                        print(f"❌ Meal planning sub-seed error ({slot}):", exc)
                        continue
                    for item in sub_results:
                        _record(item, slot)
                trace.add(
                    "Meal planning aggregation",
                    f"Đã gom {len(aggregated)} món duy nhất từ {sum(min(sub_seeds_per_slot, len(self.SLOT_SUBSEEDS.get(s, [s]))) for s in slots)} sub-seed × {len(slots)} slot.",
                    evidence=[
                        str((item.get('payload') or {}).get('name') or (item.get('payload') or {}).get('food') or (item.get('payload') or {}).get('Shrt_Desc'))
                        for item in aggregated[:8]
                    ]
                )
                if multi_day:
                    target_count = max(top_k, min(60, horizon_days * 4))
                else:
                    target_count = max(top_k, 16)  # full-day combo: ≥3 món × 4 bữa + dự phòng
                results = self._meal_planning_results(
                    aggregated, target_count, trace, strict=False
                )
            else:
                seed = self.MEAL_TYPE_SEEDS.get(slots[0], self.GENERIC_MEAL_SEED) if slots[0] else self.GENERIC_MEAL_SEED
                slot_query = f"{retrieval_query}\n{seed}"
                slot_results = generic_agent.run(
                    slot_query,
                    max(top_k, 8),
                    trace,
                    collections=collections,
                )
                for item in slot_results:
                    _record(item, slots[0])
                results = self._meal_planning_results(aggregated, max(top_k, 8), trace, strict=False)
        elif routed_intent == "weight_projection":
            trace.add(
                "Weight projection intent",
                "Câu hỏi là ước tính tăng/giảm cân nên response generator sẽ dùng công thức năng lượng và nêu giả định.",
                detail="Không truy xuất món ăn ngẫu nhiên; prompt Agentic RAG yêu cầu dùng chênh lệch kcal / 7700 khi có đủ dữ liệu."
            )
            results = []
        elif routed_intent == "off_topic":
            trace.add(
                "Off-topic intent",
                "Câu hỏi không liên quan dinh dưỡng — bỏ qua bước truy xuất, trả lời ngắn rồi gợi ý quay về chủ đề.",
                detail="Không inject food CONTEXT để tránh lôi món ăn ngẫu nhiên vào câu trả lời chung."
            )
            results = []
        elif routed_intent == "nutrition_qa":
            generic_agent = self._generic_agent()
            results = generic_agent.run(
                retrieval_query,
                top_k,
                trace,
                collections=generic_agent._focused_nutrition_collections(retrieval_query)
            )
        else:
            results = self._generic_agent().run(retrieval_query, top_k, trace)

        context = self._context_from_results(results)
        citations = CitationBuilder.dedupe([
            result.get("citation") or CitationBuilder.from_payload(result.get("payload"))
            for result in results
        ])

        if not context and routed_intent not in ("weight_projection",):
            trace.add(
                "Response Generator",
                "Không tìm thấy dữ liệu phù hợp trong Qdrant. Trả lời thân thiện và gợi ý user mô tả cụ thể hơn.",
                status="warning"
            )
        else:
            trace.add(
                "Response Generator",
                "Sinh câu trả lời cuối cùng từ context đã truy xuất và citation.",
                evidence=[
                    str(citation.get("title") or citation.get("dataset") or citation.get("collection"))
                    for citation in citations[:5]
                ]
            )
        answer = await self.response_generator.generate(
            query=query,
            intent=routed_intent,
            context=context,
            citations=citations,
            trace=trace.steps,
            conversation_context=conversation_context,
            user_profile_text=profile_text
        )

        food_confidence = self._build_food_confidence(results)

        response = {
            "type": "agentic_rag",
            "intent": routed_intent,
            "answer": answer,
            "results": results,
            "citations": citations,
            "context_used": context[:5],
            "food_confidence": food_confidence,
            "trace": trace.steps,
            "session_id": session_id,
            "cache_hit": False
        }
        if use_cache:
            self._cache_set(cache_key, response)
        return response

    async def run_stream(
        self,
        query,
        top_k=6,
        intent=None,
        session_id=None,
        conversation_context=None,
        is_follow_up=None,
        user_profile=None
    ):
        """Streaming execution of Agentic RAG pipeline: retrieves context and streams tokens."""
        routed_intent = self.router.classify(query, forced_intent=intent)
        profile_text = self._format_user_profile(user_profile)
        trace = AgenticTrace()

        if conversation_context and self._is_pure_affirmation(query):
            anchor = self._last_assistant_question(conversation_context)
            if anchor:
                query = f"{anchor.rstrip('?').strip()} - user xác nhận đồng ý ({query})"

        if self._is_vague_followup(query, is_follow_up, conversation_context):
            recent_topic = self._extract_recent_topic(conversation_context)
            topic_hint = recent_topic[:160] if recent_topic else "chủ đề vừa rồi"
            yield (
                f"Bạn muốn mình gợi ý cụ thể về điều gì liên quan đến \"{topic_hint}\"?\n\n"
                "Ví dụ:\n"
                "- Các thực phẩm tương tự (dinh dưỡng/calorie gần giống)\n"
                "- Cách kết hợp vào bữa ăn (sáng/trưa/tối)\n"
                "- Khẩu phần phù hợp với mục tiêu (giảm cân, tăng cơ...)\n\n"
                "Bạn cho mình biết hướng nào để mình tra số liệu chính xác nhé."
            )
            return

        retrieval_query = self._retrieval_query(
            query,
            conversation_context=conversation_context,
            is_follow_up=is_follow_up
        )

        if routed_intent == "image_retrieval":
            results = self.recipe_agent.image_retrieval(retrieval_query, top_k, trace)
        elif routed_intent == "recipe_reasoning":
            results = self.recipe_agent.recipe_reasoning(retrieval_query, top_k, trace)
        elif routed_intent == "ingredient_comparison":
            results = self._generic_agent().ingredient_comparison(retrieval_query, top_k, trace)
        elif routed_intent == "multi_hop":
            results = self.recipe_agent.multi_hop(retrieval_query, top_k, trace)
        elif routed_intent in ("weight_projection", "off_topic"):
            results = []
        else:
            generic_agent = self._generic_agent()
            results = generic_agent.run(
                retrieval_query,
                top_k,
                trace,
                collections=generic_agent._focused_nutrition_collections(retrieval_query)
            )

        context = self._context_from_results(results)
        citations = CitationBuilder.dedupe([
            result.get("citation") or CitationBuilder.from_payload(result.get("payload"))
            for result in results
        ])

        async for chunk in self.response_generator.generate_stream(
            query=query,
            intent=routed_intent,
            context=context,
            citations=citations,
            conversation_context=conversation_context,
            user_profile_text=profile_text
        ):
            yield chunk
