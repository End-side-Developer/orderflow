import json
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from orderflow_api.core.config import settings
from orderflow_api.schemas.ai_chat import AiChatRequest, AiChatResponse
from orderflow_api.api.dependencies.auth import get_current_user
from orderflow_api.schemas.users import UserRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

_CHAT_SYSTEM = (
    "You are the OrderFlow assistant. Help users navigate the case management system, "
    "understand legal terminology, and get case guidance. Be concise and helpful. "
    'Always respond as valid JSON: {"reply": "your answer here"}.'
)


def _extract_reply(raw_text: str) -> str:
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return str(data.get("reply", raw_text))
    except (json.JSONDecodeError, ValueError):
        pass
    return raw_text


@router.post("/chat", response_model=AiChatResponse)
def post_ai_chat(
    request: AiChatRequest,
    user: Annotated[UserRecord, Depends(get_current_user)],
):
    try:
        provider = (settings.orderflow_ai_default_provider or "gemini").lower()
        model = settings.orderflow_ai_default_model or "gemini-2.0-flash"
        prompt = f"{_CHAT_SYSTEM}\n\nUser: {request.message}"

        if provider == "groq":
            from orderflow_api.core.groq_client import call_groq_json, extract_groq_text
            raw = call_groq_json(
                api_key=settings.orderflow_ai_groq_api_key or "",
                model=model,
                prompt=prompt,
                temperature=0.7,
                request_label="ai_chat",
            )
            reply_text = _extract_reply(extract_groq_text(raw))
        else:
            from orderflow_api.core.gemini_client import call_gemini_json, extract_gemini_text
            gemini_model = model if model.startswith("gemini") else "gemini-2.0-flash"
            raw = call_gemini_json(
                prompt=prompt,
                api_key=settings.orderflow_ai_gemini_api_key or "",
                model=gemini_model,
                temperature=0.7,
                max_output_tokens=settings.orderflow_ai_gemini_max_output_tokens,
                request_label="ai_chat",
            )
            reply_text = _extract_reply(extract_gemini_text(raw))

        return AiChatResponse(reply=reply_text, model=model)
    except Exception as e:
        logger.error("Error calling AI provider for AI Chat: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to communicate with AI provider.",
        )
