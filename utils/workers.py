from decimal import Decimal
import json
import requests
import marshal
import random
from typing import Optional
from datetime import datetime, timedelta

from models.db import get_sync_db
from web3 import Web3, middleware
from web3.types import TxReceipt
from aiohttp import client_exceptions
from models.user import Wallet
from models.other import Currency, Game, GameStatus, Network, Ticket, Jackpot
from utils import worker
from sqlalchemy import func
from models.user import Balance, BalanceChangeHistory
from globals import redis
from settings import settings
from utils.web3 import AWSHTTPProvider


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
        Game.deleted.is_(False)
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
        game_type=game.game_type,
        description=game.description,
        country=game.country,
        repeat=True,
        repeat_days=game.repeat_days,
        scheduled_datetime=scheduled_datetime,
        price=game.price,
        max_win_amount=game.max_win_amount,
        prize=game.prize,
        currency_id=game.currency_id,
        limit_by_ticket=game.limit_by_ticket,
        max_limit_grid=game.max_limit_grid,
        min_ticket_count=game.min_ticket_count,
        image=game.image,
        status=GameStatus.PENDING,
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

        tickets = db.query(Ticket).filter(
            Ticket.game_id == game.id
        ).all()

        prize = float(game.prize or 1000)
        prize_per_winner = prize // float(game.max_win_amount or 8)

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
                user_balance.balance += Decimal(prize_per_ticket)
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
        Jackpot.repeat.is_(True),
        Jackpot.id == jackpot_id,
        Jackpot.deleted.is_(False)
    ).first()

    if not jackpot:
        return False

    tz = timedelta(hours=jackpot.tzone)
    now = datetime.now() + tz
    next_day = now

    while True:
        next_day += timedelta(days=1)

        if next_day.weekday() in jackpot.repeat_days:
            break

        if next_day - now > timedelta(days=14):
            return False

    scheduled_datetime = next_day.replace(
        hour=jackpot.scheduled_datetime.hour,
        minute=jackpot.scheduled_datetime.minute,
    )

    jackpot_inst = Jackpot(
        name=f"game #{str(jackpot.id + 1)}",
        game_type=jackpot.game_type,
        description=jackpot.description,
        country=jackpot.country,
        repeat=True,
        repeat_days=jackpot.repeat_days,
        scheduled_datetime=scheduled_datetime,
        price=jackpot.price,
        max_win_amount=jackpot.max_win_amount,
        prize=jackpot.prize,
        currency_id=jackpot.currency_id,
        limit_by_ticket=jackpot.limit_by_ticket,
        max_limit_grid=jackpot.max_limit_grid,
        min_ticket_count=jackpot.min_ticket_count,
        image=jackpot.image,
        status=GameStatus.PENDING,
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
    Proceed the game instance and distribute the prize money
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

        tickets = db.query(Ticket).filter(
            Ticket.game_id == jackpot.id
        ).all()
        total_prize = db.query(func.sum(Ticket.amount)).filter(
            Ticket.game_id == jackpot.id
        ).scalar() or 0

        percentage = jackpot.percentage or 10
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

        for _tickets in winners:
            for ticket in _tickets:
                user_balance = db.query(Balance).with_for_update().filter(
                    Balance.user_id == ticket.user_id
                ).first()

                if not user_balance:
                    continue

                previous_balance = user_balance.balance
                user_balance.balance += Decimal(prize)
                db.add(user_balance)

                balance_change = BalanceChangeHistory(
                    user_id=ticket.user_id,
                    balance_id=user_balance.id,
                    change_amount=prize,
                    change_type="jackpot",
                    previous_balance=previous_balance,
                    new_balance=user_balance.balance
                )
                db.add(balance_change)
        jackpot.status = GameStatus.COMPLETED
        db.add(jackpot)

        if jackpot.repeat:
            generate_jackpot(jackpot.id)

    db.commit()

    return True


def get_w3(
    network_id: int,
    private_key: str = settings.private_key
) -> Web3:
    db = next(get_sync_db())
    network = db.query(Network).filter(
        Network.id == network_id
    ).first()

    if not network:
        return False

    try:
        w3 = Web3(AWSHTTPProvider(network.rpc_url))

        if not w3.is_connected():
            return False
    except client_exceptions.ClientError:
        return False

    acct = w3.eth.account.from_key(private_key)

    w3.middleware_onion.inject(middleware.SignAndSendRawMiddlewareBuilder.build(acct), layer=0)
    w3.eth.default_account = acct.address

    return w3


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

    try:

        currency = db.query(Currency).filter(
            Currency.id == balance_change_history.currency_id
        ).first()

        if not currency:
            return False

        w3 = get_w3(
            currency.network_id,
            wallet.private_key
        )

        abi = redis.get("abi")

        contract = w3.eth.contract(
            address=w3.to_checksum_address(currency.address),
            abi=json.loads(abi)
        )

        amount = int(balance_change_history.change_amount * 10 ** currency.decimals)
        _hash = contract.functions.transfer(
            w3.to_checksum_address(address),
            amount
        ).transact({
            "from": w3.eth.default_account
        })

        tx = w3.eth.get_transaction_receipt(_hash)
    except Exception as e:
        args['web3'].append(str(e))
        balance_change_history.args = json.dumps(args)
        db.add(balance_change_history)
        db.commit()

        add_job_to_scheduler(
            "add_to_queue",
            ["withdraw", history_id, counter + 1],
            datetime.now() + timedelta(minutes=1)
        )
        return False

    if tx.status != 1:
        args['web3'].append("Transaction failed")
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
        Balance.user_id == balance_change_history.id
    ).with_for_update().first()

    if not balance:
        balance = Balance(user_id=balance_change_history.id)

        status = BalanceChangeHistory.Status.CANCELED

    else:
        balance.balance -= Decimal(balance_change_history.change_amount)

        status = BalanceChangeHistory.Status.SUCCESS

    balance_change_history.status = status
    balance_change_history.proof = tx.transactionHash

    db.add(balance)
    db.add(balance_change_history)
    db.commit()


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