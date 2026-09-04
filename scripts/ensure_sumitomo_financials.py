"""Keep data/sumitomo_financials.json stocked with quarter rows to fill in.

Sumitomo Electric's quarterly numbers have no free, machine-readable feed:
EDINET's v2 API needs a registered subscription key and Yahoo's
fundamentals endpoints are crumb-gated, so this file is hand-maintained -
the same arrangement data/backlog.json already uses for DART's 수주잔고.

What is automatable is the paperwork: this script appends an empty row for
every fiscal quarter that has closed since the last run (Sumitomo's fiscal
year ends 31 March, so Q1 is Apr-Jun) and never touches a row that already
has values. Fill the nulls in from the company's 決算短信 and the dashboard
picks them up on the next deploy.
"""
import datetime

from common import DATA_DIR, load_json, save_json, sync_to_docs

FINANCIALS_PATH = DATA_DIR / "sumitomo_financials.json"

FIRST_FISCAL_YEAR = 2021  # FY2021 = Apr 2021 - Mar 2022, matching the trade series' start
SEGMENT_KEYS = ("infocom", "electronics", "automotive", "environment_energy", "industrial_materials")


def quarter_bounds(fiscal_year: int, q: int) -> tuple[datetime.date, datetime.date]:
    """FY ends 31 March: Q1 = Apr-Jun of `fiscal_year`, Q4 = Jan-Mar of the next."""
    start_month = 4 + 3 * (q - 1)
    year = fiscal_year + (start_month - 1) // 12
    start_month = (start_month - 1) % 12 + 1
    start = datetime.date(year, start_month, 1)
    end_month = start_month + 2
    end_year = year + (end_month - 1) // 12
    end_month = (end_month - 1) % 12 + 1
    next_month_start = datetime.date(end_year + (end_month // 12), end_month % 12 + 1, 1)
    return start, next_month_start - datetime.timedelta(days=1)


def blank_row(fiscal_year: int, q: int) -> dict:
    start, end = quarter_bounds(fiscal_year, q)
    return {
        "quarter": f"FY{fiscal_year}Q{q}",
        "label": f"{start.strftime('%y.%m')}-{end.strftime('%m')}",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "revenue": None,
        "operating_income": None,
        "net_income": None,
        "segments": {key: {"revenue": None, "operating_income": None} for key in SEGMENT_KEYS},
        "source": "manual",
        "note": "",
    }


def main():
    today = datetime.date.today()
    data = load_json(
        FINANCIALS_PATH,
        {
            "note": "스미토모전기공업(5802.T) 분기 실적. 자동 수집 경로가 없어 직접 입력하는 파일입니다 - 스크립트는 빈 분기 행만 추가하고 값이 채워진 행은 건드리지 않습니다.",
            "source": "manual",
            "currency": "JPY",
            "unit": "million",
            "unit_label": "백만 엔",
            "fiscal_year_end_month": 3,
            "fiscal_note": "3월 결산. FY2025Q1 = 2025년 4~6월.",
            "segment_labels": {
                "infocom": "정보통신",
                "electronics": "일렉트로닉스",
                "automotive": "자동차",
                "environment_energy": "환경에너지",
                "industrial_materials": "산업소재 외",
            },
            "quarters": [],
        },
    )

    existing = {row.get("quarter") for row in data.get("quarters", [])}
    added = []
    for fiscal_year in range(FIRST_FISCAL_YEAR, today.year + 1):
        for q in (1, 2, 3, 4):
            _, end = quarter_bounds(fiscal_year, q)
            if end >= today:
                continue  # quarter hasn't closed yet
            name = f"FY{fiscal_year}Q{q}"
            if name in existing:
                continue
            data.setdefault("quarters", []).append(blank_row(fiscal_year, q))
            added.append(name)

    data["quarters"].sort(key=lambda r: r["period_end"])
    filled = sum(1 for r in data["quarters"] if r.get("revenue") is not None)
    save_json(FINANCIALS_PATH, data)
    sync_to_docs()
    print(f"- 분기 행 {len(data['quarters'])}개 (신규 {len(added)}개: {', '.join(added) or '없음'})")
    print(f"- 매출이 입력된 분기: {filled}개 / {len(data['quarters'])}개")
    if filled == 0:
        print("  NOTE: data/sumitomo_financials.json 의 revenue/operating_income 을 채우면")
        print("        대시보드의 '수출 vs 실적' 차트가 함께 그려집니다.")


if __name__ == "__main__":
    main()
