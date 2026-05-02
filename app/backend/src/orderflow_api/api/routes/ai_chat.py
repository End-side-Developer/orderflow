import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from orderflow_api.schemas.ai_chat import AiChatRequest, AiChatResponse
from orderflow_api.api.dependencies.auth import get_current_user
from orderflow_api.schemas.users import UserRecord
from orderflow_api.core.gemini_client import call_gemini_json, extract_gemini_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

@router.post("/chat", response_model=AiChatResponse)
def post_ai_chat(
    request: AiChatRequest,
    user: Annotated[UserRecord, Depends(get_current_user)],
):
    try:
        
        system_prompt = (
            "You are OrderFlow's help assistant. Answer concisely. "
            "Do not provide legal advice. Constrain responses to navigation, "
            "definitions of OrderFlow terms, and case-help guidance."
        )
        
        # In a real app we'd maintain message history
        # call_gemini_json expects specific args (prompt, temperature, etc)
        # not a raw gemini_payload dict.
        json_resp = call_gemini_json(
            prompt=request.message,
            api_key=settings.orderflow_ai_gemini_api_key or "",
            model=settings.orderflow_ai_default_model,
            temperature=0.7,
            max_output_tokens=settings.orderflow_ai_gemini_max_output_tokens,
            request_label="ai_chat"
        )
        
        reply_text = extract_gemini_text(json_resp)
        
        return AiChatResponse(
            reply=reply_text,
            model="gemini-2.5-pro" # typical model 
        )
    except Exception as e:
        logger.error(f"Error calling Gemini for AI Chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to communicate with AI provider.",
        )
