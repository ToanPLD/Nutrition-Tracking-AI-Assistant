# api/routes/food_analysis.py

import base64
import io
import re
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
import httpx
from PIL import Image
from pydantic import BaseModel

from core.pipelines.food_analysis_pipeline import FoodAnalysisPipeline

router = APIRouter(prefix="/api/food", tags=["Food Analysis"])

_pipeline = None


def get_food_analysis_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = FoodAnalysisPipeline()
    return _pipeline


class FoodAnalysisJSONRequest(BaseModel):
    image: Optional[str] = None
    question: Optional[str] = ""


def _load_image_from_bytes(image_bytes: bytes) -> Image.Image:
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img.thumbnail((512, 512))
        return img
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")


async def _load_image_from_source(source: str) -> Image.Image:
    if not source or not isinstance(source, str):
        raise HTTPException(status_code=400, detail="Image payload is required")
    source = source.strip()
    if source.startswith("data:image/") or ";base64," in source:
        base64_data = re.sub(r"^data:image\/[a-zA-Z0-9\+\-\.]+;base64,", "", source)
        try:
            image_bytes = base64.b64decode(base64_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Malformed base64 image data")
        return _load_image_from_bytes(image_bytes)
    elif source.startswith("http://") or source.startswith("https://"):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(source)
                res.raise_for_status()
                return _load_image_from_bytes(res.content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch image from URL: {str(e)}")
    else:
        try:
            image_bytes = base64.b64decode(source)
            return _load_image_from_bytes(image_bytes)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image string (must be URL or Base64)")


@router.post("/analyze")
async def analyze_food_image(
    request: Request,
    file: Optional[UploadFile] = File(None),
    question: Optional[str] = Form(default="")
):
    content_type = request.headers.get("content-type", "").lower()
    image = None
    filename = None
    prompt_question = question or ""

    if "application/json" in content_type:
        try:
            body = await request.json()
            req = FoodAnalysisJSONRequest(**body)
            if not req.image:
                raise HTTPException(status_code=400, detail="Field 'image' is required in JSON payload")
            image = await _load_image_from_source(req.image)
            filename = "upload.jpg"
            prompt_question = req.question or ""
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON request: {str(e)}")
    else:
        if not file:
            form = await request.form()
            if "image" in form and isinstance(form["image"], str):
                image = await _load_image_from_source(form["image"])
                prompt_question = form.get("question", "")
            else:
                raise HTTPException(status_code=400, detail="No file or image uploaded")
        else:
            if not file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                raise HTTPException(status_code=400, detail="Invalid file type")
            filename = file.filename
            image_bytes = await file.read()
            image = _load_image_from_bytes(image_bytes)

    try:
        result = await get_food_analysis_pipeline().analyze(
            image=image,
            filename=filename,
            question=prompt_question
        )
    except Exception as e:
        print("[FoodAnalysis] Pipeline error:", repr(e))
        raise HTTPException(status_code=500, detail=f"Processing failed: {type(e).__name__}")

    return JSONResponse(content=result)
