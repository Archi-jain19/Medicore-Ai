from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    conversation_id: int | None = None
    message: str = Field(min_length=2, max_length=2000)
    strategy: Literal["hybrid", "adaptive", "reranked", "basic"] = "hybrid"

    @field_validator("message")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Message is too short")
        return v


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict[str, Any]] | None = None
    verification: dict[str, Any] | None = None
    retrieval_strategy: str | None = None
    created_at: datetime


class ChatResponse(BaseModel):
    conversation_id: int
    title: str
    user_message: MessageOut
    reply: MessageOut
    status: Literal["ok", "extractive", "limited_evidence", "needs_more_info", "insufficient_evidence", "generation_unavailable", "knowledge_base_missing"]
    emergency_notice: str | None = None
    analysis: dict[str, Any] | None = None
    notes: list[str] = []
    disclaimer: str


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
