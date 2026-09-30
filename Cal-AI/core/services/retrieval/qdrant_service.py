import hashlib
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from qdrant_client import models
from config.settings import settings


class QdrantService:

    def __init__(self):

        print("👉 QDRANT URL:", settings.QDRANT_URL)

        if settings.QDRANT_URL.startswith("https"):
            self.client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
                prefer_grpc=False,
                timeout=60.0
            )
        else:
            self.client = QdrantClient(url=settings.QDRANT_URL)

        if not hasattr(self.client, "search"):
            def _compat_search(collection_name, query_vector, limit=5, query_filter=None, with_payload=True, with_vectors=False, score_threshold=None, offset=None, **kwargs):
                query_kwargs = {
                    "collection_name": collection_name,
                    "query": query_vector,
                    "limit": limit,
                    "query_filter": query_filter,
                    "with_payload": with_payload,
                    "with_vectors": with_vectors
                }
                if score_threshold is not None:
                    query_kwargs["score_threshold"] = score_threshold
                if offset is not None:
                    query_kwargs["offset"] = offset
                res = self.client.query_points(**query_kwargs)
                return getattr(res, "points", res)
            self.client.search = _compat_search

        self._collections_cache = set()
        self._refresh_collections()

    def _refresh_collections(self):
        try:
            cols = self.client.get_collections().collections
            self._collections_cache = {c.name for c in cols}
        except Exception as e:
            print("❌ Cannot fetch collections:", e)

    def available_collections(self):
        if not self._collections_cache:
            self._refresh_collections()
        return self._collections_cache

    def ensure_collection(self, name, dim):

        try:
            if name in self._collections_cache:
                return

            print(f"🆕 Creating collection: {name} (dim={dim})")

            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=dim,
                    distance=Distance.COSINE
                )
            )

            self._collections_cache.add(name)

        except Exception as e:
            print("❌ Qdrant connection error:", e)

    def _generate_id(self, payload: dict):
        raw = str(payload)
        return int(hashlib.md5(raw.encode()).hexdigest()[:8], 16)

    def upsert_generic(self, collection_name, items):

        if not items:
            return

        BATCH_SIZE = 32

        for i in range(0, len(items), BATCH_SIZE):

            chunk = items[i:i + BATCH_SIZE]

            try:
                dim = len(chunk[0]["vector"])
                self.ensure_collection(collection_name, dim)

                points = []

                for item in chunk:
                    pid = self._generate_id(item["payload"])

                    points.append(
                        PointStruct(
                            id=pid,
                            vector=item["vector"],
                            payload=item["payload"]
                        )
                    )

                self.client.upsert(
                    collection_name=collection_name,
                    points=points
                )

            except Exception as e:
                print("❌ Upsert error:", e)

    def _build_range_filter(self, min_calories=None, max_calories=None):
        if min_calories is None and max_calories is None:
            return None

        range_kwargs = {}
        if min_calories is not None:
            range_kwargs["gte"] = min_calories
        if max_calories is not None:
            range_kwargs["lte"] = max_calories

        return models.Filter(
            must=[
                models.FieldCondition(
                    key="calories",
                    range=models.Range(**range_kwargs)
                )
            ]
        )

    def search(
        self,
        collection_name,
        vector,
        top_k=5,
        query_filter=None,
        min_calories=None,
        max_calories=None,
        with_vectors=False
    ):

        if vector is None:
            return []

        try:
            final_filter = query_filter or self._build_range_filter(
                min_calories=min_calories,
                max_calories=max_calories
            )

            return self.client.search(
                collection_name=collection_name,
                query_vector=vector,
                limit=top_k,
                query_filter=final_filter,
                with_payload=True,
                with_vectors=with_vectors
            )

        except Exception as e:
            print(f"❌ Search error ({collection_name}):", e)
            return []

    def hybrid_search(self, collection, vector_a, vector_b, top_k=5, alpha=0.6):
        """
        ⚠️ CHỈ dùng khi vector cùng dimension
        """

        if len(vector_a) != len(vector_b):
            print("⚠️ Skip hybrid_search (dimension mismatch)")
            return self.search(collection, vector_a, top_k)

        try:
            hits_a = self.search(collection, vector_a, top_k)
            hits_b = self.search(collection, vector_b, top_k)

            score_map = {}

            for hit in hits_a:
                score_map[hit.id] = alpha * hit.score

            for hit in hits_b:
                if hit.id in score_map:
                    score_map[hit.id] += (1 - alpha) * hit.score
                else:
                    score_map[hit.id] = (1 - alpha) * hit.score

            merged = {hit.id: hit for hit in hits_a + hits_b}

            final_hits = list(merged.values())

            final_hits.sort(
                key=lambda x: score_map.get(x.id, 0),
                reverse=True
            )

            return final_hits[:top_k]

        except Exception as e:
            print("❌ Hybrid search error:", e)
            return []
