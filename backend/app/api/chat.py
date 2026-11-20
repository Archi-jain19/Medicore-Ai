import json

from fastapi import APIRouter, Request, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.rate_limit import limiter
from app.models import ChatMessage, Conversation
from app.models.entities import utcnow
from app.rag import generator, pipeline
from app.rag.config import DEFAULT_RANKING
from app.rag.retriever import get_retriever
from app.schemas.chat import ChatRequest, ChatResponse, ConversationDetail, ConversationOut, MessageOut
from app.services.activity import log_activity

router = APIRouter(tags=["assistant"])


def _owned(db, user, conv_id: int) -> Conversation:
    conv = db.scalar(select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user.id))
    if conv is None:
        raise NotFoundError("We could not find that conversation.")
    return conv


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat(request: Request, body: ChatRequest, db: DbSession, user: CurrentUser):
    """Evidence-grounded answer. The model only sees retrieved passages; no fabricated fallback answers."""
    conv = _owned(db, user, body.conversation_id) if body.conversation_id else None

    result = pipeline.answer_question(body.message, get_retriever(), generator.get_llm(), body.strategy)

    if conv is None:
        title = body.message[:60] + ("…" if len(body.message) > 60 else "")
        conv = Conversation(user_id=user.id, title=title)
        db.add(conv)
        db.flush()
    user_msg = ChatMessage(conversation_id=conv.id, role="user", content=body.message)
    answer = result["answer"] or ""
    reply = ChatMessage(conversation_id=conv.id, role="assistant", content=answer, sources=result["sources"],
                        verification=result["verification"], retrieval_strategy=body.strategy)
    db.add_all([user_msg, reply])
    conv.updated_at = utcnow()
    log_activity(db, user.id, "chat.message", "conversation", conv.id, {"status": result["status"]})
    db.commit()
    db.refresh(user_msg)
    db.refresh(reply)
    return ChatResponse(
        conversation_id=conv.id, title=conv.title, user_message=MessageOut.model_validate(user_msg),
        reply=MessageOut.model_validate(reply), status=result["status"], emergency_notice=result["emergency_notice"],
        analysis=result["analysis"], notes=result["notes"], disclaimer=result["disclaimer"],
    )


@router.get("/chat/history", response_model=list[ConversationOut])
def history(db: DbSession, user: CurrentUser):
    rows = db.execute(
        select(Conversation, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [ConversationOut(id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at, message_count=n)
            for c, n in rows]


@router.get("/chat/{conversation_id}", response_model=ConversationDetail)
def conversation(conversation_id: int, db: DbSession, user: CurrentUser):
    conv = _owned(db, user, conversation_id)
    return ConversationDetail(id=conv.id, title=conv.title, created_at=conv.created_at, updated_at=conv.updated_at,
                              message_count=len(conv.messages),
                              messages=[MessageOut.model_validate(m) for m in conv.messages])


@router.delete("/chat/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, db: DbSession, user: CurrentUser):
    conv = _owned(db, user, conversation_id)
    db.delete(conv)
    log_activity(db, user.id, "chat.delete", "conversation", conversation_id)
    db.commit()


# ------------------------------------------------------------------ knowledge-base introspection
@router.get("/rag/status")
def rag_status(user: CurrentUser):
    r = get_retriever()
    s = get_settings()
    return {
        "knowledge_base_built": r is not None,
        "generation_configured": bool(s.gemini_api_key),
        "generation_model": s.gemini_model if s.gemini_api_key else None,
        "embedding_model": s.embedding_model,
        "chunks": r.index.ntotal if r else 0,
        "documents_by_source": r.manifest.get("documents_by_source") if r else {},
        "built_at": r.manifest.get("built_at") if r else None,
        "ranking": DEFAULT_RANKING.as_dict(),
    }


@router.get("/rag/qa-evaluation")
def rag_qa_evaluation(user: CurrentUser):
    """Results of the everyday-question benchmark for the full flow (retrieval, answers, citations, fallbacks).
    Per-question details are left out to keep the response small."""
    path = get_settings().models_dir / "rag" / "qa_evaluation.json"
    if not path.exists():
        raise NotFoundError("These accuracy results are not available yet.")
    report = json.loads(path.read_text(encoding="utf-8"))
    report.pop("questions", None)
    return report


@router.get("/rag/evaluation")
def rag_evaluation(user: CurrentUser):
    path = get_settings().models_dir / "rag" / "evaluation.json"
    if not path.exists():
        raise NotFoundError("These accuracy results are not available yet.")
    return json.loads(path.read_text(encoding="utf-8"))
