import random
import uuid
from sqlalchemy import select
from models.db import get_sync_db
from models.other import Game, GameInstance, GameStatus, GameType, Ticket
from utils import worker
from sqlalchemy import select
from models.other import Game, GameInstance, GameStatus
from models.user import Balance, BalanceChangeHistory


@worker.register
def generate_game():
    """
    creating a new game instance based on Game
    """
    db = get_sync_db()
    game = db.execute(
        select(Game).filter(Game.as_default is True)
    )
    game = game.scalars().first()

    if not game:
        game = Game(
            name=f"game #{str(uuid.uuid4())}",
            game_type=GameType.GLOBAL,
            description="Default game",
            as_default=True
        )

        db.add(game)
        db.commit()
        db.refresh(game)

    game_inst = GameInstance(
        game_id=game.id,
        status=GameStatus.PENDING,
    )
    db.add(game_inst)
    db.commit()
    db.refresh(game_inst)

    return True


@worker.register
def proceed_game():
    """
    Proceed the game instance and distribute the prize money
    """
    db = get_sync_db()

    with db.begin():
        # Find all PENDING GameInstance records and lock them for update
        pending_games = db.execute(
            select(GameInstance)
            .with_for_update()
            .filter(GameInstance.status == GameStatus.PENDING)
        ).scalars().all()

        for game_inst in pending_games:
            game = db.execute(
                select(Game).filter(Game.id == game_inst.game_id)
            ).scalars().first()

            if not game:
                continue

            tickets = db.execute(
                select(Ticket).filter(Ticket.game_instance_id == game_inst.id)
            ).scalars().all()

            # Разыграно будет 80%
            total_prize_pool = 0.8 * len(tickets) * float(game.price)
            prize_per_winner = total_prize_pool // game.max_win_amount

            winners = []
            while len(winners) == prize_per_winner:
                # генератор случ. числел
                winning_numbers = random.sample(
                    [ticket.numbers for ticket in tickets],
                    1
                )[0]
                # проверка на наличие победителей
                sub_winners = [
                    ticket
                    for ticket in tickets
                    if set(ticket.numbers).issubset(set(winning_numbers))
                ]
                if sub_winners:
                    winners.append(sub_winners)

            for _tickets in winners:
                # Если комбинация совпала на нескольких билетах,
                # то все билеты исключаются, а приз делится пропорционально.
                prize_per_ticket = prize_per_winner / len(_tickets)
                for ticket in _tickets:
                    ticket = db.execute(
                        select(Ticket)
                        .with_for_update()
                        .filter(Ticket.id == ticket.id)
                    ).scalars().first()
                    ticket.won = True
                    ticket.amount = prize_per_ticket

                    user_balance = db.execute(
                        select(Balance)
                        .with_for_update()
                        .filter(Balance.user_id == ticket.user_id)
                    ).scalars().first()

                    if not user_balance:
                        continue

                    previous_balance = user_balance.balance
                    user_balance.balance += prize_per_ticket

                    balance_change = BalanceChangeHistory(
                        user_id=ticket.user_id,
                        balance_id=user_balance.id,
                        change_amount=prize_per_ticket,
                        change_type="win",
                        previous_balance=previous_balance,
                        new_balance=user_balance.balance
                    )

                    db.add(balance_change)

            game_inst.status = GameStatus.COMPLETED
    db.commit()
    generate_game()

    return True
