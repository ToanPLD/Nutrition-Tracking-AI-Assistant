# Refactor Food Scan Workflow with Gemini Vision Attention & Attentive RAG Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the brittle local vision pipeline and silent fallback with an accurate, transparent food image analysis system powered by Gemini Multimodal Vision Attention and attentive Qdrant RAG grounding.

**Architecture:** Node.js backend sends authenticated food image payloads (Base64/URL) with a 60s timeout to Cal-AI's dual-ingestion `/api/food/analyze` endpoint. Cal-AI utilizes `GeminiVisionService` with visual self-attention to identify dish identity, ingredients, and portion gram estimates, grounds the results against Qdrant vector database (`vn_food_vectors_768`, `food_nutrition_vectors_768`), scales macros, and transparently returns explicit error codes whenever a step fails.

**Tech Stack:** FastAPI, Python 3.10+, AsyncOpenAI (Google Gemini endpoint), Pillow, Qdrant Client, TypeScript, Express, Node.js fetch.

**Spec:** [`docs/superpowers/specs/2026-10-04-refactor-food-scan-vision-pipeline-design.md`](file:///d:/Sources/Code/Nutrition-Tracking-AI-Assistant/docs/superpowers/specs/2026-10-04-refactor-food-scan-vision-pipeline-design.md)

## Global Constraints

- Never silently mask errors with a hardcoded mock record like `Salad with Grilled Chicken`.
- All timeouts must allow up to 60,000ms for full multimodal reasoning and vector retrieval.
- Both `application/json` (Base64 or image URL) and `multipart/form-data` must be accepted by `/api/food/analyze`.
- Use the established Gemini resilient model pool: `gemini-3.8-flash`, `gemini-3.1-flash-lite-preview`, `gemini-flash-latest`.
- Macro nutrient scaling must multiply the base 100g database profile by `(estimated_grams / 100.0)`.

## Review Focus

- Data URL prefixes (e.g. `data:image/jpeg;base64,...`) must be properly stripped before base64 decoding.
- Non-food images or low confidence (<0.35) must return a clear `UNRECOGNIZED_FOOD` status instead of hallucinated recipes.
- Network timeouts or API key issues with Google Gemini must return HTTP 503 `AI_SERVICE_UNAVAILABLE` with error diagnostics.
- Backend timeout or Cal-AI disconnect must throw an `AppError` resulting in HTTP 502 with user-friendly error copy.
- Images exceeding maximum dimensions must be safely downscaled to 512x512 with Pillow maintaining aspect ratio.

---

### Task 1: Dual-Ingestion Endpoint in Cal-AI

**Files:**
- Modify: `Cal-AI/api/routes/food_analysis.py`
- Create: `Cal-AI/tests/test_food_analysis_endpoint.py`

**Interfaces:**
- Consumes: HTTP POST request with either `application/json` (`FoodAnalysisJSONRequest`) or `multipart/form-data` (`file: UploadFile`).
- Produces: Normalized PIL Image and optional question passed into `get_food_analysis_pipeline().analyze(...)`.

- [ ] **Step 1: Write failing unit test for dual ingestion**

Create `Cal-AI/tests/test_food_analysis_endpoint.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.mark.asyncio
async def test_analyze_endpoint_accepts_json_base64(monkeypatch):
    # Dummy base64 1x1 png
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

    from core.pipelines.food_analysis_pipeline import FoodAnalysisPipeline
    monkeypatch.setattr(FoodAnalysisPipeline, "analyze", mock_analyze)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/food/analyze", json={"image": dummy_b64, "question": ""})
    assert response.status_code == 200
    assert response.json()["name"] == "Bún bò Huế"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest Cal-AI/tests/test_food_analysis_endpoint.py -v`
Expected: FAIL (422 Unprocessable Entity because `/api/food/analyze` only accepts Form/File)

- [ ] **Step 3: Implement Dual Ingestion in `Cal-AI/api/routes/food_analysis.py`**

Define `FoodAnalysisJSONRequest` with Pydantic:
```python
class FoodAnalysisJSONRequest(BaseModel):
    image: Optional[str] = None
    question: Optional[str] = ""
```
Update `@router.post("/analyze")` to inspect `Request` header:
- If `application/json`: Parse `FoodAnalysisJSONRequest`, handle base64 string (strip `data:image/...;base64,` prefix) or fetch URL via `httpx`.
- If `multipart/form-data`: Read uploaded file.
- Decode into PIL Image, thumbnail to 512x512, call `get_food_analysis_pipeline().analyze(image=image, filename=..., question=question)`.
- If parsing fails or invalid image, raise `HTTPException(status_code=400, detail="Invalid image payload")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest Cal-AI/tests/test_food_analysis_endpoint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Cal-AI/api/routes/food_analysis.py Cal-AI/tests/test_food_analysis_endpoint.py
git commit -m "feat(cal-ai): support dual JSON and multipart ingestion on food analyze endpoint"
```

---

### Task 2: Gemini Multimodal Vision Service

**Files:**
- Create: `Cal-AI/core/services/vision/gemini_vision_service.py`
- Create: `Cal-AI/tests/test_gemini_vision_service.py`

**Interfaces:**
- Consumes: PIL Image, optional filename or context hint.
- Produces: `dict` with keys `dish_name`, `vietnamese_name`, `confidence`, `portion` (`estimated_grams`, `description`), `visible_ingredients`, `visual_notes`, `is_food`.

- [ ] **Step 1: Write failing test for GeminiVisionService**

Create `Cal-AI/tests/test_gemini_vision_service.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch
from PIL import Image
from core.services.vision.gemini_vision_service import GeminiVisionService

@pytest.mark.asyncio
async def test_gemini_vision_analyze_success():
    service = GeminiVisionService()
    img = Image.new("RGB", (100, 100), color="red")

    mock_resp = AsyncMock()
    mock_resp.choices = [
        AsyncMock(message=AsyncMock(content='''{
            "dish_name": "Phở bò",
            "vietnamese_name": "Phở bò tái nạm",
            "confidence": 0.95,
            "portion": {"estimated_grams": 450, "description": "1 tô vừa"},
            "visible_ingredients": ["bánh phở", "thịt bò", "hành lá"],
            "visual_notes": "Tô phở nóng nhiều hành hoa",
            "is_food": true
        }'''))
    ]

    with patch.object(service._client.chat.completions, "create", return_value=mock_resp):
        result = await service.analyze_food(img)

    assert result["dish_name"] == "Phở bò"
    assert result["portion"]["estimated_grams"] == 450
    assert result["is_food"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest Cal-AI/tests/test_gemini_vision_service.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'core.services.vision.gemini_vision_service'`)

- [ ] **Step 3: Implement `GeminiVisionService` in `Cal-AI/core/services/vision/gemini_vision_service.py`**

- Initialize `AsyncOpenAI` pointing to `settings.LLM_BASE_URL` with `settings.GEMINI_API_KEY`.
- Maintain `RESILIENT_MODELS = ["gemini-3.8-flash", "gemini-3.1-flash-lite-preview", "gemini-flash-latest"]`.
- Method `analyze_food(image: Image.Image, hint: str = "") -> dict`:
  - Convert image to base64 JPEG.
  - Send system prompt enforcing strict JSON output schema.
  - On 429 or 503, loop to the next model in `RESILIENT_MODELS`.
  - Parse JSON response, validate required fields, and return structured dict.
  - If non-food detected, return `{"is_food": False, "confidence": 0.1, "dish_name": "unknown"}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest Cal-AI/tests/test_gemini_vision_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Cal-AI/core/services/vision/gemini_vision_service.py Cal-AI/tests/test_gemini_vision_service.py
git commit -m "feat(cal-ai): implement GeminiVisionService with visual self-attention and resilience"
```

---

### Task 3: Pipeline Integration & Attentive RAG Nutrition Grounding

**Files:**
- Modify: `Cal-AI/core/pipelines/food_analysis_pipeline.py:870-980`
- Create: `Cal-AI/tests/test_food_analysis_pipeline.py`

**Interfaces:**
- Consumes: PIL Image, `GeminiVisionService`, `FoodRAGService`.
- Produces: Complete food analysis output with name, portion, macros, confidence score, and visual evidence.

- [ ] **Step 1: Write failing test for attentive pipeline flow**

Create `Cal-AI/tests/test_food_analysis_pipeline.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch
from PIL import Image
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
        "visible_ingredients": ["bánh phở", "thịt bò"],
        "visual_notes": "Tô phở lớn",
        "is_food": True
    }

    mock_rag_hit = [
        type("Hit", (), {
            "score": 0.92,
            "payload": {
                "dish_name": "Phở bò",
                "calories_per_100g": 90,
                "protein_per_100g": 6.5,
                "carbs_per_100g": 12.0,
                "fat_per_100g": 2.0
            }
        })()
    ]

    with patch.object(pipeline.gemini_vision, "analyze_food", new_callable=AsyncMock, return_value=mock_vision), \
         patch.object(pipeline.rag, "hybrid_search", return_value=mock_rag_hit):
        res = await pipeline.analyze(image=img)

    assert res["name"] == "Phở bò tái nạm"
    # 500g = 5 * 100g -> 5 * 90 = 450 kcal
    assert res["calories"] == 450
    assert res["protein"] == pytest.approx(32.5)
    assert res["confidence"] == 0.95
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest Cal-AI/tests/test_food_analysis_pipeline.py -v`
Expected: FAIL (AttributeError: 'FoodAnalysisPipeline' has no attribute 'gemini_vision')

- [ ] **Step 3: Integrate `GeminiVisionService` into `FoodAnalysisPipeline`**

In `Cal-AI/core/pipelines/food_analysis_pipeline.py`:
- Add lazy property `gemini_vision`:
  ```python
  @property
  def gemini_vision(self):
      if self._gemini_vision is None:
          from core.services.vision.gemini_vision_service import GeminiVisionService
          self._gemini_vision = GeminiVisionService()
      return self._gemini_vision
  ```
- In `async def analyze(self, image, user_id=None, filename=None, question=None)`:
  - Call `vision = await self.gemini_vision.analyze_food(image, hint=question or filename)`
  - If `not vision.get("is_food")`: return structured unrecognized food dict without raising 500.
  - Extract `search_text = vision.get("vietnamese_name") or vision.get("dish_name")`.
  - Query `self.rag.hybrid_search(text=search_text)`.
  - Calculate `grams = vision.get("portion", {}).get("estimated_grams", 350)`.
  - Scale base nutrients: `scale = grams / 100.0`.
  - If no RAG match found, fall back to Gemini's estimated values per portion rather than a hardcoded dummy dish.
  - Return standardized response dictionary.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest Cal-AI/tests/test_food_analysis_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add Cal-AI/core/pipelines/food_analysis_pipeline.py Cal-AI/tests/test_food_analysis_pipeline.py
git commit -m "feat(cal-ai): integrate Gemini vision and attentive nutrition grounding into analysis pipeline"
```

---

### Task 4: Backend Service Realignment & Active Error Reporting

**Files:**
- Modify: `backend/src/modules/user/services/food-analysis.service.ts:80-155`
- Test: Verification via manual execution / script

**Interfaces:**
- Consumes: `FoodAnalysisDto` (`imageUrl`, `source`) from API controller.
- Produces: JSON response with `analysisId`, `name`, `totalKcal`, `protein`, `carbs`, `fats`, `confidence`, `estimatedPortion`.
- Error behavior: Throws `AppError` on any upstream failure (no silent masking).

- [ ] **Step 1: Update `analyzeImage` in `food-analysis.service.ts`**

In `backend/src/modules/user/services/food-analysis.service.ts`:
- Adjust the Cal-AI request:
  ```typescript
  const response = await fetch(`${ENV.CAL_AI_BASE_URL}/api/food/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image: persistentImageUrl || data.imageUrl,
      question: '',
    }),
    signal: AbortSignal.timeout(ENV.CAL_AI_VISION_TIMEOUT_MS || 60000),
  });
  ```
- Replace silent catch fallback:
  ```typescript
  if (!response.ok) {
    const errText = await response.text().catch(() => '');
    throw new AppError(
      `Cal-AI analysis failed (HTTP ${response.status}): ${errText || 'Unknown error'}`,
      response.status >= 500 ? 502 : 400
    );
  }
  ```
- Map returned fields from Cal-AI response into `foods` and `foodrecognitionresults` database tables.

- [ ] **Step 2: Commit**

```bash
git add backend/src/modules/user/services/food-analysis.service.ts
git commit -m "feat(backend): align Cal-AI image scan payload and enforce active error reporting"
```

---

### Task 5: End-to-End Verification & Diagnostics

**Files:**
- Create: `Cal-AI/scripts/test_food_scan_e2e.py`

**Interfaces:**
- Runs an end-to-end synthetic image test through `GeminiVisionService` and the `/api/food/analyze` route.

- [ ] **Step 1: Write E2E script to verify real Gemini Vision call**

Create `Cal-AI/scripts/test_food_scan_e2e.py` to:
- Generate a test food image (or load an existing test image).
- Send to `GeminiVisionService`.
- Assert output has `dish_name`, `confidence > 0.7`, and valid non-zero macro numbers.
- Test error reporting: Send invalid base64 string, assert status 400.

- [ ] **Step 2: Execute E2E verification**

Run: `python Cal-AI/scripts/test_food_scan_e2e.py`
Expected: Output confirms successful dish recognition, accurate macro calculation, and proper error throwing on bad input.

- [ ] **Step 3: Commit and Finalize**

```bash
git add Cal-AI/scripts/test_food_scan_e2e.py
git commit -m "test: add e2e verification script for food scan pipeline"
```
