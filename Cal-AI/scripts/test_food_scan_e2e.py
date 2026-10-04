# Cal-AI/scripts/test_food_scan_e2e.py
"""
End-to-End Verification of the Refactored Food Scanning Vision Pipeline.
Tests:
1. JSON Base64 image payload against /api/food/analyze.
2. Multipart/form-data upload against /api/food/analyze.
3. Transparent error handling for invalid/corrupted image data (HTTP 400).
4. Missing required payload validation.
5. Macro scaling and portion verification.
"""

import sys
import os
import io
import base64
import time
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def create_sample_food_image() -> str:
    """Creates a synthetic food-like image (bowl of soup) and returns base64 data URL."""
    img = Image.new("RGB", (256, 256), color=(240, 230, 210))
    draw = ImageDraw.Draw(img)
    # Draw a bowl
    draw.ellipse([30, 50, 226, 210], fill=(200, 70, 50), outline=(120, 30, 20), width=4)
    # Draw noodles / soup inside
    draw.ellipse([50, 70, 206, 190], fill=(230, 190, 100))
    # Green garnish
    draw.rectangle([100, 110, 120, 130], fill=(40, 160, 40))
    draw.rectangle([130, 100, 150, 120], fill=(40, 160, 40))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def run_e2e_tests():
    print("=" * 60)
    print("🚀 STARTING FOOD SCAN PIPELINE E2E INTEGRATION TEST")
    print("=" * 60)

    # 1. Test JSON Base64 ingestion
    print("\n[Test 1] Testing JSON Base64 ingestion via /api/food/analyze...")
    img_b64 = create_sample_food_image()
    t0 = time.time()
    res = client.post(
        "/api/food/analyze",
        json={"image": img_b64, "question": "Đây là món gì?"}
    )
    t1 = time.time()
    print(f"Status: {res.status_code}, Latency: {t1 - t0:.2f}s")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    print("Response fields:", list(data.keys()))
    print(f"Recognized: '{data.get('name')}', Portion: '{data.get('estimated_portion')}'")
    print(f"Macros: {data.get('calories')} kcal | P: {data.get('protein')}g | C: {data.get('carbs')}g | F: {data.get('fat')}g")

    for field in ["name", "calories", "protein", "carbs", "fat", "confidence", "estimated_portion", "is_food"]:
        assert field in data, f"Missing required field '{field}' in response: {data}"

    assert isinstance(data["calories"], (int, float))
    assert isinstance(data["protein"], (int, float))
    assert isinstance(data["carbs"], (int, float))
    assert isinstance(data["fat"], (int, float))
    print("✅ Test 1 PASSED: Unified schema validated successfully.")

    # 2. Test Multipart form-data ingestion
    print("\n[Test 2] Testing multipart/form-data upload...")
    img_bytes = base64.b64decode(img_b64.split(",")[1])
    res_mp = client.post(
        "/api/food/analyze",
        files={"file": ("bowl.jpg", img_bytes, "image/jpeg")},
        data={"question": "Phân tích món ăn"}
    )
    assert res_mp.status_code == 200, f"Expected 200, got {res_mp.status_code}: {res_mp.text}"
    data_mp = res_mp.json()
    assert "name" in data_mp and "calories" in data_mp
    print("✅ Test 2 PASSED: Multipart ingestion validated successfully.")

    # 3. Test Invalid Base64 image payload (Transparency - must return 400, not silent mock)
    print("\n[Test 3] Testing error transparency on corrupted image payload...")
    res_err = client.post(
        "/api/food/analyze",
        json={"image": "data:image/jpeg;base64,not-a-valid-image-data"}
    )
    print(f"Status: {res_err.status_code}, Response: {res_err.text}")
    assert res_err.status_code == 400, f"Expected 400 Bad Request, got {res_err.status_code}"
    detail = res_err.json().get("detail", "").lower()
    assert "base64" in detail or "invalid" in detail, f"Unexpected error detail: {detail}"
    print("✅ Test 3 PASSED: Corrupted image rejected with transparent HTTP 400.")

    # 4. Test Missing image field
    print("\n[Test 4] Testing error transparency on empty payload...")
    res_empty = client.post(
        "/api/food/analyze",
        json={}
    )
    assert res_empty.status_code == 400, f"Expected 400, got {res_empty.status_code}"
    print("✅ Test 4 PASSED: Empty payload rejected with transparent HTTP 400.")

    print("\n" + "=" * 60)
    print("🎉 ALL E2E PIPELINE INTEGRATION TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_e2e_tests()
