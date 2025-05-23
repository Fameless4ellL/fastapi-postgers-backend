import dataclasses
from datetime import timedelta
from operator import methodcaller
from typing import Annotated, Union, Literal, Optional

from fastapi import status, Security, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pytz.tzinfo import DstTzInfo
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import get_logs_db, Metric, HiddenMetric, get_db, User
from src.models.user import Role
from src.routers import admin
from src.utils.dependencies import get_admin_token, Token, get_timezone
from src.schemes.admin import DatePicker, Countries
from src.schemes import BadResponse
from src.utils.datastructure import MultiValueStrEnum


@dataclasses.dataclass
class PeriodData:
    trunc: str
    limit: int
    strftime: str
    func: str


class Period(MultiValueStrEnum):
    HOUR = "hour", PeriodData(trunc="hour", limit=1, strftime="%H:%M", func="date_trunc")
    DAY = "day", PeriodData(trunc="hour", limit=1, strftime="%H:%M", func="date_trunc")
    WEEK = "week", PeriodData(trunc="day", limit=7, strftime="%Y-%m-%d", func="date_trunc")
    MONTH = "month", PeriodData(trunc="day", limit=30, strftime="%Y-%m-%d", func="date_trunc")
    YEAR = "year", PeriodData(trunc="month", limit=365, strftime="%Y-%m", func="date_trunc")


class Group(MultiValueStrEnum):
    STATS = "stats", [
        Metric.MetricType.FTD,
        Metric.MetricType.AVG_SESSION_TIME,
        Metric.MetricType.LTV,
        Metric.MetricType.GGR,
        Metric.MetricType.TOTAL_SOLD_TICKETS,
        Metric.MetricType.ACTIVE_USERS,
        Metric.MetricType.ARPPU,
        Metric.MetricType.ARPU,
    ]
    LOBBY = "lobby", [
        Metric.MetricType.TOTAL_SOLD_TICKETS,
        Metric.MetricType.ACTIVE_USERS,
        Metric.MetricType.TICKETS_SOLD,
        Metric.MetricType.TOTAL_PRIZE_FUNDS,
    ]


@dataclasses.dataclass
class DashboardFilter(DatePicker, Countries):
    group: Group = Group.STATS
    period: Period = Period.MONTH


class DashboardMetricStats(BaseModel):
    group: Literal["stats"] = Field(default="stats", exclude=True)

    FTD: Optional[float] = 0
    AVG_SESSION_TIME: Optional[dict] = {}
    LTV: Optional[float] = 0
    GGR: Optional[float] = 0
    TOTAL_SOLD_TICKETS: Optional[float] = 0
    ACTIVE_USERS: Optional[float] = 0
    ARPPU: Optional[dict] = {}
    ARPU: Optional[dict] = {}


class DashboardMetricLobby(BaseModel):
    group: Literal["lobby"] = Field(default="lobby", exclude=True)

    TOTAL_SOLD_TICKETS: Optional[float] = 0
    ACTIVE_USERS: Optional[float] = 0
    TICKETS_SOLD: Optional[float] = 0
    TOTAL_PRIZE_FUNDS: Optional[float] = 0


class Dashboard(BaseModel):
    metrics: Union[
        DashboardMetricStats,
        DashboardMetricLobby
    ] = Field(discriminator='group')


class UpdateMetricVisibilityRequest(BaseModel):
    metrics: list[Metric.MetricType]
    is_hidden: bool


@admin.get(
    "/dashboard",
    responses={
        400: {"model": BadResponse},
        200: {"model": Dashboard},
    },
)
async def dashboard(
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]),],
    timezone: Annotated[DstTzInfo, Depends(get_timezone)],
    _db: Annotated[AsyncSession, Depends(get_db)],
    db: Annotated[AsyncSession, Depends(get_logs_db)],
    item: Annotated[DashboardFilter, Depends(DashboardFilter)],
):
    """
    Получение информации о метриках
    """
    fun = methodcaller(item.period.label.func, item.period.label.trunc, Metric.created)
    stmt = (
        select(
            Metric.name,
            fun(func).label('period'),
            func.sum(Metric.value).label('total_value')
        )
        .filter(Metric.name.in_(item.group.label))
        .group_by(Metric.name, 'period')
        .order_by('period')
    )

    if item.countries:
        stmt = stmt.where(Metric.country.in_(item.countries))

    if item.date_from and item.date_to:
        stmt = stmt.where(
            Metric.created >= item.date_from,
            Metric.created <= item.date_to
        )
    elif item.date_from:
        stmt = stmt.where(
            Metric.created >= item.date_from,
        )
    elif item.date_to:
        stmt = stmt.where(
            Metric.created <= item.date_to,
        )
    else:
        if item.period is Period.HOUR:
            stmt = stmt.where(
                Metric.created >= func.now() - timedelta(hours=item.period.label.limit),
            )
        else:
            stmt = stmt.where(
                Metric.created >= func.now() - timedelta(days=item.period.label.limit),
            )

    metrics = await db.execute(stmt)
    metrics = metrics.fetchall()

    # Check if the user has hidden metrics
    stmt = (
        select(HiddenMetric.metric_name)
        .filter(HiddenMetric.user_id == token.id)
        .filter(HiddenMetric.is_hidden.is_(True))
    )
    hidden_metrics = await db.execute(stmt)
    hidden_metrics = hidden_metrics.scalars().all()
    exclude = set(metric.name for metric in hidden_metrics)

    metrics_dict = Dashboard(metrics={"group": item.group.value}).metrics.model_dump()
    metrics_dict["group"] = item.group.value
    for metric in metrics:
        name, period, value = metric

        if name.name in exclude:
            metrics_dict[name.name] = None
            continue

        if isinstance(metrics_dict[name.name], (int, float)):
            metrics_dict[name.name] += float(value)
        else:
            period = timezone.localize(period).strftime(item.period.label.strftime)

            if metrics_dict[name.name].keys() and item.period is Period.HOUR:
                period = next(iter(metrics_dict[name.name].keys()))

            metrics_dict[name.name][period] = float(value)

    if Metric.MetricType.ACTIVE_USERS in item.group.label:
        all_users = select(func.count(User.id))
        all_users = await _db.execute(all_users)
        all_users = all_users.scalar()

        # calc percentage between active users and all users
        if metrics_dict[Metric.MetricType.ACTIVE_USERS.name]:
            active_users: float = metrics_dict[Metric.MetricType.ACTIVE_USERS.name]
            active_users = active_users / all_users * 100
        else:
            active_users = metrics_dict[Metric.MetricType.ACTIVE_USERS.name]

        metrics_dict[Metric.MetricType.ACTIVE_USERS.name] = active_users

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Dashboard(metrics=metrics_dict).model_dump(mode="json", exclude_none=True),
    )


@admin.post(
    "/dashboard/metrics/visibility",
    responses={
        400: {"model": BadResponse},
        200: {"description": "Metric visibility updated successfully"},
    },
)
async def update_metric_visibility(
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
    ])],
    db: Annotated[AsyncSession, Depends(get_logs_db)],
    request: UpdateMetricVisibilityRequest,
):
    """
    Update the visibility of a metric for the current user.
    """
    for metric in request.metrics:
        stmt = (
            select(HiddenMetric)
            .filter(
                HiddenMetric.user_id == token.id,
                HiddenMetric.metric_name == metric,
            )
        )
        db_metric = await db.execute(stmt)
        db_metric = db_metric.scalars().first()

        if db_metric:
            db_metric.is_hidden = request.is_hidden
        else:
            new_hidden_metric = HiddenMetric(
                user_id=token.id,
                metric_name=metric,
                is_hidden=request.is_hidden
            )
            db.add(new_hidden_metric)

    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Metric visibility updated successfully"}
    )
