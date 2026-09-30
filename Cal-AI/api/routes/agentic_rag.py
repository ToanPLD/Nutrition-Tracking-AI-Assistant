import json
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


router = APIRouter(prefix="/api/agent", tags=["Agentic RAG"])
_agentic_rag = None


class AgenticQueryRequest(BaseModel):
    question: Optional[str] = None
    query: Optional[str] = None
    top_k: int = Field(default=6, ge=1, le=20)
    intent: Optional[str] = None
    session_id: Optional[str] = None
    conversation_context: Optional[str] = None
    history: Optional[List[Dict[str, Any]]] = None
    is_follow_up: Optional[bool] = None
    user_profile: Optional[Dict[str, Any]] = None

    @property
    def final_query(self) -> str:
        return (self.question or self.query or "").strip()


def get_agentic_rag():
    global _agentic_rag
    if _agentic_rag is None:
        from core.agent.agentic_rag import AgenticRAG
        _agentic_rag = AgenticRAG()
    return _agentic_rag


def _resolve_context(req: AgenticQueryRequest) -> Optional[str]:
    if req.conversation_context:
        return req.conversation_context
    if req.history:
        lines = []
        for h in req.history:
            sender = h.get("sender", "user")
            text = h.get("text", "")
            lines.append(f"{sender}: {text}")
        return "\n".join(lines)
    return None


def _enrich_response(result: Any) -> Any:
    if isinstance(result, dict):
        ans = result.get("answer", "")
        if "response" not in result:
            result["response"] = ans
        if "text" not in result:
            result["text"] = ans
    return result


@router.post("/query")
async def query_agentic_rag(req: AgenticQueryRequest):
    q = req.final_query
    if not q:
        raise HTTPException(status_code=422, detail="Missing `question` or `query` field.")

    agent = get_agentic_rag()
    conv_ctx = _resolve_context(req)
    result = await agent.run(
        query=q,
        top_k=req.top_k,
        intent=req.intent,
        session_id=req.session_id,
        conversation_context=conv_ctx,
        is_follow_up=req.is_follow_up,
        user_profile=req.user_profile
    )
    return _enrich_response(result)


@router.get("/query")
async def query_agentic_rag_get(
    q: Optional[str] = None,
    question: Optional[str] = Query(default=None),
    top_k: int = 6,
    intent: Optional[str] = None,
    session_id: Optional[str] = None,
    conversation_context: Optional[str] = None,
    is_follow_up: Optional[bool] = None
):
    final_query = (q or question or "").strip()
    if not final_query:
        raise HTTPException(status_code=422, detail="Missing query parameter `q` or `question`.")

    agent = get_agentic_rag()
    result = await agent.run(
        query=final_query,
        top_k=top_k,
        intent=intent,
        session_id=session_id,
        conversation_context=conversation_context,
        is_follow_up=is_follow_up
    )
    return _enrich_response(result)


@router.post("/query/stream")
async def query_agentic_rag_stream(req: AgenticQueryRequest):
    q = req.final_query
    if not q:
        raise HTTPException(status_code=422, detail="Missing `question` or `query` field.")

    agent = get_agentic_rag()
    conv_ctx = _resolve_context(req)

    async def event_generator():
        try:
            async for chunk in agent.run_stream(
                query=q,
                top_k=req.top_k,
                intent=req.intent,
                session_id=req.session_id,
                conversation_context=conv_ctx,
                is_follow_up=req.is_follow_up,
                user_profile=req.user_profile
            ):
                payload = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:
            err_payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err_payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/query/stream")
async def query_agentic_rag_stream_get(
    q: Optional[str] = None,
    question: Optional[str] = Query(default=None),
    top_k: int = 6,
    intent: Optional[str] = None,
    session_id: Optional[str] = None,
    conversation_context: Optional[str] = None,
    is_follow_up: Optional[bool] = None
):
    final_query = (q or question or "").strip()
    if not final_query:
        raise HTTPException(status_code=422, detail="Missing query parameter `q` or `question`.")

    agent = get_agentic_rag()

    async def event_generator():
        try:
            async for chunk in agent.run_stream(
                query=final_query,
                top_k=top_k,
                intent=intent,
                session_id=session_id,
                conversation_context=conversation_context,
                is_follow_up=is_follow_up
            ):
                payload = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:
            err_payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err_payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
