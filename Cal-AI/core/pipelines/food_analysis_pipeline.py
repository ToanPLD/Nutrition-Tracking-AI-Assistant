from core.services.vision.qwen_vl_service import QwenVLService
from core.embedding.clip_service import CLIPService
from core.embedding.text_embedding_service import TextEmbeddingService
from core.services.rag.food_rag_service import FoodRAGService
from core.services.rerank.cross_encoder import CrossEncoderReranker
from core.services.user.user_tracking import UserTrackingService
from core.services.cache.embedding_cache import EmbeddingCache
from core.services.cache.redis_cache import RedisCache
from core.services.llm.llm_service import LLMService
from core.services.vision.vit_cnn_service import ViTCNNFoodClassifier
from config.settings import settings
import hashlib
import json
import os
import re
import unicodedata

try:
    from qdrant_client import models as qdrant_models
except Exception:
    from core.services.retrieval.qdrant_rest_client import models as qdrant_models

class FoodAnalysisPipeline:

    def __init__(self):
        self._qwen = None
        self._clip = None
        self._text_embed = None
        self._rag = None
        self._rerank = None
        self._user_tracking = None
        self._cache = None
        self._response_cache = None
        self._llm = None
        self._image_classifier = None
        self._gemini_vision = None

    @property
    def gemini_vision(self):
        if self._gemini_vision is None:
            from core.services.vision.gemini_vision_service import GeminiVisionService
            self._gemini_vision = GeminiVisionService()
        return self._gemini_vision
    @property
    def qwen(self):
        if self._qwen is None:
            self._qwen = QwenVLService()
        return self._qwen

    @property
    def clip(self):
        if self._clip is None:
            self._clip = CLIPService()
        return self._clip

    @property
    def text_embed(self):
        if self._text_embed is None:
            self._text_embed = TextEmbeddingService()
        return self._text_embed

    @property
    def rag(self):
        if self._rag is None:
            self._rag = FoodRAGService()
        return self._rag

    @property
    def rerank(self):
        if self._rerank is None:
            self._rerank = CrossEncoderReranker()
        return self._rerank

    @property
    def user_tracking(self):
        if self._user_tracking is None:
            self._user_tracking = UserTrackingService()
        return self._user_tracking

    @property
    def cache(self):
        if self._cache is None:
            self._cache = EmbeddingCache()
        return self._cache

    @property
    def response_cache(self):
        # Separate Redis client from EmbeddingCache so we can drop one without
        # the other if a cached analysis turns out to be wrong.
        if self._response_cache is None:
            self._response_cache = RedisCache()
        return self._response_cache

    @property
    def llm(self):
        if self._llm is None:
            self._llm = LLMService()
        return self._llm

    @property
    def image_classifier(self):
        if self._image_classifier is None:
            self._image_classifier = ViTCNNFoodClassifier(clip=self.clip)
        return self._image_classifier

    def _image_key(self, image):
        return hashlib.md5(image.tobytes()).hexdigest()

    def _response_cache_key(self, image, question):
        # Image bytes are normalized to 512×512 in the route handler before
        # reaching here, so the same upload always produces the same digest.
        # Question is normalized (strip + lowercase) so trivial whitespace
        # differences still hit the cache.
        question_norm = self._normalize_text(question or "").strip()
        question_digest = hashlib.sha1(
            question_norm.encode("utf-8")
        ).hexdigest()[:16]
        # v5: bumped 2026-05-09 — filename match moved BEFORE Qwen-VL so
        # dataset uploads skip the 60-100s vision call entirely. Also
        # restored Qdrant keyword indexes on image_file/image_name (got
        # dropped during the --recreate ingest).
        return f"food_analysis:v5:{self._image_key(image)}:{question_digest}"

    def _response_cache_get(self, key):
        raw = self.response_cache.get(key)
        if not raw:
            return None
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception:
            return None

    def _response_cache_put(self, key, value, ttl=3600):
        try:
            self.response_cache.set(
                key,
                json.dumps(value, ensure_ascii=False),
                ttl=ttl,
            )
        except Exception:
            pass

    def _normalize_text(self, text):
        text = unicodedata.normalize("NFKD", str(text or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return text.lower()

    def _lookup_by_filename(self, filename):
        # When the user uploads an image whose filename matches a payload's
        # image_file/image_name in the recipe dataset (e.g. they picked a file
        # straight from kagglehub), bypass CLIP/vision drift by pulling the
        # authoritative recipe record directly. CLIP base struggles on food
        # and the multimodal collection is partial, so this short-circuit is
        # how dataset-image uploads stay reliable.
        if not filename:
            return None

        base = os.path.basename(str(filename))
        stem, _ = os.path.splitext(base)

        conditions = []
        for value in {base, stem}:
            if not value:
                continue
            conditions.append(qdrant_models.FieldCondition(
                key="image_file",
                match=qdrant_models.MatchValue(value=value),
            ))
            conditions.append(qdrant_models.FieldCondition(
                key="image_name",
                match=qdrant_models.MatchValue(value=value),
            ))

        if not conditions:
            return None

        flt = qdrant_models.Filter(should=conditions)
        for collection in (
            settings.RECIPE_IMAGE_DATASET_COLLECTION,
            settings.FOOD_RECIPE_IMAGES_TEXT_COLLECTION,
        ):
            try:
                points, _ = self.rag.client.scroll(
                    collection_name=collection,
                    scroll_filter=flt,
                    limit=1,
                    with_payload=True,
                )
            except Exception as exc:
                print(f"[FoodAnalysis] filename lookup error ({collection}):", exc)
                continue
            if points:
                payload = dict(points[0].payload or {})
                payload.setdefault("source_collection", collection)
                return payload

        return None

    def _category_from_title(self, title):
        """Derive coarse category from the recipe title using token matching.
        Substring matching collapses 'pancakes' → 'cake' → dessert, so we
        tokenize on word boundaries before checking the keyword set."""
        if not title:
            return None
        title_lower = title.lower()
        tokens = set(re.findall(r"[a-z]+", title_lower))

        def _has(words):
            for w in words:
                if " " in w:
                    if w in title_lower:
                        return True
                elif w in tokens:
                    return True
            return False

        if _has((
            "cake", "cookie", "cookies", "tart", "pie", "mousse",
            "cheesecake", "kouign", "pudding", "cupcake", "cupcakes",
            "brownie", "brownies", "macaron", "souffle", "compote",
            "crumble", "cobbler", "sorbet", "gelato",
            "ice cream", "panna cotta",
        )):
            return "dessert"
        if _has((
            "salsa", "sauce", "dip", "dressing", "vinaigrette",
            "chutney", "relish", "marinade", "rub", "glaze",
        )):
            return "condiment"
        if _has((
            "cocktail", "smoothie", "lemonade", "juice", "spritz",
            "punch", "tea", "latte", "cooler", "fizz", "tonic",
        )):
            return "drink"
        if _has((
            "salad", "soup", "stew", "casserole", "chicken", "beef",
            "pork", "fish", "shrimp", "steak", "pasta", "rice",
            "noodle", "noodles", "burger", "sandwich", "pizza",
            "curry", "stir-fry",
            "okonomiyaki", "pancake", "pancakes", "omelette",
            "frittata", "tortilla", "wrap", "taco", "tacos",
            "burrito", "risotto", "ramen", "udon", "lasagna",
            "quiche", "galette", "breadcrumbs",
        )):
            return "main"
        return "main"

    def _vision_from_match(self, direct_match, filename):
        """Build a complete `vision` dict directly from a filename-matched
        recipe payload, bypassing Qwen-VL. Used for dataset uploads where
        the DB record is already authoritative; saves ~60-100s vs. running
        the vision model first and then overwriting its output."""
        title = (
            direct_match.get("title")
            or direct_match.get("recipe_name")
            or direct_match.get("name")
            or direct_match.get("dish_name")
            or "unknown"
        )
        ingredients_list = (
            direct_match.get("cleaned_ingredients_list")
            or direct_match.get("ingredients_list")
            or []
        )
        ingredients = (
            [str(i) for i in ingredients_list[:15] if i]
            if isinstance(ingredients_list, list) else []
        )
        instructions = (
            direct_match.get("instructions")
            or direct_match.get("instructions_preview")
            or ""
        )
        return {
            "dish_name": title,
            "confidence": 0.95,
            "category": self._category_from_title(title),
            "ingredients": ingredients,
            "instructions": str(instructions) if instructions else "",
            "description": f"Recipe row matched by filename: {title}",
            "identification_evidence": [
                f"filename_match:{os.path.basename(str(filename or ''))}"
            ],
            "image_quality": {},
            "possible_dishes": [],
            "image_observations": [],
            "visible_vs_inferred": {
                "visible": [],
                "inferred": [title],
                "not_visible": []
            },
            "sub_items": [],
            "visual_form": "unknown",
            "portion_description": None,
            "portion_estimation": {},
            "uncertainty": {"level": "low"},
        }

    def _is_unknown_vision(self, vision):
        dish = self._normalize_text(vision.get("dish_name", ""))
        return not dish or dish in {"unknown", "none", "null", "khong ro"}

    def _classifier_query_text(self, classification):
        predictions = (classification or {}).get("top_predictions") or []
        terms = []
        for item in predictions[:3]:
            terms.extend([
                item.get("name"),
                item.get("label"),
                *(item.get("aliases") or [])[:3],
            ])
        visual_matches = (
            ((classification or {}).get("qdrant_visual_analysis") or {})
            .get("top_matches") or []
        )
        for item in visual_matches[:5]:
            terms.extend([
                item.get("name"),
                item.get("image_caption"),
                " ".join(item.get("ingredients") or []),
                " ".join(str(tag) for tag in (item.get("visual_tags") or [])),
            ])
        return " ".join(str(term) for term in terms if term).strip()

    # Override classifier only when it disagrees with the vision model AND
    # is at least this confident. Below this we leave vision alone — the
    # vision model usually knows finer-grained dish names than CLIP zero-shot.
    CLASSIFIER_OVERRIDE_THRESHOLD = 0.30

    def _vision_matches_classifier(self, vision_dish, classification):
        """Return True if the vision-model dish name overlaps with any
        alias of any top classifier prediction. Used to detect 'classifier
        and vision agree' so we leave vision alone."""
        vision_norm = self._normalize_text(vision_dish)
        if not vision_norm:
            return False
        candidates = self.image_classifier.CANDIDATES
        candidate_by_label = {c["label"]: c for c in candidates}
        for prediction in (classification.get("top_predictions") or [])[:3]:
            label = prediction.get("label") or ""
            cand = candidate_by_label.get(label) or {
                "aliases": [prediction.get("name") or label]
            }
            for alias in cand.get("aliases") or []:
                alias_norm = self._normalize_text(alias)
                if alias_norm and alias_norm in vision_norm:
                    return True
            # Also accept the classifier display name itself
            display_norm = self._normalize_text(cand.get("display"))
            if display_norm and display_norm in vision_norm:
                return True
        return False

    def _classifier_dish_label(self, top_prediction):
        """Pick the human-friendly dish name from a classifier prediction.
        Prefers display (e.g. "cơm tấm") over raw label ("com tam"),
        and never returns a Qdrant nearest-neighbor recipe title."""
        if not top_prediction:
            return None
        return (
            top_prediction.get("display")
            or top_prediction.get("name")
            or top_prediction.get("label")
        )

    def _merge_classifier_with_vision(self, vision, classification):
        vision = vision if isinstance(vision, dict) else {}
        classification = classification if isinstance(classification, dict) else {}
        predictions = classification.get("top_predictions") or []
        top = predictions[0] if predictions else {}

        if not predictions:
            vision["vit_cnn_analysis"] = classification
            return vision

        classifier_confidence = self._to_float(classification.get("confidence")) or 0
        # 1) Vision returned "unknown" — replace it with classifier seed (existing behavior).
        if self._is_unknown_vision(vision) and classifier_confidence >= settings.IMAGE_CLASSIFIER_MIN_CONFIDENCE:
            seeded = self.image_classifier.to_vision_seed(classification)
            seeded["vit_cnn_analysis"] = classification
            return seeded

        # 2) Vision returned something but disagrees with a confident classifier.
        # Override dish_name only when:
        #   - classifier confidence is meaningful (≥ threshold), AND
        #   - vision dish does NOT already match any classifier candidate alias
        # If they agree, vision is finer-grained and stays. Use the classifier
        # CANDIDATE display name (e.g. "cơm tấm"), NOT the Qdrant nearest-neighbor
        # recipe title — pixel-similar images can still be different dishes.
        vision_dish = (vision.get("dish_name") or "").strip()
        agree = self._vision_matches_classifier(vision_dish, classification)
        if (
            not agree
            and classifier_confidence >= self.CLASSIFIER_OVERRIDE_THRESHOLD
        ):
            classifier_dish = self._classifier_dish_label(top)
            if classifier_dish:
                vision["dish_name"] = classifier_dish
                vision["confidence"] = max(
                    self._to_float(vision.get("confidence")) or 0,
                    classifier_confidence,
                )
                vision.setdefault("identification_evidence", []).append(
                    f"Classifier override: vision said '{vision_dish}' "
                    f"but CLIP classifier identified '{classifier_dish}' "
                    f"(score {classifier_confidence:.2f})."
                )

        vision["vit_cnn_analysis"] = classification
        existing = vision.get("possible_dishes")
        existing = existing if isinstance(existing, list) else []
        classifier_dishes = [
            {
                "name": item.get("name"),
                "probability": item.get("probability"),
                "why": "ViT/CNN classifier",
            }
            for item in predictions[:3]
            if item.get("name")
        ]
        visual_matches = (
            (classification.get("qdrant_visual_analysis") or {})
            .get("top_matches") or []
        )
        qdrant_dishes = [
            {
                "name": item.get("name"),
                "probability": item.get("score"),
                "why": f"Qdrant visual nearest neighbor ({item.get('collection')})",
            }
            for item in visual_matches[:5]
            if item.get("name")
        ]
        vision["possible_dishes"] = (existing[:5] or classifier_dishes) + qdrant_dishes
        vision["possible_dishes"] = vision["possible_dishes"][:8]
        vision["visual_rag_matches"] = visual_matches[:8]
        if not vision.get("identification_evidence"):
            vision["identification_evidence"] = [
                f"ViT/CNN classifier top-1: {top.get('name')}."
            ]
        if visual_matches:
            vision.setdefault("image_observations", [])
            vision["image_observations"].extend([
                f"Qdrant visual match: {item.get('name')} (score {item.get('score')})."
                for item in visual_matches[:3]
                if item.get("name")
            ])
        return vision

    def _normalize_vision_details(self, vision):
        dish = self._normalize_text(vision.get("dish_name", ""))
        category = self._normalize_text(vision.get("category", ""))
        visual_form = self._normalize_text(vision.get("visual_form", ""))

        if "pizza" in dish or "pizza" in category:
            if not visual_form and "whole" in category:
                vision["visual_form"] = "whole pizza"
            elif not visual_form:
                vision["visual_form"] = "pizza"

            portion = self._normalize_text(vision.get("portion_description", ""))
            if "slice" in portion and vision.get("visual_form") == "whole pizza":
                vision["portion_description"] = "ước tính 1 pizza nguyên chiếc cỡ vừa"

        if "sushi" in dish or "sushi" in category:
            if not visual_form or visual_form == "slice":
                vision["visual_form"] = "sushi platter"

            if dish == "sushi" and vision.get("visual_form") == "sushi platter":
                vision["dish_name"] = "sushi platter"

            portion = self._normalize_text(vision.get("portion_description", ""))
            if not portion:
                vision["portion_description"] = "nhiều miếng sushi trên đĩa"

        return vision

    def _enrich_query(self, vision):
        dish = vision.get("dish_name", "")
        desc = vision.get("description", "")
        ingredients = " ".join(vision.get("ingredients") or [])
        classifier_text = self._classifier_query_text(vision.get("vit_cnn_analysis"))
        sub_items = " ".join(
            f"{item.get('name', '')} {item.get('count', '')} {' '.join(item.get('visible_ingredients') or [])}"
            for item in (vision.get("sub_items") or [])
            if isinstance(item, dict)
        )
        visual_rag = " ".join(
            " ".join([
                str(item.get("name") or ""),
                str(item.get("image_caption") or ""),
                " ".join(item.get("ingredients") or []),
                " ".join(str(tag) for tag in (item.get("visual_tags") or [])),
            ])
            for item in (vision.get("visual_rag_matches") or [])[:5]
            if isinstance(item, dict)
        )

        if "cơm tấm" in dish.lower():
            return (
                f"{dish}. {desc}. {ingredients}. {classifier_text}. "
                "broken rice grilled pork chop shredded pork skin egg meatloaf fried egg Vietnamese rice plate"
            )

        if "pizza" in self._normalize_text(dish):
            return (
                f"{dish}. {desc}. {ingredients}. {classifier_text}. "
                "pizza cheese sausage pepperoni ham meat tomato sauce bbq sauce whole pizza"
            )

        if "sushi" in self._normalize_text(f"{dish} {desc} {ingredients} {classifier_text} {sub_items}"):
            return (
                f"{dish}. {desc}. {ingredients}. {classifier_text}. {sub_items}. {visual_rag}. "
                "sushi platter sushi set salmon nigiri maki roll uramaki avocado cucumber nori seaweed rice tempura shrimp sashimi Japanese"
            )

        return f"{dish} {desc} {ingredients} {classifier_text} {sub_items} {visual_rag}".strip()

    def _to_float(self, value):
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group()) if match else None

    def _nutrition_estimate_from_vision(self, vision):
        if not isinstance(vision, dict):
            return None

        raw = vision.get("nutrition_estimate")
        if not isinstance(raw, dict):
            return None
        portion_estimation = vision.get("portion_estimation")
        portion_estimation = portion_estimation if isinstance(portion_estimation, dict) else {}

        estimate = {
            "calories": self._to_float(raw.get("calories")),
            "protein": self._to_float(raw.get("protein")),
            "carbs": self._to_float(raw.get("carbs")),
            "fat": self._to_float(raw.get("fat")),
            "fiber": self._to_float(raw.get("fiber")),
            "sugar": self._to_float(raw.get("sugar")),
            "sodium_mg": self._to_float(raw.get("sodium_mg")),
            "serving_size": (
                vision.get("portion_description")
                or portion_estimation.get("method")
                or raw.get("basis")
            ),
            "note": raw.get("basis") or "ước tính trực tiếp từ model vision theo khẩu phần nhìn thấy"
        }

        macro_values = [
            estimate.get("calories"),
            estimate.get("protein"),
            estimate.get("carbs"),
            estimate.get("fat")
        ]
        return estimate if any(value not in (None, 0) for value in macro_values) else None

    def _estimated_grams_from_vision(self, vision):
        if not isinstance(vision, dict):
            return None

        portion_estimation = vision.get("portion_estimation")
        if not isinstance(portion_estimation, dict):
            return None

        grams = self._to_float(portion_estimation.get("estimated_grams"))
        return grams if grams and grams > 0 else None

    # Default visible-portion grams per visual_form bucket. Used as the
    # multiplier when vision identified a dish_name but failed to estimate
    # grams, and we recovered per_100g macros from a RAG fallback lookup.
    _DEFAULT_PORTION_GRAMS = {
        "noodle_soup": 400,
        "soup": 300,
        "bowl": 300,
        "plate": 280,
        "mixed_meal": 320,
        "salad": 200,
        "sandwich": 180,
        "pizza": 200,
        "sushi": 180,
        "dessert": 120,
        "snack": 100,
        "drink": 250,
    }

    # Friendly Vietnamese labels for visual_form buckets (shown to end user).
    _VISUAL_FORM_VI = {
        "noodle_soup": "một tô bún/phở",
        "soup": "một tô canh/súp",
        "bowl": "một tô",
        "plate": "một đĩa",
        "mixed_meal": "một suất ăn",
        "salad": "một phần salad",
        "sandwich": "một ổ bánh mì",
        "pizza": "một phần pizza",
        "sushi": "một phần sushi",
        "dessert": "một phần tráng miệng",
        "snack": "một phần ăn vặt",
        "drink": "một ly đồ uống",
    }

    # Friendly source labels — Qdrant collection names are internal jargon
    # and must not leak into user-facing copy.
    _SOURCE_LABEL_VI = {
        "vn_food_vectors_768": "Bảng dinh dưỡng món Việt",
        "food_common_vectors_768": "Bảng dinh dưỡng thực phẩm thông dụng",
        "food_nutrition_vectors_768": "Bảng dinh dưỡng tổng hợp",
        "nutrition5k_vectors_768": "Cơ sở Nutrition5k",
        "food_nutrition_dev_vectors_768": "Bảng dinh dưỡng mở rộng",
        "food_global_10k_vectors_768": "Bảng dinh dưỡng thực phẩm toàn cầu",
        "food_text_vectors_768": "Bảng dinh dưỡng tham chiếu",
        "food_vectors_768": "Bảng dinh dưỡng tham chiếu",
        "food_fruit_vectors_768": "Bảng dinh dưỡng trái cây",
        "beverage_vectors_768": "Bảng dinh dưỡng đồ uống",
        "beverage_text_vectors_768": "Bảng dinh dưỡng đồ uống",
    }

    def _default_portion_grams(self, vision):
        if not isinstance(vision, dict):
            return 250
        visual_form = str(vision.get("visual_form") or "").strip().lower()
        return self._DEFAULT_PORTION_GRAMS.get(visual_form, 250)

    def _visual_form_label(self, vision):
        visual_form = str((vision or {}).get("visual_form") or "").strip().lower()
        return self._VISUAL_FORM_VI.get(visual_form, "một phần ăn")

    def _source_label(self, collection):
        return self._SOURCE_LABEL_VI.get(
            str(collection or "").strip(),
            "bảng dinh dưỡng tham chiếu",
        )

    # Curated collections searched first by the dish-name fallback. Recipe
    # collections (recipes_64k, food_ingredients_recipes_multimodal) tend to
    # dominate the generic hybrid search for short dish names like "pho" but
    # carry no per_100g macros; querying nutrition-bearing collections
    # directly is the only way to recover real numbers.
    _DISH_FALLBACK_COLLECTIONS = (
        "vn_food_vectors_768",
        "food_common_vectors_768",
        "food_nutrition_vectors_768",
        "nutrition5k_vectors_768",
        "food_global_10k_vectors_768",
        "food_text_vectors_768",
    )

    # Minimum cosine similarity for the dish-name fallback to be considered a
    # plausible semantic match. Below this the top hit is essentially the
    # least-unrelated neighbor (e.g. searching "Zuni Ricotta Gnocchi" in a
    # Vietnamese-food collection returns "cùi dừa già"), and accepting it
    # produces wildly wrong macros attributed to the actual dish.
    _DISH_FALLBACK_MIN_SCORE = 0.62
    # Above this we trust the hit even without lexical token overlap — useful
    # for legitimate cross-language synonyms the embedding captures.
    _DISH_FALLBACK_STRONG_SCORE = 0.78

    def _dish_name_tokens(self, value):
        """Lower-cased, accent-stripped tokens (≥ 3 chars) from a dish/food
        name. Used for cheap lexical overlap as a sanity check on top of the
        vector similarity score."""
        normalized = self._normalize_text(value or "")
        if not normalized:
            return set()
        # Split on anything non-alphanumeric; ignore short generic glue words.
        raw_tokens = re.split(r"[^a-z0-9]+", normalized)
        stop = {"and", "with", "the", "for", "mon", "and", "kieu", "cua"}
        return {t for t in raw_tokens if len(t) >= 3 and t not in stop}

    def _payload_name_candidates(self, payload):
        """Names we'll compare against the queried dish_name. Recipe rows
        usually expose multiple of these — checking all reduces false
        rejections when the canonical column name varies by collection."""
        if not payload:
            return []
        keys = (
            "food_name", "name", "dish_name", "title",
            "recipe_name", "product_name", "label", "vi_name",
        )
        return [str(payload.get(k)) for k in keys if payload.get(k)]

    def _dish_name_nutrition_lookup(self, dish_name):
        """Fallback RAG search when vision identifies a dish_name but no
        nutrition data made it through (low image quality, sparse dataset for
        the cuisine). Returns the first payload that exposes per_100g macros
        AND is plausibly the same dish (vector score ≥ threshold and/or
        lexical token overlap). Rejecting weak hits prevents the pipeline
        from labeling unrelated nutrition (e.g. coconut) as the dish's macros
        and forcing the LLM to cite it in the answer.
        """
        if not dish_name:
            return None
        cleaned = str(dish_name).strip()
        if len(cleaned) < 2:
            return None
        try:
            text_vec = self.text_embed.embed(cleaned)
        except Exception as exc:
            print("[FoodAnalysis] dish-name embed failed:", exc)
            return None
        if text_vec is None:
            return None

        query_tokens = self._dish_name_tokens(cleaned)
        best_rejected = None

        client = self.rag.client
        for collection in self._DISH_FALLBACK_COLLECTIONS:
            try:
                hits = client.search(
                    collection_name=collection,
                    query_vector=text_vec,
                    limit=6,
                    with_payload=True,
                    score_threshold=self._DISH_FALLBACK_MIN_SCORE,
                )
            except Exception as exc:
                print(f"[FoodAnalysis] dish fallback {collection} search failed:", exc)
                continue
            for hit in hits or []:
                payload = dict(getattr(hit, "payload", None) or {})
                payload.setdefault("source_collection", collection)
                if not self._payload_nutrition_per_100g(payload):
                    continue

                score = getattr(hit, "score", None) or 0.0
                payload_tokens = set()
                for name in self._payload_name_candidates(payload):
                    payload_tokens |= self._dish_name_tokens(name)

                has_overlap = bool(query_tokens & payload_tokens)
                if score >= self._DISH_FALLBACK_STRONG_SCORE or has_overlap:
                    return payload

                if best_rejected is None:
                    matched_name = next(iter(self._payload_name_candidates(payload)), "?")
                    best_rejected = (collection, matched_name, score)

        if best_rejected is not None:
            collection, matched_name, score = best_rejected
            print(
                f"[FoodAnalysis] dish-name fallback rejected '{cleaned}' → "
                f"'{matched_name}' (collection={collection}, score={score:.3f}) "
                "— no lexical overlap and score below strong threshold."
            )
        return None

    def _portion_estimate_from_rag(self, vision, retrieved):
        grams = self._estimated_grams_from_vision(vision)
        per_100g = self._payload_nutrition_per_100g(retrieved)
        if not grams or not per_100g:
            return None

        scale = grams / 100
        return {
            "calories": (
                round(per_100g["calories"] * scale)
                if per_100g.get("calories") is not None
                else None
            ),
            "protein": (
                round(per_100g["protein"] * scale, 1)
                if per_100g.get("protein") is not None
                else None
            ),
            "carbs": (
                round(per_100g["carbs"] * scale, 1)
                if per_100g.get("carbs") is not None
                else None
            ),
            "fat": (
                round(per_100g["fat"] * scale, 1)
                if per_100g.get("fat") is not None
                else None
            ),
            "serving_size": f"ước tính theo phần nhìn thấy khoảng {round(grams)} g",
            "note": "tính từ dữ liệu dinh dưỡng theo 100g và khẩu phần model vision ước lượng"
        }

    def _payload_nutrition_per_100g(self, payload):
        if not payload:
            return None

        calories = (
            payload.get("energy-kcal_100g")
            or payload.get("calories")
            or payload.get("kcal")
        )
        protein = (
            payload.get("proteins_100g")
            or payload.get("protein")
            or payload.get("proteins")
        )
        carbs = (
            payload.get("carbohydrates_100g")
            or payload.get("carbohydrate")
            or payload.get("carbs")
            or payload.get("carb")
        )
        fat = payload.get("fat_100g") or payload.get("fat") or payload.get("total_fat")

        values = {
            "calories": self._to_float(calories),
            "protein": self._to_float(protein),
            "carbs": self._to_float(carbs),
            "fat": self._to_float(fat)
        }

        return values if any(value is not None for value in values.values()) else None

    def _payload_declared_nutrition(self, payload):
        if not payload:
            return None

        text = str(payload.get("nutrition") or "")
        if not text:
            return None

        patterns = {
            "calories": r"calories?\s+(\d+(?:\.\d+)?)",
            "protein": r"protein\s+(\d+(?:\.\d+)?)\s*g",
            "carbs": r"(?:total\s+)?carbohydrate\s+(\d+(?:\.\d+)?)\s*g",
            "fat": r"(?:total\s+)?fat\s+(\d+(?:\.\d+)?)\s*g"
        }

        values = {}
        lower = text.lower()
        for key, pattern in patterns.items():
            match = re.search(pattern, lower)
            values[key] = float(match.group(1)) if match else None

        return values if any(value is not None for value in values.values()) else None

    def _nutrition_summary(self, retrieved, estimated):
        per_100g = self._payload_nutrition_per_100g(retrieved)
        declared = self._payload_declared_nutrition(retrieved)
        matched_item = (
            retrieved.get("name")
            or retrieved.get("dish_name")
            or retrieved.get("food_name")
            or retrieved.get("product_name")
            or retrieved.get("recipe_name")
            if retrieved else None
        )

        estimated = estimated or None

        if per_100g and estimated:
            note = (
                "RAG cung cấp chỉ số theo 100g; estimated_visible_portion là ước tính cho phần ăn nhìn thấy trong ảnh."
            )
        elif retrieved:
            note = (
                "RAG cung cấp recipe/context phù hợp nhưng không có calories chuẩn theo khẩu phần; "
                "estimated_visible_portion chỉ có khi model vision hoặc khẩu phần đủ dữ liệu."
            )
        else:
            note = "Không có RAG phù hợp; chỉ trả dữ liệu model vision quan sát được từ ảnh."

        return {
            "matched_item": matched_item,
            "basis": (
                retrieved.get("serving_size")
                or ("100 g" if per_100g else (estimated or {}).get("serving_size"))
                if retrieved else (estimated or {}).get("serving_size")
            ),
            "per_100g": per_100g,
            "declared_nutrition": declared,
            "estimated_visible_portion": estimated,
            "note": note
        }

    async def analyze(self, image, user_id=None, filename=None, question=None):

        # STEP 0: RESPONSE CACHE
        # Same image + same question → return the previously computed answer
        # instead of re-running the 60–100s vision/RAG/LLM pipeline. We still
        # log the meal for the caller's user_id so cache hits don't break
        # tracking semantics.
        cache_key = self._response_cache_key(image, question)
        cached = self._response_cache_get(cache_key)
        if cached is not None:
            cached["cache_hit"] = True
            if user_id:
                try:
                    self.user_tracking.log_meal(user_id, cached)
                except Exception as exc:
                    print("[FoodAnalysis] cache-hit log_meal failed:", exc)
            return cached

        # STEP 1: FILENAME SHORT-CIRCUIT (try direct match before vision call)
        direct_match = self._lookup_by_filename(filename)
        vision = None
        if direct_match:
            vision = self._vision_from_match(direct_match, filename)
        else:
            # Multi-modal Vision Attention with Gemini Vision Service
            vision = await self.gemini_vision.analyze_food(
                image,
                hint=question or filename or "",
            )

        # STEP 2: Food detection & confidence thresholding
        is_food = vision.get("is_food", True)
        confidence = self._to_float(vision.get("confidence")) or 0.0
        if confidence > 1.0:
            confidence = confidence / 100.0

        if not is_food or confidence < 0.2:
            unrecog_name = vision.get("vietnamese_name") or vision.get("dish_name") or "Không rõ món ăn"
            result = {
                "name": unrecog_name,
                "dish_name": unrecog_name,
                "is_food": False,
                "confidence": round(confidence, 2) if confidence > 0 else 0.1,
                "calories": 0,
                "protein": 0.0,
                "carbs": 0.0,
                "fat": 0.0,
                "estimated_portion": "N/A",
                "visible_ingredients": vision.get("visible_ingredients", []),
                "visual_notes": vision.get("visual_notes", "Không phát hiện món ăn trong ảnh"),
                "cache_hit": False,
            }
            return result

        # STEP 3: Food recognition & portion extraction
        dish = vision.get("vietnamese_name") or vision.get("dish_name") or ""
        portion_info = vision.get("portion") or {}
        estimated_grams = float(portion_info.get("estimated_grams") or 350.0)
        portion_description = portion_info.get("description") or f"1 khẩu phần (khoảng {int(estimated_grams)}g)"

        # STEP 4: Vector retrieval grounding (Qdrant)
        hits = []
        best = {}
        if direct_match:
            best = direct_match
        elif dish:
            try:
                hits = self.rag.hybrid_search(
                    dish_name=dish,
                    vision_context=vision,
                    top_k=settings.RAG_CANDIDATE_TOP_K
                )
            except Exception as e:
                print(f"[FoodAnalysis] RAG hybrid search failed: {e}")
                hits = []

            if hits:
                best = hits[0].payload if hasattr(hits[0], "payload") else (hits[0] if isinstance(hits[0], dict) else {})

        # STEP 5: Scale macros by estimated portion grams (database is per 100g)
        scale = estimated_grams / 100.0
        calories = 0
        protein = 0.0
        carbs = 0.0
        fat = 0.0

        if best:
            raw_cal = best.get("calories")
            raw_pro = best.get("protein")
            raw_carbs = best.get("carbs")
            raw_fat = best.get("fat")

            if raw_cal is not None:
                calories = round(float(raw_cal) * scale)
            if raw_pro is not None:
                protein = round(float(raw_pro) * scale, 1)
            if raw_carbs is not None:
                carbs = round(float(raw_carbs) * scale, 1)
            if raw_fat is not None:
                fat = round(float(raw_fat) * scale, 1)

        # Fallback if vector DB had no macros or no match
        if calories == 0 and protein == 0.0 and carbs == 0.0 and fat == 0.0:
            v_nut = vision.get("nutrition") or {}
            if v_nut:
                calories = round(float(v_nut.get("calories") or 350) * (estimated_grams / 350.0))
                protein = round(float(v_nut.get("protein") or 15.0) * (estimated_grams / 350.0), 1)
                carbs = round(float(v_nut.get("carbs") or 40.0) * (estimated_grams / 350.0), 1)
                fat = round(float(v_nut.get("fat") or 10.0) * (estimated_grams / 350.0), 1)
            else:
                calories = round(350.0 * (estimated_grams / 350.0))
                protein = round(15.0 * (estimated_grams / 350.0), 1)
                carbs = round(45.0 * (estimated_grams / 350.0), 1)
                fat = round(12.0 * (estimated_grams / 350.0), 1)

        result = {
            "name": dish,
            "dish_name": dish,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "confidence": round(confidence, 2),
            "estimated_portion": portion_description,
            "is_food": True,
            "visible_ingredients": vision.get("visible_ingredients", []),
            "visual_notes": vision.get("visual_notes", ""),
            "retrieved_nutrition": best,
            "estimated_nutrition": {
                "calories": calories,
                "protein": protein,
                "carbs": carbs,
                "fat": fat,
                "serving_size": portion_description,
            },
            "raw_vision": vision,
            "cache_hit": False,
        }

        # Optional LLM natural language answer if question provided
        if question:
            try:
                answer = await self.llm.answer_food_image(
                    question=question,
                    analysis=result
                )
                if answer:
                    result["answer"] = answer
            except Exception as e:
                print(f"[FoodAnalysis] LLM answer failed: {e}")

        # Save to response cache
        self._response_cache_put(cache_key, result)

        # STEP 6: USER TRACKING
        if user_id:
            try:
                self.user_tracking.log_meal(user_id, result)
            except Exception as exc:
                print("[FoodAnalysis] log_meal failed:", exc)

        return result
