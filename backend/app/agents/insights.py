from typing import List, Optional
import os
from uuid import UUID
from sqlalchemy.orm import Session

from app.db.models.ticket import Ticket
from app.db.models.resolution import Resolution
from app.utils.embeddings import get_embedding
from app.utils.llm import summarize_root_cause_with_llm
# from app.agents.web_solutions_agent import WebSolutionsAgent
import logging
import json as _json
from app.utils.embeddings import get_embedding
import numpy as np


class InsightsBuddy:
    def __init__(self, db: Session):
        self.db = db
        self._logger = logging.getLogger(__name__)
        def llm_confidence_score(self, new_ticket, similar_ticket, resolution_text, historical_confidence, similarity_score, llm_client):
            """
            Use LLM to determine confidence score and justification for a recommended step.
            """
            prompt = (
                f"You are a technical support AI.\n"
                f"A new support ticket is being analyzed.\n"
                f"New Ticket Title: {new_ticket['title']}\n"
                f"New Ticket Description: {new_ticket['description']}\n\n"
                f"Candidate Step comes from a similar historical ticket:\n"
                f"Similar Ticket Title: {similar_ticket['title']}\n"
                f"Similar Ticket Description: {similar_ticket['description']}\n"
                f"Resolution Text: {resolution_text}\n"
                f"Historical Confidence Score: {historical_confidence}\n"
                f"Similarity Score: {similarity_score}\n\n"
                f"Based on the above, output a JSON object with two fields: confidence_score (0-100, integer, how likely this step will resolve the new ticket) and justification (a short explanation for your score)."
            )
            response = llm_client.complete(
                system_prompt="You are a technical support AI.",
                user_prompt=prompt,
                temperature=0.0,
                max_tokens=256
            )
            try:
                result = _json.loads(response)
                score = int(result.get("confidence_score", 0))
                justification = result.get("justification", "")
            except Exception:
                score = 0
                justification = "LLM response could not be parsed."
            return score, justification


    def analyse_ticket(self, ticket_id: UUID, progress=None) -> dict:
            """Top‑level entrypoint called by the MCP server/UI.

            * loads the ticket
            * ensures an embedding exists
            * finds the most similar past resolutions
            * asks an LLM to produce a root cause / recommendation summary
            """
            ticket = self.db.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
            if not ticket:
                raise ValueError(f"ticket {ticket_id} not found")

            if progress:
                progress("Computing ticket embedding")

            # compute or update the ticket embedding
            if ticket.embedding is None:
                self.index_ticket(ticket)

            ticket_text = f"Title: {ticket.title}\nDescription: {ticket.description}"


            if progress:
                progress("Finding similar tickets")

            # Find all tickets with embeddings, not the current ticket
            all_ticket_rows = (
                self.db.query(Ticket)
                .filter(Ticket.embedding != None)
                .filter(Ticket.ticket_id != ticket.ticket_id)
                .all()
            )

            # Calculate semantic similarity for all tickets (title + description)
            import numpy as np
            all_similar_tickets = []
            for t in all_ticket_rows:
                distance = float(np.linalg.norm(np.array(t.embedding) - np.array(ticket.embedding)))
                similarity_pct = max(0, min(100, int((1 - (distance / 2)) * 100)))
                all_similar_tickets.append({
                    "ticket_id": str(t.ticket_id),
                    "title": t.title,
                    "description": t.description,
                    "created_at": t.created_at,
                    "assigned_to": str(t.assigned_to) if t.assigned_to else None,
                    "similarity": similarity_pct,
                })
            # Count all tickets with similarity >= 70
            count_above_70 = sum(1 for t in all_similar_tickets if t["similarity"] >= 70)
            logging.info(f"--------------------Total similar tickets: {len(all_similar_tickets)}, Count above 70% similarity: {count_above_70}")
            # Store all ticket ids with >=70% similarity
            ids_above_70 = [t["ticket_id"] for t in all_similar_tickets if t["similarity"] >= 70]
            # Also store all ticket objects with >=70% similarity (for created_at)
            tickets_above_70 = [t for t in all_similar_tickets if t["similarity"] >= 70]
            # Sort by similarity descending and take top 5 for display (for outcome)
            similar_tickets = sorted(all_similar_tickets, key=lambda x: x["similarity"], reverse=True)[:5]
            similar_ticket_ids = [x["ticket_id"] for x in similar_tickets]
            total_similar_count = len(all_similar_tickets)

            self._logger.info(f"Total similar tickets (semantic similarity): {total_similar_count}")
            self._logger.info(f"Count of similar tickets >=70%: {count_above_70}")
            for t in similar_tickets:
                self._logger.info(f"SELECTED TicketID={t['ticket_id']}, Title={t['title']}, CreatedAt={t['created_at']}, Similarity={t['similarity']}%")


            if progress:
                progress("Fetching historical resolutions")

            # ENFORCE: If there are no similar tickets above 70% similarity, do NOT generate or store any recommended steps
            from app.utils.llm import LLMClient
            llm_client = LLMClient()
            new_ticket_info = {"title": ticket.title, "description": ticket.description}
            # Only consider similar tickets with similarity >70
            filtered_similar = [t for t in similar_tickets if t["similarity"] > 70]
            self._logger.info(f"[RecommendedSteps] Found {len(filtered_similar)} similar tickets with >70% similarity: {filtered_similar}")
            recommended_steps = []
            if filtered_similar:
                # Gather all valid historical resolutions with resolution_text and confidence_score
                historical_candidates = []
                for t in filtered_similar:
                    res = self.db.query(Resolution).filter(Resolution.ticket_id == t["ticket_id"]).order_by(Resolution.confidence_score.desc()).first()
                    # Only use tickets with a non-empty, non-null resolution_text
                    if res and res.resolution_text and str(res.resolution_text).strip():
                        historical_candidates.append({
                            "ticket_id": t["ticket_id"],
                            "title": t["title"],
                            "description": t["description"],
                            "resolution_text": res.resolution_text,
                            "confidence_score": float(res.confidence_score)
                        })
                self._logger.info(f"[RecommendedSteps] {len(historical_candidates)} historical tickets with valid resolution_text and confidence_score: {historical_candidates}")
                # Log all considered historical candidates and their confidence scores before LLM
                if historical_candidates:
                    sorted_candidates = sorted(historical_candidates, key=lambda x: x["confidence_score"], reverse=True)
                    log_data = [
                        {
                            "ticket_id": c["ticket_id"],
                            "title": c["title"],
                            "confidence_score": c["confidence_score"]
                        }
                        for c in sorted_candidates
                    ]
                    self._logger.info("[RecommendedSteps] Historical candidates considered (sorted by confidence_score):\n%s", _json.dumps(log_data, indent=2))
                # Sort by confidence_score descending, take top 5
                top_candidates = sorted(historical_candidates, key=lambda x: x["confidence_score"], reverse=True)[:5]
                for cand in top_candidates:
                    step_prompt = (
                        f"You are a technical support AI.\n"
                        f"A new support ticket needs actionable steps to resolve it.\n"
                        f"Here is a similar historical ticket's information:\n"
                        f"- Similar Ticket Description: {cand['description']}\n"
                        f"- Similar Ticket Resolution: {cand['resolution_text']}\n"
                        f"- Similar Ticket Resolution Confidence Score: {cand['confidence_score']} (how well it worked for the old ticket)\n"
                        f"Here is the new ticket's information:\n"
                        f"- New Ticket Title: {ticket.title}\n"
                        f"- New Ticket Description: {ticket.description}\n"
                        f"Your task: Using the similar ticket's resolution as a reference, generate a clear, actionable step (not a summary or paraphrase) that could resolve the new ticket.\n"
                        f"Also, provide a confidence_score (0-100, integer) for how likely this step will resolve the new ticket, based on the similarity of the tickets and the confidence score for the old ticket.\n"
                        f"Return a JSON object with fields: title (brief summary of the action step), description (specific action step to resolve the incident), confidence_score (0-100, integer), justification (short reason for your confidence score). If no actionable step can be generated, return null."
                    )
                    self._logger.info(f"[RecommendedSteps] LLM prompt for candidate {cand['ticket_id']}:\n{step_prompt}")
                    step_result = llm_client.complete(
                        system_prompt="You are a technical support AI.",
                        user_prompt=step_prompt,
                        temperature=0.0,
                        max_tokens=256
                    )
                    self._logger.info(f"[RecommendedSteps] LLM response for candidate {cand['ticket_id']}: {step_result}")
                    try:
                        parsed = _json.loads(step_result)
                        # Post-processing: filter out responses that echo or closely paraphrase ticket info
                        if parsed and isinstance(parsed, dict) and parsed.get("description"):
                            desc = parsed["description"].strip().lower()
                            hist_title = cand["title"].strip().lower()
                            hist_desc = cand["description"].strip().lower()
                            new_title = ticket.title.strip().lower()
                            new_desc = ticket.description.strip().lower()
                            # Substring checks for stricter filtering
                            def is_similar(a, b):
                                return a == b or a in b or b in a
                            if (
                                is_similar(desc, hist_title) or is_similar(desc, hist_desc)
                                or is_similar(desc, new_title) or is_similar(desc, new_desc)
                            ):
                                self._logger.warning(f"[RecommendedSteps] LLM response rejected for echoing or paraphrasing ticket info: {desc}")
                                self._logger.warning(f"Compared against: hist_title='{hist_title}', hist_desc='{hist_desc}', new_title='{new_title}', new_desc='{new_desc}'")
                            else:
                                # Move justification to reasoning and remove justification
                                if "justification" in parsed:
                                    parsed["reasoning"] = parsed.pop("justification")
                                # Remove justification if still present
                                parsed.pop("justification", None)
                                recommended_steps.append(parsed)
                    except Exception as e:
                        self._logger.warning(f"[RecommendedSteps] LLM parse error: {e} | result: {step_result}")
            else:
                self._logger.info(f"[RecommendedSteps] No similar tickets above 70% similarity for ticket {ticket_id}; recommendedsteps will remain empty.")
            self._logger.info(f"[RecommendedSteps] Final recommended_steps for ticket {ticket_id}:\n%s", _json.dumps(recommended_steps, indent=2))
                # Deduplicate recommended steps by semantic similarity (>75%) and keep the one with higher confidence_score
                
            filtered_steps = []
            used = set()
            embeddings = []
            for step in recommended_steps:
                desc = (step.get("description") or "").strip()
                if desc:
                    embeddings.append(get_embedding(desc))
                else:
                    embeddings.append(None)
            for i, step_i in enumerate(recommended_steps):
                if i in used or not embeddings[i]:
                    continue
                keep = True
                for j, step_j in enumerate(recommended_steps):
                    if i == j or j in used or not embeddings[j]:
                        continue
                    # Compute cosine similarity
                    sim = np.dot(embeddings[i], embeddings[j]) / (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j]))
                    if sim > 0.75:
                        # If duplicate, keep the one with higher confidence_score
                        score_i = float(step_i.get("confidence_score", 0))
                        score_j = float(step_j.get("confidence_score", 0))
                        if score_j > score_i:
                            keep = False
                            break
                        else:
                            used.add(j)
                if keep:
                    filtered_steps.append(step_i)
                    used.add(i)
            self._logger.info(f"[RecommendedSteps] Deduplicated by similarity for ticket {ticket_id}:\n%s", _json.dumps(filtered_steps, indent=2))
            res_obj = self.db.query(Resolution).filter(Resolution.ticket_id == ticket_id).order_by(Resolution.created_at.desc()).first()
            if res_obj:
                # If there are no valid recommended steps, recommendedsteps must be empty
                if filtered_steps:
                    self._logger.info(f"[RecommendedSteps] Adding recommended steps to recommendedsteps for ticket {ticket_id}")
                    res_obj.recommendedsteps = filtered_steps
                    # Store the reasoning for the first recommended step in the reasoning column for hover in frontend
                    res_obj.reasoning = filtered_steps[0].get("reasoning") if filtered_steps[0].get("reasoning") else None
                else:
                    self._logger.info(f"[RecommendedSteps] No valid recommended steps for ticket {ticket_id}, recommendedsteps will be empty.")
                    res_obj.recommendedsteps = []
                    res_obj.reasoning = None
                # Always store count of similar tickets >=70% similarity
                res_obj.total_similar_tickets_above70 = count_above_70
                self.db.commit()
                self.db.refresh(res_obj)
                self._logger.info(f"[RecommendedSteps] Steps and count_above_70 added to recommendedsteps for ticket {ticket_id} and found {count_above_70} similar tickets >=70% similarity")
                self._logger.info(f"[RecommendedSteps] Outcome field for ticket {ticket_id}: {getattr(res_obj, 'outcome', None)}")
            # Define similar_resolutions for top similar tickets
            similar_resolutions = []
            if similar_ticket_ids:
                # Attach similarity score to each resolution
                ticket_similarity_map = {t["ticket_id"]: t["similarity"] for t in similar_tickets}
                similar_resolutions = []
                db_resolutions = (
                    self.db.query(Resolution)
                    .filter(Resolution.ticket_id.in_(similar_ticket_ids))
                    .order_by(Resolution.confidence_score.desc())
                    .limit(10)
                    .all()
                )
                for r in db_resolutions:
                    similarity = ticket_similarity_map.get(str(r.ticket_id), None)
                    r_dict = dict(r.__dict__)
                    r_dict["similarity"] = similarity
                    # Use the outcome field from the Resolution table
                    # If outcome is None, fallback to similar_tickets
                    if r_dict.get("outcome") is None:
                        # Add total_similarity_count, count_above_70, ids_above_70, and all ticket objects with created_at
                        r_dict["outcome"] = [{
                            "total_similarity_count": total_similar_count,
                            "count_above_70": count_above_70,
                            "ids_above_70": ids_above_70,
                            "tickets_above_70": tickets_above_70
                        }] + similar_tickets
                    similar_resolutions.append(r_dict)

            historical_snippets: List[str] = []
            if similar_resolutions:
                tickets_by_id = {t["ticket_id"]: t for t in similar_tickets}
                for r in similar_resolutions:
                    ticket_id = r.get("ticket_id") if isinstance(r, dict) else getattr(r, "ticket_id", None)
                    t = tickets_by_id.get(str(ticket_id))
                    resolution_text = r.get("resolution_text") if isinstance(r, dict) else getattr(r, "resolution_text", "")
                    if t:
                        snippet = (
                            f"Ticket: {t['title']}\n"
                            f"Created At: {t['created_at']}\n"
                            f"Resolution: {resolution_text}"
                        )
                    else:
                        snippet = f"Resolution: {resolution_text}"
                    historical_snippets.append(snippet)

            # record audit event (optional)
            # ... code here to log to ai_audit_log table if desired ...

            if progress:
                progress("Searching the web for similar discussions")

            # web_solutions = self.find_web_solutions(ticket.title, ticket.description)

            if progress:
                progress("Summarizing what worked and what did not")

            root_cause, recommendation = summarize_root_cause_with_llm(
                ticket_text, historical_snippets
            )
            return {
                "ticket_id": str(ticket.ticket_id),
                "ticket": ticket,
                "similar_resolutions": similar_resolutions,
                "similar_tickets": similar_tickets,
                "root_cause": root_cause,
                "recommendation": recommendation,
                "recommended_steps": filtered_steps,
                # "web_solutions": web_solutions,
            }

    def find_web_solutions(
            self,
            title: str,
            description: str,
        ) -> List[dict]:
            """
            Find web-based solutions by searching across public websites.
            # Delegates to WebSolutionsAgent for comprehensive web search.
            """
            try:
                from app.config import WEB_SEARCH_MAX_RESULTS
                # solutions = self._web_solutions_agent.find_solutions(
                #     title,
                #     description,
                #     max_results=WEB_SEARCH_MAX_RESULTS
                # )
                # self._logger.info(f"Found {len(solutions)} web solutions")
                # return solutions
            except Exception as e:
                self._logger.error(f"Error finding web solutions: {e}", exc_info=True)
                return []
