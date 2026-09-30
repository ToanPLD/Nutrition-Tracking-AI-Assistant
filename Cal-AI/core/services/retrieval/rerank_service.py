import unicodedata
from typing import Any, Dict, List, Optional


class FlashRankService:
    """Ultra-lightweight neural cross-encoder reranker running on CPU via ONNX Runtime."""

    _instance = None

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2"):
        self.model_name = model_name
        self._ranker = None
        self._available = False
        self._init_ranker()

    def _init_ranker(self):
        try:
            from flashrank import Ranker
            # Initialize Ranker (downloads tiny model once ~4MB to cache)
            self._ranker = Ranker(model_name=self.model_name, cache_dir="./cache")
            self._available = True
            print(f"[INFO] FlashRank initialized with model: {self.model_name}")
        except Exception as exc:
            print(f"[WARN] FlashRank unavailable, will fallback to score sorting: {exc}")
            self._available = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = FlashRankService()
        return cls._instance

    @staticmethod
    def _extract_passage_text(payload: Dict[str, Any]) -> str:
        """Constructs a descriptive representation of the food payload for reranking."""
        parts = []
        name = (
            payload.get("name")
            or payload.get("title")
            or payload.get("recipe_name")
            or payload.get("food_name")
            or payload.get("dish_name")
            or payload.get("food")
            or payload.get("Shrt_Desc")
            or ""
        )
        if name:
            parts.append(str(name))

        category = payload.get("category") or payload.get("source_dataset")
        if category:
            parts.append(f"Loại: {category}")

        calories = payload.get("calories") or payload.get("Energ_Kcal") or payload.get("energy_kcal")
        if calories:
            parts.append(f"{calories} kcal")

        protein = payload.get("protein") or payload.get("Protein_(g)")
        if protein:
            parts.append(f"Protein: {protein}g")

        ingredients = payload.get("cleaned_ingredients") or payload.get("ingredients")
        if ingredients:
            if isinstance(ingredients, list):
                parts.append(", ".join(str(i) for i in ingredients[:5]))
            else:
                parts.append(str(ingredients)[:120])

        return " | ".join(parts)[:300]

    def rerank_hits(
        self,
        query: str,
        hits: List[Any],
        top_k: int = 5
    ) -> List[Any]:
        """Reranks Qdrant search hits using FlashRank cross-encoder relevance."""
        if not hits:
            return []

        if not self._available or self._ranker is None:
            return hits[:top_k]

        passages = []
        for idx, hit in enumerate(hits):
            payload = getattr(hit, "payload", {}) or {}
            text = self._extract_passage_text(payload)
            passages.append({
                "id": idx,
                "text": text,
                "meta": hit
            })

        try:
            from flashrank import RerankRequest
            rerank_request = RerankRequest(query=query, passages=passages)
            ranked_results = self._ranker.rerank(rerank_request)

            reranked_hits = []
            for item in ranked_results[:top_k]:
                hit = item.get("meta")
                if hit is not None:
                    # Save cross-encoder score on hit
                    hit.rerank_score = float(item.get("score", 0.0))
                    reranked_hits.append(hit)

            return reranked_hits
        except Exception as exc:
            print(f"[ERROR] Rerank error: {exc}")
            return hits[:top_k]
