"""FastAPI-застосунок «Курси валют НБУ з аналітикою Gemini»."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import gemini_client, nbu
from .models import AnalysisRequest, AnalysisResponse, ConvertResponse, HistoryResponse, Rate

STATIC = Path(__file__).parent / "static"
PERIODS = (7, 30, 90, 365)

app = FastAPI(title="Курси валют НБУ з аналітикою Gemini", version="1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "model": gemini_client.MODEL}


@app.get("/api/rates", response_model=list[Rate])
async def rates() -> list[Rate]:
    """Усі офіційні курси НБУ на сьогодні."""
    try:
        return await nbu.get_rates()
    except nbu.NbuError as error:
        raise HTTPException(502, str(error))


async def load_history(code: str, days: int) -> HistoryResponse:
    if days not in PERIODS:
        raise HTTPException(422, "Період має бути 7, 30, 90 або 365 днів.")
    try:
        name, points = await nbu.get_history(code, days)
    except nbu.CurrencyNotFound:
        raise HTTPException(404, f"Валюту «{code.upper()}» не знайдено в курсах НБУ.")
    except nbu.NbuError as error:
        raise HTTPException(502, str(error))
    return HistoryResponse(code=code.upper(), name=name, days=days, points=points,
                           stats=nbu.compute_stats(points))


@app.get("/api/history", response_model=HistoryResponse)
async def history(code: str = Query(min_length=3, max_length=3), days: int = 30) -> HistoryResponse:
    """Курс однієї валюти за період і його статистика."""
    return await load_history(code, days)


@app.get("/api/convert", response_model=ConvertResponse)
async def convert(amount: float = Query(gt=0, le=1e12),
                  source: str = Query(min_length=3, max_length=3),
                  target: str = Query(min_length=3, max_length=3)) -> ConvertResponse:
    """Конвертація за офіційним курсом НБУ через гривню (крос-курс)."""
    source, target = source.upper(), target.upper()
    try:
        source_rate = None if source == "UAH" else await nbu.get_rate(source)
        target_rate = None if target == "UAH" else await nbu.get_rate(target)
    except nbu.CurrencyNotFound as error:
        raise HTTPException(404, f"Валюту «{str(error).upper()}» не знайдено в курсах НБУ.")
    except nbu.NbuError as error:
        raise HTTPException(502, str(error))
    rate = nbu.cross_rate(source_rate, target_rate)
    day = (source_rate or target_rate).date if (source_rate or target_rate) else ""
    return ConvertResponse(amount=amount, source=source, target=target,
                           result=round(amount * rate, 4), rate=round(rate, 6), date=day)


@app.post("/api/analysis", response_model=AnalysisResponse)
async def analysis(request: AnalysisRequest) -> AnalysisResponse:
    """Gemini пояснює динаміку курсу на основі статистики, яку рахує сервер."""
    data = await load_history(request.code, request.days)
    try:
        result, model = await gemini_client.generate_analysis(
            data.code, data.name, data.days, data.points, data.stats)
    except gemini_client.GeminiError as error:
        raise HTTPException(502, str(error))
    return AnalysisResponse(**result.model_dump(), code=data.code, days=data.days,
                            stats=data.stats, model=model)
