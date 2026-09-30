from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_ENABLED: bool = False

    TEXT_EMBEDDING_MODEL: str = "sentence-transformers/all-mpnet-base-v2"  
    IMAGE_EMBEDDING_MODEL: str = "Qwen/Qwen3-VL-Embedding-8B"          

    TEXT_VECTOR_DIM: int = 768
    IMAGE_VECTOR_DIM: int = 4096

    TEXT_COLLECTIONS: List[str] = [
        "beverage_text_vectors_768",
        "exercise_text_vectors_768",
        "food_text_vectors_768",
        "diet_recommendations_vectors",
        "exercise_vectors_768",
        "food_vectors_768",
        "food_nutrition_vectors_768",
        "nutrition5k_vectors_768",
        "food_nutrition_dev_vectors_768",
        "food_fruit_vectors_768",
        "food_global_10k_vectors_768",
        "exercise_gym_vectors_768",
        "lifestyle_vectors_768",
        "food_common_vectors_768",
        "lifestyle_obesity_vectors_768",
        "recipes_vectors_768",
        "beverage_vectors_768",
        "food_recipes_vectors_768",
        "recipes_64k_vectors_768",
        "food_recipe_images_text_768",
        "meta_vectors",
        "vn_food_vectors_768",
    ]

    FOOD_RAG_COLLECTIONS: List[str] = [
        "food_ingredients_recipes_multimodal",
        "food_recipes_vectors_768",
        "recipes_vectors_768",
        "recipes_64k_vectors_768",
        "food_recipe_images_text_768",
        "food_text_vectors_768",
        "food_common_vectors_768",
        "food_global_10k_vectors_768",
        "food_nutrition_vectors_768",
        "nutrition5k_vectors_768",
        "food_nutrition_dev_vectors_768",
        "food_vectors_768",
        "food_fruit_vectors_768",
        "vn_food_vectors_768",
    ]

    RECIPES_64K_COLLECTION: str = "recipes_64k_vectors_768"
    FOOD_RECIPE_IMAGES_TEXT_COLLECTION: str = "food_recipe_images_text_768"

    RECIPE_IMAGE_DATASET: str = (
        "pes12017000148/food-ingredients-and-recipe-dataset-with-images"
    )
    RECIPE_IMAGE_DATASET_COLLECTION: str = "food_ingredients_recipes_multimodal"
    RECIPE_IMAGE_META_DOMAIN: str = "recipe_image"

    LEGACY_COLLECTIONS: List[str] = [
        "food_vectors",
        "food_text_vectors",
        "beverage_vectors",
        "exercise_vectors",
        "lifestyle_vectors"
    ]

    TOP_K: int = 3
    FINAL_TOP_K: int = 5

    HYBRID_WEIGHT: float = 0.6
    VISION_MIN_CONFIDENCE: float = 0.65
    RAG_LOW_CONFIDENCE_THRESHOLD: float = 0.70
    RAG_REJECT_PACKAGED_ON_GENERIC_IMAGE: bool = True
    RAG_USE_QDRANT_NAME_FILTER: bool = False
    RAG_CANDIDATE_TOP_K: int = 20

    BATCH_SIZE: int = 32
    CACHE_TTL: int = 86400
    REDIS_CACHE_COMPRESS_MIN_BYTES: int = 2048
    REDIS_CACHE_MAX_VALUE_BYTES: int = 250000
    AGENTIC_CACHE_TTL: int = 1800
    AGENTIC_CACHE_ENABLED: bool = True
    EMBED_CACHE_TTL: int = 86400
    EMBED_CACHE_ENABLED: bool = True
    # L1 (in-process) embedding cache — hit cost ≈ μs, much faster than the
    # cloud Redis RTT (~270ms from VN). 256 entries × ~6 KB ≈ 1.5 MB / worker.
    EMBED_L1_CACHE_SIZE: int = 256

    VISION_MODEL: str = "llava:7b"
    VISION_API_URL: str = "http://localhost:11434/api/generate"
    VISION_TIMEOUT_SECONDS: float = 90.0
    VISION_IMAGE_MAX_SIDE: int = 640
    VISION_IMAGE_JPEG_QUALITY: int = 60
    IMAGE_CLASSIFIER_ENABLED: bool = True
    IMAGE_CLASSIFIER_BACKBONE: str = "yolov8s+unet+resnet50+clip-vit"
    IMAGE_CLASSIFIER_MODEL: str = "openai/clip-vit-base-patch32"
    # LoRA fine-tune for CLIP vision tower. Empty path disables and falls
    # back to the base model. Adapter directory must contain the PEFT
    # adapter_config.json + adapter weights produced by
    # training/train_clip_lora.py.
    CLIP_LORA_PATH: str = "models/clip-food-lora"
    CLIP_LORA_ENABLED: bool = True
    IMAGE_CLASSIFIER_CNN_ENABLED: bool = True
    IMAGE_CLASSIFIER_CNN_MODEL: str = "torchvision/resnet50-imagenet1k"
    IMAGE_CLASSIFIER_TOP_K: int = 5
    IMAGE_CLASSIFIER_MIN_CONFIDENCE: float = 0.08
    VISION_YOLO_ENABLED: bool = True
    VISION_YOLO_MODEL: str = "yolov8s.pt"
    VISION_YOLO_CONFIDENCE: float = 0.20
    VISION_YOLO_IMAGE_SIZE: int = 640
    VISION_UNET_ENABLED: bool = False
    VISION_UNET_MODEL_PATH: str = ""
    VISION_UNET_INPUT_SIZE: int = 256
    VISION_UNET_MASK_THRESHOLD: float = 0.50
    VISION_QDRANT_ENABLED: bool = True
    VISION_QDRANT_IMAGE_COLLECTIONS: List[str] = [
        "food_ingredients_recipes_multimodal",
        "food_image_vectors"
    ]
    VISION_QDRANT_TOP_K: int = 8
    VISION_QDRANT_MIN_SCORE: float = 0.18
    VISION_QDRANT_SCORE_WEIGHT: float = 0.35

    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.8-flash"
    LLM_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    LLM_API_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    LLM_BACKEND: str = "gemini"  # gemini | openai | ollama
    LLM_TIMEOUT_SECONDS: float = 60.0
    LLM_NUM_PREDICT: int = 500

    # Cloudflare R2
    CLOUDFLARE_R2_ENDPOINT: str = "https://65af18d008d80bd6b17d94abb5976544.r2.cloudflarestorage.com"
    CLOUDFLARE_R2_BUCKET: str = "images"
    CLOUDFLARE_R2_TOKEN: str = ""
    CLOUDFLARE_R2_KEY: str = ""
    CLOUDFLARE_R2_PUBLIC_URL: str = "https://65af18d008d80bd6b17d94abb5976544.r2.cloudflarestorage.com/images"


settings = Settings()
