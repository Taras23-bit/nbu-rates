const $ = (id) => document.getElementById(id);
const POPULAR = ["USD", "EUR", "PLN", "GBP", "CHF", "CZK", "CAD"];
let allRates = [];
let days = 30;

function setStatus(text, isError = false) {
  const el = $("status");
  el.hidden = !text;
  el.textContent = text || "";
  el.classList.toggle("error", isError);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

const fmt = (value, digits = 4) =>
  Number(value).toLocaleString("uk-UA", { minimumFractionDigits: digits, maximumFractionDigits: digits });

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(Array.isArray(data.detail) ? "Перевірте введені дані." : data.detail);
  }
  return data;
}

// --- Курси на сьогодні ---
function renderRates(filter = "") {
  const q = filter.trim().toLowerCase();
  const list = q
    ? allRates.filter((r) => r.code.toLowerCase().includes(q) || r.name.toLowerCase().includes(q))
    : [...allRates].sort((a, b) => {
        const ia = POPULAR.indexOf(a.code), ib = POPULAR.indexOf(b.code);
        return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.code.localeCompare(b.code);
      });
  $("rates").innerHTML = list.map((r) =>
    `<tr data-code="${r.code}"><td><b>${r.code}</b></td><td>${escapeHtml(r.name)}</td>` +
    `<td class="num">${fmt(r.rate)}</td></tr>`).join("");
}

function fillSelects() {
  const options = allRates.map((r) => `<option value="${r.code}">${r.code} — ${escapeHtml(r.name)}</option>`).join("");
  $("currency").innerHTML = options;
  $("currency").value = "USD";
  $("from").innerHTML = options + '<option value="UAH">UAH — Українська гривня</option>';
  $("to").innerHTML = '<option value="UAH">UAH — Українська гривня</option>' + options;
  $("from").value = "USD";
  $("to").value = "UAH";
}

// --- Графік ---
function drawChart(points) {
  const W = 1000, H = 300, L = 70, R = 20, T = 20, B = 40;
  const rates = points.map((p) => p.rate);
  let min = Math.min(...rates), max = Math.max(...rates);
  if (min === max) { min -= 0.01; max += 0.01; }
  const pad = (max - min) * 0.1;
  min -= pad; max += pad;
  const x = (i) => L + (W - L - R) * (points.length === 1 ? 0.5 : i / (points.length - 1));
  const y = (v) => T + (H - T - B) * (1 - (v - min) / (max - min));
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.rate).toFixed(1)}`).join(" ");
  const area = `${x(0)},${H - B} ${line} ${x(points.length - 1)},${H - B}`;
  const ticks = [0, 0.5, 1].map((f) => min + (max - min) * f);
  const last = points[points.length - 1];
  $("chart").innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Графік курсу">
      ${ticks.map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e5e9ef"/>
        <text x="${L - 8}" y="${y(v) + 4}" text-anchor="end" font-size="12" fill="#5a6779">${fmt(v, 2)}</text>`).join("")}
      <polygon points="${area}" fill="#1f6f5c" opacity="0.08"/>
      <polyline points="${line}" fill="none" stroke="#1f6f5c" stroke-width="2.5"/>
      <circle cx="${x(points.length - 1)}" cy="${y(last.rate)}" r="4.5" fill="#1f6f5c"/>
      <text x="${L}" y="${H - 12}" font-size="12" fill="#5a6779">${points[0].date}</text>
      <text x="${W - R}" y="${H - 12}" font-size="12" fill="#5a6779" text-anchor="end">${last.date}</text>
    </svg>`;
}

function tile(label, value, sub = "", cls = "") {
  return `<div class="tile"><div class="label">${label}</div><div class="value ${cls}">${value}</div><div class="sub">${sub}</div></div>`;
}

async function loadHistory() {
  const code = $("currency").value;
  $("tiles").innerHTML = "";
  $("chart").innerHTML = '<p class="muted">Завантаження…</p>';
  $("analysis").hidden = true;
  try {
    const data = await api(`/api/history?code=${code}&days=${days}`);
    const s = data.stats;
    const cls = s.change > 0 ? "up" : s.change < 0 ? "down" : "";
    $("tiles").innerHTML =
      tile("Зараз", fmt(s.last), "грн за 1 " + data.code) +
      tile("Зміна", (s.change_percent > 0 ? "+" : "") + fmt(s.change_percent, 2) + " %",
           (s.change > 0 ? "+" : "") + fmt(s.change) + " грн", cls) +
      tile("Мінімум", fmt(s.minimum), s.minimum_date) +
      tile("Максимум", fmt(s.maximum), s.maximum_date) +
      tile("Волатильність", fmt(s.volatility_percent, 3) + " %", "денні зміни");
    drawChart(data.points);
  } catch (error) {
    $("chart").innerHTML = `<p class="status error">${escapeHtml(error.message)}</p>`;
  }
}

// --- Конвертер ---
$("convert").addEventListener("submit", async (event) => {
  event.preventDefault();
  const amount = $("amount").value, from = $("from").value, to = $("to").value;
  try {
    const data = await api(`/api/convert?amount=${amount}&source=${from}&target=${to}`);
    $("convert-result").textContent = `${fmt(data.amount, 2)} ${data.source} = ${fmt(data.result, 2)} ${data.target}`;
    $("convert-rate").textContent = `1 ${data.source} = ${fmt(data.rate, 4)} ${data.target} · курс НБУ на ${data.date}`;
  } catch (error) {
    $("convert-result").textContent = "";
    $("convert-rate").textContent = error.message;
  }
});

// --- Аналітика Gemini ---
$("analyze").addEventListener("click", async () => {
  const button = $("analyze");
  button.disabled = true;
  button.textContent = "Gemini аналізує…";
  try {
    const data = await api("/api/analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: $("currency").value, days }),
    });
    const trend = $("trend");
    trend.textContent = `${data.code} за ${data.days} дн: ${data.trend}`;
    trend.className = "badge" + (data.trend === "зростання" ? " up" : "");
    $("summary").textContent = data.summary;
    $("points").innerHTML = data.key_points.map((p) => `<li>${escapeHtml(p)}</li>`).join("");
    $("explanation").textContent = data.explanation;
    $("disclaimer").textContent = `${data.disclaimer} Модель: ${data.model}.`;
    $("analysis").hidden = false;
  } catch (error) {
    $("summary").textContent = error.message;
    $("points").innerHTML = "";
    $("explanation").textContent = "";
    $("trend").textContent = "Помилка";
    $("disclaimer").textContent = "";
    $("analysis").hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Пояснити динаміку";
  }
});

// --- Події та старт ---
$("search").addEventListener("input", (e) => renderRates(e.target.value));
$("rates").addEventListener("click", (e) => {
  const row = e.target.closest("tr");
  if (!row) return;
  $("currency").value = row.dataset.code;
  loadHistory();
  $("currency").scrollIntoView({ behavior: "smooth", block: "center" });
});
$("currency").addEventListener("change", loadHistory);
$("periods").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  days = Number(b.dataset.days);
  document.querySelectorAll("#periods button").forEach((x) => x.classList.toggle("active", x === b));
  loadHistory();
});

(async () => {
  setStatus("Завантажую курси НБУ…");
  try {
    allRates = await api("/api/rates");
    $("rates-date").textContent = allRates.length ? `станом на ${allRates[0].date}` : "";
    renderRates();
    fillSelects();
    setStatus("");
    loadHistory();
  } catch (error) {
    setStatus(error.message, true);
  }
})();
