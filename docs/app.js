// 스미토모전기 광부품 수출 모니터.
//
// GitHub Actions 가 data/*.json 을 갱신하고 docs/data/ 로 동기화하면, 이
// 페이지가 그것을 그대로 읽어 그립니다. 빌드 과정은 없습니다.

async function loadJSON(path, fallback) {
  try {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    if (fallback !== undefined) return fallback;
    throw new Error(`${path}: ${err.message}`);
  }
}

let EXPORTS, STOCK, FINANCIALS;

async function boot() {
  try {
    [EXPORTS, STOCK, FINANCIALS] = await Promise.all([
      loadJSON("data/jp_trade_exports.json"),
      loadJSON("data/sumitomo_stock.json", { daily: [] }),
      loadJSON("data/sumitomo_financials.json", { quarters: [] }),
    ]);
  } catch (err) {
    document.querySelector(".shell").innerHTML =
      `<div class="note"><b>데이터를 불러오지 못했습니다.</b> ${err.message}<br />` +
      `GitHub Actions 워크플로가 한 번 실행되면 <code>docs/data/</code> 가 채워집니다.</div>`;
    return;
  }
  if (!EXPORTS.categories || !Object.keys(EXPORTS.categories).length) {
    document.querySelector(".shell").innerHTML =
      `<div class="note"><b>아직 수집된 수출 데이터가 없습니다.</b> ` +
      `<code>Actions → Update dashboard → Run workflow</code> 로 첫 수집을 실행하세요.</div>`;
    return;
  }
  render();
}

function render() {
  // ---------------------------------------------------------------------------
  // 파생값 계산. 원자료는 월별 금액과 중량뿐이고, 이동평균·증감률·평균단가는
  // 전부 여기서 만듭니다.
  // ---------------------------------------------------------------------------
  const CORE = ["optical_fiber", "optical_fiber_cable", "optical_connector"];
  const SERIES_VARS = ["--s1", "--s2", "--s3", "--s4", "--s5"];
  
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  
  const catIds = Object.keys(EXPORTS.categories);
  const catColor = (id) => css(SERIES_VARS[catIds.indexOf(id) % SERIES_VARS.length]);
  
  const UNIT = EXPORTS.value_unit_label || "USD";
  
  const months = (() => {
    const set = new Set();
    for (const c of Object.values(EXPORTS.categories)) for (const r of c.monthly) set.add(r.month);
    return [...set].sort();
  })();
  
  function align(rows, field) {
    const by = new Map(rows.map((r) => [r.month, r]));
    return months.map((m) => {
      const v = by.get(m)?.[field];
      return v === undefined ? null : v;
    });
  }
  function ratio(now, before) {
    if (now == null || before == null || before === 0) return null;
    return now / before - 1;
  }
  // 구간 안에 빈 달이 하나라도 있으면 평균을 내지 않습니다. 안 채워진 달이
  // 추세선에서 조용히 메워지는 편이 빈 자리보다 나쁩니다.
  function mma(values, window = 3) {
    return values.map((_, i) => {
      if (i < window - 1) return null;
      const slice = values.slice(i - window + 1, i + 1);
      return slice.some((v) => v == null) ? null : slice.reduce((a, b) => a + b, 0) / window;
    });
  }
  function yoy(values) {
    return values.map((v, i) => (i < 12 ? null : ratio(v, values[i - 12])));
  }
  function sum(list) {
    if (!list.length) return months.map(() => null);
    return months.map((_, i) => {
      let total = 0, any = false;
      for (const s of list) { if (s[i] == null) continue; total += s[i]; any = true; }
      return any ? total : null;
    });
  }
  // 기준 시점을 계열마다 따로 잡으면(각자의 첫 값 = 100) 시작일이 다른 계열끼리
  // 비교가 성립하지 않습니다. 모든 계열을 같은 달에 맞추고, 그 이전 구간은
  // 100 아래로 그려지게 둡니다.
  function rebaseAt(values, baseIdx) {
    const base = values[baseIdx];
    if (base == null || base === 0) {
      const fallback = values.find((v) => v != null && v !== 0);
      if (fallback === undefined) return values.map(() => null);
      return values.map((v) => (v == null ? null : (v / fallback) * 100));
    }
    return values.map((v) => (v == null ? null : (v / base) * 100));
  }
  
  const daily = (STOCK.daily || []).slice().sort((a, b) => a.date.localeCompare(b.date));
  // 월말 종가. 일별 시계열을 한 번만 훑으며 각 달의 마지막 거래일을 집습니다.
  const stockMonthly = (() => {
    let i = 0, carried = null;
    return months.map((m) => {
      const bound = `${m.replace("-", "")}31`;
      let price = null;
      while (i < daily.length && daily[i].date <= bound) { price = daily[i].close; i++; }
      if (price != null) carried = price;
      return price ?? carried;
    });
  })();
  
  const cats = {};
  for (const [id, c] of Object.entries(EXPORTS.categories)) {
    const values = align(c.monthly, "value");
    const weights = align(c.monthly, "weight_kg");
    const filled = weights.filter((w) => w != null).length;
    // 중량이 몇 달만 보고된 품목은 평균단가를 그리지 않습니다 - 4개월짜리
    // 단가 선은 없는 추세를 있는 것처럼 보이게 합니다.
    const hasWeight = filled >= 12 && filled >= weights.length * 0.5;
    cats[id] = {
      id, label: c.label, hs: c.hs, caveat: c.caveat,
      values, weights, hasWeight, weightFilled: filled,
      asp: values.map((v, i) => (v == null || !weights[i] ? null : v / weights[i])),
      yoy: yoy(mma(values)),
      color: catColor(id),
      partners: c.partners || {},
    };
  }
  
  const fmt = {
    m: (v, d = 1) => (v == null ? "—" : (v / 1e6).toLocaleString("ko-KR", { maximumFractionDigits: d })),
    pct: (v, d = 1) => (v == null || !isFinite(v) ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toLocaleString("ko-KR", { maximumFractionDigits: d })}%`),
    num: (v, d = 1) => (v == null ? "—" : v.toLocaleString("ko-KR", { maximumFractionDigits: d })),
    month: (m) => `${m.slice(2, 4)}.${m.slice(5, 7)}`,
  };
  const dirClass = (v) => (v == null || !isFinite(v) ? "" : v >= 0 ? "up" : "down");
  
  // ---------------------------------------------------------------------------
  // 차트. 이중 축은 쓰지 않습니다 - 단위가 다르면 지수화하거나 차트를 나눕니다.
  // ---------------------------------------------------------------------------
  const FONT = { family: "'IBM Plex Mono', ui-monospace, monospace", size: 10 };
  
  function makePlot(hostId, datasets, { labels, yFormat, yTitle, legend = true, logScale = false }) {
    const host = document.getElementById(hostId);
    if (!host) return;
    // 차트 라이브러리는 CDN에서 옵니다. 못 불러왔을 때 예외가 위로 튀면 그
    // 아래의 표까지 통째로 안 그려지므로, 차트 하나만 실패하고 나머지는 남깁니다.
    if (typeof Chart === "undefined") {
      host.innerHTML = `<div class="plot-fallback">차트를 불러오지 못했습니다. 아래 표의 수치는 그대로 유효합니다.</div>`;
      return;
    }
    const canvas = document.createElement("canvas");
    host.append(canvas);
    try {
    new Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: legend
            ? {
                position: "bottom",
                labels: {
                  color: css("--ink-2"), boxWidth: 10, boxHeight: 3, usePointStyle: true,
                  pointStyle: "line", padding: 14,
                  font: { family: "'IBM Plex Sans KR', sans-serif", size: 11 },
                },
              }
            : { display: false },
          tooltip: {
            backgroundColor: css("--ink"),
            titleColor: css("--surface"),
            bodyColor: css("--surface"),
            titleFont: { family: "'IBM Plex Mono', monospace", size: 11 },
            bodyFont: { family: "'IBM Plex Sans KR', sans-serif", size: 12 },
            padding: 10,
            borderWidth: 0,
            callbacks: { label: (ctx) => `${ctx.dataset.label}: ${yFormat(ctx.parsed.y)}` },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            border: { color: css("--rule-strong") },
            ticks: { color: css("--ink-3"), font: FONT, maxTicksLimit: 13, autoSkipPadding: 12 },
          },
          y: {
            type: logScale ? "logarithmic" : "linear",
            grid: { color: css("--grid"), drawTicks: false },
            border: { display: false },
            title: yTitle ? { display: true, text: yTitle, color: css("--ink-3"), font: FONT } : undefined,
            ticks: {
              color: css("--ink-3"), font: FONT, padding: 8,
              callback: (v) => (logScale && ![50, 100, 200, 400, 800, 1600].includes(v) ? "" : yFormat(v)),
            },
          },
        },
      },
    });
    } catch (err) {
      host.innerHTML = `<div class="plot-fallback">차트를 그리지 못했습니다: ${err.message}</div>`;
    }
  }
  
  const line = (label, data, color, extra = {}) => ({
    label, data,
    borderColor: color, backgroundColor: color,
    borderWidth: 2, pointRadius: 0, pointHoverRadius: 4,
    tension: 0.18, spanGaps: false, ...extra,
  });
  const bars = (label, data, color, extra = {}) => ({
    type: "bar", label, data,
    backgroundColor: color, borderWidth: 0, borderRadius: 2,
    ...extra,
  });
  
  const labels = months.map(fmt.month);
  const coreIds = CORE.filter((id) => cats[id]);
  const coreTotal = sum(coreIds.map((id) => cats[id].values));
  const coreMma = mma(coreTotal);
  
  // ---- 요약 타일 -------------------------------------------------------------
  const lastIdx = months.length - 1;
  const tiles = document.getElementById("tiles");
  for (const id of catIds) {
    const c = cats[id];
    let i = lastIdx;
    while (i >= 0 && c.values[i] == null) i--;
    if (i < 0) continue;
    const mom = ratio(c.values[i], c.values[i - 1]);
    const y = ratio(c.values[i], c.values[i - 12]);
    const el = document.createElement("div");
    el.className = "tile";
    el.innerHTML =
      `<div class="tile-name"><span class="swatch" style="background:${c.color}"></span>${c.label}</div>` +
      `<div class="tile-hs">HS ${c.hs.join(" · ")}</div>` +
      `<div class="tile-value">${fmt.m(c.values[i])}<span class="unit">백만 ${UNIT}</span></div>` +
      `<div class="tile-deltas">` +
        `<span>MoM <b class="${dirClass(mom)}">${fmt.pct(mom, 0)}</b></span>` +
        `<span>YoY <b class="${dirClass(y)}">${fmt.pct(y, 0)}</b></span>` +
      `</div>` +
      `<div class="tile-foot">${c.hasWeight ? `평균단가 ${fmt.num(c.asp[i], 1)} ${UNIT}/kg` : "중량 미보고 — 단가 산출 불가"}</div>`;
    tiles.append(el);
  }
  if (daily.length) {
    const last = daily[daily.length - 1];
    const before = (days) => {
      const t = new Date(+last.date.slice(0, 4), +last.date.slice(4, 6) - 1, +last.date.slice(6, 8));
      t.setDate(t.getDate() - days);
      const key = `${t.getFullYear()}${String(t.getMonth() + 1).padStart(2, "0")}${String(t.getDate()).padStart(2, "0")}`;
      let found = null;
      for (const r of daily) { if (r.date > key) break; found = r; }
      return found?.close ?? null;
    };
    const el = document.createElement("div");
    el.className = "tile";
    el.innerHTML =
      `<div class="tile-name"><span class="swatch" style="background:${css("--stock")}"></span>스미토모전기</div>` +
      `<div class="tile-hs">5802.T · TSE</div>` +
      `<div class="tile-value">${fmt.num(last.close, 1)}<span class="unit">${STOCK.currency || "JPY"}</span></div>` +
      `<div class="tile-deltas">` +
        `<span>1M <b class="${dirClass(ratio(last.close, before(30)))}">${fmt.pct(ratio(last.close, before(30)), 0)}</b></span>` +
        `<span>1Y <b class="${dirClass(ratio(last.close, before(365)))}">${fmt.pct(ratio(last.close, before(365)), 0)}</b></span>` +
      `</div>` +
      `<div class="tile-foot">${last.date.slice(0, 4)}.${last.date.slice(4, 6)}.${last.date.slice(6, 8)} 종가</div>`;
    tiles.append(el);
  }
  
  // ---- 지수 비교 (수출 · 주가 · 매출) ----------------------------------------
  const quarters = (FINANCIALS.quarters || []).map((q) => {
    const from = q.period_start.slice(0, 7);
    const to = q.period_end.slice(0, 7);
    let total = null;
    months.forEach((m, i) => {
      if (m < from || m > to || coreTotal[i] == null) return;
      total = (total || 0) + coreTotal[i];
    });
    return { ...q, from, to, exportValue: total };
  });
  const revenueMonthly = months.map(() => null);
  for (const q of quarters) {
    if (q.revenue == null) continue;
    months.forEach((m, i) => { if (m >= q.from && m <= q.to) revenueMonthly[i] = q.revenue; });
  }
  // 분기 실적이 비어 있으면 연간 실적(자동 수집)을 쓴 계단선으로 대신합니다.
  const annual = (FINANCIALS.annual || []).slice().sort((a, b) => a.fiscal_year_end.localeCompare(b.fiscal_year_end));
  const UNIT_LABEL = FINANCIALS.unit_label || "백만 엔";
  if (!revenueMonthly.some((v) => v != null) && annual.length) {
    for (const row of annual) {
      // 결산기가 3월이라 "2026-03" 은 2025-04 ~ 2026-03 을 덮습니다.
      const [ey, em] = row.fiscal_year_end.split("-").map(Number);
      const end = `${ey}-${String(em).padStart(2, "0")}`;
      const startYear = em === 12 ? ey : ey - 1;
      const start = `${startYear}-${String((em % 12) + 1).padStart(2, "0")}`;
      months.forEach((m, i) => { if (m >= start && m <= end) revenueMonthly[i] = row.revenue; });
    }
  }
  const hasRevenue = revenueMonthly.some((v) => v != null);
  const hasPrice = stockMonthly.some((v) => v != null);
  
  // 세 계열이 모두 값을 갖는 가장 이른 달을 공통 기준으로 씁니다 - 실적이
  // 가장 늦게 시작하므로 보통 그 시작월이 됩니다.
  const baseIdx = (() => {
    for (let i = 0; i < months.length; i++) {
      if (coreMma[i] == null) continue;
      if (hasPrice && stockMonthly[i] == null) continue;
      if (hasRevenue && revenueMonthly[i] == null) continue;
      return i;
    }
    return months.findIndex((_, i) => coreMma[i] != null);
  })();
  const baseMonth = months[baseIdx] || months[0];
  
  const indexDatasets = [line("수출 (광통신 3품목, 3M평균)", rebaseAt(coreMma, baseIdx), css("--s1"))];
  if (hasPrice) indexDatasets.push(line("주가 5802.T", rebaseAt(stockMonthly, baseIdx), css("--stock")));
  if (hasRevenue) {
    const quarterly = quarters.some((q) => q.revenue != null);
    indexDatasets.push(line(quarterly ? "매출 (분기)" : "매출 (연간)", rebaseAt(revenueMonthly, baseIdx), css("--result"), { stepped: true, borderDash: [4, 3] }));
  }
  
  document.getElementById("index-title").textContent =
    `${baseMonth.replace("-", "년 ")}월 = 100`;
  document.getElementById("index-sub").textContent =
    "광섬유 · 광섬유 케이블 · 광배선 합계" +
    (hasPrice ? "" : " · 주가 계열은 아직 수집 전이라 표시되지 않습니다");
  makePlot("plot-index", indexDatasets, {
    labels,
    yFormat: (v) => fmt.num(v, 0),
    yTitle: "지수 (로그 눈금)",
    logScale: true,
  });
  
  makePlot("plot-core", [
    bars(`월 수출액 (백만 ${UNIT})`, coreTotal.map((v) => (v == null ? null : v / 1e6)), css("--s1") + "40"),
    line("3개월 이동평균", coreMma.map((v) => (v == null ? null : v / 1e6)), css("--s1")),
  ], { labels, yFormat: (v) => fmt.num(v, 0), yTitle: `백만 ${UNIT}` });
  
  document.getElementById("price-sub").textContent = hasPrice
    ? `월말 종가 · ${STOCK.currency || "JPY"} · ${STOCK.provider === "yahoo_jp" ? "Yahoo Japan, 무수정 종가" : "Yahoo Finance, 액면분할 반영 종가"}`
    : "아직 수집 전";
  if (hasPrice) {
    makePlot("plot-price", [line("월말 종가", stockMonthly, css("--stock"))], {
      labels, yFormat: (v) => fmt.num(v, 0), yTitle: STOCK.currency || "JPY", legend: false,
    });
  } else {
    document.getElementById("plot-price").innerHTML =
      `<div style="height:100%;display:flex;align-items:center;justify-content:center;color:var(--ink-3);font-size:12.5px;text-align:center;padding:0 24px">` +
      `주가 계열이 아직 채워지지 않았습니다.<br />수집 워크플로가 한 번 성공하면 10년치가 한꺼번에 들어옵니다.</div>`;
  }
  
  const qLabels = quarters.map((q) => q.label || q.quarter);
  const qDatasets = [bars(`수출 합계 (백만 ${UNIT})`, quarters.map((q) => (q.exportValue == null ? null : q.exportValue / 1e6)), css("--s1") + "99")];
  document.getElementById("quarter-sub").textContent =
    "결산기가 3월이라 FY2025Q1 은 2025년 4~6월" + (hasRevenue ? " · 매출은 별도 지수 차트에서 비교" : "");
  makePlot("plot-quarter", qDatasets, { labels: qLabels, yFormat: (v) => fmt.num(v, 0), yTitle: `백만 ${UNIT}`, legend: false });
  
  // 매출과 영업이익은 단위가 같으므로 한 축에 둡니다. 회사예상은 실적과
  // 섞이지 않게 별도 계열(점선 테두리)로 표시합니다.
  const forecast = FINANCIALS.annual_forecast || null;
  const annualAll = forecast ? [...annual, forecast] : annual;
  if (annualAll.length) {
    document.getElementById("annual-sub").textContent =
      `${UNIT_LABEL} · ${FINANCIALS.annual_source || ""}` + (forecast ? " · 마지막 연도는 회사예상" : "");
    makePlot("plot-annual", [
      bars("매출", annualAll.map((r) => (r.forecast ? null : r.revenue)), css("--s1") + "99", { stack: "a" }),
      bars("매출 (회사예상)", annualAll.map((r) => (r.forecast ? r.revenue : null)), css("--s1") + "44", { stack: "a" }),
      bars("영업이익", annualAll.map((r) => (r.forecast ? null : r.operating_income)), css("--s2") + "cc", { stack: "b" }),
      bars("영업이익 (회사예상)", annualAll.map((r) => (r.forecast ? r.operating_income : null)), css("--s2") + "55", { stack: "b" }),
    ], {
      labels: annualAll.map((r) => r.label),
      yFormat: (v) => fmt.num(v / 1000, 0) + "십억",
      yTitle: UNIT_LABEL,
    });
  
    const pct1 = (a, b) => (a == null || !b ? "—" : fmt.pct(a / b - 1, 0));
    const rows = annualAll.map((r, i) => {
      const prev = i > 0 ? annualAll[i - 1] : null;
      const margin = r.operating_income && r.revenue ? r.operating_income / r.revenue : null;
      return `<tr><td>${r.label}${r.forecast ? " <span class=\"tile-hs\">회사예상</span>" : ""}</td>` +
        `<td>${fmt.num(r.revenue / 1000, 0)}</td>` +
        `<td class="${dirClass(prev && r.revenue / prev.revenue - 1)}">${pct1(r.revenue, prev && prev.revenue)}</td>` +
        `<td>${r.operating_income == null ? "—" : fmt.num(r.operating_income / 1000, 0)}</td>` +
        `<td class="${dirClass(prev && prev.operating_income && r.operating_income / prev.operating_income - 1)}">${pct1(r.operating_income, prev && prev.operating_income)}</td>` +
        `<td>${margin == null ? "—" : (margin * 100).toFixed(1) + "%"}</td></tr>`;
    }).join("");
    document.getElementById("annual-table").innerHTML =
      `<table><caption>연간 실적 <span class="tile-hs">십억 엔 · 3월 결산</span></caption>` +
      `<thead><tr><th>결산기</th><th>매출</th><th>YoY</th><th>영업이익</th><th>YoY</th><th>영업이익률</th></tr></thead>` +
      `<tbody>${rows}</tbody></table>`;
  } else {
    document.getElementById("plot-annual").innerHTML =
      `<div class="plot-fallback">연간 실적을 아직 수집하지 못했습니다.</div>`;
  }
  
  const hasQuarterly = quarters.some((q) => q.revenue != null);
  document.getElementById("financials-note").innerHTML = hasQuarterly
    ? `<b>분기 실적</b>은 직접 입력한 값이고, 연간 실적은 자동 수집분입니다.`
    : `<b>실적은 연간만 자동으로 들어옵니다.</b> 분기 수치는 무료로 열려 있는 기계 판독용 경로가 없습니다 — ` +
      `EDINET v2 API는 발급키가 필요하고, Yahoo의 재무 엔드포인트는 차단돼 있으며, Yahoo Japan 業績 페이지는 연간 행만 제공합니다. ` +
      `분기 단위로 보시려면 <code>data/sumitomo_financials.json</code> 의 분기 행에 <code>revenue</code>·<code>operating_income</code> 을 ` +
      `결산단신에서 옮겨 적으면 됩니다. 채우는 즉시 위 지수 차트의 매출선이 연간 계단에서 분기 계단으로 바뀝니다.`;
  
  // ---- 품목별 ----------------------------------------------------------------
  const legendHost = document.getElementById("cat-legend");
  for (const id of catIds) {
    const c = cats[id];
    const s = document.createElement("span");
    s.innerHTML = `<i style="background:${c.color}"></i>${c.label}`;
    legendHost.append(s);
  }
  
  makePlot("plot-value", catIds.map((id) => line(cats[id].label, mma(cats[id].values).map((v) => (v == null ? null : v / 1e6)), cats[id].color)), {
    labels, yFormat: (v) => fmt.num(v, 0), yTitle: `백만 ${UNIT}`, legend: false,
  });
  makePlot("plot-yoy", catIds.map((id) => line(cats[id].label, cats[id].yoy.map((v) => (v == null ? null : v * 100)), cats[id].color)), {
    labels, yFormat: (v) => `${fmt.num(v, 0)}%`, yTitle: "YoY", legend: false,
  });
  
  const aspIds = catIds.filter((id) => cats[id].hasWeight);
  const noWeight = catIds.filter((id) => !cats[id].hasWeight).map((id) => cats[id].label);
  document.getElementById("asp-sub").textContent =
    `${UNIT}/kg · 3개월 이동평균` +
    (noWeight.length ? ` · ${noWeight.join(", ")} 는 원자료에 중량이 거의 보고되지 않아 제외` : "");
  makePlot("plot-asp", aspIds.map((id) => line(cats[id].label, mma(cats[id].asp), cats[id].color)), {
    labels, yFormat: (v) => fmt.num(v, 0), yTitle: `${UNIT}/kg`,
  });
  
  // ---- 목적지 표 --------------------------------------------------------------
  const destHost = document.getElementById("dest-section");
  const last12 = new Set(months.slice(-12));
  for (const id of catIds) {
    const c = cats[id];
    const entries = Object.entries(c.partners);
    if (!entries.length) continue;
  
    const trailingTotal = months.reduce((acc, m, i) => (last12.has(m) && c.values[i] != null ? acc + c.values[i] : acc), 0);
    const rows = entries.map(([code, info]) => {
      const v = align(info.monthly, "value");
      const w = align(info.monthly, "weight_kg");
      const asp = v.map((x, i) => (x == null || !w[i] ? null : x / w[i]));
      return {
        name: info.name || code,
        trailing: months.reduce((acc, m, i) => (last12.has(m) && v[i] != null ? acc + v[i] : acc), 0),
        valueYoy: ratio(v[lastIdx], v[lastIdx - 12]),
        valueMom: ratio(v[lastIdx], v[lastIdx - 1]),
        volYoy: ratio(w[lastIdx], w[lastIdx - 12]),
        aspYoy: ratio(asp[lastIdx], asp[lastIdx - 12]),
      };
    }).sort((a, b) => b.trailing - a.trailing).slice(0, 8);
  
    const totalRow = {
      valueYoy: ratio(c.values[lastIdx], c.values[lastIdx - 12]),
      valueMom: ratio(c.values[lastIdx], c.values[lastIdx - 1]),
      volYoy: ratio(c.weights[lastIdx], c.weights[lastIdx - 12]),
      aspYoy: ratio(c.asp[lastIdx], c.asp[lastIdx - 12]),
    };
  
    const cell = (v) => `<td class="${dirClass(v)}">${fmt.pct(v, 0)}</td>`;
    const body = rows.map((r) => {
      const share = trailingTotal ? r.trailing / trailingTotal : null;
      return `<tr><td>${r.name}</td>` +
        `<td class="bar-cell">${share == null ? "—" : (share * 100).toFixed(0) + "%"}` +
        `<span class="bar" style="width:${Math.max(0, Math.min(1, share || 0)) * 46}px;background:${c.color}"></span></td>` +
        cell(r.valueYoy) + cell(r.valueMom) + cell(r.volYoy) + cell(r.aspYoy) + `</tr>`;
    }).join("");
  
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    wrap.innerHTML =
      `<table><caption>${c.label} <span class="tile-hs">HS ${c.hs.join(" · ")}</span></caption>` +
      `<thead><tr><th>목적지</th><th>비중 12M</th><th>금액 YoY</th><th>금액 MoM</th><th>물량 YoY</th><th>단가 YoY</th></tr></thead>` +
      `<tbody>${body}<tr><td>전체</td><td>100%</td>${cell(totalRow.valueYoy)}${cell(totalRow.valueMom)}${cell(totalRow.volYoy)}${cell(totalRow.aspYoy)}</tr></tbody></table>`;
    destHost.append(wrap);
  
    if (c.caveat) {
      const note = document.createElement("p");
      note.className = "section-note";
      note.style.marginTop = "-6px";
      note.textContent = c.caveat;
      destHost.append(note);
    }
  }
  
  // ---- 머리말 / 꼬리말 --------------------------------------------------------
  const cov = EXPORTS.coverage || {};
  document.getElementById("coverage").textContent =
    `Japan Customs · ${cov.first_month || "?"} — ${cov.last_month || "?"} · monthly`;
  document.getElementById("meta").innerHTML =
    `<span><b>수출</b> ${cov.first_month} ~ ${cov.last_month} (${months.length}개월)</span>` +
    `<span><b>주가</b> ${daily.length ? `${daily[0].date.slice(0, 4)} ~ ${daily[daily.length - 1].date.slice(0, 4)} · ${daily.length}거래일` : "수집 전"}</span>` +
    `<span><b>실적</b> ${quarters.filter((q) => q.revenue != null).length} / ${quarters.length}분기 입력</span>` +
    `<span><b>갱신</b> ${(EXPORTS.updated_at || "").slice(0, 10)}</span>`;
  document.getElementById("unit-note").innerHTML =
    `<b>금액 단위는 엔이 아니라 FOB 미 달러이고, 공표가 약 3개월 늦습니다.</b> ` +
    `재무성 원본(엔화)은 e-Stat에만 있는데 파일 목록이 자바스크립트로 그려져 링크를 긁을 수 없고 API는 appId 발급이 필요합니다. ` +
    `그래서 재무성 신고자료를 UN이 재배포하는 UN Comtrade를 사용했습니다.`;
  document.getElementById("footer").innerHTML =
    `출처 — 수출: UN Comtrade가 재배포하는 일본 재무성 관세국 신고자료 · ` +
    `주가: ${STOCK.provider === "yahoo_jp" ? "Yahoo Japan" : "Yahoo Finance"} (5802.T) · 분기 실적: 직접 입력.<br />` +
    `<b>이 수치는 스미토모전기 한 회사의 수출이 아닙니다.</b> HS 세번 통계는 기업이 아니라 품목 단위 집계라, ` +
    `여기 실린 값은 일본 전체의 해당 품목 수출입니다. 회사 실적의 선행지표로 보는 용도입니다.<br />` +
    `대만은 UN Comtrade 관례에 따라 "기타 아시아(Other Asia, nes)"로, 미국은 M49 840 대신 확장코드 842로 보고됩니다.`;
}

boot();
