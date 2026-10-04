# Design Spec: Refactor Food Scan Workflow with Gemini Vision Attention & Attentive RAG Grounding

- **Date**: 2026-10-04
- **Topic**: Refactor Food Image Scan Pipeline & Attentive RAG Nutrition Grounding
- **Status**: Approved / Ready for Implementation Planning

---

## 1. Context & Motivation

In the current Nutrition Tracking AI Assistant, scanning a food image produces consistently inaccurate results and frequently defaults to a generic mock record (`Salad with Grilled Chicken, 450 kcal`). Investigation revealed three root causes:

1. **Protocol Mismatch & Abrupt Timeout in Backend**:
   - [`backend/src/modules/user/services/food-analysis.service.ts`](file:///d:/Sources/Code/Nutrition-Tracking-AI-Assistant/backend/src/modules/user/services/food-analysis.service.ts) sent a JSON payload `{ image: data.imageUrl }` with an aggressive 5,000ms (`AbortSignal.timeout(5000)`) limit.
   - Meanwhile, [`Cal-AI/api/routes/food_analysis.py`](file:///d:/Sources/Code/Nutrition-Tracking-AI-Assistant/Cal-AI/api/routes/food_analysis.py) strictly required `multipart/form-data` (`file: UploadFile = File(...)`).
   - Every scan request resulted in a 422 Unprocessable Entity or timeout, silently dropping into the catch block and returning the hardcoded Salad fallback.

2. **Severely Limited Local Vision Pipeline**:
   - `Cal-AI` relied on `ViTCNNFoodClassifier` with a hardcoded static dictionary of ~10 Vietnamese dishes (`CANDIDATES`).
   - The multimodal fallback called Ollama `llava:7b` at `http://localhost:11434`, which is offline on the target system.

3. **Flat Vector Search Lacking Attention**:
   - Qdrant queries relied on single pooled 768-dim/512-dim cosine vectors without attention to specific visual components (broth style, toppings, noodle types, side dishes).

4. **User Requirement for Error Transparency**:
   - Silent failures and placeholder masking must be eliminated. Any error occurring across API communication, image decoding, model inference, or database retrieval must be explicitly surfaced with clear diagnostics.

---

## 2. Goals & Non-Goals

### Goals
- **End-to-End Multimodal Vision**: Leverage Google Gemini Multimodal Vision API (`gemini-3.8-flash` via `AsyncOpenAI`) to extract fine-grained visual attention features (dish name, ingredients, portion size, visual nuances) across all Vietnamese and international dishes.
- **Unified Dual-Ingestion Endpoint**: Support both `application/json` (Base64 string or image URL) and `multipart/form-data` in `Cal-AI/api/routes/food_analysis.py`.
- **Backend Realignment**: Increase backend timeout from 5s to 60s, synchronize payload structure, and remove the hardcoded fallback mock.
- **Attentive RAG Grounding**: Use structured tokens extracted by Gemini Vision Attention to query Qdrant (`vn_food_vectors_768`, `food_nutrition_vectors_768`) and calculate realistic macronutrients based on estimated portion weights.
- **Active Error Reporting**: Provide granular, transparent error codes (`INVALID_IMAGE`, `AI_SERVICE_UNAVAILABLE`, `UNRECOGNIZED_FOOD`, `PIPELINE_ERROR`) without silent swallowing.

### Non-Goals
- Modifying text-based multi-turn chat orchestration in `backend/src/modules/chat/chat.service.ts`.
- Retraining local CLIP-LoRA or YOLO models; these are bypassed in favor of Gemini Multimodal Vision for user scan requests.
- Modifying Cloudflare R2 image persistence logic.

---

## 3. Architecture & Data Flow

```
[Client / Mobile App]
       │
       │ 1. POST /api/user/food-analysis (Image Base64 or URL)
       ▼
[Node.js Backend (food-analysis.service.ts)]
       │ • Timeout: 60,000ms
       │ • Payload: JSON { image: persistentImageUrl, question: "" }
       ▼
[Cal-AI FastAPI (/api/food/analyze)]
       │ • Dual Ingestion (JSON / Form Data)
       │ • Base64 / URL validation & Pillow preprocessing (512x512)
       ▼
[GeminiVisionService (Cal-AI)]
       │ • Uses model tier: gemini-3.8-flash -> gemini-3.1-flash-lite-preview -> gemini-flash-latest
       │ • Prompt with structured JSON schema
       │ • Extracts: dish_name, vietnamese_name, ingredients, portion grams, confidence
       ▼
[FoodRAGService & Qdrant Grounding]
       │ • Attentive lookup in vn_food_vectors_768 & food_nutrition_vectors_768
       │ • Retrieve exact base macro ratios per 100g
       │ • Scale total calories, protein, carbs, fat to estimated grams
       ▼
[Response Formatter]
       │ • Formats clean response payload
       ▼
[Node.js Backend]
       │ • Persists food entry and recognition result in MySQL
       ▼
[Client Response]
```

---

## 4. Component Specifications

### 4.1. Cal-AI API Route (`Cal-AI/api/routes/food_analysis.py`)
- Define Pydantic request model:
  ```python
  class FoodAnalysisJSONRequest(BaseModel):
      image: str
      question: Optional[str] = ""
  ```
- Endpoint logic:
  - If `application/json`: Parse `image` (handle Base64 data URL or HTTP URL via `httpx`).
  - If `multipart/form-data`: Read uploaded file bytes.
  - Convert to RGB PIL Image with maximum dimension 512x512.
  - Return JSON with HTTP 200 on success, or HTTP 400/502/503 on error.

### 4.2. Gemini Vision Analyzer (`Cal-AI/core/services/vision/gemini_vision_service.py`)
- Extends the existing `LLMService` client (`https://generativelanguage.googleapis.com/v1beta/openai/`).
- Sends multimodal chat completion with `image_url` containing base64 data.
- Enforces response format:
  ```json
  {
    "dish_name": "string",
    "vietnamese_name": "string",
    "confidence": 0.95,
    "portion": {
      "estimated_grams": 450,
      "description": "string"
    },
    "visible_ingredients": ["string"],
    "visual_notes": "string",
    "is_food": true
  }
  ```
- Resilience: If primary model returns 429/503, automatically retries candidate models in `RESILIENT_MODELS`.

### 4.3. Attentive RAG Grounding (`Cal-AI/core/services/rag/food_rag_service.py`)
- Query Qdrant with:
  1. Primary text vector of `vietnamese_name` or `dish_name`.
  2. Filter / search against `vn_food_vectors_768` and `food_nutrition_vectors_768`.
- If matched record found:
  - Compute scaling factor: `scale = estimated_grams / 100.0`.
  - Calculate `calories`, `protein`, `carbs`, `fat`.
- If vector DB has no direct match:
  - Fall back to Gemini's estimated nutritional values for the recognized dish and log grounding miss.

### 4.4. Backend Service Update (`backend/src/modules/user/services/food-analysis.service.ts`)
- Modify `analyzeImage`:
  - Request body: `JSON.stringify({ image: persistentImageUrl || data.imageUrl })`.
  - Headers: `{ 'Content-Type': 'application/json' }`.
  - Timeout: `signal: AbortSignal.timeout(ENV.CAL_AI_VISION_TIMEOUT_MS || 60000)`.
  - Remove silent catch fallback:
    ```typescript
    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new AppError(errBody.detail || 'Cal-AI analysis failed', response.status >= 500 ? 502 : 400);
    }
    ```

---

## 5. Error Handling & Transparency Matrix

| Failure Point | HTTP Code | Error Code / Message | Action / Reporting Behavior |
| :--- | :--- | :--- | :--- |
| **Corrupted Image / Invalid format** | 400 | `INVALID_IMAGE` | Prompt user to upload a valid JPG/PNG/WebP image. |
| **Non-food Image (`is_food: false` / `confidence < 0.35`)** | 200 / 422 | `UNRECOGNIZED_FOOD` | Return recognition payload with low confidence flag so UI guides the user to retake the photo. |
| **Gemini Rate Limit (429) / Outage (503)** | 503 | `AI_SERVICE_UNAVAILABLE` | Auto-failover to backup Gemini Flash models. If all fail, return 503 with exact error details. |
| **Cal-AI Offline / Timeout (>60s)** | 502 | `CAL_AI_UNAVAILABLE` | Backend throws 502 Bad Gateway to notify frontend that AI server is unavailable. |
| **Qdrant Unreachable** | 200 (Degraded) | `RAG_OFFLINE_FALLBACK` | Cal-AI uses Gemini's intrinsic nutritional knowledge with warning log. |

---

## 6. Verification & Testing Plan

1. **Unit & Contract Testing**:
   - Test Cal-AI `/api/food/analyze` with Base64 JSON payload.
   - Test Cal-AI `/api/food/analyze` with multipart upload.
   - Test invalid image payload handling (assert 400 Bad Request).
2. **Integration Testing**:
   - Send standard Vietnamese dishes (e.g. Phở bò, Cơm tấm sườn bì chả, Bún chả).
   - Verify Gemini Vision correctly extracts Vietnamese dish name and ingredients.
   - Verify Qdrant grounding returns accurate macros scaled by portion size.
   - Test backend `analyzeImage` against Cal-AI with 60s timeout.
3. **Failure Mode Testing**:
   - Simulate Cal-AI offline: verify backend throws error rather than returning "Salad with Grilled Chicken".
