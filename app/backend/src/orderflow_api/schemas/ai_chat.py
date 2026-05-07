from typing import Literal, Optional
from pydantic import BaseModel


class AiChatRequest(BaseModel):
    message: str
    context: Optional[Literal["navigation", "legal_term", "case_help"]] = None


class AiChatResponse(BaseModel):
    reply: str
    model: str
