import dataclasses
from datetime import timedelta, datetime
from typing import Annotated

from fastapi import status, Security, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import get_logs_db, Metric, HiddenMetric
from src.models.user import Role
from src.routers import admin
from src.utils.dependencies import get_admin_token, Token
from src.schemes.admin import DatePicker, Countries
from src.schemes import BadResponse
from src.utils.datastructure import MultiValueStrEnum


@dataclasses.dataclass
class PeriodData:
    trunc: str
    limit: int
    strftime: str


class Period(MultiValueStrEnum):
    DAY = "day", PeriodData(trunc="hour", limit=1, strftime="%I:%M")
    WEEK = "week", PeriodData(trunc="day", limit=7, strftime="%Y-%m-%d")
    MONTH = "month", PeriodData(trunc="day", limit=30, strftime="%Y-%m-%d")
    YEAR = "year", PeriodData(trunc="month", limit=365, strftime="%Y-%m")


@dataclasses.dataclass
class DashboardFilter(DatePicker, Countries):
    period: Period = Period.MONTH


class DashboardMetric(BaseModel):
    FTD: int = 0
    AVG_SESSION_TIME: dict = {}
    LTV: int = 0
    GGR: int = 0
    TOTAL_SOLD_TICKETS: int = 0
    DAU: int = 0
    ARPPU: dict = {}
    ARPU: dict = {}


class Dashboard(BaseModel):
    metrics: DashboardMetric = Field(default_factory=DashboardMetric)


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
    db: Annotated[AsyncSession, Depends(get_logs_db)],
    item: Annotated[DashboardFilter, Depends(DashboardFilter)],
):
    """
    Получение информации о метриках
    """
    stmt = (
        select(
            Metric.name,
            func.date_trunc(item.period.label.trunc, Metric.created).label('period'),
            func.sum(Metric.value).label('total_value')
        )
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
    else:
        stmt = stmt.where(
            Metric.created >= datetime.now() - timedelta(days=item.period.label.limit),
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
    exclude = set(hidden_metrics)

    metrics_dict = DashboardMetric()
    for metric in metrics:
        name, period, value = metric

        metric = getattr(metrics_dict, name.name)

        if isinstance(metric, (int,)):
            metric += float(value)
        else:
            metric[period.strftime(item.period.label.strftime)] = float(value)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "metrics": metrics_dict.model_dump(mode="json", exclude=exclude),
        }
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
    hidden_metric = await db.execute(
        select(HiddenMetric).filter(
            HiddenMetric.user_id == token.id,
            HiddenMetric.metric_name.in_(request.metrics),
        )
    )
    hidden_metric = hidden_metric.scalars().all()

    for metric in hidden_metric:
        if metric.hidden_metric:
            metric.is_hidden = request.is_hidden
        else:
            metric = HiddenMetric(
                user_id=token.id,
                metric_name=request.metric,
                is_hidden=request.is_hidden
            )
        db.add(metric)

    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Metric visibility updated successfully"}
    )
