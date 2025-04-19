import json
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from globals import q
from models.db import get_sync_db, get_sync_logs_db
from models.log import TransactionLog
from models.other import (
    Currency,
    Game,
    GameStatus,
    GameView,
    JackpotType,
    Ticket,
    Jackpot,
    TicketStatus,
    RepeatType
)
from models.user import Balance, BalanceChangeHistory
from models.user import Notification, Wallet
from settings import settings
from utils import worker
from utils.web3 import transfer
from .rng import get_random_sync as get_random


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
        game_inst.id,
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
    from routers.utils import url_for
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

        game.status = GameStatus.ACTIVE
        db.add(game)
        db.commit()

        start_date = datetime.now()
        game.event_start = start_date

        # Получаем билеты
        tickets = db.query(Ticket).filter(
            Ticket.game_id == game.id
        ).all()

        if not tickets or len(tickets) < game.min_ticket_count:
            game.status = GameStatus.CANCELLED
            db.add(game)
            db.commit()

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
            cond = len(drawn_numbers) < num_winning_combinations
        else:
            cond = len(drawn_numbers) < game.limit_by_ticket

        # Генерация  выигрышной комбинации до game.limit_by_ticket
        while cond:
            winners = winners | get_winners(
                game,
                tickets,
                drawn_numbers,
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
                        change_type="won",
                        previous_balance=previous_balance,
                        new_balance=balance
                    )
                    db.add(balance_change)
                    db.commit()
                    db.refresh(balance_change)

                    deposit(
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

        game.status = GameStatus.COMPLETED
        db.add(game)

        if game.repeat:
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
        jackpot_inst.id,
        job_id=f"proceed_jackpot_{jackpot_inst.id}",
    )

    return True


@worker.register
def proceed_jackpot(jackpot_id: Optional[int] = None):
    """
    Proceed the jackpot instance and distribute the prize money
    """
    from routers.utils import url_for
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
                change_type="jackpot",
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

            deposit(
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


class TransactionLogError(Exception):
    pass


def track(action):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            db = next(get_sync_logs_db())
            transaction_log = TransactionLog(
                action=action,
                status=TransactionLog.Status.PENDING,
            )
            db.add(transaction_log)
            db.commit()
            db.refresh(transaction_log)

            log_args = transaction_log.arguments or {}
            log_args.setdefault('errors', [])
            log_args.setdefault('results', "")

            main_db = next(get_sync_db())

            balance_change_history = main_db.query(BalanceChangeHistory).filter(
                BalanceChangeHistory.id == kwargs.get("history_id"),
            ).first()

            if not balance_change_history:
                transaction_log.status = TransactionLog.Status.FAILED
                log_args['errors'].append("Balance change history not found")
                transaction_log.arguments = log_args
                db.add(transaction_log)
                db.commit()
                return False

            transaction_log.user_id = balance_change_history.user_id
            transaction_log.transaction_id = balance_change_history.proof

            result = None
            try:
                result = func(*args, **kwargs)
                transaction_log.status = TransactionLog.Status.SUCCESS
                log_args['results'] = result
                transaction_log.arguments = log_args
            except TransactionLogError as e:
                transaction_log.status = TransactionLog.Status.FAILED
                log_args['errors'].append(str(e))
                transaction_log.arguments = log_args
            except Exception as e:
                transaction_log.status = TransactionLog.Status.FAILED
                log_args['errors'].append(str(e))
                transaction_log.arguments = log_args
            finally:
                transaction_log.timestamp = datetime.now()
                db.add(transaction_log)
                db.commit()

            return result
        return wrapper
    return decorator


@track(TransactionLog.TransactionAction.DEPOSIT)
@worker.register
def deposit(
    history_id: int,
    change_type: str = 'jackpot',
    counter: int = 0
):
    db = next(get_sync_db())

    balance_change_history = db.query(BalanceChangeHistory).filter(
        BalanceChangeHistory.id == history_id,
        BalanceChangeHistory.change_type == change_type,
        BalanceChangeHistory.status == BalanceChangeHistory.Status.PENDING
    ).first()

    if not balance_change_history:
        return False

    args = json.loads(balance_change_history.args or "{}")
    args.setdefault('web3', [])

    if counter > 3:
        args['error'] = "Max retries exceeded"
        balance_change_history.args = json.dumps(args)
        balance_change_history.status = BalanceChangeHistory.Status.WEB3_ERROR
        db.add(balance_change_history)
        db.commit()
        raise TransactionLogError("Max retries exceeded")

    wallet = db.query(Wallet).filter(
        Wallet.user_id == balance_change_history.user_id
    ).first()

    if not wallet:
        args['error'] = "Missing wallet"
        balance_change_history.args = json.dumps(args)
        balance_change_history.status = BalanceChangeHistory.Status.CANCELED
        db.add(balance_change_history)
        db.commit()
        raise TransactionLogError("Missing wallet")

    currency = db.query(Currency).options(
        joinedload(Currency.network)
    ).filter(
        Currency.id == balance_change_history.currency_id
    ).first()

    if not currency:
        args['error'] = "Missing currency or network"
        balance_change_history.args = json.dumps(args)
        balance_change_history.status = BalanceChangeHistory.Status.CANCELED
        db.add(balance_change_history)
        db.commit()
        raise TransactionLogError("Missing currency or network")

    tx = balance_change_history.proof or ""

    tx, err = transfer(
        currency,
        settings.private_key,
        float(balance_change_history.change_amount),
        wallet.address,
        tx
    )

    if not tx:
        args['web3'].append(str(err))
        balance_change_history.args = json.dumps(args)
        db.add(balance_change_history)
        db.commit()

        q.enqueue_at(
            datetime.now() + timedelta(minutes=1),
            deposit,
            history_id,
            change_type,
            counter + 1
        )
        raise TransactionLogError(str(err))

    balance = db.query(Balance).filter(
        Balance.user_id == balance_change_history.user_id,
        Balance.currency_id == balance_change_history.currency_id
    ).with_for_update().first()

    if not balance:
        balance = Balance(
            user_id=balance_change_history.user_id,
            currency_id=balance_change_history.currency_id,
            balance=Decimal(balance_change_history.change_amount)
        )
    else:
        balance.balance += Decimal(balance_change_history.change_amount)

    status = BalanceChangeHistory.Status.SUCCESS

    balance_change_history.status = status
    balance_change_history.proof = tx

    db.add(balance)
    db.add(balance_change_history)
    db.commit()

    return tx


@track(TransactionLog.TransactionAction.WITHDRAW)
@worker.register
def withdraw(
    history_id: int,
    counter: int = 0
):
    db = next(get_sync_db())

    balance_change_history = db.query(BalanceChangeHistory).filter(
        BalanceChangeHistory.id == history_id,
        BalanceChangeHistory.change_type == "withdraw",
        BalanceChangeHistory.status == BalanceChangeHistory.Status.PENDING
    ).first()

    if not balance_change_history:
        return False

    args = json.loads(balance_change_history.args or "{}")
    args.setdefault('web3', [])
    address = args.get("address")

    if not address:
        args['error'] = "Missing address"
        balance_change_history.args = json.dumps(args)
        balance_change_history.status = BalanceChangeHistory.Status.CANCELED
        db.add(balance_change_history)
        db.commit()
        return False

    if counter > 3:
        args['error'] = "Max retries exceeded"
        balance_change_history.args = json.dumps(args)
        balance_change_history.status = BalanceChangeHistory.Status.WEB3_ERROR
        db.add(balance_change_history)

        balance = db.query(Balance).filter(
            Balance.user_id == balance_change_history.user_id
        ).with_for_update().first()

        if balance:
            balance.balance += Decimal(balance_change_history.change_amount)
            db.add(balance)

        db.commit()
        return

    wallet = db.query(Wallet).filter(
        Wallet.user_id == balance_change_history.user_id
    ).first()

    if not wallet:
        args['error'] = "Missing wallet"
        balance_change_history.args = json.dumps(args)
        balance_change_history.status = BalanceChangeHistory.Status.CANCELED
        db.add(balance_change_history)
        db.commit()
        return False

    currency = db.query(Currency).options(
        joinedload(Currency.network)
    ).filter(
        Currency.id == balance_change_history.currency_id
    ).first()

    if not currency:
        args['error'] = "Missing currency or network"
        balance_change_history.args = json.dumps(args)
        balance_change_history.status = BalanceChangeHistory.Status.CANCELED
        db.add(balance_change_history)
        db.commit()
        return False

    tx = balance_change_history.proof or ""

    tx, err = transfer(
        currency,
        wallet.private_key,
        float(balance_change_history.change_amount),
        address,
        tx
    )

    if not tx:
        args['web3'].append(str(err))
        balance_change_history.args = json.dumps(args)
        db.add(balance_change_history)
        db.commit()

        q.enqueue_at(
            datetime.now() + timedelta(minutes=1),
            withdraw,
            history_id,
            counter + 1
        )
        return False

    balance = db.query(Balance).filter(
        Balance.user_id == balance_change_history.user_id,
        Balance.currency_id == balance_change_history.currency_id
    ).with_for_update().first()

    if not balance:
        balance = Balance(
            user_id=balance_change_history.user_id,
            currency_id=balance_change_history.currency_id
        )

        status = BalanceChangeHistory.Status.CANCELED

    else:
        balance.balance -= Decimal(balance_change_history.change_amount)

        status = BalanceChangeHistory.Status.SUCCESS

    balance_change_history.status = status
    balance_change_history.proof = tx

    db.add(balance)
    db.add(balance_change_history)
    db.commit()

    return tx


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
