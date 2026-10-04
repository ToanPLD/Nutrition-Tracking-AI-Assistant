# core/services/vision/gemini_vision_service.py

import base64
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional
from PIL import Image
from openai import AsyncOpenAI
import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


VISION_PROMPT = """Bạn là một chuyên gia thị giác máy tính và chuyên gia dinh dưỡng cao cấp.
Nhiệm vụ của bạn là quan sát kỹ bức ảnh được cung cấp, sử dụng cơ chế Visual Self-Attention để bóc tách chi tiết:
1. Món ăn này có phải là thức ăn / đồ uống không? (is_food)
2. Tên món ăn chính xác bằng tiếng Việt có dấu (vietnamese_name) và tên tiếng Anh / phổ quát (dish_name).
3. Các thành phần nguyên liệu, topping, nước dùng, nước sốt nhìn thấy rõ trong ảnh (visible_ingredients).
4. Ước tính kích thước và khối lượng thực tế của khẩu phần ăn theo gram (portion: estimated_grams, description).
5. Các ghi chú đặc trưng thị giác (màu sắc, độ béo, rau ăn kèm, phương pháp chế biến) (visual_notes).
6. Độ tự tin nhận diện từ 0.0 đến 1.0 (confidence).

Yêu cầu xuất ra DUY NHẤT một chuỗi JSON hợp lệ theo đúng cấu trúc sau (không kèm giải thích ngoài JSON):
{
  "dish_name": "Tên món ăn tiếng Anh hoặc phổ thông",
  "vietnamese_name": "Tên món ăn tiếng Việt chính xác có dấu",
  "confidence": 0.95,
  "portion": {
    "estimated_grams": 450,
    "description": "1 tô cỡ vừa / 1 đĩa tiêu chuẩn"
  },
  "visible_ingredients": ["nguyên liệu 1", "nguyên liệu 2"],
  "visual_notes": "Ghi chú quan sát thị giác",
  "is_food": true
}
Nếu ảnh không phải đồ ăn thức uống, trả về is_food: false, confidence: 0.1, dish_name: "unknown", vietnamese_name: "Không rõ món ăn".
"""


class GeminiVisionService:

    RESILIENT_MODELS = [
        "gemini-3.8-flash",
        "gemini-3.1-flash-lite-preview",
        "gemini-flash-latest",
    ]

    def __init__(self):
        api_key = (
            getattr(settings, "GEMINI_API_KEY", "")
            or getattr(settings, "LLM_API_KEY", "")
            or getattr(settings, "OPENAI_API_KEY", "")
            or "dummy_key"
        )
        base_url = (
            getattr(settings, "GEMINI_BASE_URL", "")
            or getattr(settings, "LLM_BASE_URL", "")
            or "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        timeout = httpx.Timeout(settings.LLM_TIMEOUT_SECONDS or 60.0, connect=10.0)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def _image_to_base64_url(self, image: Image.Image) -> str:
        img = image.convert("RGB")
        max_side = max(384, int(getattr(settings, "VISION_IMAGE_MAX_SIDE", 640)))
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"

    def _extract_json(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        # Remove markdown code block if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
            text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            # Try to match the first JSON object in text
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"Could not parse JSON from model response: {text[:100]}...")

    async def analyze_food(self, image: Image.Image, hint: str = "") -> Dict[str, Any]:
        image_url = self._image_to_base64_url(image)

        user_content: List[Dict[str, Any]] = [
            {"type": "text", "text": f"Hãy phân tích món ăn trong ảnh này. {f'Gợi ý: {hint}' if hint else ''}"},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]

        last_error = None
        for model in self.RESILIENT_MODELS:
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": VISION_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.2,
                    max_tokens=1000,
                )
                raw_text = response.choices[0].message.content or "{}"
                data = self._extract_json(raw_text)

                # Ensure default values
                data.setdefault("is_food", True)
                data.setdefault("confidence", 0.85)
                data.setdefault("dish_name", "Unknown Dish")
                data.setdefault("vietnamese_name", data.get("dish_name", "Không rõ"))
                data.setdefault("visible_ingredients", [])
                data.setdefault("visual_notes", "")
                data.setdefault("portion", {"estimated_grams": 350, "description": "1 khẩu phần tiêu chuẩn"})
                data["_model_used"] = model
                return data

            except Exception as exc:
                logger.warning(f"[GeminiVisionService] Model '{model}' failed: {exc!r}. Retrying fallback...")
                last_error = exc

        logger.error(f"[GeminiVisionService] All models in resilience pool failed. Last error: {last_error}")
        raise RuntimeError(f"Gemini Vision Service unavailable across all models: {last_error}")
