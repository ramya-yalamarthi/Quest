from app.db.session import SessionLocal
from app.db.models.ticket import Ticket
from app.utils.embeddings import get_embedding


def main() -> None:
    db = SessionLocal()
    try:
        tickets = db.query(Ticket).filter(Ticket.embedding == None).all()
        if not tickets:
            print("No tickets to backfill.")
            return

        for t in tickets:
            text = f"Title: {t.title}\nDescription: {t.description}"
            t.embedding = get_embedding(text)
            db.add(t)

        db.commit()
        print(f"Backfilled embeddings for {len(tickets)} tickets.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
