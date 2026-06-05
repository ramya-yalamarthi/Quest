from app.db.session import SessionLocal
from app.db.models.resolution import Resolution
from app.db.models.ticket import Ticket
from app.utils.embeddings import get_embedding


def main() -> None:
    db = SessionLocal()
    try:
        resolutions = (
            db.query(Resolution)
            .filter(Resolution.embedding == None)
            .all()
        )

        if not resolutions:
            print("No resolutions to backfill.")
            return

        ticket_ids = [r.ticket_id for r in resolutions]
        tickets_by_id = {
            t.ticket_id: t
            for t in db.query(Ticket).filter(Ticket.ticket_id.in_(ticket_ids)).all()
        }

        for r in resolutions:
            t = tickets_by_id.get(r.ticket_id)
            if t:
                text = f"Title: {t.title}\nDescription: {t.description}\nResolution: {r.resolution_text}"
            else:
                text = r.resolution_text
            r.embedding = get_embedding(text)
            db.add(r)

        db.commit()
        print(f"Backfilled embeddings for {len(resolutions)} resolutions.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
