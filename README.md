# Курси валют НБУ з аналітикою Gemini

Лабораторна робота 2 з дисципліни «Хмарні обчислення», група ТК-42.

Вебсервіс показує офіційні курси гривні НБУ, динаміку валюти за період, конвертер і пояснення динаміки від Gemini.

## Як це працює

```
Браузер ──► FastAPI (Render)
              ├─ GET  /api/rates     → API НБУ: усі курси на сьогодні
              ├─ GET  /api/history   → API НБУ: курс валюти за 7/30/90/365 днів + статистика
              ├─ GET  /api/convert   → конвертація через гривню (крос-курс НБУ)
              └─ POST /api/analysis  → статистика рахується на сервері, Gemini пояснює її (JSON за схемою)
```

| Компонент | Призначення |
|---|---|
| `app/main.py` | FastAPI: сторінка й ендпоінти API |
| `app/nbu.py` | Запити до API НБУ, кеш на 30 хв, статистика, крос-курс |
| `app/gemini_client.py` | Промпт і виклик Gemini (structured output), повтори й запасні моделі |
| `app/models.py` | Pydantic-моделі даних і схеми відповіді Gemini |
| `app/static/` | Сторінка: таблиця курсів, графік (SVG), конвертер, аналітика |
| `tests/` | 19 тестів pytest із підставними відповідями НБУ та Gemini |

Джерела даних НБУ (без ключа):
- курси на сьогодні: `https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json`;
- курс за період: `https://bank.gov.ua/NBU_Exchange/exchange_site?start=yyyymmdd&end=yyyymmdd&valcode=usd&sort=exchangedate&order=asc&json`.

Статистику (зміна, мінімум, максимум, середнє, волатильність) рахує сервер, а Gemini лише пояснює її словами.
Так модель не помиляється в арифметиці. У промпті заборонено давати поради купувати чи продавати валюту.

## Локальний запуск

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="ваш_ключ"      # https://aistudio.google.com/apikey
uvicorn app.main:app --reload
```
Сторінка: http://127.0.0.1:8000, документація API: http://127.0.0.1:8000/docs.

## Тести

```bash
pytest -v
```

## Розгортання на Render

1. New → **Blueprint** → підключити цей репозиторій (налаштування з `render.yaml`).
2. Задати змінну середовища `GEMINI_API_KEY`.
3. Сервіс буде доступний за адресою `https://<назва>.onrender.com`.
