try:
    from qdrant_client import QdrantClient, models
except Exception:
    from core.services.retrieval.qdrant_rest_client import QdrantRestClient as QdrantClient, models
from config.settings import settings


class QdrantMetaService:

    def __init__(self):
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY
        )

        self.meta_collection = "meta_vectors"

        # ✅ FIX duplicate key + dùng 768 collections
        self.collections = {
            "food": "food_vectors_768",
            "beverage": "beverage_vectors_768",
            "exercise": "exercise_vectors_768",
            "lifestyle": "lifestyle_vectors_768",
            "diet": "diet_recommendations_vectors",
            "recipe_food": "food_recipes_vectors_768",
            "recipe_general": "recipes_vectors_768",
            "recipe_image": settings.RECIPE_IMAGE_DATASET_COLLECTION
        }

        self._init_collections()

    # ================= INIT =================

    def _init_collections(self):

        try:
            collections = [
                c.name for c in self.client.get_collections().collections
            ]

            if self.meta_collection in collections:
                return

            print(f"🆕 Creating meta collection (768): {self.meta_collection}")

            self.client.create_collection(
                collection_name=self.meta_collection,
                vectors_config=models.VectorParams(
                    size=settings.TEXT_VECTOR_DIM,  # ✅ 768
                    distance=models.Distance.COSINE
                )
            )

        except Exception as e:
            print("⚠️ Qdrant not ready (skip init):", e)

    # ================= UPSERT META =================

    def upsert_meta(self, items):

        if not items:
            return

        try:
            self.client.upsert(
                collection_name=self.meta_collection,
                points=[
                    models.PointStruct(
                        id=item["id"],
                        vector=item["vector"],
                        payload=item["payload"]
                    )
                    for item in items
                ]
            )

        except Exception as e:
            print("❌ Meta upsert error:", e)

    # ================= SEARCH =================

    def search(self, vector, top_k=5):

        if vector is None:
            return []

        try:
            return self.client.search(
                collection_name=self.meta_collection,
                query_vector=vector,
                limit=top_k,
                with_payload=True
            )

        except Exception as e:
            print("❌ Meta search error:", e)
            return []

    # ================= FETCH FULL DATA =================

    def fetch_full_data(self, hits):

        results = []

        for h in hits:

            payload = h.payload or {}

            domain = payload.get("domain")
            ref_id = payload.get("ref_id")

            if not domain or domain not in self.collections:
                print("⚠️ Unknown domain:", domain)
                continue

            collection = self.collections[domain]

            try:
                point = self.client.retrieve(
                    collection_name=collection,
                    ids=[ref_id],
                    with_payload=True
                )

                if point:
                    results.append({
                        "meta_score": h.score,
                        "data": point[0].payload
                    })

            except Exception as e:
                print(f"❌ Fetch error ({collection}):", e)

        return results
