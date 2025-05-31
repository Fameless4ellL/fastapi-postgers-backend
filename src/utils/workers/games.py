import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Optional

from sqlalchemy import func

from src.globals import q
from src.models.db import get_sync_db
from src.models.other import (
    Game,
    GameStatus,
    GameView,
    JackpotType,
    Ticket,
    Jackpot,
    TicketStatus,
    RepeatType
)
from src.models.user import Balance, BalanceChangeHistory
from src.models.user import Notification
from src.utils import worker
from ..rng import get_random_sync as get_random


logger = logging.getLogger(__name__)


@worker.register
def generate_game(
    game_id: int,
) -> bool:
    """
    creating a new game instance based on Game
    """
    db = next(get_sync_db())
    game = db.query(Game).filter(
        Game.repeat.is_(True),
        Game.id == game_id,
        Game.status != GameStatus.DELETED
    ).first()

    if not game:
        return False

    tz = timedelta(hours=game.zone)
    now = datetime.now() + tz
    next_day = now

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

    game_inst = Game(
        name=f"game #{str(game.id)}",
        status=GameStatus.PENDING,
        scheduled_datetime=scheduled_datetime,
        **{
            key: getattr(game, key)
            for key in Game.__table__.columns.keys()
            if key not in {
                "id", "name", "scheduled_datetime",
                "event_start", "event_end", 'status'
            }
        }
    )
    db.add(game_inst)
    db.commit()
    db.refresh(game_inst)

    q.enqueue_at(
        scheduled_datetime,
        proceed_game,
        game_id=game_inst.id,
        job_id=f"proceed_game_{game_inst.id}",
    )

    return True


def get_winners(
    game: Game,
    tickets: list[Ticket],
    drawn_numbers: list[int],
) -> set[Ticket]:
    """
    Generate winning numbers for the game instance
    """
    number = get_random(1, game.max_limit_grid)

    if number in drawn_numbers:
        return set()

    drawn_numbers.append(number)

    _winners = {
        ticket
        for ticket in tickets
        if set(drawn_numbers).issubset(set(ticket.numbers))
    }

    if not _winners:
        drawn_numbers.pop()
        return set()

    if game.kind == GameView.MONETARY:
        max_win_per_combination = float(game.max_win_amount or 100)
        prize_per_winner = max_win_per_combination / len(_winners)

    for ticket in _winners:
        if game.kind == GameView.MONETARY:
            ticket.amount = prize_per_winner
        ticket.status = TicketStatus.COMPLETED
        ticket.won = True
        ticket.numbers = drawn_numbers

    return _winners


@worker.register
def proceed_game(game_id: Optional[int] = None):
    """
    Proceed the game instance and distribute the prize money
    """
    from src.utils.validators import url_for
    db = next(get_sync_db())

    if game_id:
        pending_games = db.query(Game).filter(
            Game.status == GameStatus.PENDING,
            Game.id == game_id
        ).with_for_update().all()
    else:
        pending_games = db.query(Game).filter(
            Game.status == GameStatus.PENDING
        ).with_for_update().all()

    for game in pending_games:
        if not game:
            continue

        logger.info(f"Proceeding game {game.id} - {game.name}")

        game.status = GameStatus.ACTIVE
        db.add(game)
        db.commit()

        start_date = datetime.now()
        game.event_start = start_date
        logger.info(f"Game {game.id} started at {start_date}")

        # Получаем билеты
        tickets = db.query(Ticket).filter(
            Ticket.game_id == game.id
        ).all()

        if not tickets or len(tickets) < game.min_ticket_count:

            logger.warning(
                f"Game {game.id} - {game.name} has no tickets or not enough tickets"
            )
            game.status = GameStatus.CANCELLED
            db.add(game)
            db.commit()

            if game.repeat:
                generate_game(game.id)

            # TODO вернуть деньги пользователям
            continue

        if game.kind == GameView.MONETARY:
            # Рассчитываем призовой фонд
            ticket_price = float(game.price or 1)
            total_tickets = float(game.prize)

            jackpot = db.query(Jackpot).filter(
                Jackpot._type == JackpotType[game.game_type.name],
                Jackpot.status == GameStatus.PENDING
            ).first()
            if not jackpot:
                percentage = float(jackpot.percentage) or 10
                percentage = percentage / 100
            else:
                percentage = 0

            # 10% на джекпот и 10% на расходы
            total_prize = total_tickets * ticket_price * (1 - percentage - 0.1)

            max_win_per_combination = float(game.max_win_amount or 100)
            num_winning_combinations = int(total_prize // max_win_per_combination)
            actual_prize_fund = num_winning_combinations * max_win_per_combination
            jackpot_remainder = total_prize - actual_prize_fund
            # Сохраняем остаток в джекпот
            if jackpot:
                jackpot.amount += Decimal(jackpot_remainder)
                db.add(jackpot)

        winners = set()
        drawn_numbers = []

        if game.kind == GameView.MONETARY:
            cond = partial(
                lambda x: len(x) < game.num_winning_combinations,
                drawn_numbers
            )
        else:
            cond = partial(
                lambda x: len(x) < game.limit_by_ticket,
                drawn_numbers
            )

        # Генерация  выигрышной комбинации до game.limit_by_ticket
        logger.info(
            f"Generating winning combinations for game {game.id} - {game.name}"
        )
        while cond():
            winners = winners | get_winners(
                game,
                tickets,
                drawn_numbers,
            )
        logger.info(
            f"Generated {len(drawn_numbers)} winning combinations for game {game.id} - {game.name}"
        )

        tickets = [
            ticket
            for ticket in tickets
            if ticket not in winners
        ]

        if game.kind == GameView.MONETARY:
            # Генерация остальных выигрышных комбинаций
            while len(drawn_numbers) < num_winning_combinations:
                _winners = get_winners(
                    game,
                    tickets,
                    drawn_numbers,
                )
                if _winners:
                    winners = winners | _winners
                    tickets = [
                        ticket
                        for ticket in tickets
                        if ticket not in _winners
                    ]

        game.numbers = drawn_numbers

        for _ticket in winners:
            if game.kind == GameView.MONETARY:
                if not _ticket.demo:
                    user_balance = db.query(Balance).with_for_update().filter(
                        Balance.user_id == _ticket.user_id
                    ).first()

                    if not user_balance:
                        user_balance = Balance(
                            user_id=_ticket.user_id,
                            currency_id=game.currency_id
                        )
                        db.add(user_balance)
                        db.commit()

                    previous_balance = user_balance.balance
                    balance = user_balance.balance + Decimal(_ticket.amount)

                    balance_change = BalanceChangeHistory(
                        user_id=_ticket.user_id,
                        balance_id=user_balance.id,
                        currency_id=game.currency_id,
                        change_amount=_ticket.amount,
                        game_id=game.id,
                        game_type=BalanceChangeHistory.GameInstanceType.GAME,
                        change_type="won",
                        previous_balance=previous_balance,
                        new_balance=balance
                    )
                    db.add(balance_change)
                    db.commit()
                    db.refresh(balance_change)

                    logger.info(
                        f"User {_ticket.user_id} won {_ticket.amount} {game.currency.code} in game {game.id}"
                    )
                    worker.deposit(
                        history_id=balance_change.id,
                        change_type=balance_change.change_type
                    )

                notification = Notification(
                    user_id=_ticket.user_id,
                    head="You won!",
                    body=f"You won! {_ticket.amount} {game.currency.code}",
                    args=json.dumps({
                        "game": game.name,
                        "type": type(game).__name__,
                        "image": url_for("static", path=game.image),
                        "amount": str(_ticket.amount),
                        "currency": game.currency.code
                    })
                )
                db.add(notification)
                db.commit()

            else:
                notification = Notification(
                    user_id=_ticket.user_id,
                    head="You won!",
                    body=f"You won! {game.prize}",
                    args=json.dumps({
                        "game": game.name,
                        "type": type(game).__name__,
                        "image": url_for("static", path=game.image),
                        "amount": str(_ticket.amount),
                        "currency": game.currency.code
                    })
                )
                db.add(notification)
                db.commit()

        db.add_all(winners)

        end_date = datetime.now()
        game.event_end = end_date
        logger.info(f"Game {game.id} ended at {end_date}")

        game.status = GameStatus.COMPLETED
        db.add(game)

        if game.repeat:
            logger.info(f"Generating new game instance for {game.id} - {game.name}")
            generate_game(game.id)

    db.commit()

    return True


@worker.register
def generate_jackpot(
    jackpot_id: int,
) -> bool:
    """
    creating a new jackpot instance based on Jackpot
    """
    db = next(get_sync_db())
    jackpot = db.query(Jackpot).filter(
        Jackpot.repeat_type != RepeatType.NONE,
        Jackpot.id == jackpot_id,
    ).first()

    if not jackpot:
        return False

    next_day = jackpot.next_scheduled_date()
    if not next_day:
        return False

    scheduled_datetime = next_day.replace(
        hour=jackpot.scheduled_datetime.hour,
        minute=jackpot.scheduled_datetime.minute,
    )

    fund_start = scheduled_datetime - timedelta(days=7)
    fund_end = scheduled_datetime - timedelta(days=1)

    jackpot_inst = Jackpot(
        name=f"Jackpot #{str(jackpot.id + 1)}",
        status=GameStatus.PENDING,
        scheduled_datetime=scheduled_datetime,
        fund_start=fund_start,
        fund_end=fund_end,
        **{
            key: getattr(jackpot, key)
            for key in Jackpot.__table__.columns.keys()
            if key not in {
                "id", "name", "scheduled_datetime",
                "fund_start", "fund_end", "event_start",
                "event_end", "status"
            }
        }
    )
    db.add(jackpot_inst)
    db.commit()
    db.refresh(jackpot_inst)

    q.enqueue_at(
        scheduled_datetime,
        proceed_jackpot,
        jackpot_id=jackpot_inst.id,
        job_id=f"proceed_jackpot_{jackpot_inst.id}",
    )

    return True


@worker.register
def proceed_jackpot(jackpot_id: Optional[int] = None):
    """
    Proceed the jackpot instance and distribute the prize money
    """
    from src.utils.validators import url_for
    db = next(get_sync_db())

    if jackpot_id:
        jackpots = db.query(Jackpot).filter(
            Jackpot.status == GameStatus.PENDING,
            Jackpot.id == jackpot_id
        ).with_for_update().all()
    else:
        jackpots = db.query(Jackpot).filter(
            Jackpot.status == GameStatus.PENDING
        ).with_for_update().all()

    for jackpot in jackpots:

        if not jackpot:
            continue

        start_date = datetime.now()
        jackpot.event_start = start_date

        tickets = db.query(Ticket).filter(
            Ticket.jackpot_id == jackpot.id
        ).all()

        if not tickets:
            jackpot.status = GameStatus.CANCELLED
            db.add(jackpot)
            db.commit()
            continue

        total_prize = db.query(func.sum(Ticket.amount)).filter(
            Ticket.game_id == jackpot.id
        ).scalar() or 0

        percentage = jackpot.percentage or 10
        if percentage == 0:
            raise ValueError("Percentage cannot be zero")
        prize = total_prize * (percentage / 100)

        remaining_tickets = tickets
        winning_number = ""

        while len(remaining_tickets) > 1:
            digit = get_random(0, 9)  # Выпавшее число может быть от 0 до 9
            new_winning_number = winning_number + str(digit)

            # Filter tickets based on the current sequence of digits
            filtered_tickets = [
                ticket for ticket in remaining_tickets
                if ticket.numbers.startswith(new_winning_number)
            ]

            if filtered_tickets:
                # Update the winning number and remaining tickets
                winning_number = new_winning_number
                remaining_tickets = filtered_tickets
            else:
                # Retry with a new digit if no tickets match
                continue

        jackpot.numbers = [int(digit) for digit in winning_number]

        if remaining_tickets:
            ticket = remaining_tickets[0]

            user_balance = db.query(Balance).with_for_update().filter(
                Balance.user_id == ticket.user_id
            ).first()

            if not user_balance:
                user_balance = Balance(
                    user_id=ticket.user_id,
                    currency_id=jackpot.currency_id
                )
                db.add(user_balance)
                db.commit()
                db.refresh(user_balance)

            previous_balance = user_balance.balance
            balance = user_balance.balance + Decimal(prize)

            balance_change = BalanceChangeHistory(
                user_id=ticket.user_id,
                balance_id=user_balance.id,
                currency_id=jackpot.currency_id,
                change_amount=prize,
                change_type="won",
                game_id=jackpot.id,
                game_type=BalanceChangeHistory.GameInstanceType.JACKPOT,
                previous_balance=previous_balance,
                new_balance=balance
            )

            notification = Notification(
                user_id=ticket.user_id,
                head="You won!",
                body=f"You won! {prize} {jackpot.currency.code}",
                args=json.dumps({
                    "game": jackpot.name,
                    "type": type(jackpot).__name__,
                    "image": url_for("static", path=jackpot.image),
                    "amount": str(prize),
                    "currency": jackpot.currency.code
                })
            )

            db.add(notification)
            db.add(balance_change)
            db.commit()
            db.refresh(balance_change)

            worker.deposit(
                history_id=balance_change.id,
                change_type=balance_change.change_type
            )

        end_date = datetime.now()
        jackpot.event_end = end_date

        jackpot.status = GameStatus.COMPLETED
        db.add(jackpot)

        if jackpot.repeat_type != RepeatType.NONE:
            generate_jackpot(jackpot.id)

    db.commit()

    return True


@worker.register
def set_pending_jackpot(
    jackpot_id: int,
    status: GameStatus
):
    db = next(get_sync_db())
    jackpot = db.query(Jackpot).filter(
        Jackpot.id == jackpot_id
    ).first()

    if not jackpot:
        return False

    jackpot.status = status
    db.add(jackpot)
    db.commit()

    return True
