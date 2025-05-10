import dataclasses
from datetime import timedelta, datetime
from typing import Annotated, Union

from fastapi import status, Security, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import get_logs_db, Metric
from models.user import Role
from routers import admin
from routers.utils import get_admin_token
from schemes.admin import DatePicker, Countries
from schemes.base import BadResponse
from utils.datastructure import MultiValueStrEnum


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


class Dashboard(BaseModel):
    metrics: list[dict[Metric.MetricType, Union[dict[datetime, float]], float]]



@admin.get(
    "/dashboard",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
        200: {"model": Dashboard},
    },
)
async def dashboard(
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

    metrics_dict = {}
    for metric in metrics:
        name, period, value = metric

        if name in {
            Metric.MetricType.GGR,
            Metric.MetricType.DAU,
            Metric.MetricType.TOTAL_SOLD_TICKETS,
            Metric.MetricType.LTV,
            Metric.MetricType.FTD,
        }:
            metrics_dict.setdefault(name.name, 0.0)
            metrics_dict[name.name] += float(value)
        else:
            metrics_dict.setdefault(name.name, {})
            metrics_dict[name.name][period.strftime(item.period.label.strftime)] = float(value)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "metrics": metrics_dict
        }
    )
