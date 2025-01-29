import random
from typing import Optional
from datetime import datetime, timedelta
from models.db import get_sync_db
from models.other import Game, GameInstance, GameStatus, Ticket
from utils import worker
from models.user import Balance, BalanceChangeHistory
from globals import scheduler


@worker.register
def generate_game(
    game_id: int,
) -> bool:
    """
    creating a new game instance based on Game
    """
    db = get_sync_db()
    game = db.query(Game).filter(
        Game.repeat.is_(True),
        Game.id == game_id
    ).first()

    if not game:
        return False

    tz = timedelta(hours=game.zone)
    now = datetime.now() + tz
    next_day = now + timedelta(days=1)

    while True:
        next_day += timedelta(days=1)

        if next_day.weekday() in game.repeat_days:
            break

        if next_day - now > timedelta(days=14):
            return False

    scheduled_datetime = next_day.replace(
        hour=game.scheduled_datetime.hour,
        minute=game.scheduled_datetime.minute,
    )

    game_inst = GameInstance(
        game_id=game.id,
        status=GameStatus.PENDING,
        scheduled_datetime=scheduled_datetime
    )
    db.add(game_inst)
    db.commit()
    db.refresh(game_inst)

    from worker.worker import add_to_queue
    scheduler.add_job(
        add_to_queue,
        "date",
        args=["proceed_game", game_inst.id],
        run_date=game.scheduled_datetime
    )

    return True


@worker.register
def proceed_game(game_id: Optional[int] = None):
    """
    Proceed the game instance and distribute the prize money
    """
    db = get_sync_db()

    if game_id:
        pending_games = db.query(GameInstance).filter(
            GameInstance.status == GameStatus.PENDING,
            GameInstance.id == game_id
        ).with_for_update().all()
    else:
        pending_games = db.query(GameInstance).filter(
            GameInstance.status == GameStatus.PENDING
        ).with_for_update().all()

    for game_inst in pending_games:
        game = db.query(Game).filter(Game.id == game_inst.game_id).first()

        if not game:
            continue

        tickets = db.query(Ticket).filter(
            Ticket.game_instance_id == game_inst.id
        ).all()

        # Разыграно будет 80%
        total_prize_pool = 0.8 * len(tickets) * float(game.price)
        prize_per_winner = total_prize_pool // float(game.max_win_amount or 8)

        winners = []
        _tickets = [ticket.numbers for ticket in tickets]

        while len(winners) != prize_per_winner:
            if not _tickets:
                break
            # генератор случ. числел
            winning_numbers = random.sample(
                _tickets,
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
                ticket = db.query(Ticket).with_for_update().filter(
                    Ticket.id == ticket.id
                ).first()
                ticket.won = True
                ticket.amount = prize_per_ticket
                db.add(ticket)

                user_balance = db.query(Balance).with_for_update().filter(
                    Balance.user_id == ticket.user_id
                ).first()

                if not user_balance:
                    continue

                previous_balance = user_balance.balance
                user_balance.balance += prize_per_ticket
                db.add(user_balance)

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
        db.add(game_inst)

        if game.repeat:
            generate_game(game.id)

    db.commit()

    return True
