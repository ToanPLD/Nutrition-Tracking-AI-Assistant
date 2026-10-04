import math
import re
import unicodedata

import numpy as np
try:
    from qdrant_client import QdrantClient
except Exception:
    from core.services.retrieval.qdrant_rest_client import QdrantRestClient as QdrantClient

from config.settings import settings
from core.embedding.clip_service import CLIPService


class ViTCNNFoodClassifier:
    """
    CLIP uses a ViT image encoder, so this service gives the image pipeline
    a concrete ViT-based visual classifier without adding another heavy model.
    """

    CANDIDATES = [
        {
            "label": "bun bo hue",
            "display": "bún bò Huế",
            "aliases": ["bun bo hue", "beef noodle soup", "vietnamese spicy beef noodle soup"],
            "ingredients": ["bún", "thịt bò", "nước dùng", "rau thơm"],
            "visual_form": "noodle_soup",
            "category": "main",
        },
        {
            "label": "bun rieu",
            "display": "bún riêu",
            "aliases": ["bun rieu", "crab noodle soup", "tomato crab noodle soup"],
            "ingredients": ["bún", "cà chua", "riêu cua", "nước dùng"],
            "visual_form": "noodle_soup",
            "category": "main",
        },
        {
            "label": "pho",
            "display": "phở",
            "aliases": ["pho", "vietnamese noodle soup", "beef pho", "chicken pho"],
            "ingredients": ["bánh phở", "nước dùng", "thịt", "rau thơm"],
            "visual_form": "noodle_soup",
            "category": "main",
        },
        {
            "label": "com tam",
            "display": "cơm tấm",
            "aliases": [
                "com tam", "broken rice", "vietnamese rice plate",
                "vietnamese pork chop", "vietnamese pork chops",
                "grilled pork chop", "pork chop", "pork chops"
            ],
            "ingredients": ["cơm", "sườn", "pork chop", "trứng", "đồ chua"],
            "visual_form": "rice_plate",
            "category": "main",
        },
        {
            "label": "pizza",
            "display": "pizza",
            "aliases": ["pizza", "cheese pizza", "pepperoni pizza"],
            "ingredients": ["đế bánh", "phô mai", "sốt cà chua"],
            "visual_form": "pizza",
            "category": "main",
        },
        {
            "label": "sushi",
            "display": "sushi",
            "aliases": ["sushi", "maki", "nigiri", "sashimi", "sushi platter"],
            "ingredients": ["cơm sushi", "rong biển", "cá", "hải sản"],
            "visual_form": "sushi",
            "category": "main",
        },
        {
            "label": "salad with chicken",
            "display": "salad gà",
            "aliases": ["salad", "chicken salad", "vegetable salad with chicken"],
            "ingredients": ["rau", "thịt gà"],
            "visual_form": "salad",
            "category": "main",
        },
        {
            "label": "rice bowl",
            "display": "cơm tô",
            "aliases": ["rice bowl", "rice plate", "cooked rice"],
            "ingredients": ["cơm", "món mặn"],
            "visual_form": "bowl",
            "category": "main",
        },
        {
            "label": "noodle soup",
            "display": "mì/bún nước",
            "aliases": ["noodle soup", "ramen", "udon", "noodles in broth"],
            "ingredients": ["mì hoặc bún", "nước dùng"],
            "visual_form": "noodle_soup",
            "category": "main",
        },
        {
            "label": "burger",
            "display": "burger",
            "aliases": ["burger", "hamburger", "cheeseburger"],
            "ingredients": ["bánh mì", "thịt", "rau", "sốt"],
            "visual_form": "sandwich",
            "category": "main",
        },
        {
            "label": "sandwich",
            "display": "sandwich",
            "aliases": ["sandwich", "banh mi", "bread sandwich"],
            "ingredients": ["bánh mì", "nhân"],
            "visual_form": "sandwich",
            "category": "main",
        },
        {
            "label": "pasta",
            "display": "pasta",
            "aliases": ["pasta", "spaghetti", "macaroni"],
            "ingredients": ["mì pasta", "sốt"],
            "visual_form": "plate",
            "category": "main",
        },
        {
            "label": "fried chicken",
            "display": "gà chiên",
            "aliases": ["fried chicken", "chicken nuggets", "crispy chicken"],
            "ingredients": ["thịt gà", "lớp bột chiên"],
            "visual_form": "plate",
            "category": "main",
        },
        {
            "label": "steak",
            "display": "bít tết",
            "aliases": ["steak", "beef steak", "grilled beef"],
            "ingredients": ["thịt bò"],
            "visual_form": "plate",
            "category": "main",
        },
        {
            "label": "soup",
            "display": "súp/canh",
            "aliases": ["soup", "broth", "stew"],
            "ingredients": ["nước dùng"],
            "visual_form": "soup",
            "category": "main",
        },
        {
            "label": "dessert",
            "display": "món tráng miệng",
            "aliases": ["dessert", "cake", "sweet", "ice cream"],
            "ingredients": ["đường", "bột hoặc sữa"],
            "visual_form": "dessert",
            "category": "dessert",
        },
    ]

    YOLO_FOOD_LABELS = {
        "banana", "apple", "orange", "broccoli", "carrot", "hot dog",
        "pizza", "donut", "cake", "sandwich"
    }
    YOLO_CONTAINER_LABELS = {
        "bowl", "cup", "wine glass", "fork", "knife", "spoon", "dining table"
    }
    VISUAL_MATCH_STOPWORDS = {
        "food", "dish", "meal", "recipe", "fresh", "healthy", "snack",
        "diet", "table", "plate", "cheese", "with", "and", "the"
    }

    def __init__(self, clip=None):
        self.clip = clip or CLIPService()
        self._qdrant = None
        self._qdrant_error = None
        self._yolo = None
        self._yolo_error = None
        self._unet = None
        self._unet_device = None
        self._unet_error = None
        self._cnn = None
        self._cnn_preprocess = None
        self._cnn_categories = []
        self._cnn_device = None
        self._cnn_error = None

    def _normalize_text(self, text):
        text = unicodedata.normalize("NFKD", str(text or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return text.replace("đ", "d").lower()

    def _normalize_vector(self, vector):
        array = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(array)
        if norm == 0:
            return array
        return array / norm

    def _qdrant_client(self):
        if not settings.VISION_QDRANT_ENABLED:
            return None
        if self._qdrant is not None:
            return self._qdrant
        if self._qdrant_error:
            return None

        try:
            self._qdrant = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
                prefer_grpc=False,
                timeout=20.0
            )
            return self._qdrant
        except Exception as exc:
            self._qdrant_error = str(exc)
            return None

    def _payload_name(self, payload):
        for key in ["dish_name", "food_name", "name", "title", "recipe_title", "product_name"]:
            value = (payload or {}).get(key)
            if value not in (None, ""):
                return str(value)
        return None

    def _payload_ingredients(self, payload):
        if not payload:
            return []

        for key in [
            "cleaned_ingredients_list", "ingredients_list", "visible_ingredients",
            "ingredients", "cleaned_ingredients", "ingredients_text"
        ]:
            value = payload.get(key)
            if not value:
                continue
            if isinstance(value, list):
                return [str(item) for item in value if item][:8]
            return [
                item.strip()
                for item in re.split(r"[,;|]", str(value))
                if item.strip()
            ][:8]
        return []

    def _compact_visual_hit(self, hit, collection):
        payload = hit.payload or {}
        return {
            "collection": collection,
            "score": round(float(getattr(hit, "score", 0) or 0), 4),
            "name": self._payload_name(payload),
            "ingredients": self._payload_ingredients(payload),
            "image_caption": payload.get("image_caption"),
            "visual_tags": payload.get("visual_tags", []),
            "category": payload.get("category") or payload.get("categories"),
            "source_dataset": payload.get("source_dataset"),
            "source_row": payload.get("source_row"),
            "image_name": payload.get("image_name"),
        }

    def _search_visual_qdrant(self, image_vec, top_k=None):
        client = self._qdrant_client()
        if client is None or image_vec is None:
            return {
                "enabled": bool(settings.VISION_QDRANT_ENABLED),
                "error": self._qdrant_error,
                "top_matches": [],
            }

        top_k = top_k or settings.VISION_QDRANT_TOP_K
        matches = []
        errors = []
        for collection in settings.VISION_QDRANT_IMAGE_COLLECTIONS:
            try:
                # Multimodal recipe collection uses named vector "image".
                query_vector = (
                    ("image", image_vec)
                    if collection == settings.RECIPE_IMAGE_DATASET_COLLECTION
                    else image_vec
                )
                hits = client.search(
                    collection_name=collection,
                    query_vector=query_vector,
                    limit=top_k,
                    with_payload=True
                )
                for hit in hits or []:
                    if float(hit.score or 0) < settings.VISION_QDRANT_MIN_SCORE:
                        continue
                    matches.append(self._compact_visual_hit(hit, collection))
            except Exception as exc:
                errors.append(f"{collection}: {exc}")

        matches.sort(key=lambda item: item.get("score", 0), reverse=True)
        return {
            "enabled": True,
            "collections": list(settings.VISION_QDRANT_IMAGE_COLLECTIONS),
            "top_matches": matches[:top_k],
            "errors": errors[:3],
        }

    def _filename_bonus(self, candidate, filename_hint):
        normalized = self._normalize_text(filename_hint)
        if not normalized:
            return 0.0

        compact = re.sub(r"[^a-z0-9]+", " ", normalized)
        aliases = [candidate["label"], candidate["display"], *candidate.get("aliases", [])]
        for alias in aliases:
            alias_norm = self._normalize_text(alias)
            alias_tokens = [token for token in re.findall(r"[a-z0-9]+", alias_norm) if len(token) > 1]
            if alias_norm and alias_norm in compact:
                return 0.18
            if alias_tokens and all(token in compact for token in alias_tokens[:3]):
                return 0.12
        return 0.0

    def _load_yolo(self):
        if not settings.VISION_YOLO_ENABLED:
            return False
        if self._yolo is not None:
            return True
        if self._yolo_error:
            return False

        try:
            from ultralytics import YOLO

            self._yolo = YOLO(settings.VISION_YOLO_MODEL)
            return True
        except Exception as exc:
            self._yolo_error = str(exc)
            return False

    def _detect_yolo(self, image, top_k=8):
        if not self._load_yolo():
            return {
                "enabled": False,
                "model": settings.VISION_YOLO_MODEL,
                "error": self._yolo_error,
                "detections": [],
                "selected_region": None,
            }

        try:
            rgb = image.convert("RGB")
            width, height = rgb.size
            results = self._yolo.predict(
                source=np.asarray(rgb),
                conf=settings.VISION_YOLO_CONFIDENCE,
                imgsz=settings.VISION_YOLO_IMAGE_SIZE,
                verbose=False
            )
            detections = []
            result = results[0] if results else None
            names = getattr(result, "names", {}) if result is not None else {}
            boxes = getattr(result, "boxes", None) if result is not None else None

            if boxes is not None:
                xyxy = boxes.xyxy.detach().cpu().numpy().tolist()
                confs = boxes.conf.detach().cpu().numpy().tolist()
                classes = boxes.cls.detach().cpu().numpy().astype(int).tolist()
                for bbox, confidence, class_id in zip(xyxy, confs, classes):
                    label = str(names.get(class_id, class_id))
                    x1, y1, x2, y2 = self._clamp_bbox(bbox, width, height)
                    area_ratio = ((x2 - x1) * (y2 - y1)) / max(1, width * height)
                    detections.append({
                        "label": label,
                        "confidence": round(float(confidence), 4),
                        "bbox": [x1, y1, x2, y2],
                        "area_ratio": round(float(area_ratio), 4),
                        "is_food_like": label in self.YOLO_FOOD_LABELS,
                        "is_food_container": label in self.YOLO_CONTAINER_LABELS,
                    })

            detections.sort(
                key=lambda item: (
                    item["is_food_like"],
                    item["is_food_container"],
                    item["confidence"],
                    item["area_ratio"],
                ),
                reverse=True
            )
            selected = self._select_yolo_region(detections, width, height)
            return {
                "enabled": True,
                "model": settings.VISION_YOLO_MODEL,
                "detections": detections[:top_k],
                "selected_region": selected,
            }
        except Exception as exc:
            return {
                "enabled": False,
                "model": settings.VISION_YOLO_MODEL,
                "error": str(exc),
                "detections": [],
                "selected_region": None,
            }

    def _select_yolo_region(self, detections, width, height):
        candidates = [
            item for item in detections
            if (
                item.get("is_food_like")
                or item.get("is_food_container")
            )
            and item.get("label") != "dining table"
        ]
        if not candidates:
            candidates = [
                item for item in detections
                if item.get("is_food_like") or item.get("is_food_container")
            ]
        if not candidates:
            return None

        first = candidates[0]
        should_union = (
            len(candidates) > 1
            and (
                first.get("area_ratio", 1) < 0.35
                or not first.get("is_food_like")
            )
        )
        if not should_union:
            return first

        union_items = candidates[:4]
        x1 = min(item["bbox"][0] for item in union_items)
        y1 = min(item["bbox"][1] for item in union_items)
        x2 = max(item["bbox"][2] for item in union_items)
        y2 = max(item["bbox"][3] for item in union_items)
        bbox = self._clamp_bbox([x1, y1, x2, y2], width, height)
        union_area_ratio = (
            (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        ) / max(1, width * height)

        # If union expands to almost the whole photo, the largest single region
        # is a cleaner crop for classifier embeddings.
        if union_area_ratio > 0.78:
            return first

        labels = sorted({item.get("label") for item in union_items if item.get("label")})
        return {
            "label": "combined_food_region",
            "confidence": round(max(float(item.get("confidence") or 0) for item in union_items), 4),
            "bbox": bbox,
            "area_ratio": round(float(union_area_ratio), 4),
            "is_food_like": any(item.get("is_food_like") for item in union_items),
            "is_food_container": any(item.get("is_food_container") for item in union_items),
            "source_labels": labels,
        }

    def _load_unet(self):
        if not settings.VISION_UNET_ENABLED:
            return False
        if self._unet is not None:
            return True
        if self._unet_error:
            return False
        if not settings.VISION_UNET_MODEL_PATH:
            self._unet_error = "VISION_UNET_MODEL_PATH is not configured"
            return False

        try:
            import torch

            self._unet_device = "cuda" if torch.cuda.is_available() else "cpu"
            self._unet = torch.jit.load(
                settings.VISION_UNET_MODEL_PATH,
                map_location=self._unet_device
            )
            self._unet.eval()
            return True
        except Exception as exc:
            self._unet_error = str(exc)
            return False

    def _segment_unet(self, image):
        if not self._load_unet():
            return {
                "enabled": False,
                "model_path": settings.VISION_UNET_MODEL_PATH,
                "error": self._unet_error,
                "mask_area_ratio": None,
                "bbox": None,
            }

        try:
            import torch
            from PIL import Image

            rgb = image.convert("RGB")
            original_width, original_height = rgb.size
            input_size = int(settings.VISION_UNET_INPUT_SIZE)
            resized = rgb.resize((input_size, input_size), Image.BILINEAR)
            array = np.asarray(resized, dtype=np.float32) / 255.0
            tensor = (
                torch.from_numpy(array)
                .permute(2, 0, 1)
                .unsqueeze(0)
                .to(self._unet_device)
            )
            with torch.no_grad():
                output = self._unet(tensor)
                if isinstance(output, (list, tuple)):
                    output = output[0]
                if isinstance(output, dict):
                    output = output["out"] if "out" in output else next(iter(output.values()))
                mask = torch.sigmoid(output).detach().cpu().numpy()[0]

            mask = np.squeeze(mask)
            binary = mask >= settings.VISION_UNET_MASK_THRESHOLD
            ys, xs = np.where(binary)
            if len(xs) == 0 or len(ys) == 0:
                return {
                    "enabled": True,
                    "model_path": settings.VISION_UNET_MODEL_PATH,
                    "mask_area_ratio": 0,
                    "bbox": None,
                }

            scale_x = original_width / input_size
            scale_y = original_height / input_size
            bbox = [
                int(xs.min() * scale_x),
                int(ys.min() * scale_y),
                int((xs.max() + 1) * scale_x),
                int((ys.max() + 1) * scale_y),
            ]
            return {
                "enabled": True,
                "model_path": settings.VISION_UNET_MODEL_PATH,
                "mask_area_ratio": round(float(binary.mean()), 4),
                "bbox": self._clamp_bbox(bbox, original_width, original_height),
            }
        except Exception as exc:
            return {
                "enabled": False,
                "model_path": settings.VISION_UNET_MODEL_PATH,
                "error": str(exc),
                "mask_area_ratio": None,
                "bbox": None,
            }

    def _clamp_bbox(self, bbox, width, height):
        x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
        x1 = max(0, min(width - 1, x1))
        y1 = max(0, min(height - 1, y1))
        x2 = max(x1 + 1, min(width, x2))
        y2 = max(y1 + 1, min(height, y2))
        return [x1, y1, x2, y2]

    def _expand_bbox(self, bbox, width, height, padding=0.08):
        x1, y1, x2, y2 = bbox
        pad_x = int((x2 - x1) * padding)
        pad_y = int((y2 - y1) * padding)
        return self._clamp_bbox(
            [x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y],
            width,
            height
        )

    def _crop_food_region(self, image, yolo_analysis, unet_analysis):
        width, height = image.size
        bbox = None
        source = "full_image"

        if (unet_analysis or {}).get("bbox"):
            bbox = unet_analysis["bbox"]
            source = "unet_mask"
        elif (yolo_analysis or {}).get("selected_region"):
            bbox = yolo_analysis["selected_region"].get("bbox")
            source = "yolov8s_detection"

        if not bbox:
            return image, {
                "source": source,
                "bbox": None,
                "area_ratio": 1.0,
            }

        crop_bbox = self._expand_bbox(bbox, width, height)
        x1, y1, x2, y2 = crop_bbox
        return image.crop((x1, y1, x2, y2)), {
            "source": source,
            "bbox": crop_bbox,
            "area_ratio": round(((x2 - x1) * (y2 - y1)) / max(1, width * height), 4),
        }

    def _load_cnn(self):
        if not settings.IMAGE_CLASSIFIER_CNN_ENABLED:
            return False
        if self._cnn is not None:
            return True
        if self._cnn_error:
            return False

        try:
            import torch
            from torchvision.models import ResNet50_Weights, resnet50

            weights = ResNet50_Weights.IMAGENET1K_V1
            self._cnn_device = "cuda" if torch.cuda.is_available() else "cpu"
            self._cnn_preprocess = weights.transforms()
            self._cnn_categories = weights.meta.get("categories", [])
            self._cnn = resnet50(weights=weights).to(self._cnn_device)
            self._cnn.eval()
            return True
        except Exception as exc:
            self._cnn_error = str(exc)
            return False

    def _classify_cnn(self, image, top_k=5):
        if not self._load_cnn():
            return {
                "enabled": False,
                "model": settings.IMAGE_CLASSIFIER_CNN_MODEL,
                "error": self._cnn_error,
                "top_predictions": [],
            }

        try:
            import torch

            tensor = self._cnn_preprocess(image.convert("RGB")).unsqueeze(0).to(self._cnn_device)
            with torch.no_grad():
                logits = self._cnn(tensor)[0]
                probs = torch.nn.functional.softmax(logits, dim=0)
                values, indexes = torch.topk(probs, k=min(top_k, len(probs)))

            predictions = []
            for value, index in zip(values.detach().cpu().tolist(), indexes.detach().cpu().tolist()):
                label = self._cnn_categories[index] if index < len(self._cnn_categories) else str(index)
                predictions.append({
                    "label": label,
                    "probability": round(float(value), 4),
                })

            return {
                "enabled": True,
                "model": settings.IMAGE_CLASSIFIER_CNN_MODEL,
                "top_predictions": predictions,
            }
        except Exception as exc:
            return {
                "enabled": False,
                "model": settings.IMAGE_CLASSIFIER_CNN_MODEL,
                "error": str(exc),
                "top_predictions": [],
            }

    def _cnn_bonus(self, candidate, cnn_analysis):
        labels = " ".join(
            self._normalize_text(item.get("label", ""))
            for item in (cnn_analysis or {}).get("top_predictions", [])
        )
        if not labels:
            return 0.0

        candidate_terms = [candidate["label"], candidate["display"], *candidate.get("aliases", [])]
        for term in candidate_terms:
            term_norm = self._normalize_text(term)
            if term_norm and term_norm in labels:
                return 0.08

        visual_form = candidate.get("visual_form")
        if visual_form == "pizza" and "pizza" in labels:
            return 0.10
        if visual_form == "sandwich" and any(term in labels for term in ["burger", "cheeseburger", "hotdog", "sandwich"]):
            return 0.06
        if visual_form == "noodle_soup" and any(term in labels for term in ["soup", "bowl", "hot pot", "consomme"]):
            return 0.04
        if visual_form == "sushi" and "sushi" in labels:
            return 0.08
        if visual_form == "dessert" and any(term in labels for term in ["cake", "ice cream", "trifle", "custard"]):
            return 0.06
        if visual_form == "rice_plate" and any(term in labels for term in ["meat loaf", "plate", "mashed potato"]):
            return 0.07
        return 0.0

    def _detector_bonus(self, candidate, yolo_analysis):
        labels = {
            self._normalize_text(item.get("label", ""))
            for item in (yolo_analysis or {}).get("detections", [])
            if item.get("is_food_like") or item.get("is_food_container")
        }
        if not labels:
            return 0.0

        visual_form = candidate.get("visual_form")
        candidate_terms = {
            self._normalize_text(term)
            for term in [candidate["label"], candidate["display"], *candidate.get("aliases", [])]
        }
        if labels & candidate_terms:
            return 0.12
        if visual_form == "pizza" and "pizza" in labels:
            return 0.14
        if visual_form == "sandwich" and any(term in labels for term in ["sandwich", "hot dog"]):
            return 0.08
        if visual_form == "dessert" and any(term in labels for term in ["cake", "donut"]):
            return 0.02
        if visual_form in {"bowl", "noodle_soup", "soup"} and "bowl" in labels:
            return 0.05
        return 0.0

    def _qdrant_bonus(self, candidate, qdrant_analysis):
        matches = (qdrant_analysis or {}).get("top_matches") or []
        if not matches:
            return 0.0

        candidate_tokens = self._candidate_tokens(candidate)
        if not candidate_tokens:
            return 0.0

        best_overlap = 0.0
        for match in matches[:5]:
            match_text = " ".join([
                str(match.get("name") or ""),
                str(match.get("image_caption") or ""),
                " ".join(match.get("ingredients") or []),
                " ".join(str(tag) for tag in (match.get("visual_tags") or [])),
            ])
            match_tokens = set(re.findall(r"[a-z0-9]+", self._normalize_text(match_text)))
            overlap = candidate_tokens & match_tokens
            if overlap:
                best_overlap = max(best_overlap, float(match.get("score") or 0))

        return min(0.16, best_overlap * settings.VISION_QDRANT_SCORE_WEIGHT)

    def _candidate_tokens(self, candidate, include_ingredients=True):
        tokens = set()
        terms = [
            candidate.get("label"),
            candidate.get("display"),
            *candidate.get("aliases", []),
        ]
        if include_ingredients:
            terms.extend(candidate.get("ingredients", []))

        for term in terms:
            tokens.update(re.findall(r"[a-z0-9]+", self._normalize_text(term)))
        return {
            token for token in tokens
            if len(token) > 2 and token not in self.VISUAL_MATCH_STOPWORDS
        }

    def _match_tokens(self, match):
        text = " ".join([
            str(match.get("name") or ""),
            str(match.get("image_caption") or ""),
            " ".join(match.get("ingredients") or []),
            " ".join(str(tag) for tag in (match.get("visual_tags") or [])),
        ])
        return {
            token for token in re.findall(r"[a-z0-9]+", self._normalize_text(text))
            if len(token) > 2 and token not in self.VISUAL_MATCH_STOPWORDS
        }

    def _rerank_visual_matches(self, qdrant_analysis, predictions):
        qdrant_analysis = qdrant_analysis if isinstance(qdrant_analysis, dict) else {}
        matches = qdrant_analysis.get("top_matches") or []
        if not matches or not predictions:
            return qdrant_analysis

        candidate_tokens = set()
        prediction_scope = (
            predictions[:1]
            if float(predictions[0].get("probability") or 0) >= 0.5
            else predictions[:3]
        )
        for prediction in prediction_scope:
            candidate_tokens.update(self._candidate_tokens({
                "label": prediction.get("label"),
                "display": prediction.get("name"),
                "aliases": prediction.get("aliases") or [],
                "ingredients": prediction.get("ingredients") or [],
            }, include_ingredients=False))

        relevant = []
        for match in matches:
            overlap = candidate_tokens & self._match_tokens(match)
            if not overlap:
                continue
            item = dict(match)
            item["relevance_terms"] = sorted(overlap)[:8]
            item["relevance_score"] = round(
                len(overlap) + float(match.get("score") or 0),
                4
            )
            relevant.append(item)

        relevant.sort(
            key=lambda item: (item.get("relevance_score", 0), item.get("score", 0)),
            reverse=True
        )
        updated = dict(qdrant_analysis)
        updated["raw_match_count"] = len(matches)
        updated["top_matches"] = relevant[:settings.VISION_QDRANT_TOP_K]
        return updated

    def classify(self, image, filename_hint=None, top_k=None):
        top_k = top_k or settings.IMAGE_CLASSIFIER_TOP_K
        yolo_analysis = self._detect_yolo(image)
        unet_analysis = self._segment_unet(image)
        analysis_image, crop_analysis = self._crop_food_region(
            image=image,
            yolo_analysis=yolo_analysis,
            unet_analysis=unet_analysis
        )
        raw_image_vec = self.clip.embed_image_pil(analysis_image)
        image_vec = self._normalize_vector(raw_image_vec)
        cnn_analysis = self._classify_cnn(analysis_image)
        qdrant_analysis = self._search_visual_qdrant(raw_image_vec)
        prompts = [
            f"a clear food photo of {candidate['label']}"
            for candidate in self.CANDIDATES
        ]
        text_vectors = [
            self._normalize_vector(vector)
            for vector in self.clip.embed_text_batch(prompts)
        ]

        raw_scores = []
        for candidate, text_vec in zip(self.CANDIDATES, text_vectors):
            score = float(np.dot(image_vec, text_vec))
            score += self._filename_bonus(candidate, filename_hint)
            score += self._detector_bonus(candidate, yolo_analysis)
            score += self._cnn_bonus(candidate, cnn_analysis)
            score += self._qdrant_bonus(candidate, qdrant_analysis)
            raw_scores.append(score)

        max_score = max(raw_scores) if raw_scores else 0.0
        exp_scores = [math.exp((score - max_score) * 12) for score in raw_scores]
        total = sum(exp_scores) or 1.0

        predictions = []
        for candidate, score, exp_score in zip(self.CANDIDATES, raw_scores, exp_scores):
            predictions.append({
                "name": candidate["display"],
                "label": candidate["label"],
                "probability": round(exp_score / total, 4),
                "score": round(score, 4),
                "visual_form": candidate["visual_form"],
                "category": candidate["category"],
                "ingredients": candidate["ingredients"],
                "aliases": candidate["aliases"],
            })

        predictions.sort(key=lambda item: (item["probability"], item["score"]), reverse=True)
        qdrant_analysis = self._rerank_visual_matches(qdrant_analysis, predictions)
        return {
            "model": settings.IMAGE_CLASSIFIER_MODEL,
            "backbone": settings.IMAGE_CLASSIFIER_BACKBONE,
            "detector_analysis": yolo_analysis,
            "segmentation_analysis": unet_analysis,
            "crop_analysis": crop_analysis,
            "cnn_analysis": cnn_analysis,
            "qdrant_visual_analysis": qdrant_analysis,
            "top_predictions": predictions[:top_k],
            "confidence": predictions[0]["probability"] if predictions else 0,
        }

    def to_vision_seed(self, classification):
        predictions = classification.get("top_predictions") or []
        visual_matches = (
            (classification.get("qdrant_visual_analysis") or {})
            .get("top_matches") or []
        )
        qdrant_top = next(
            (
                item for item in visual_matches
                if item.get("name") and float(item.get("score") or 0) >= settings.VISION_QDRANT_MIN_SCORE
            ),
            None
        )
        if not predictions and not qdrant_top:
            return {
                "dish_name": "unknown",
                "confidence": 0,
                "possible_dishes": [],
            }

        top = predictions[0] if predictions else {}
        dish_name = qdrant_top.get("name") if qdrant_top else top["name"]
        ingredients = (
            qdrant_top.get("ingredients")
            if qdrant_top and qdrant_top.get("ingredients")
            else top.get("ingredients", [])
        )
        confidence = (
            min(0.95, float(qdrant_top.get("score") or 0))
            if qdrant_top
            else top["probability"]
        )
        possible_dishes = []
        if qdrant_top:
            possible_dishes.append({
                "name": qdrant_top.get("name"),
                "probability": qdrant_top.get("score"),
                "why": f"Qdrant visual nearest neighbor ({qdrant_top.get('collection')})",
            })
        possible_dishes.extend([
            {
                "name": item["name"],
                "probability": item["probability"],
                "why": "ViT image classifier similarity",
            }
            for item in predictions[:5]
        ])
        detector = classification.get("detector_analysis") or {}
        crop = classification.get("crop_analysis") or {}
        detector_labels = [
            item.get("label")
            for item in detector.get("detections", [])[:5]
            if item.get("label")
        ]

        return {
            "dish_name": dish_name,
            "possible_dishes": possible_dishes[:6],
            "description": f"YOLOv8s/UNet/ResNet50/CLIP-Qdrant nhận diện ảnh giống {dish_name} nhất.",
            "image_observations": [
                (
                    f"YOLOv8s phát hiện vùng chính bằng {crop.get('source')} tại bbox {crop.get('bbox')}."
                    if crop.get("bbox") else "YOLOv8s không tách được vùng món rõ, dùng toàn ảnh để phân tích."
                ),
                (
                    "YOLO labels: " + ", ".join(detector_labels[:5]) + "."
                    if detector_labels else "Không có label YOLO food/container rõ."
                ),
                (
                    f"ViT/CNN classifier top-1: {top.get('name')} ({round(top.get('probability', 0) * 100)}%)."
                    if top else "Không có top prediction từ ViT/CNN classifier."
                )
            ] + [
                f"Qdrant visual match: {item.get('name')} (score {item.get('score')})."
                for item in visual_matches[:3]
                if item.get("name")
            ],
            "visible_vs_inferred": {
                "visible": [],
                "inferred": [dish_name, *ingredients],
                "not_visible": ["khẩu phần chính xác", "gia vị ẩn", "cách nấu chi tiết"],
            },
            "identification_evidence": [
                "YOLOv8s detect vùng món, UNet refine mask nếu có checkpoint, ResNet50 classify crop, CLIP/Qdrant đối chiếu nearest-neighbor.",
            ],
            "ingredients": ingredients,
            "category": top.get("category") or (qdrant_top.get("category") if qdrant_top else "unknown"),
            "visual_form": top.get("visual_form") or "unknown",
            "portion_description": None,
            "portion_estimation": {
                "servings": None,
                "estimated_grams": None,
                "volume_or_count": None,
                "method": "unknown",
                "uncertainty": "high",
            },
            "nutrition_estimate": {
                "calories": None,
                "protein": None,
                "carbs": None,
                "fat": None,
                "fiber": None,
                "sugar": None,
                "sodium_mg": None,
                "basis": "YOLOv8s/UNet/ResNet50 classifier chỉ nhận diện món, không đủ dữ liệu khẩu phần để tính nutrition.",
                "main_calorie_drivers": [],
            },
            "dietary_assessment": {
                "health_score_0_10": None,
                "strengths": [],
                "concerns": [],
                "suitable_for": [],
                "caution_for": [],
            },
            "risk_flags": [],
            "recommendations": {},
            "table_rows": [],
            "uncertainty": {
                "level": "high",
                "reasons": ["Chỉ có nhận diện ảnh từ classifier, chưa có khẩu phần rõ."],
                "needs_user_input": ["Khẩu phần hoặc kích thước bát/đĩa khoảng bao nhiêu?"],
            },
            "confidence": confidence,
            "vit_cnn_analysis": classification,
            "visual_rag_matches": visual_matches[:5],
        }
