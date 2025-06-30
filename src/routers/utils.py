import mimetypes

import pycountry
from fastapi import status, Query, APIRouter
from fastapi.responses import JSONResponse, Response
from src.globals import storage
from src.schemes import Country


settings_router = APIRouter(tags=["v1.public.settings"])


@settings_router.get("/file/games")
async def get_file(path: str):
    response = None
    try:
        response = storage.get_object("games", path)
        data = response.data
        content_type, _ = mimetypes.guess_type(path)

    except Exception:
        return Response(status_code=404, content="Image not found")
    finally:
        if response:
            response.close()
            response.release_conn()

    return Response(
        content=data,
        media_type=content_type or "application/octet-stream"
    )


@settings_router.get(
    "/countries",
    responses={200: {"model": Country}}
)
async def get_countries(
    q: str = Query('', description="Search query")
):
    """
    Получение список стран
    """
    try:
        if q:
            countries = pycountry.countries.search_fuzzy(q)
        else:
            countries = sorted(pycountry.countries, key=lambda x: x.name)
    except LookupError:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=[]
        )

    excluded_alpha_3 = {
        "ATA",
        "GRL",
        "HKG",
        "PRI",
        "TWN",
        "GIB",
        "BMU",
        "FLK",
        "VAT",
        "ESH",
        "PSE",
        "KAZ",
        "RUS",
    }
    data = [{
        "alpha_3": country.alpha_3,
        "name": country.name,
        "flag": country.flag
    }
        for country in countries
        if country.alpha_3 not in excluded_alpha_3
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )
