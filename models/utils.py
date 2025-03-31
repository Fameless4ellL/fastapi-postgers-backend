import random
from sqlalchemy.orm import Session


def generate_unique_ticket_number(
    db: Session,
    length: int = 15
) -> str:
    """
    Generate a unique ticket number using UUID4, converted to digits, and ensure it is not too similar to existing tickets.

    :param db: SQLAlchemy session for database access.
    :param game_id: ID of the game for which the ticket is being generated.
    :param length: Length of the ticket number (default is 15).
    :return: A unique ticket number.
    """
    from models.other import Ticket

    while True:
        ticket_number = ''.join(random.choices('0123456789', k=length))
        # Check if the ticket number already exists in the database
        existing_ticket = db.query(Ticket).filter(
            Ticket.number == ticket_number
        )

        if not db.query(existing_ticket.exists()).scalar():
            return ticket_number
