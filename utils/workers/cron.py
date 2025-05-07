from datetime import timedelta, datetime
from decimal import Decimal

from sqlalchemy import func, literal_column

from models import (
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
from utils import worker


def yesterday():
    return (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


@worker.register
def calculate_metrics():
    db = next(get_sync_db())
    logs = next(get_sync_logs_db())

    # Total sold tickets = общее количество проданных за период билетов
    total_sold_tickets = db.query(func.count(Ticket.id)).filter(
        Ticket.status == TicketStatus.COMPLETED,
        Ticket.created_at >= yesterday()
    ).scalar()

    # active users
    active_users = (
        db.query(User)
        .with_entities(User.id)
        .filter(User.last_session >= yesterday(), User.role == Role.USER.value)
    ).all()

    # ARPU = общий доход / количество активных пользователей за период
    # общий доход - сумма средств, полученных за период от продаж билетов
    # активный пользователь - пользователь, у которого в течение периода была хотя бы одна сессия в Bingo
    general_income = (
        db.query(func.sum(Ticket.amount))
        .filter(
            Ticket.status == TicketStatus.COMPLETED,
            Ticket.created_at >= yesterday()
        )
        .scalar() or 0
    )
    arpu = general_income / len(active_users) if len(active_users) > 0 else 0

    # ARPPU = общий доход / количество платящих пользователей за период
    # платящий пользователь - пользователь, совершивший в течение периода >=1 покупки билета
    paying_users_count = (
        db.query(func.count(func.distinct(Ticket.user_id)))
        .filter(
            Ticket.status == TicketStatus.COMPLETED,
            Ticket.created_at >= yesterday()
        )
        .scalar()
    )
    arppu = general_income / paying_users_count if paying_users_count > 0 else 0

    # GGR = сумма стоимости всех купленных билетов - сумма всех выигрышей за период
    ggr = (
        db.query(func.sum(Ticket.amount))
        .filter(
            Ticket.status == TicketStatus.COMPLETED,
            Ticket.won.is_(True),
            Ticket.created_at >= yesterday()
        )
        .scalar() or 0
    )

    # FTD rate =(Количество пользователей с FTD / количество зарегистрировавшихся пользователей) × 100%
    registered_users_count = (
        db.query(func.count(User.id))
        .filter(User.role == Role.USER.value)
        .scalar()
    )
    first_time_deposit = (
        db.query(func.count(func.distinct(BalanceChangeHistory.user_id)))
        .filter(
            BalanceChangeHistory.change_type == "deposit",
            BalanceChangeHistory.created_at >= yesterday()
        )
        .scalar()
    )
    ftd = (first_time_deposit / registered_users_count) * 100 if registered_users_count > 0 else 0

    # DAU, WAU, MAU = количество активных пользователей за период
    au = len(active_users)

    # Session Time (Avg) = среднее время сессии пользователей
    subquery = (
        logs.query((
            func.extract('epoch', UserActionLog.timestamp) -
            func.lag(func.extract('epoch', UserActionLog.timestamp)).over(partition_by=UserActionLog.user_id, order_by=UserActionLog.timestamp))
            .label("time_diff")
        )
        .filter(UserActionLog.timestamp >= yesterday())
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

    currency = db.query(Currency).first()

    for metric_type, value in metrics.items():
        new_stat = Metric(
            name=metric_type,
            currency_id=currency.id,
            value=Decimal(value),
            created=datetime.now()
        )
        logs.add(new_stat)
    logs.commit()
