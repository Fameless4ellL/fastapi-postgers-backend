from datetime import timedelta, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, literal_column, DECIMAL

from src.models import (
    Ticket,
    get_sync_db,
    Metric,
    User,
    Role,
    BalanceChangeHistory,
    get_sync_logs_db,
    UserActionLog,
    Currency,
    Game,
    Jackpot, GameView,
)
from src.utils import worker
from settings import settings


def yesterday():
    return (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def hour_left():
    return datetime.now() - timedelta(minutes=15)


@worker.register
def calculate_metrics(date: Optional[datetime] = None):

    update_today = False
    if date is None:
        update_today = True
        date = hour_left()

    db = next(get_sync_db())
    logs = next(get_sync_logs_db())

    regions = db.query(User.country).distinct(User.country).all()
    currency = db.query(Currency).first()  # TODO change, after adding currencies

    global_games = (
        db.query(func.count(func.distinct(Game.id)))
        .filter(
            Game.created_at >= date,
            Game.country.is_(None)
        )
        .scalar()
    )
    global_jackpots = (
        db.query(func.count(func.distinct(Jackpot.id)))
        .filter(
            Jackpot.created_at >= date,
            Jackpot.country.is_(None)
        )
        .scalar()
    )
    global_games = sum([global_jackpots + global_games])

    games_prize = (
            db.query(func.sum(func.cast(Game.prize, DECIMAL)))
            .filter(
                Game.kind == GameView.MONETARY,
                Game.created_at >= date,
                Game.country.is_(None)
            )
            .scalar() or 0
    )
    jackpot_prize = (
            db.query(func.sum(Jackpot.amount))
            .filter(
                Game.kind == GameView.MONETARY,
                Jackpot.created_at >= date,
                Jackpot.country.is_(None)
            )
            .scalar() or 0
    )
    global_total_prize_funds = games_prize + jackpot_prize

    for region in regions:
        country = region[0]
        # Total sold tickets = общее количество проданных за период билетов
        total_sold_tickets = db.query(func.count(Ticket.id)).filter(
            Ticket.created_at >= date,
            User.country == country
        ).join(
            User,
            Ticket.user_id == User.id
        ).scalar()

        # active users
        active_users = (
            db.query(User)
            .with_entities(User.id)
            .filter(
                User.last_session >= date,
                User.role == Role.USER.value,
                User.country == country,
            )
        ).all()

        # ARPU = общий доход / количество активных пользователей за период
        # общий доход - сумма средств, полученных за период от продаж билетов
        # активный пользователь - пользователь, у которого в течение периода была хотя бы одна сессия в Bingo
        general_income = (
            db.query(func.sum(BalanceChangeHistory.change_amount))
            .filter(
                BalanceChangeHistory.status == BalanceChangeHistory.Status.SUCCESS,
                BalanceChangeHistory.change_type == "ticket purchase",
                BalanceChangeHistory.created_at >= date,
                User.country == country
            )
            .join(User, BalanceChangeHistory.user_id == User.id)
            .scalar() or 0
        )
        arpu = abs(general_income) / len(active_users) if len(active_users) > 0 else 0

        # ARPPU = общий доход / количество платящих пользователей за период
        # платящий пользователь - пользователь, совершивший в течение периода >=1 покупки билета
        paying_users_count = (
            db.query(func.count(func.distinct(Ticket.user_id)))
            .filter(
                Ticket.created_at >= date,
                User.country == country
            )
            .join(User, Ticket.user_id == User.id)
            .scalar()
        )
        arppu = abs(general_income) / paying_users_count if paying_users_count > 0 else 0

        # GGR = сумма стоимости всех купленных билетов - сумма всех выигрышей за период
        ggr = (
            db.query(func.sum(BalanceChangeHistory.change_amount))
            .filter(
                BalanceChangeHistory.status == BalanceChangeHistory.Status.SUCCESS,
                BalanceChangeHistory.change_type == "won",
                BalanceChangeHistory.created_at >= date,
                User.country == country
            )
            .join(User, BalanceChangeHistory.user_id == User.id)
            .scalar() or 0
        )

        # FTD rate =(Количество пользователей с FTD / количество зарегистрировавшихся пользователей) × 100%
        registered_users_count = (
            db.query(func.count(User.id))
            .filter(
                User.role == Role.USER.value,
                User.country == country
            )
            .scalar()
        )
        first_time_deposit = (
            db.query(func.count(func.distinct(BalanceChangeHistory.user_id)))
            .filter(
                BalanceChangeHistory.change_type == "deposit",
                BalanceChangeHistory.created_at >= date,
                User.country == country
            )
            .join(User, BalanceChangeHistory.user_id == User.id)
            .scalar()
        )
        ftd = (first_time_deposit / registered_users_count) * 100 if registered_users_count > 0 else 0

        # DAU, WAU, MAU = количество активных пользователей за период
        au = len(active_users)

        # Session Time (Avg) = среднее время сессии пользователей
        subquery = (
            logs.query((
                func.extract('epoch', UserActionLog.timestamp) -
                func.lag(
                    func.extract('epoch', UserActionLog.timestamp))
                    .over(partition_by=UserActionLog.user_id, order_by=UserActionLog.timestamp)
                )
                .label("time_diff")
            )
            .filter(
                UserActionLog.timestamp >= date,
                UserActionLog.country == country,
            )
            .subquery()
        )
        avg_session_time = (
            logs.query(func.avg(literal_column("time_diff")))
            .select_from(subquery)
            .scalar() or Decimal(0)
        )

        # LTV(Lifetime Value) = ARPU × Средний срок жизни игрока Session Time (Avg)
        ltv = arpu * float(avg_session_time)

        # ALL_GAMES = количество всех игр
        local_games = (
            db.query(func.count(func.distinct(Game.id)))
            .filter(
                Game.created_at >= date,
                Game.country == country
            )
            .scalar()
        )
        jackpot = (
            db.query(func.count(func.distinct(Jackpot.id)))
            .filter(
                Jackpot.created_at >= date,
                Jackpot.country == country
            )
            .scalar()
        )
        instabingo = (
            db.query(func.count(func.distinct(Ticket.instabingo_id)))
            .filter(
                Ticket.created_at >= date,
                User.country == country
            )
            .join(User, Ticket.user_id == User.id)
            .scalar()
        )
        games = sum([local_games, jackpot, instabingo])

        # all tickets
        tickets = (
            db.query(func.count(Ticket.id))
            .filter(
                Ticket.created_at >= date,
                User.country == country
            )
            .join(User, Ticket.user_id == User.id)
            .scalar()
        )

        # TOTAL_PRIZE_FUNDS
        local_games = (
            db.query(func.sum(func.cast(Game.prize, DECIMAL)))
            .filter(
                Game.kind == GameView.MONETARY,
                Game.created_at >= date,
                Game.country == country
            )
            .scalar() or 0
        )
        jackpot = (
            db.query(func.sum(Jackpot.amount))
            .filter(
                Jackpot.created_at >= date,
                Jackpot.country == country
            )
            .scalar() or 0
        )
        total_prize_funds = local_games + jackpot

        metrics = {
            Metric.MetricType.TOTAL_SOLD_TICKETS: total_sold_tickets,
            Metric.MetricType.ARPU: arpu,
            Metric.MetricType.ARPPU: arppu,
            Metric.MetricType.GGR: ggr,
            Metric.MetricType.FTD: ftd,
            Metric.MetricType.ACTIVE_USERS: au,
            Metric.MetricType.AVG_SESSION_TIME: avg_session_time,
            Metric.MetricType.LTV: ltv,
            Metric.MetricType.TICKETS_SOLD: tickets,
            Metric.MetricType.TOTAL_PRIZE_FUNDS: total_prize_funds,
            Metric.MetricType.ALL_GAMES: games
        }

        obj = []
        for metric_type, value in metrics.items():
            obj.append(
                Metric(
                    name=metric_type,
                    currency_id=currency.id,
                    value=Decimal(value),
                    country=country,
                    created=date + timedelta(hours=1) if update_today else date,
                )
            )
        logs.add_all(obj)
        logs.commit()

    # Globals
    obj = [
        Metric(
            name=Metric.MetricType.ALL_GAMES,
            currency_id=currency.id,
            value=Decimal(global_games),
            country=None,
            created=date + timedelta(hours=1) if update_today else date,
        ),
        Metric(
            name=Metric.MetricType.TOTAL_PRIZE_FUNDS,
            currency_id=currency.id,
            value=Decimal(global_total_prize_funds),
            country=None,
            created=date + timedelta(hours=1) if update_today else date,
        )
    ]
    logs.add_all(obj)
    logs.commit()

    return True


@worker.register
def recalculate_metrics():
    if not settings.debug:
        return

    db = next(get_sync_db())

    user = db.query(User).order_by(User.created_at).with_entities(User.created_at).first()

    if not user:
        return

    now = datetime.now()
    for i in range(0, (now - user.created_at).days + 1):
        date = (user.created_at + timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        for j in range(0, 24):
            date = date + timedelta(hours=j)
            calculate_metrics(date)
