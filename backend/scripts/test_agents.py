import os
from uuid import uuid4

from app.db.session import SessionLocal
from app.mcp.server import MCPServer
from app.mcp.tools import create_ticket, ensure_user
from app.utils import embeddings, llm


def main() -> None: 
    db = SessionLocal()
    try:
        user = ensure_user(
            db,
            email="anjali.mamidi03@gmail.com",
            display_name="Support Tester",
            role="SUPPORT",
        )
        ticket = create_ticket(
            db,
            title = "Degraded Blob Upload Performance in Azure Storage Account",
            description = "Blob uploads to the Azure Storage account are experiencing unusually high latency. Upload times have increased from approximately 200 ms to over 2 seconds. No recent network or configuration changes have been reported.",
            created_by_user_id=user.user_id,
        )

        server = MCPServer(db)
        result = server.handle_new_ticket(ticket.ticket_id, engineer_id=user.user_id)

        print("ticket_id:", ticket.ticket_id)
        print("root_cause:", result["insights"]["root_cause"])
        print("recommendation:", result["insights"]["recommendation"])
        print("similar_count:", len(result["insights"]["similar_resolutions"]))
        print("draft_email_id:", result["draft_email"].email_id)
        print("draft_email_subject:", result["draft_email"].subject)
        print("draft_email_body:\n", result["draft_email"].body)
        print("similar_resolutions:")
        for r in result["insights"]["similar_resolutions"]:
            print("  - resolution_id:", r.resolution_id)
            print("    ticket_id:", r.ticket_id)
            print("    resolution_text:", r.resolution_text)
    finally:
        db.close()


if __name__ == "__main__":
    main()
