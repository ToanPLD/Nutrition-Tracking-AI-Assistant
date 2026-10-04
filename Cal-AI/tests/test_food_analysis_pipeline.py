import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from PIL import Image
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.pipelines.food_analysis_pipeline import FoodAnalysisPipeline


@pytest.mark.asyncio
async def test_pipeline_uses_gemini_vision_and_grounds_macros():
    pipeline = FoodAnalysisPipeline()
    img = Image.new("RGB", (100, 100), color="green")

    mock_vision = {
        "dish_name": "Phở bò",
        "vietnamese_name": "Phở bò tái nạm",
        "confidence": 0.95,
        "portion": {"estimated_grams": 500, "description": "1 tô phở lớn 500g"},
        "visible_ingredients": ["bánh phở", "thịt bò tái", "hành lá"],
        "visual_notes": "Tô phở lớn",
        "is_food": True
    }

    mock_rag_hit = [
        MagicMock(
            score=0.92,
            payload={
                "food_name": "Phở bò",
                "calories": 90,
                "protein": 6.5,
                "carbs": 12.0,
                "fat": 2.0
            }
        )
    ]

    with patch.object(pipeline.gemini_vision, "analyze_food", new_callable=AsyncMock, return_value=mock_vision), \
         patch.object(pipeline.rag, "hybrid_search", return_value=mock_rag_hit):
        res = await pipeline.analyze(image=img)

    assert res["name"] == "Phở bò tái nạm"
    # 500g = 5 * 100g -> 5 * 90 = 450 kcal
    assert res["calories"] == 450
    assert res["protein"] == pytest.approx(32.5)
    assert res["carbs"] == pytest.approx(60.0)
    assert res["fat"] == pytest.approx(10.0)
    assert res["confidence"] == 0.95
    assert res["estimated_portion"] == "1 tô phở lớn 500g"


@pytest.mark.asyncio
async def test_pipeline_handles_unrecognized_food():
    pipeline = FoodAnalysisPipeline()
    img = Image.new("RGB", (100, 100), color="black")

    mock_vision = {
        "dish_name": "unknown",
        "vietnamese_name": "Không rõ món ăn",
        "confidence": 0.1,
        "portion": {"estimated_grams": 0, "description": "N/A"},
        "visible_ingredients": [],
        "visual_notes": "Ảnh tối không thấy thức ăn",
        "is_food": False
    }

    with patch.object(pipeline.gemini_vision, "analyze_food", new_callable=AsyncMock, return_value=mock_vision):
        res = await pipeline.analyze(image=img)

    assert res["is_food"] is False
    assert res["confidence"] == 0.1
    assert "Không rõ" in res["name"]
