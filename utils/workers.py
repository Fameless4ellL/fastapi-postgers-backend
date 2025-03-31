from decimal import Decimal
from functools import wraps
import json
import requests
import marshal
import random
from typing import Optional
from datetime import datetime, timedelta

from models.db import get_sync_db, get_sync_logs_db
from models.user import Notification, Wallet
from models.other import (
    Currency,
    Game,
    GameStatus,
    GameView,
    Ticket,
    Jackpot,
    TicketStatus,
    RepeatType
)
from utils.web3 import transfer
from sqlalchemy.orm import joinedload
from utils import worker
from sqlalchemy import func
from models.user import Balance, BalanceChangeHistory
from globals import redis
from settings import settings
from models.log import TransactionLog


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

    add_job_to_scheduler(
        "add_to_queue",
        ["proceed_game", game_inst.id],
        scheduled_datetime
    )

    return True


@worker.register
def proceed_game(game_id: Optional[int] = None):
    """
    Proceed the game instance and distribute the prize money
    """
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

        tickets = db.query(Ticket).filter(
            Ticket.game_id == game.id
        ).all()

        if game.kind == GameView.MONETARY:
            prize = float(game.prize or 1000)
            prize_per_winner = prize // float(game.max_win_amount or 8)
        else:
            prize_per_winner = 1

        winners = []
        _tickets = [ticket.numbers for ticket in tickets]

        while len(winners) != prize_per_winner:
            if not _tickets:
                break
            # генератор случ. числел # TODO: добавить в RNG и использовать его
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

        game.numbers = winners

        for _tickets in winners:
            # Если комбинация совпала на нескольких билетах,
            # то все билеты исключаются, а приз делится пропорционально.
            prize_per_ticket = prize_per_winner / len(_tickets)
            for ticket in _tickets:
                ticket = db.query(Ticket).with_for_update().filter(
                    Ticket.id == ticket.id
                ).first()
                ticket.won = True

                if game.kind == GameView.MONETARY:
                    ticket.amount = prize_per_ticket
                    ticket.status = TicketStatus.COMPLETED

                    user_balance = db.query(Balance).with_for_update().filter(
                        Balance.user_id == ticket.user_id
                    ).first()

                    if not user_balance:
                        user_balance = Balance(
                            user_id=ticket.user_id,
                            currency_id=game.currency_id
                        )
                        db.add(user_balance)
                        db.commit()

                    previous_balance = user_balance.balance
                    balance = user_balance.balance + Decimal(prize)

                    balance_change = BalanceChangeHistory(
                        user_id=ticket.user_id,
                        balance_id=user_balance.id,
                        currency_id=game.currency_id,
                        change_amount=prize_per_ticket,
                        change_type="win",
                        previous_balance=previous_balance,
                        new_balance=balance
                    )

                    notification = Notification(
                        user_id=ticket.user_id,
                        head="You won!",
                        body=f"You won! {prize_per_ticket} {game.currency.code}",
                        args=json.dumps({
                            "game": game.name,
                            "amount": prize_per_ticket,
                            "currency": game.currency.code
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

                db.add(ticket)

        end_date = datetime.now()
        game.event_end = end_date

        game.status = GameStatus.COMPLETED
        db.add(game)

        if game.repeat:
            generate_game(game.id)

    db.commit()

    return True


@worker.register
def add_to_queue(func_name: str, *args, **kwargs):
    try:
        func_params = {
            "args": args,
            "kwargs": kwargs
        }
        json_params = json.dumps(func_params)

        value = marshal.dumps({
            "func": func_name,
            **json.loads(json_params)
        })

        return redis.lpush(worker.WORKER_TASK_KEY, value)

    except Exception as error:
        print('add_to_queue ERROR:', error)


def add_job_to_scheduler(func_name, args, run_date):
    payload = {
        "func_name": func_name,
        "args": args,
        "run_date": run_date.strftime("%Y-%m-%d %H:%M:%S")
    }
    response = requests.post(
        f"http://api:8000/v1/cron/add_job/?key={settings.cron_key}",
        json=payload
    )
    print(response.text)
    if response.status_code != 200:
        raise Exception(f"Failed to add job: {response.text}")


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

    # tz = timedelta(hours=jackpot.tzone)
    # now = datetime.now() + tz

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

    add_job_to_scheduler(
        "add_to_queue",
        ["proceed_jackpot", jackpot_inst.id],
        scheduled_datetime
    )

    return True


@worker.register
def proceed_jackpot(jackpot_id: Optional[int] = None):
    """
    Proceed the jackpot instance and distribute the prize money
    """
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
        total_prize = db.query(func.sum(Ticket.amount)).filter(
            Ticket.game_id == jackpot.id
        ).scalar() or 0

        percentage = jackpot.percentage or 10
        if percentage == 0:
            raise ValueError("Percentage cannot be zero")
        prize = total_prize * (percentage / 100)

        winners = []
        _tickets = [ticket.numbers for ticket in tickets]

        while len(winners) != 1:
            if not _tickets:
                break
            # генератор случ. числел # TODO: добавить в RNG и использовать его
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

        jackpot.numbers = winners

        for _tickets in winners:
            for ticket in _tickets:
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
                        "amount": prize,
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

        add_job_to_scheduler(
            "add_to_queue",
            ["deposit", history_id, counter + 1],
            datetime.now() + timedelta(minutes=1)
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

        add_job_to_scheduler(
            "add_to_queue",
            ["withdraw", history_id, counter + 1],
            datetime.now() + timedelta(minutes=1)
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

# def buy_tickets():
#     db = next(get_sync_db())
    
#     wallet = db.query(Wallet).filter(
#         User.id == user.id
#     )
#     wallet = wallet.scalar()

#     if wallet is None:
#         return JSONResponse(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             content=BadResponse(message="Wallet not found").model_dump()
#         )

#     balance_result = await db.execute(
#         select(Balance)
#         .with_for_update()
#         .filter(Balance.user_id == user.id)
#     )
#     user_balance = balance_result.scalar() or Balance(balance=0)
#     total_price = game.price * len(item.numbers)

#     try:
#         contract = w3.eth.contract(
#             address=currency.address,
#             abi=json.loads(await aredis.get("abi"))
#         )
#         amount = int(total_price * 10 ** currency.decimals)

#         w3.eth.default_account = wallet.address
#         _hash = await contract.functions.transfer(settings.address, amount).transact()
#         tx = await w3.eth.wait_for_transaction_receipt(_hash, timeout=60)

#         if tx is None or tx.status != 1:
#             return JSONResponse(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 content=BadResponse(message="Transaction failed").model_dump()
#             )
#     except Exception as e:
#         return JSONResponse(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             content=BadResponse(message=str(e)).model_dump()
#         )