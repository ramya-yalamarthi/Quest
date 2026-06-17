from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
import json
import queue
import threading
from pydantic import BaseModel
import logging

from app.deps import get_db
from app.auth.deps import get_current_user
from app.auth.jwt import decode_token
from app.mcp.server import MCPServer
from app.schemas.resolution import ResolutionOut
from app.schemas.feedback import FeedbackCreate, FeedbackOut
from app.db.models.recommendation_feedback import RecommendationFeedback
from app.orchestrator.audit import AuditLogger
from app.orchestrator.db_sink import postgres_audit_sink


router = APIRouter(prefix="/mcp", tags=["mcp"])
logger = logging.getLogger(__name__)


def support_only(current):
    """Only SUPPORT or MANAGER role can trigger agent analysis."""
    if current["role"] not in {"SUPPORT", "MANAGER", "SUPPORT_MANAGER"}:
        raise HTTPException(status_code=403, detail="Only SUPPORT or MANAGER role allowed")


class AnalyzeTicketRequest(BaseModel):
    ticket_id: UUID


class SimilarResolution(BaseModel):
    resolution_id: Optional[str]
    ticket_id: Optional[str]
    resolution_text: str
    root_cause: Optional[str] = None
    outcome: Optional[list[dict]] = None
    confidence_score: Optional[float] = None
    similarity: Optional[float] = None


class WebSolution(BaseModel):
    title: str
    url: str
    summary: Optional[str] = None
    steps: list[str]


class AnalyzeTicketResponse(BaseModel):
    ticket_id: UUID
    ticket_summary: str
    error_codes: list[str]
    root_cause: str
    recommendation: str
    similar_count: int
    draft_email_subject: str
    draft_email_body: str
    similar_resolutions: list[SimilarResolution]
    web_solutions: list[WebSolution]


class ApproveEmailRequest(BaseModel):
    email_id: UUID


class UpdateDraftRequest(BaseModel):
    email_id: UUID
    subject: Optional[str] = None
    body: Optional[str] = None


class LogResolutionRequest(BaseModel):
    ticket_id: UUID
    resolution_text: str
    root_cause: Optional[str] = None
    outcome: Optional[list[dict]] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    is_kb: bool = False
    recommendedsteps: Optional[list[dict]] = None


def build_analyze_response(result: dict) -> AnalyzeTicketResponse:
    ticket = result["insights"]["ticket"]
    draft_email = result["draft_email"]
    # Convert ORM objects to dict if needed
    if hasattr(ticket, "__dict__"):
        ticket_data = dict(ticket.__dict__)
    elif isinstance(ticket, dict):
        ticket_data = ticket
    else:
        ticket_data = {}

    if hasattr(draft_email, "__dict__"):
        draft_email_data = dict(draft_email.__dict__)
    elif isinstance(draft_email, dict):
        draft_email_data = draft_email
    else:
        draft_email_data = {}

    similar_resolutions = []
    for r in result["insights"]["similar_resolutions"]:
        if hasattr(r, "__dict__"):
            r_data = dict(r.__dict__)
        elif isinstance(r, dict):
            r_data = r
        else:
            r_data = {}
        resolution_id = r_data.get("resolution_id")
        ticket_id = r_data.get("ticket_id")
        similarity = r_data.get("similarity")
        resolution_id = str(resolution_id) if resolution_id else None
        ticket_id = str(ticket_id) if ticket_id else None
        resolution_text = r_data.get("resolution_text")
        if resolution_text is None:
            resolution_text = ""
        similar_resolutions.append(SimilarResolution(
            resolution_id=resolution_id,
            ticket_id=ticket_id,
            resolution_text=resolution_text,
            root_cause=r_data.get("root_cause"),
            outcome=r_data.get("outcome"),
            confidence_score=r_data.get("confidence_score"),
            similarity=similarity
        ))

    web_solutions = [
        WebSolution(
            title=item["title"],
            url=item["url"],
            summary=item.get("summary"),
            steps=item.get("steps", []),
        )
        for item in result["insights"].get("web_solutions", [])
    ]

    from fastapi import HTTPException
    ticket_id = ticket_data.get("ticket_id")
    if not ticket_id:
        raise HTTPException(status_code=500, detail="ticket_id missing in response")
    return AnalyzeTicketResponse(
        ticket_id=ticket_id,
        ticket_summary=result["insights"].get("ticket_summary", ""),
        error_codes=result["insights"].get("error_codes", []),
        root_cause=result["insights"]["root_cause"],
        recommendation=result["insights"]["recommendation"],
        similar_count=len(similar_resolutions),
        draft_email_subject=draft_email_data.get("subject", "") if draft_email_data else "",
        draft_email_body=draft_email_data.get("body", "") if draft_email_data else "",
        similar_resolutions=similar_resolutions,
        web_solutions=web_solutions,
    )


@router.post("/analyze", response_model=AnalyzeTicketResponse)
def analyze_ticket(
    payload: AnalyzeTicketRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Run InsightsBuddy agent on a ticket: compute embeddings, find similar
    resolutions, call LLM for summary, and create a draft email."""
    support_only(current)
    
    server = MCPServer(db)
    engineer_id = UUID(current["user_id"])
    engineer_name = current.get("display_name")
    
    try:
        result = server.handle_new_ticket(
            payload.ticket_id,
            engineer_id=engineer_id,
            engineer_name=engineer_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return build_analyze_response(result)


@router.get("/analyze/stream")
def analyze_ticket_stream(
    ticket_id: UUID,
    token: str,
    db: Session = Depends(get_db),
):
    try:
        current = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    support_only(current)

    engineer_id = UUID(current["user_id"])
    engineer_name = current.get("display_name")
    q: queue.Queue[tuple[str, object]] = queue.Queue()

    def progress(step: str) -> None:
        q.put(("step", step))

    def run() -> None:
        from app.db.session import SessionLocal
        thread_db = SessionLocal()
        try:
            server = MCPServer(thread_db)
            result = server.handle_new_ticket(
                ticket_id,
                engineer_id=engineer_id,
                engineer_name=engineer_name,
                progress=progress,
            )
            q.put(("done", result))
        except Exception as e:
            logger.exception("Analyze ticket failed", extra={"ticket_id": str(ticket_id)})
            q.put(("error", "Analysis failed"))
        finally:
            thread_db.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def event_stream():
        while True:
            kind, payload = q.get()
            if kind == "step":
                yield f"event: step\ndata: {payload}\n\n"
            elif kind == "done":
                response = build_analyze_response(payload)
                data = response.model_dump(mode="json")
                yield f"event: done\ndata: {json.dumps(data)}\n\n"
                break
            elif kind == "error":
                yield f"event: error\ndata: {payload}\n\n"
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/approve-email")
def approve_email(
    payload: ApproveEmailRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Approve a draft email, send it, and return the updated record."""
    support_only(current)
    
    server = MCPServer(db)
    
    try:
        email = server.approve_and_send(payload.email_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    return {
        "email_id": email.email_id,
        "type": email.type,
        "subject": email.subject,
        "message": "Email approved and sent",
    }


@router.post("/update-draft")
def update_draft(
    payload: UpdateDraftRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Update a draft email before approval."""
    support_only(current)

    server = MCPServer(db)

    try:
        email = server.update_draft_email(
            email_id=payload.email_id,
            subject=payload.subject,
            body=payload.body,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "email_id": email.email_id,
        "type": email.type,
        "subject": email.subject,
        "body": email.body,
    }


class ImproveEmailRequest(BaseModel):
    subject: str
    body: str


class ImproveEmailResponse(BaseModel):
    subject: str
    body: str


@router.post("/improve-email", response_model=ImproveEmailResponse)
def improve_email(
    payload: ImproveEmailRequest,
    current=Depends(get_current_user),
):
    """Improve a user-written email draft with AI assistance."""
    logger.info(f"Improving email - Subject: {payload.subject[:50]}, Body length: {len(payload.body)}")
    support_only(current)
    
    from app.utils.llm import improve_email_draft
    
    try:
        improved_subject, improved_body = improve_email_draft(
            subject=payload.subject,
            body=payload.body
        )
        logger.info(f"Email improved successfully - New subject: {improved_subject[:50]}")
        
        return {
            "subject": improved_subject,
            "body": improved_body,
        }
    except Exception as e:
        logger.error(f"Error improving email: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to improve email: {str(e)}")


@router.post("/log-resolution", response_model=ResolutionOut)
def log_resolution(
    payload: LogResolutionRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Record the final resolution for a ticket after the engineer reviews."""
    support_only(current)
    
    server = MCPServer(db)
    engineer_id = UUID(current["user_id"])
    
    resolution = server.log_final_resolution(
        ticket_id=payload.ticket_id,
        resolution_text=payload.resolution_text,
        root_cause=payload.root_cause,
        outcome=payload.outcome,
        confidence=payload.confidence,
        reasoning=payload.reasoning,
        engineer_id=engineer_id,
        is_kb=payload.is_kb,
        recommendedsteps=payload.recommendedsteps,
    )

    return resolution


@router.post("/feedback", response_model=FeedbackOut)
def submit_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """Record an engineer like/dislike on a recommendation advisory.

    Audits the vote (was_used=True for a 'like') alongside the agent's own
    audit trail. Invalid verdict is rejected at the schema layer (422).
    """
    support_only(current)

    created_by = None
    try:
        created_by = UUID(current["user_id"])
    except (KeyError, ValueError, TypeError):
        created_by = None

    fb = RecommendationFeedback(
        ticket_id=payload.ticket_id,
        ai_event_id=payload.ai_event_id,
        verdict=payload.verdict,
        comment=payload.comment,
        created_by=created_by,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    AuditLogger(db_sink=postgres_audit_sink).log(
        str(payload.ticket_id),
        "recommendation",
        note=f"engineer feedback: {payload.verdict}",
        was_used=(payload.verdict == "like"),
    )
    return fb


@router.get("/feedback/{ticket_id}", response_model=list[FeedbackOut])
def list_feedback(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    """List all feedback recorded for a ticket's recommendation advisories."""
    support_only(current)
    return (
        db.query(RecommendationFeedback)
        .filter(RecommendationFeedback.ticket_id == ticket_id)
        .order_by(RecommendationFeedback.created_at.desc())
        .all()
    )
