import json
import requests
import marshal
import random
from typing import Optional
from datetime import datetime, timedelta

from models.db import get_sync_db
from models.other import Game, GameInstance, GameStatus, Ticket
from utils import worker
from models.user import Balance, BalanceChangeHistory
from globals import redis
from settings import settings


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
        Game.id == game_id
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

    game_inst = GameInstance(
        game_id=game.id,
        status=GameStatus.PENDING,
        scheduled_datetime=scheduled_datetime
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

        prize = game.prize or 1000
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
