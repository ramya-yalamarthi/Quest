import json

class SummarizationAgent:
    """
    Support ticket summarization agent.
    Input:
        user_summary: str
        user_description: str
    Output:
        ai_summary: str (1–3 sentences)
    Returns:
        JSON: {"summary": ""}
    """
    PROMPT = (
        "You are a support ticket summarization assistant.\n"
        "Generate a concise summary of the issue in 1–3 sentences.\n"
        "Focus on:\n"
        "the core problem\n"
        "system affected\n"
        "any mentioned error codes\n"
        "the impact on the user\n"
        "Extract any error codes mentioned in the title or description.\n"
        "Return JSON:\n"
        '{\n"summary": "",\n"error_codes": []\n}'
    )

    def __init__(self, user_summary: str, user_description: str):
        self.user_summary = user_summary
        self.user_description = user_description

    def run(self, llm):
        """
        Calls the LLM with the summarization prompt and user inputs.
        Args:
            llm: An LLM interface with a .generate(prompt) method.
        Returns:
            dict: {"summary": ai_summary, "error_codes": [codes]}
        """
        input_text = f"Summary: {self.user_summary}\nDescription: {self.user_description}"
        prompt = self.PROMPT + "\n" + input_text
        response = llm.complete(
            system_prompt="You are a support ticket summarization assistant.",
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=180
        )
        try:
            result = json.loads(response)
            # Ensure error_codes is always a list
            if "error_codes" not in result:
                result["error_codes"] = []
            return result
        except Exception:
            return {"summary": response.strip(), "error_codes": []}
