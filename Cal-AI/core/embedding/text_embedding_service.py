import hashlib
import json
import threading
from collections import OrderedDict

try:
    import torch
    from sentence_transformers import SentenceTransformer
except ImportError:
    torch = None
    SentenceTransformer = None

from config.settings import settings
from core.services.cache.redis_cache import RedisCache


class _LRUCache:
    """Tiny thread-safe LRU. Keeps eviction O(1) via OrderedDict."""

    def __init__(self, capacity: int):
        self.capacity = max(1, int(capacity))
        self._data: "OrderedDict[str, list]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            value = self._data.get(key)
            if value is None:
                return None
            self._data.move_to_end(key)
            return value

    def put(self, key: str, value):
        if value is None:
            return
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self._data[key] = value
                return
            self._data[key] = value
            if len(self._data) > self.capacity:
                self._data.popitem(last=False)

    def stats(self):
        with self._lock:
            return {"size": len(self._data), "capacity": self.capacity}


class TextEmbeddingService:

    # Shared across instances within a process so multiple importers don't
    # each allocate their own L1/L2 (they would still be correct, just wasteful).
    _shared_l1 = None
    _shared_l2 = None

    def __init__(self):
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers or torch is not installed in the current environment.")

        print("[INFO] Loading 768 embedding model (mpnet)...")

        self.device = "cuda" if (torch and torch.cuda.is_available()) else "cpu"

        self.model = SentenceTransformer(
            "sentence-transformers/all-mpnet-base-v2",
            device=self.device
        )

        if TextEmbeddingService._shared_l1 is None:
            TextEmbeddingService._shared_l1 = _LRUCache(
                getattr(settings, "EMBED_L1_CACHE_SIZE", 256)
            )
        self._l1 = TextEmbeddingService._shared_l1

        if TextEmbeddingService._shared_l2 is None and getattr(
            settings, "EMBED_CACHE_ENABLED", True
        ):
            TextEmbeddingService._shared_l2 = RedisCache()
        self._l2 = TextEmbeddingService._shared_l2

    def _clean_text(self, text: str):
        if not text:
            return ""

        return text[:300]

    def _cache_key(self, text: str) -> str:
        # mpnet model is fixed and outputs 768-d unit vectors, so the only
        # input variable is the text. Hash it for a compact key.
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        return f"embed:mpnet768:v1:{digest}"

    def _l2_get(self, key: str):
        if not self._l2:
            return None
        raw = self._l2.get(key)
        if not raw:
            return None
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception:
            return None

    def _l2_put(self, key: str, vector):
        if not self._l2 or vector is None:
            return
        try:
            self._l2.set(
                key,
                json.dumps(vector, separators=(",", ":")),
                ttl=getattr(settings, "EMBED_CACHE_TTL", 86400),
            )
        except Exception:
            pass

    def _cache_get(self, text: str):
        """Layered lookup: L1 (μs) → L2 (Redis, ~RTT)."""
        key = self._cache_key(text)
        hit = self._l1.get(key)
        if hit is not None:
            return hit
        hit = self._l2_get(key)
        if hit is not None:
            # Promote into L1 so the next hit on this text is free.
            self._l1.put(key, hit)
        return hit

    def _cache_put(self, text: str, vector):
        if vector is None:
            return
        key = self._cache_key(text)
        self._l1.put(key, vector)
        self._l2_put(key, vector)

    def embed(self, text: str):
        if not text:
            return None

        cached = self._cache_get(text)
        if cached is not None:
            return cached

        try:
            vector = self.model.encode(
                text,
                normalize_embeddings=True,
            )
            result = vector.tolist()
            self._cache_put(text, result)
            return result

        except Exception as e:
            print("❌ Embed error:", e)
            return None

    def embed_batch(self, texts: list[str]):

        if not texts:
            return []

        # Resolve cache hits first; only encode the misses on GPU.
        results = [None] * len(texts)
        miss_indices = []
        miss_texts = []
        for index, text in enumerate(texts):
            if not text:
                continue
            cached = self._cache_get(text)
            if cached is not None:
                results[index] = cached
            else:
                miss_indices.append(index)
                miss_texts.append(text)

        if not miss_texts:
            return results

        try:
            vectors = self.model.encode(
                miss_texts,
                batch_size=64,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            for offset, vec in enumerate(vectors):
                index = miss_indices[offset]
                serialized = vec.tolist()
                results[index] = serialized
                self._cache_put(miss_texts[offset], serialized)
            return results

        except Exception as e:
            print("❌ Batch embed error:", e)
            return []

    def cache_stats(self):
        return {
            "l1": self._l1.stats() if self._l1 else None,
            "l2_connected": bool(self._l2 and getattr(self._l2, "client", None)),
        }
