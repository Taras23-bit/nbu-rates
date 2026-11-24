"""Тести з підставними відповідями НБУ та Gemini (без мережі)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import gemini_client, main, nbu
from app.models import GeminiAnalysis, HistoryPoint, Rate

RATES = [Rate(code="USD", name="Долар США", rate=41.5, date="24.11.2026"),
         Rate(code="EUR", name="Євро", rate=48.0, date="24.11.2026"),
         Rate(code="PLN", name="Злотий", rate=11.2, date="24.11.2026")]
POINTS = [HistoryPoint(date="20.11.2026", rate=41.0), HistoryPoint(date="21.11.2026", rate=41.4),
          HistoryPoint(date="22.11.2026", rate=40.8), HistoryPoint(date="23.11.2026", rate=41.5)]
ANALYSIS = GeminiAnalysis(summary="Курс зріс на 1,22 %.", trend="зростання",
                          key_points=["Мінімум 22.11", "Максимум 23.11"], explanation="Долар подорожчав.")


@pytest.fixture
def client(monkeypatch):
    async def fake_rates():
        return RATES

    async def fake_history(code, days):
        if code.upper() == "XXX":
            raise nbu.CurrencyNotFound(code)
        return "Долар США", POINTS

    async def fake_analysis(code, name, days, points, stats):
        return ANALYSIS, "test-model"

    monkeypatch.setattr(nbu, "get_rates", fake_rates)
    monkeypatch.setattr(nbu, "get_history", fake_history)
    monkeypatch.setattr(gemini_client, "generate_analysis", fake_analysis)
    return TestClient(main.app)


def test_index_page(client):
    assert "Курси валют НБУ" in client.get("/").text


def test_rates(client):
    data = client.get("/api/rates").json()
    assert [r["code"] for r in data] == ["USD", "EUR", "PLN"]


def test_history_with_stats(client):
    data = client.get("/api/history?code=usd&days=30").json()
    assert data["code"] == "USD" and len(data["points"]) == 4
    assert data["stats"]["minimum"] == 40.8 and data["stats"]["minimum_date"] == "22.11.2026"
    assert data["stats"]["change_percent"] == 1.22


def test_history_unknown_currency(client):
    assert client.get("/api/history?code=XXX&days=30").status_code == 404


@pytest.mark.parametrize("url", ["/api/history?code=USD&days=13", "/api/history?code=US&days=30",
                                 "/api/convert?amount=-5&source=USD&target=UAH"])
def test_invalid_input(client, url):
    assert client.get(url).status_code == 422


def test_convert_cross_rate(client):
    data = client.get("/api/convert?amount=100&source=EUR&target=USD").json()
    assert data["rate"] == round(48.0 / 41.5, 6)
    assert data["result"] == round(100 * 48.0 / 41.5, 4)


def test_convert_to_and_from_uah(client):
    assert client.get("/api/convert?amount=10&source=USD&target=UAH").json()["result"] == 415.0
    assert client.get("/api/convert?amount=415&source=UAH&target=USD").json()["result"] == 10.0


def test_convert_unknown_currency(client):
    assert client.get("/api/convert?amount=1&source=ABC&target=UAH").status_code == 404


def test_analysis(client):
    data = client.post("/api/analysis", json={"code": "usd", "days": 30}).json()
    assert data["trend"] == "зростання" and data["model"] == "test-model"
    assert data["stats"]["last"] == 41.5 and "не є фінансовою порадою" in data["disclaimer"]


def test_analysis_rejects_bad_period(client):
    assert client.post("/api/analysis", json={"code": "USD", "days": 12}).status_code == 422


def test_nbu_error_gives_502(client, monkeypatch):
    async def broken():
        raise nbu.NbuError("Сервіс курсів НБУ тимчасово недоступний.")

    monkeypatch.setattr(nbu, "get_rates", broken)
    response = client.get("/api/rates")
    assert response.status_code == 502 and "НБУ" in response.json()["detail"]


def test_stats_volatility_and_extremes():
    stats = nbu.compute_stats(POINTS)
    assert (stats.maximum, stats.maximum_date) == (41.5, "23.11.2026")
    assert stats.change == 0.5 and stats.volatility_percent > 0


def test_nbu_parsing(monkeypatch):
    async def fake_json(url, params):
        if url == nbu.RATES_URL:
            return [{"r030": 840, "txt": "Долар США", "rate": 41.5, "cc": "USD", "exchangedate": "24.11.2026"}]
        assert params["valcode"] == "usd" and params["order"] == "asc"
        return [{"exchangedate": "23.11.2026", "cc": "USD", "txt": "Долар США", "rate": 41.5,
                 "units": 1, "rate_per_unit": 41.5}]

    monkeypatch.setattr(nbu, "_get_json", fake_json)
    assert asyncio.run(nbu.get_rates())[0].code == "USD"
    name, points = asyncio.run(nbu.get_history("USD", 7))
    assert name == "Долар США" and points[0].rate == 41.5


def test_prompt_has_stats_and_rules():
    prompt = gemini_client.build_prompt("USD", "Долар США", 30, POINTS, nbu.compute_stats(POINTS))
    assert "+1.22 %" in prompt and "не давай порад" in prompt and "22.11.2026" in prompt


def test_sample_points_limits_prompt():
    many = [HistoryPoint(date=str(i), rate=40 + i / 100) for i in range(365)]
    sample = gemini_client.sample_points(many, 40)
    assert len(sample) == 40 and sample[0] == many[0] and sample[-1] == many[-1]


class FakeModels:
    def __init__(self, failures):
        self.failures, self.calls = failures, []

    async def generate_content(self, model, contents, config):
        self.calls.append(model)
        if self.failures.get(model):
            raise gemini_client.errors.APIError(self.failures[model], {"error": {"message": "busy"}})
        return type("R", (), {"text": ANALYSIS.model_dump_json()})()


def run_with(monkeypatch, failures):
    fake = FakeModels(failures)
    client = type("C", (), {"aio": type("A", (), {"models": fake})()})()
    monkeypatch.setattr(gemini_client.genai, "Client", lambda api_key: client)

    async def no_wait(seconds):
        return None

    monkeypatch.setattr(gemini_client.asyncio, "sleep", no_wait)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    stats = nbu.compute_stats(POINTS)
    return fake, asyncio.run(gemini_client.generate_analysis("USD", "Долар", 30, POINTS, stats))


def test_gemini_falls_back_on_503(monkeypatch):
    fake, (analysis, model) = run_with(monkeypatch, {gemini_client.MODELS[0]: 503})
    assert model == gemini_client.MODELS[1] and analysis.trend == "зростання"


def test_gemini_bad_key_not_retried(monkeypatch):
    with pytest.raises(gemini_client.GeminiError, match="GEMINI_API_KEY"):
        run_with(monkeypatch, {m: 403 for m in gemini_client.MODELS})
