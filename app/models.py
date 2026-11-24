"""Pydantic-моделі: дані НБУ, статистика, схема відповіді Gemini та відповіді API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Rate(BaseModel):
    code: str           # літерний код валюти, напр. USD
    name: str           # назва українською
    rate: float         # гривень за 1 одиницю валюти
    date: str           # дата курсу ДД.ММ.РРРР


class HistoryPoint(BaseModel):
    date: str
    rate: float


class Stats(BaseModel):
    first: float
    last: float
    change: float               # last - first, грн
    change_percent: float       # у відсотках
    minimum: float
    minimum_date: str
    maximum: float
    maximum_date: str
    average: float
    volatility_percent: float   # стандартне відхилення денних змін, %


class HistoryResponse(BaseModel):
    code: str
    name: str
    days: int
    points: list[HistoryPoint]
    stats: Stats


class ConvertResponse(BaseModel):
    amount: float
    source: str
    target: str
    result: float
    rate: float                 # скільки target за 1 source
    date: str


class AnalysisRequest(BaseModel):
    code: str = Field(min_length=3, max_length=3)
    days: Literal[7, 30, 90, 365] = 30

    @field_validator("code")
    @classmethod
    def upper_code(cls, value: str) -> str:
        return value.strip().upper()


# --- Схема, яку ми вимагаємо від Gemini (structured output) ---

class GeminiAnalysis(BaseModel):
    summary: str = Field(description="2-3 речення: як змінився курс за період, з числами")
    trend: Literal["зростання", "падіння", "стабільно"] = Field(
        description="Загальний напрям курсу гривні до валюти за період")
    key_points: list[str] = Field(description="3-4 короткі спостереження про динаміку з датами й числами")
    explanation: str = Field(description="2-3 речення простими словами, що означає така динаміка для людини")


class AnalysisResponse(GeminiAnalysis):
    code: str
    days: int
    stats: Stats
    model: str
    disclaimer: str = "Аналітика має ознайомчий характер і не є фінансовою порадою."
