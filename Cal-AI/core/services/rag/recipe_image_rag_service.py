try:
    from qdrant_client import QdrantClient, models
except Exception:
    from core.services.retrieval.qdrant_rest_client import QdrantRestClient as QdrantClient, models

from config.settings import settings
from core.embedding.clip_service import CLIPService
from core.embedding.text_embedding_service import TextEmbeddingService


class RecipeImageRAGService:
    """
    Dedicated multimodal RAG service for:
    pes12017000148/food-ingredients-and-recipe-dataset-with-images

    Qdrant collection uses named vectors:
    - text: 768-d MPNet recipe context vector
    - image: 512-d CLIP image/text vector for image retrieval
    """

    def __init__(self, collection_name=None):
        self.collection_name = (
            collection_name or settings.RECIPE_IMAGE_DATASET_COLLECTION
        )
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            prefer_grpc=False,
            timeout=60.0
        )
        self._text_embed = None
        self._clip = None

    @property
    def text_embed(self):
        if self._text_embed is None:
            self._text_embed = TextEmbeddingService()
        return self._text_embed

    @property
    def clip(self):
        if self._clip is None:
            self._clip = CLIPService()
        return self._clip

    def ensure_collection(self, recreate=False):
        existing = {
            collection.name
            for collection in self.client.get_collections().collections
        }

        if self.collection_name in existing and recreate:
            print(f"🧹 Recreating collection: {self.collection_name}")
            self.client.delete_collection(self.collection_name)
            existing.remove(self.collection_name)

        if self.collection_name in existing:
            self._ensure_payload_indexes()
            return

        print(f"🆕 Creating multimodal collection: {self.collection_name}")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "text": models.VectorParams(
                    size=settings.TEXT_VECTOR_DIM,
                    distance=models.Distance.COSINE
                ),
                "image": models.VectorParams(
                    size=settings.IMAGE_VECTOR_DIM,
                    distance=models.Distance.COSINE
                )
            }
        )
        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self):
        indexes = {
            "domain": models.PayloadSchemaType.KEYWORD,
            "source_dataset": models.PayloadSchemaType.KEYWORD,
            "title_slug": models.PayloadSchemaType.KEYWORD,
            "image_name": models.PayloadSchemaType.KEYWORD,
            "image_extension": models.PayloadSchemaType.KEYWORD,
            "has_image": models.PayloadSchemaType.BOOL,
            "has_caption": models.PayloadSchemaType.BOOL,
            "ingredient_count": models.PayloadSchemaType.INTEGER,
            "source_row": models.PayloadSchemaType.INTEGER,
        }

        for field_name, field_schema in indexes.items():
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=field_schema
                )
            except Exception:
                # Qdrant raises when the index already exists; that is fine.
                pass

    def upsert_points(self, items):
        if not items:
            return

        self.ensure_collection()
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=item["id"],
                    vector={
                        "text": item["text_vector"],
                        "image": item["image_vector"]
                    },
                    payload=item["payload"]
                )
                for item in items
            ]
        )

    def _build_filter(
        self,
        has_image=None,
        ingredient=None,
        title=None,
        max_ingredient_count=None
    ):
        must = []

        if has_image is not None:
            must.append(
                models.FieldCondition(
                    key="has_image",
                    match=models.MatchValue(value=bool(has_image))
                )
            )

        if ingredient:
            must.append(
                models.FieldCondition(
                    key="ingredients_search",
                    match=models.MatchText(text=str(ingredient))
                )
            )

        if title:
            must.append(
                models.FieldCondition(
                    key="title",
                    match=models.MatchText(text=str(title))
                )
            )

        if max_ingredient_count is not None:
            must.append(
                models.FieldCondition(
                    key="ingredient_count",
                    range=models.Range(lte=int(max_ingredient_count))
                )
            )

        return models.Filter(must=must) if must else None

    def search_text(
        self,
        query,
        top_k=5,
        has_image=None,
        ingredient=None,
        title=None,
        max_ingredient_count=None
    ):
        vector = self.text_embed.embed(query)
        if vector is None:
            return []

        query_filter = self._build_filter(
            has_image=has_image,
            ingredient=ingredient,
            title=title,
            max_ingredient_count=max_ingredient_count
        )

        try:
            return self.client.search(
                collection_name=self.collection_name,
                query_vector=("text", vector),
                query_filter=query_filter,
                limit=top_k,
                with_payload=True
            )
        except Exception as exc:
            if not query_filter:
                raise exc
            return self.client.search(
                collection_name=self.collection_name,
                query_vector=("text", vector),
                query_filter=self._build_filter(
                    has_image=has_image,
                    max_ingredient_count=max_ingredient_count
                ),
                limit=top_k,
                with_payload=True
            )

    def search_images(
        self,
        query=None,
        image=None,
        top_k=5,
        ingredient=None,
        title=None,
        max_ingredient_count=None
    ):
        if image is not None:
            vector = self.clip.embed_image_pil(image)
        else:
            vector = self.clip.embed_text(query or "food recipe image")

        if vector is None:
            return []

        query_filter = self._build_filter(
            has_image=True,
            ingredient=ingredient,
            title=title,
            max_ingredient_count=max_ingredient_count
        )

        try:
            return self.client.search(
                collection_name=self.collection_name,
                query_vector=("image", vector),
                query_filter=query_filter,
                limit=top_k,
                with_payload=True
            )
        except Exception as exc:
            if not query_filter:
                raise exc
            return self.client.search(
                collection_name=self.collection_name,
                query_vector=("image", vector),
                query_filter=self._build_filter(
                    has_image=True,
                    max_ingredient_count=max_ingredient_count
                ),
                limit=top_k,
                with_payload=True
            )

    def format_hits(self, hits):
        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append({
                "score": hit.score,
                "title": payload.get("title"),
                "ingredients": payload.get("cleaned_ingredients_list")
                    or payload.get("ingredients_list"),
                "instructions": payload.get("instructions"),
                "image_name": payload.get("image_name"),
                "image_file": payload.get("image_file"),
                "image_path": payload.get("image_path"),
                "image_caption": payload.get("image_caption"),
                "citation": payload.get("citation"),
                "payload": payload
            })
        return results
