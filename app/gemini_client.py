"""Аналітика динаміки курсу через Google Gemini API зі structured output (JSON-схема)."""

import asyncio
import logging
import os

from google import genai
from google.genai import errors
from pydantic import ValidationError

from .models import GeminiAnalysis, HistoryPoint, Stats

# Основна модель і запасні: якщо одна перевантажена (503) або недоступна, пробуємо наступну.
MODELS = [m.strip() for m in os.getenv(
    "GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.5-flash,gemini-2.5-flash").split(",") if m.strip()]
MODEL = MODELS[0]
ATTEMPTS_PER_MODEL = 2
RETRY_CODES = {429, 500, 502, 503, 504}   # тимчасові збої: повторюємо
SKIP_CODES = {404}                        # модель недоступна: одразу до наступної

log = logging.getLogger("nbu-rates")


class GeminiError(Exception):
    pass


def sample_points(points: list[HistoryPoint], limit: int = 40) -> list[HistoryPoint]:
    """Для довгих періодів беремо рівномірну вибірку точок, щоб промпт був коротким."""
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(i * step)] for i in range(limit)]


def build_prompt(code: str, name: str, days: int, points: list[HistoryPoint], stats: Stats) -> str:
    series = "; ".join(f"{p.date}: {p.rate:.4f}" for p in sample_points(points))
    return (
        "Ти — фінансовий аналітик, який пояснює дані простою українською мовою.\n"
        f"Валюта: {code} ({name}). Офіційний курс НБУ, гривень за 1 {code}, за останні {days} днів.\n"
        f"Статистика (вже розрахована, не перераховуй): на початку {stats.first:.4f}, наприкінці {stats.last:.4f}, "
        f"зміна {stats.change:+.4f} грн ({stats.change_percent:+.2f} %), "
        f"мінімум {stats.minimum:.4f} ({stats.minimum_date}), максимум {stats.maximum:.4f} ({stats.maximum_date}), "
        f"середнє {stats.average:.4f}, волатильність денних змін {stats.volatility_percent:.3f} %.\n"
        f"Ряд курсів: {series}.\n"
        "Вимоги:\n"
        "- спирайся лише на ці дані, не вигадуй новин і причин, яких тут немає;\n"
        "- trend: «зростання», якщо гривня подешевшала щодо валюти (курс виріс), «падіння», якщо курс знизився, "
        "«стабільно», якщо зміна менша за 0,5 %;\n"
        "- не давай порад купувати чи продавати валюту і не прогнозуй курс."
    )


async def generate_analysis(code: str, name: str, days: int, points: list[HistoryPoint],
                            stats: Stats) -> tuple[GeminiAnalysis, str]:
    """Повертає аналітику й назву моделі, яка її склала."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("Не задано змінну середовища GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(code, name, days, points, stats)
    config = {
        "response_mime_type": "application/json",
        "response_json_schema": GeminiAnalysis.model_json_schema(),
        "temperature": 0.3,
    }

    for model in MODELS:
        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                response = await client.aio.models.generate_content(
                    model=model, contents=prompt, config=config)
            except errors.APIError as error:
                log.warning("Gemini %s, спроба %d: %s %s", model, attempt, error.code, error)
                if error.code in SKIP_CODES:
                    break
                if error.code in RETRY_CODES:
                    if attempt < ATTEMPTS_PER_MODEL:
                        await asyncio.sleep(1.5 * attempt)
                    continue
                if error.code in (400, 401, 403):
                    raise GeminiError("Gemini відхилив запит: перевірте ключ GEMINI_API_KEY.") from error
                raise GeminiError(f"Помилка Gemini API ({error.code}).") from error
            except Exception as error:  # мережа
                log.warning("Gemini %s, спроба %d: %s", model, attempt, error)
                continue

            try:
                return GeminiAnalysis.model_validate_json(response.text or ""), model
            except ValidationError:
                log.warning("Gemini %s повернув JSON не за схемою", model)
                continue

    raise GeminiError("Gemini зараз перевантажений. Спробуйте ще раз за хвилину.")
