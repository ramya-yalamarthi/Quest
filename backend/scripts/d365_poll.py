"""Run the D365 poller: watch Dynamics for new Cases and auto-post recommendations.

Requires env vars: DATAVERSE_*, AZURE_*, EMBEDDING_*, OPENAI_*/LLM_*.

    python scripts/d365_poll.py            # poll every 120s
    python scripts/d365_poll.py 60         # poll every 60s

Leave it running, then create a Case in Dynamics -- within one interval the
"AI Support Recommendation" note appears on that Case's timeline.
"""
import sys

from app.orchestrator.dataverse import DataverseClient, available
from app.orchestrator.d365_poller import poll_loop


def main(argv):
    if not available():
        print("Dataverse env vars not set (DATAVERSE_URL / AZURE_*). Aborting.")
        return
    interval = int(argv[1]) if len(argv) > 1 else 120
    poll_loop(DataverseClient(), interval=interval)


if __name__ == "__main__":
    main(sys.argv)
