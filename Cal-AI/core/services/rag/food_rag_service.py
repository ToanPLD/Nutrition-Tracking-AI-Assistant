try:
    from qdrant_client import QdrantClient, models
except Exception:
    from core.services.retrieval.qdrant_rest_client import QdrantRestClient as QdrantClient, models
from config.settings import settings
import re
import unicodedata


class FoodRAGService:

    def __init__(self):
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY
        )

        # Food-image RAG should not search beverage/exercise/lifestyle collections.
        self.collections = settings.FOOD_RAG_COLLECTIONS
        self.stopwords = {
            "with", "and", "the", "food", "dish", "meal", "plate",
            "mon", "an", "va", "voi", "phan", "khau"
        }
        self.aliases = {
            "com": {"rice", "broken"},
            "tam": {"broken", "rice"},
            "suon": {"pork", "grilled", "chop", "rib"},
            "bi": {"pork", "skin", "shredded"},
            "cha": {"egg", "meatloaf", "omelet", "omelette"},
            "trung": {"egg", "fried"},
            "sushi": {"maki", "nigiri", "sashimi", "roll", "japanese"},
            "maki": {"sushi", "roll", "seaweed"},
            "nigiri": {"sushi", "salmon", "fish", "rice"},
            "sashimi": {"sushi", "salmon", "fish"},
            "salmon": {"sushi", "nigiri", "fish"},
            "avocado": {"sushi", "roll"},
            "tempura": {"sushi", "fried", "shrimp", "prawn"},
        }
        self.generic_dishes = {
            "pizza", "burger", "sandwich", "salad", "pasta", "noodle",
            "rice", "soup", "cake", "bread", "drink", "smoothie", "sushi"
        }
        self.packaged_markers = {
            "code", "brands", "brand", "quantity", "countries",
            "labels", "nutriscore_grade", "ecoscore_grade", "nova_group",
            "ingredients_text", "energy-kcal_100g"
        }

    def _name_filter(self, dish_name):
        if not dish_name or dish_name == "unknown":
            return None

        return models.Filter(
            should=[
                models.FieldCondition(
                    key="dish_name",
                    match=models.MatchText(text=dish_name)
                ),
                models.FieldCondition(
                    key="food_name",
                    match=models.MatchText(text=dish_name)
                ),
                models.FieldCondition(
                    key="name",
                    match=models.MatchText(text=dish_name)
                )
            ]
        )

    def _search_all(self, vector, top_k=5, query_filter=None):
        all_hits = []

        for col in self.collections:
            try:
                query_vector = (
                    ("text", vector)
                    if col == settings.RECIPE_IMAGE_DATASET_COLLECTION
                    else vector
                )
                hits = self.client.search(
                    collection_name=col,
                    query_vector=query_vector,
                    limit=top_k,
                    query_filter=query_filter,
                    with_payload=True
                )

                if hits:
                    all_hits.extend(hits)

            except Exception as e:
                print(f"⚠️ Skip collection {col}:", e)

        all_hits.sort(key=lambda x: x.score, reverse=True)
        return all_hits[:top_k]

    def _normalize_text(self, text):
        text = unicodedata.normalize("NFKD", str(text or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return text.lower()

    def _tokens(self, text):
        normalized = self._normalize_text(text)
        tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", normalized)
            if len(token) > 1 and token not in self.stopwords
        }

        expanded = set(tokens)
        for token in tokens:
            expanded.update(self.aliases.get(token, set()))

        return expanded

    def _payload_text(self, payload):
        if not payload:
            return ""

        priority_fields = [
            "dish_name", "food_name", "name", "product_name", "title",
            "recipe_name", "cuisine", "description", "ingredients",
            "cleaned_ingredients_list", "ingredients_text", "image_caption",
            "visual_tags", "visible_ingredients", "retrieval_text",
            "category", "categories", "domain"
        ]

        parts = []
        for key in priority_fields:
            value = payload.get(key)
            if value:
                parts.append(str(value))

        if not parts:
            parts = [str(value) for value in payload.values()]

        return " ".join(parts)

    def _is_packaged_payload(self, payload):
        keys = set(payload.keys())
        return bool(keys & self.packaged_markers)

    def _is_generic_dish(self, dish_name):
        tokens = self._tokens(dish_name)
        raw_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", self._normalize_text(dish_name))
            if len(token) > 1
        }

        return bool(raw_tokens & self.generic_dishes)

    def _vision_text(self, vision_context):
        if not vision_context:
            return ""

        if isinstance(vision_context, dict):
            values = []
            for key in [
                "dish_name", "description", "ingredients", "category",
                "visual_form", "portion_description", "filename",
                "visual_rag_matches"
            ]:
                value = vision_context.get(key)
                if value:
                    values.append(str(value))
            return " ".join(values)

        return str(vision_context)

    def _allows_packaged_payload(self, dish_name, payload, vision_context=None):
        if not settings.RAG_REJECT_PACKAGED_ON_GENERIC_IMAGE:
            return True

        if not self._is_packaged_payload(payload):
            return True

        vision_text = self._normalize_text(self._vision_text(vision_context))
        packaged_cues = {
            "package", "packaged", "packaging", "label", "brand",
            "frozen", "box", "bottle", "can", "carton", "wrapper"
        }

        if any(cue in vision_text for cue in packaged_cues):
            return True

        brand = self._normalize_text(payload.get("brands", ""))
        product = self._normalize_text(payload.get("product_name", ""))
        query = self._normalize_text(dish_name)

        if brand and brand in vision_text:
            return True
        if product and product in vision_text:
            return True

        return not self._is_generic_dish(query)

    def is_payload_relevant(self, dish_name, payload, vision_context=None):
        if not self._allows_packaged_payload(dish_name, payload, vision_context):
            return False

        query_tokens = self._tokens(dish_name)
        if not query_tokens:
            return True

        payload_tokens = self._tokens(self._payload_text(payload))
        overlap = query_tokens & payload_tokens
        required = 1 if len(query_tokens) <= 2 else 2

        return len(overlap) >= required

    def _filter_relevant(self, hits, dish_name, vision_context=None):
        if not dish_name or dish_name == "unknown":
            return []

        return [
            hit for hit in hits
            if self.is_payload_relevant(
                dish_name,
                hit.payload or {},
                vision_context=vision_context
            )
        ]

    def search(self, text_vec, dish_name=None, top_k=5, vision_context=None):

        if text_vec is None:
            return []

        query_filter = (
            self._name_filter(dish_name)
            if settings.RAG_USE_QDRANT_NAME_FILTER
            else None
        )
        hits = self._search_all(text_vec, top_k=top_k, query_filter=query_filter)
        relevant_hits = self._filter_relevant(
            hits,
            dish_name,
            vision_context=vision_context
        )
        if relevant_hits:
            return relevant_hits

        if not hits and query_filter is not None:
            hits = self._search_all(text_vec, top_k=top_k)
            return self._filter_relevant(
                hits,
                dish_name,
                vision_context=vision_context
            )

        return [] if dish_name else hits
    
    def hybrid_search(
        self,
        image_vec=None,
        text_vec=None,
        dish_name=None,
        vision_context=None,
        alpha=0.6,
        top_k=5
    ):

        if text_vec is None and image_vec is None:
            return []

        if image_vec is None or text_vec is None:
            return self.search(
                text_vec or image_vec,
                dish_name=dish_name,
                top_k=top_k,
                vision_context=vision_context
            )

        if len(image_vec) != len(text_vec):
            return self.search(
                text_vec,
                dish_name=dish_name,
                top_k=top_k,
                vision_context=vision_context
            )

        query_filter = (
            self._name_filter(dish_name)
            if settings.RAG_USE_QDRANT_NAME_FILTER
            else None
        )
        hits_a = self._search_all(image_vec, top_k=top_k, query_filter=query_filter)
        hits_b = self._search_all(text_vec, top_k=top_k, query_filter=query_filter)

        score_map = {}

        for h in hits_a:
            score_map[h.id] = alpha * h.score

        for h in hits_b:
            score_map[h.id] = score_map.get(h.id, 0) + (1 - alpha) * h.score

        merged = {h.id: h for h in hits_a + hits_b}

        final = list(merged.values())

        final.sort(key=lambda x: score_map.get(x.id, 0), reverse=True)

        final = self._filter_relevant(
            final,
            dish_name,
            vision_context=vision_context
        )

        if not final and query_filter is not None:
            return self.search(
                text_vec,
                dish_name=dish_name,
                top_k=top_k,
                vision_context=vision_context
            )

        return final[:top_k]
