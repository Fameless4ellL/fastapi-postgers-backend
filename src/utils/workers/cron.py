from datetime import timedelta, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, literal_column

from src.models import (
    Ticket,
    get_sync_db,
    Metric,
    TicketStatus,
    User,
    Role,
    BalanceChangeHistory,
    get_sync_logs_db,
    UserActionLog,
    Currency
)
from src.utils import worker
from settings import settings


def yesterday():
    return (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def hour_left():
    return (datetime.now() - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


@worker.register
def calculate_metrics(date: Optional[datetime] = None):

    update_today = False
    if date is None:
        update_today = True
        date = hour_left()

    db = next(get_sync_db())
    logs = next(get_sync_logs_db())

    regions = db.query(User.country).distinct(User.country).all()

    for region in regions:
        country = region[0]
        # Total sold tickets = общее количество проданных за период билетов
        total_sold_tickets = db.query(func.count(Ticket.id)).filter(
            Ticket.status == TicketStatus.COMPLETED,
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
            db.query(func.sum(Ticket.amount))
            .filter(
                Ticket.status == TicketStatus.COMPLETED,
                Ticket.created_at >= date,
                User.country == country
            )
            .join(User, Ticket.user_id == User.id)
            .scalar() or 0
        )
        arpu = general_income / len(active_users) if len(active_users) > 0 else 0

        # ARPPU = общий доход / количество платящих пользователей за период
        # платящий пользователь - пользователь, совершивший в течение периода >=1 покупки билета
        paying_users_count = (
            db.query(func.count(func.distinct(Ticket.user_id)))
            .filter(
                Ticket.status == TicketStatus.COMPLETED,
                Ticket.created_at >= date,
                User.country == country
            )
            .join(User, Ticket.user_id == User.id)
            .scalar()
        )
        arppu = general_income / paying_users_count if paying_users_count > 0 else 0

        # GGR = сумма стоимости всех купленных билетов - сумма всех выигрышей за период
        ggr = (
            db.query(func.sum(Ticket.amount))
            .filter(
                Ticket.status == TicketStatus.COMPLETED,
                Ticket.won.is_(True),
                Ticket.created_at >= date,
                User.country == country
            )
            .join(User, Ticket.user_id == User.id)
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

        # LTV = LTV (Lifetime Value) = ARPU × Средний срок жизни игрока Session Time (Avg)
        ltv = arpu * avg_session_time

        metrics = {
            Metric.MetricType.TOTAL_SOLD_TICKETS: total_sold_tickets,
            Metric.MetricType.ARPU: arpu,
            Metric.MetricType.ARPPU: arppu,
            Metric.MetricType.GGR: ggr,
            Metric.MetricType.FTD: ftd,
            Metric.MetricType.DAU: au,
            Metric.MetricType.AVG_SESSION_TIME: avg_session_time,
            Metric.MetricType.LTV: ltv
        }

        currency = db.query(Currency).first() # TODO change, after adding currencies

        for metric_type, value in metrics.items():
            new_stat = Metric(
                name=metric_type,
                currency_id=currency.id,
                value=Decimal(value),
                country=country,
                created=date + timedelta(hours=1) if update_today else date,
            )
            logs.add(new_stat)
        logs.commit()


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
