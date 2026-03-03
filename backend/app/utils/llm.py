import os
from typing import Tuple, List, Optional, Dict
from openai import AzureOpenAI


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
            max_completion_tokens=max_tokens,
        )

        return response.choices[0].message.content.strip()


_client = LLMClient()



def summarize_root_cause_with_llm(
    ticket_text: str, historical_snippets: List[str]
) -> Tuple[str, str]:
    """Return (root_cause, recommendation) using configured OpenAI model."""
    if not historical_snippets:
        msg = "Not enough data."
        return msg, msg
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

    def finalize_section(key: str) -> str:
        value = "\n".join([v for v in sections[key] if v is not None]).strip()
        return value or "Not enough data."

    root_cause = finalize_section("root cause")
    recommended = finalize_section("recommended steps")
    not_worked = finalize_section("what did not work")

    recommendation = recommended
    if not_worked != "Not enough data.":
        recommendation = recommendation + f"\nWhat did not work: {not_worked}"

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