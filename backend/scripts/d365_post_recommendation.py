"""Process a D365 Case and post the AI recommendation as a Note.

Usage (env vars must be set: DATAVERSE_*, AZURE_*, EMBEDDING_*, OPENAI_*/LLM_*):
    python scripts/d365_post_recommendation.py            # newest Case
    python scripts/d365_post_recommendation.py CAS-01023  # a specific Case

This is the on-demand version of the poller -- run it after creating a Case in
Dynamics to see the recommendation appear in that Case's timeline.
"""
import sys

from app.orchestrator.dataverse import DataverseClient
from app.orchestrator.d365_runner import process_case, NOTE_SUBJECT


def main(argv):
    target_num = argv[1] if len(argv) > 1 else None
    client = DataverseClient()
    corpus = client.list_cases(top=100)
    if not corpus:
        print("No cases found."); return

    if target_num:
        target = next((c for c in corpus if (c.get("ticket_number") or "").upper().startswith(target_num.upper())), None)
        if not target:
            print(f"Case {target_num} not found."); return
    else:
        target = corpus[0]  # newest (list_cases is ordered createdon desc)

    print(f"Processing {target['ticket_number']} | {target['title']}")
    advisory, note = process_case(target, corpus)
    ann = client.create_case_note(target["id"], NOTE_SUBJECT, note)
    print("\n" + note)
    print(f"\nPosted to {target['ticket_number']} (annotation {ann}).")


if __name__ == "__main__":
    main(sys.argv)
