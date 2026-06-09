import json
import os
from typing import Tuple, List, Optional, Dict
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    def __init__(self) -> None:
        self.endpoint = os.getenv("OPENAI_ENDPOINT")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_version = os.getenv("LLM_API_VERSION", "2024-12-01-preview")
        self.deployment = os.getenv("LLM_MODEL")

        if not all([self.endpoint, self.api_key, self.deployment]):
            raise RuntimeError("Missing Azure OpenAI env configuration")

        self.client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=self.api_version,
        )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> str:
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if chat_history:
            messages.extend(chat_history)

        messages.append({"role": "user", "content": user_prompt})

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content.strip()


_client = LLMClient()



def summarize_root_cause_with_llm(
    ticket_text: str, historical_snippets: List[str]
) -> Tuple[str, str]:
    """Return (root_cause, recommendation) using configured OpenAI model."""
    if not historical_snippets:
        return None, None
    history_block = "\n\n".join(historical_snippets)
    prompt = (
        "You are a technical support assistant. "
        "You are given a support ticket and a list of historical tickets with their final "
        "resolutions. Use ONLY the historical matches. Do not add new ideas, causes, or steps. "
        "Do not use general knowledge.\n\n"
        "From the historical resolutions, extract:\n"
        "1) Root cause (if explicitly stated in resolutions).\n"
        "2) Recommended steps (rewrite as present-tense, imperative actions; do not use past tense).\n"
        "3) What did not work (failed or ineffective attempts), if present.\n\n"
        "Return EXACTLY three sections in this format:\n"
        "Root cause: ...\n"
        "Recommended steps:\n- step 1\n- step 2\n"
        "What did not work: ...\n\n"
        "If a ticket has no evidence, write 'Not enough data.'.\n\n"
        "TICKET (context only, do not infer from it):\n"
        + ticket_text
        + "\n\nHISTORICAL MATCHES:\n"
        + history_block
    )
    text = _client.complete(
        system_prompt="",
        user_prompt=prompt,
        temperature=0.2,
        max_tokens=512,
    )
    lines = [line.rstrip() for line in text.splitlines()]

    sections = {
        "root cause": [],
        "recommended steps": [],
        "what did not work": [],
    }
    current = None
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                sections[current].append("")
            continue
        lower = stripped.lower()
        if lower.startswith("root cause:"):
            current = "root cause"
            sections[current].append(stripped.split(":", 1)[1].strip())
            continue
        if lower.startswith("recommended steps:"):
            current = "recommended steps"
            tail = stripped.split(":", 1)[1].strip()
            if tail:
                sections[current].append(tail)
            continue
        if lower.startswith("what did not work:"):
            current = "what did not work"
            sections[current].append(stripped.split(":", 1)[1].strip())
            continue
        if current:
            sections[current].append(stripped)

    def finalize_section(key: str) -> Optional[str]:
        value = "\n".join([v for v in sections[key] if v is not None]).strip()
        return value or None

    root_cause = finalize_section("root cause")
    recommended = finalize_section("recommended steps")
    not_worked = finalize_section("what did not work")

    recommendation = recommended
    if not_worked:
        if recommendation:
            recommendation = recommendation + f"\nWhat did not work: {not_worked}"
        else:
            recommendation = f"What did not work: {not_worked}"

    return root_cause, recommendation


def draft_email_from_summary(summary: str, sender_name: str = "Support Team") -> str:
    prompt = (
        "Write a professional support email that is ready to send to the customer. "
        "Start with a greeting and a short intro acknowledging the issue. "
        "Then say 'Please take the following action steps:' and list the steps in bullets. "
        "Use present-tense, imperative language (do not use past tense). "
        "Add the closing sentence based on the situation. example: 'If you continue to experience issues or need further assistance, please let us know. We are here to help.' "
        "End with a thank you and a professional signature using this name: "
        + sender_name
        + " and the line 'Azure Support Team'. "
        "Use ONLY the recommended steps. If the input contains a 'What did not work' section, ignore it. "
        "Do not add any other information or commentary.\n\n"
        "Return only the email body text (no subject line, no extra commentary).\n\n"
        + summary
    )
    return _client.complete(
        system_prompt="",
        user_prompt=prompt,
        temperature=0.3,
        max_tokens=512,
    )


def summarize_web_solution_steps(
    ticket_text: str,
    page_text: str,
    max_steps: int = 6,
) -> List[str]:
    if not page_text.strip():
        return []
    trimmed = page_text.strip()
    if len(trimmed) > 4000:
        trimmed = trimmed[:4000]
    prompt = (
        "You are a technical support assistant. "
        "You are given a support ticket and text scraped from a Microsoft help page. "
        "Use ONLY the page text. Do not add any new steps. "
        "If the page does not describe clear steps that resolve the ticket, reply with: Not enough data.\n\n"
        "Return step-by-step actions in this exact format:\n"
        "Steps:\n- step 1\n- step 2\n\n"
        "Keep steps short and actionable. Max "
        + str(max_steps)
        + " steps.\n\n"
        "TICKET:\n"
        + ticket_text
        + "\n\nPAGE TEXT:\n"
        + trimmed
    )
    text = _client.complete(
        system_prompt="",
        user_prompt=prompt,
        temperature=0.2,
        max_tokens=384,
    )

    steps: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("steps:"):
            continue
        if stripped.startswith("-"):
            step = stripped.lstrip("- ").strip()
            if step:
                steps.append(step)
            continue
        if stripped.lower().startswith("not enough data"):
            return []

    return steps[:max_steps]


def summarize_steps_from_snippet(
    ticket_text: str,
    snippet: str,
    max_steps: int = 3,
) -> List[str]:
    if not snippet.strip():
        return []
    prompt = (
        "You are a technical support assistant. "
        "You are given a support ticket and a short search snippet from a web result. "
        "Use ONLY the snippet. Do not add any new steps. "
        "If the snippet does not describe clear steps, reply with: Not enough data.\n\n"
        "Return step-by-step actions in this exact format:\n"
        "Steps:\n- step 1\n- step 2\n\n"
        "Keep steps short and actionable. Max "
        + str(max_steps)
        + " steps.\n\n"
        "TICKET:\n"
        + ticket_text
        + "\n\nSNIPPET:\n"
        + snippet
    )
    text = _client.complete(
        system_prompt="",
        user_prompt=prompt,
        temperature=0.2,
        max_tokens=256,
    )

    steps: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("steps:"):
            continue
        if stripped.startswith("-"):
            step = stripped.lstrip("- ").strip()
            if step:
                steps.append(step)
            continue
        if stripped.lower().startswith("not enough data"):
            return []

    return steps[:max_steps]


def generate_incident_brief(
    title: str,
    description: str,
    summary: str,
    priority: str,
    service: str,
    env: str,
    region: str,
    status: str,
    created_at: str,
    assigned_at: Optional[str],
    root_cause: Optional[str],
    similar_count: int,
    recommended_steps: List[dict],
) -> dict:
    """Generate a structured incident brief (IcM-style) for a support ticket."""
    steps_text = "\n".join(
        f"- {s.get('title', '')}: {s.get('description', '')}"
        for s in (recommended_steps or [])[:4]
    ) or "None yet — run analysis to generate."

    prompt = (
        "You are a support incident analysis assistant. Produce a structured incident brief "
        "for the following support ticket. Be specific and factual — do NOT invent data. "
        "Use only the information provided below.\n\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"AI Summary: {summary}\n"
        f"Priority: {priority} | Service: {service} | Environment: {env} | Region: {region}\n"
        f"Status: {status}\n"
        f"Opened at: {created_at}\n"
        f"Assigned at: {assigned_at or 'Not yet assigned'}\n"
        f"Root cause: {root_cause or 'Under investigation'}\n"
        f"Similar historical incidents found: {similar_count}\n"
        f"Recommended steps:\n{steps_text}\n\n"
        "Return ONLY valid JSON — no markdown fences, no commentary:\n"
        "{\n"
        '  "what_we_know": ["<bullet 1>", "<bullet 2>", ...],\n'
        '  "what_has_been_done": ["<bullet 1>", "<bullet 2>", ...],\n'
        '  "recommended_actions": [\n'
        '    {"title": "<short title>", "detail": "<one-line detail>"},\n'
        '    ...\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- what_we_know: 4–6 bullets covering impact (service/env/region/priority), "
        "the core problem, root cause status, and similar-incident count.\n"
        "- what_has_been_done: 3–5 bullets on ticket lifecycle actions taken so far "
        "(opened, assigned, analysis run, steps generated, communications).\n"
        "- recommended_actions: exactly 3 numbered actions derived strictly from the "
        "recommended steps or standard triage next steps.\n"
        "- Start any bullet that has a label with the label followed by a colon, e.g. "
        '"Impact: 1 service (Analytics Pipeline), Production, US-West-2, Priority Normal."'
    )

    text = _client.complete(
        system_prompt="You are a precise incident management assistant. Return only valid JSON.",
        user_prompt=prompt,
        temperature=0.2,
        max_tokens=900,
    )

    # Strip markdown code fences if the model added them
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]

    try:
        return json.loads(cleaned)
    except Exception:
        return {
            "what_we_know": [
                f"Impact: {service}, {env}, {region}, Priority {priority}",
                f"Issue: {title}",
                f"Root cause: {root_cause or 'Under investigation'}",
                f"Similar historical incidents: {similar_count}",
            ],
            "what_has_been_done": [
                f"Ticket opened at {created_at}",
                f"Assigned at: {assigned_at or 'Not yet assigned'}",
                f"Status: {status}",
            ],
            "recommended_actions": [
                {"title": "Run Analysis", "detail": "Click 'Analyze Ticket' to generate AI-powered recommendations."},
                {"title": "Check Similar Incidents", "detail": f"{similar_count} historical matches found — review for known fixes."},
                {"title": "Review Root Cause", "detail": root_cause or "Investigation ongoing."},
            ],
        }


def improve_email_draft(subject: str, body: str) -> Tuple[str, str]:
    """
    Improve a user-written email draft by correcting grammar, adding proper
    greeting/signature, and ensuring professional tone.
    
    Returns:
        Tuple of (improved_subject, improved_body)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"improve_email_draft called - Subject: {subject[:50]}, Body length: {len(body)}")
    
    client = LLMClient()
    
    system_prompt = """You are a professional support engineer helping customers resolve their technical problems and tickets.
Your task is to improve email drafts by:
1. Correcting grammar, spelling, and punctuation errors
2. Adding appropriate professional greeting if missing (use "Hi" or "Good morning/afternoon" - do NOT use "team" or group greetings)
3. Adding appropriate professional closing and signature if missing
4. Using a helpful, friendly, and professional tone appropriate for customer support communication
5. Maintaining the original intent and key information
6. Ensuring the tone reflects your role as a support engineer assisting a customer
7. If no subject is provided or subject is empty, create an appropriate subject line based on the email body

Keep improvements minimal - only fix what needs fixing. The tone should be helpful and supportive, not overly formal or corporate."""

    user_prompt = f"""Improve the following email draft from a support engineer to a customer:

SUBJECT: {subject if subject else "[No subject provided - please suggest one]"}

BODY:
{body}

Please provide:
1. An improved subject line (if empty, create an appropriate one based on the email content)
2. An improved email body with proper greeting (Hi/Good morning - no "team"), helpful support engineer tone, and professional closing

Format your response EXACTLY as:
SUBJECT: <improved subject>
BODY:
<improved body>"""

    logger.info("Calling LLM for email improvement...")
    response = client.complete(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=1000,
    )
    logger.info(f"LLM response received, length: {len(response)}")
    
    # Parse response
    improved_subject = subject
    improved_body = body
    
    lines = response.split("\n")
    in_body = False
    body_lines = []
    
    for line in lines:
        if line.strip().startswith("SUBJECT:"):
            improved_subject = line.replace("SUBJECT:", "").strip()
        elif line.strip().startswith("BODY:"):
            in_body = True
        elif in_body:
            body_lines.append(line)
    
    if body_lines:
        improved_body = "\n".join(body_lines).strip()
    
    logger.info(f"Email parsing complete - Improved subject: {improved_subject[:50]}")
    return improved_subject, improved_body