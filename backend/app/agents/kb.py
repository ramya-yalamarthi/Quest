"""KB Recommendations: map a ticket to internal KB articles / troubleshooting
guides by similarity, ranked by REAL outcomes (success rate + avg resolution
time), and record per-article engineer feedback (thumbs up/down).

The KB catalog (title/url/summary/category) is ops-maintained via kb_articles;
times_recommended/times_resolved/total_resolution_hours are updated by the app
as tickets get resolved, so the ranking reflects what has actually worked.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.db.models.kb_article import KBArticle
from app.db.models.ticket_kb_mapping import TicketKBMapping
from app.db.models.kb_feedback import KBFeedback
from app.orchestrator.workflows import find_workflow
from app.utils.embeddings import get_embedding


def match_kb_articles(
    db: Session, title: str, description: str, top_k: int = 3, exclude_kb_ids: set | None = None,
) -> list[dict]:
    """Embed the ticket text, find the top_k KB articles by cosine similarity,
    and rank ties by success rate (desc) then avg resolution time (asc) --
    a strong but unproven match should not outrank a weaker match with a
    proven track record.

    exclude_kb_ids: articles to skip (e.g. ones already shown and disliked) --
    the basis for "next-best recommendation after negative feedback"."""
    exclude = {str(x) for x in (exclude_kb_ids or set())}
    articles = [a for a in db.query(KBArticle).filter(KBArticle.embedding != None).all()
                if str(a.kb_id) not in exclude]
    if not articles:
        return []

    query_vec = np.array(get_embedding(f"Title: {title}\nDescription: {description}"))
    scored = []
    for a in articles:
        vec = np.array(a.embedding)
        denom = (np.linalg.norm(query_vec) * np.linalg.norm(vec))
        similarity = float(np.dot(query_vec, vec) / denom) if denom else 0.0
        scored.append((a, similarity))

    scored.sort(key=lambda t: (-t[1],))
    top = scored[: max(top_k * 3, top_k)]  # widen the pool before re-ranking by outcome
    top.sort(key=lambda t: (-t[0].success_rate, t[0].avg_resolution_hours or float("inf"), -t[1]))
    top = top[:top_k]

    out = []
    for a, sim in top:
        # Match on category ONLY (not title/summary) -- those often mention
        # adjacent terms in passing (e.g. a DNS article referencing
        # "NodePool"), which caused false "Workflow available" tags.
        workflow = find_workflow(a.category)
        out.append({
            "kb_id": str(a.kb_id), "title": a.title, "url": a.url, "summary": a.summary,
            "category": a.category, "similarity": round(sim, 4),
            "success_rate": round(a.success_rate, 4), "avg_resolution_hours": a.avg_resolution_hours,
            "times_recommended": a.times_recommended, "times_resolved": a.times_resolved,
            "workflow_available": workflow is not None,
            "workflow_steps": (workflow or {}).get("steps", []),
        })
    return out


def record_kb_mapping(db: Session, ticket_id, kb_id, similarity: float) -> None:
    db.add(TicketKBMapping(ticket_id=ticket_id, kb_id=kb_id, similarity=similarity))
    article = db.query(KBArticle).filter(KBArticle.kb_id == kb_id).first()
    if article:
        article.times_recommended += 1
    db.commit()


def record_kb_outcome(db: Session, kb_id, resolved: bool, resolution_hours: float | None = None) -> None:
    """Call when a ticket that used this KB article is resolved -- feeds the
    success-rate / avg-resolution-time ranking back into match_kb_articles()."""
    article = db.query(KBArticle).filter(KBArticle.kb_id == kb_id).first()
    if not article:
        return
    if resolved:
        article.times_resolved += 1
        if resolution_hours is not None:
            article.total_resolution_hours = float(article.total_resolution_hours or 0) + resolution_hours
    db.commit()


def submit_kb_feedback(db: Session, ticket_id, kb_id, verdict: str, comment: str = "", created_by=None) -> None:
    db.add(KBFeedback(ticket_id=ticket_id, kb_id=kb_id, verdict=verdict,
                       comment=comment or None, created_by=created_by))
    db.commit()


def find_or_create_kb_article_by_url(db: Session, url: str, title: str = "", category: str = "") -> KBArticle:
    """For reference links found dynamically (web search results, e.g. the
    D365 pipeline's Microsoft Learn refs) rather than the ops-curated catalog
    matched by embedding. Matched by URL since there's no ticket text to
    embed against -- the same URL recommended for different tickets is the
    SAME article, so its stats accumulate across tickets."""
    article = db.query(KBArticle).filter(KBArticle.url == url).first()
    if article:
        return article
    article = KBArticle(title=title or url, url=url, category=category or None)
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def record_ref_link_recommendation(db: Session, ticket_id, url: str, title: str = "") -> dict:
    """Find-or-create the KB article for this URL, record that it was shown
    on this ticket, and return its current success-rate stats for display."""
    article = find_or_create_kb_article_by_url(db, url, title)
    record_kb_mapping(db, ticket_id, article.kb_id, similarity=None)
    db.refresh(article)
    return {
        "kb_id": str(article.kb_id), "url": article.url, "title": article.title,
        "success_rate": round(article.success_rate, 4),
        "times_recommended": article.times_recommended, "times_resolved": article.times_resolved,
    }
