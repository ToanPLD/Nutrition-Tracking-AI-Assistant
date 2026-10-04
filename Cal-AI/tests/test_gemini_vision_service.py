import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from PIL import Image
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.services.vision.gemini_vision_service import GeminiVisionService


@pytest.mark.asyncio
async def test_gemini_vision_analyze_success():
    service = GeminiVisionService()
    img = Image.new("RGB", (100, 100), color="red")

    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content='''{
            "dish_name": "Phở bò",
            "vietnamese_name": "Phở bò tái nạm",
            "confidence": 0.95,
            "portion": {"estimated_grams": 450, "description": "1 tô vừa"},
            "visible_ingredients": ["bánh phở", "thịt bò", "hành lá"],
            "visual_notes": "Tô phở nóng nhiều hành hoa",
            "is_food": true
        }'''))
    ]

    with patch.object(service._client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_resp):
        result = await service.analyze_food(img)

    assert result["dish_name"] == "Phở bò"
    assert result["vietnamese_name"] == "Phở bò tái nạm"
    assert result["portion"]["estimated_grams"] == 450
    assert result["is_food"] is True
    assert result["confidence"] == 0.95


@pytest.mark.asyncio
async def test_gemini_vision_model_fallback_on_503():
    service = GeminiVisionService()
    img = Image.new("RGB", (100, 100), color="blue")

    mock_success_resp = MagicMock()
    mock_success_resp.choices = [
        MagicMock(message=MagicMock(content='''{
            "dish_name": "Cơm tấm",
            "vietnamese_name": "Cơm tấm sườn nướng",
            "confidence": 0.90,
            "portion": {"estimated_grams": 400, "description": "1 đĩa cơm tấm sườn"},
            "visible_ingredients": ["cơm tấm", "sườn nướng"],
            "visual_notes": "Sườn nướng vàng óng",
            "is_food": true
        }'''))
    ]

    # First model raises error, second succeeds
    calls = []
    async def mock_create(**kwargs):
        calls.append(kwargs.get("model"))
        if len(calls) == 1:
            raise Exception("503 Service Unavailable: No capacity available")
        return mock_success_resp

    with patch.object(service._client.chat.completions, "create", side_effect=mock_create):
        result = await service.analyze_food(img)

    assert len(calls) == 2
    assert result["dish_name"] == "Cơm tấm"
