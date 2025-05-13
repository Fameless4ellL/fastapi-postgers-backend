import json
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
from sqlalchemy.orm import joinedload

from src.globals import q
from src.models.db import get_sync_db, get_sync_logs_db
from src.models.log import TransactionLog
from src.models.other import (
    Currency,
)
from src.models.user import Balance, BalanceChangeHistory
from src.models.user import Wallet
from settings import settings
from src.utils import worker
from src.utils.web3 import transfer



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


