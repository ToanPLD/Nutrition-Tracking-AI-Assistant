import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os

# Ensure Cal-AI directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.main import app
from core.pipelines.food_analysis_pipeline import FoodAnalysisPipeline


@pytest.mark.asyncio
async def test_analyze_endpoint_accepts_json_base64(monkeypatch):
    # Valid 1x1 transparent PNG as data URL
    dummy_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

    async def mock_analyze(self, image, user_id=None, filename=None, question=None):
        return {
            "name": "Bún bò Huế",
            "calories": 520,
            "protein": 30,
            "carbs": 55,
            "fat": 18,
            "confidence": 0.92
        }

    monkeypatch.setattr(FoodAnalysisPipeline, "analyze", mock_analyze)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/food/analyze", json={"image": dummy_b64, "question": ""})

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Bún bò Huế"
    assert data["calories"] == 520


@pytest.mark.asyncio
async def test_analyze_endpoint_accepts_multipart_file(monkeypatch):
    import io
    from PIL import Image as PILImage
    buf = io.BytesIO()
    PILImage.new("RGB", (10, 10), color="blue").save(buf, format="PNG")
    dummy_png_bytes = buf.getvalue()

    async def mock_analyze(self, image, user_id=None, filename=None, question=None):
        return {
            "name": "Cơm tấm sườn",
            "calories": 650,
            "confidence": 0.95
        }

    monkeypatch.setattr(FoodAnalysisPipeline, "analyze", mock_analyze)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        files = {"file": ("test.png", dummy_png_bytes, "image/png")}
        response = await ac.post("/api/food/analyze", files=files, data={"question": ""})

    assert response.status_code == 200
    assert response.json()["name"] == "Cơm tấm sườn"


@pytest.mark.asyncio
async def test_analyze_endpoint_invalid_image():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/food/analyze", json={"image": "invalid_base64_data_!@#", "question": ""})
    assert response.status_code == 400
    assert "Invalid image" in response.json().get("detail", "")

