# 스미토모전기 광부품 수출 모니터

일본 재무성 관세국에 신고된 **광부품 월별 수출**을 스미토모전기(5802.T) **주가**·**분기 실적**과
한 화면에서 비교하는 정적 대시보드입니다. GitHub Actions가 데이터를 갱신하고 GitHub Pages로
배포합니다. 주소는 고정이며 실행할 때마다 그 자리를 덮어씁니다.

```
https://<owner>.github.io/sumitomo-optics/
```

## 처음 한 번만 하면 되는 설정

1. `Settings → Pages → Build and deployment → Source` 를 **GitHub Actions** 로 지정합니다.
2. `Actions → Update dashboard → Run workflow` 로 첫 실행을 겁니다.

발급키는 하나도 필요 없습니다. 이후에는 매일 자동으로 갱신됩니다.

## 동작 방식

```
GitHub Actions (매일 09:00 KST)
  ├─ scripts/fetch_jp_trade_stats.py        일본 광부품 월별 수출 (품목별·목적지별)
  ├─ scripts/fetch_sumitomo_stock.py        5802.T 일별 종가
  ├─ scripts/ensure_sumitomo_financials.py  분기 실적 입력용 빈 행 유지
  ├─ data/*.json 커밋 + docs/data/*.json 동기화
  └─ docs/ 를 GitHub Pages로 배포

GitHub Actions (3시간마다)
  └─ scripts/fetch_sumitomo_stock.py        주가 재시도 (Yahoo IP 제한 회피용)
```

대시보드는 빌드 과정이 없는 순수 정적 HTML/JS(`docs/`)이고, `docs/data/*.json` 을 `fetch()` 로
읽어 [Chart.js](https://www.chartjs.org/)로 그립니다.

## 수집 품목

`data/jp_trade_categories.json` 에 HS 세번으로 정의돼 있습니다. 이 파일을 고치면 품목을
추가·제외할 수 있고, 스크립트가 덮어쓰지 않습니다.

| 품목 | HS | 유의점 |
| --- | --- | --- |
| 광섬유 | 9001.10 | 8544.70에 해당하지 않는 일부 광섬유 케이블 포함 |
| 광섬유 케이블 | 8544.70 | 개별 피복 광섬유를 다발로 만든 케이블 |
| 광배선(광커넥터) | 8536.70 | 광섬유·광케이블용 커넥터. 광배선반·클로저는 별도 세번이 없어 미포함 |
| 광디바이스 | 8541.41 / 8541.49 (구 8541.40) | 감광성 반도체·LED **전체**라 일반 LED까지 포함되는 넓은 바스켓 |
| InP 등 화합물 반도체 기판 | 3818.00 | 전자용 도핑 웨이퍼 전체. InP 단독 세번이 없어 Si·GaAs 웨이퍼도 포함 |

광디바이스와 기판은 광통신과 무관한 물량이 섞이므로 총계·지수 차트에서는 빠지고,
품목별 차트와 목적지 표에만 나옵니다.

## 이 수치는 스미토모전기 한 회사의 수출이 아닙니다

HS 세번 통계는 기업이 아니라 **품목** 단위 집계라 회사별로 나눌 수 없습니다. 여기 실린 값은
**일본 전체**의 해당 품목 수출이며, 스미토모전기가 큰 비중을 차지하는 품목이라는 전제 아래
실적의 선행지표로 보는 용도입니다. 화면 하단에도 같은 취지를 적어 두었습니다.

## 데이터 출처와 한계

**수출** — [UN Comtrade](https://comtradeapi.un.org)의 공개 preview 엔드포인트. 일본 관세국(재무성)
신고자료를 UN이 재배포하는 것이라 원자료는 재무성 무역통계지만, **금액이 엔이 아니라 FOB 미
달러**이고 공표가 **약 3개월 늦습니다**. 재무성 원본(엔화)은 e-Stat에만 있는데 파일 목록이
자바스크립트로 그려져 링크를 긁을 수 없고 API는 appId 발급이 필요해, 키 없이 도는 경로가
없습니다. 엔화·최신월이 필요하면 e-Stat appId를 붙이는 방향으로 바꿀 수 있습니다 — 대시보드는
단위를 데이터 파일에서 읽으므로 수집기만 교체하면 됩니다.

Comtrade preview는 한 번에 한 달치만 주고 요청이 몰리면 429를 돌려주므로,
`fetch_jp_trade_stats.py` 는 실행당 요청 예산(기본 90건) 안에서 **최신 달부터** 채웁니다. 과거
구간이 남으면 다음 실행이 이어받고, 이미 채운 달 중 최근 4개월은 수치 정정이 있어 매번 다시 받습니다.

**주가** — Yahoo Finance 차트 엔드포인트가 1순위이고, **IP 단위 제한**에 걸리면(공용 러너 IP가
자주 걸립니다) 전혀 다른 인프라인 **finance.yahoo.co.jp 히스토리 표**로 자동 전환합니다.
Stooq는 자바스크립트 검증, kabutan은 Human Verification, minkabu는 403이라 쓸 수 없습니다.

히스토리 표는 API가 아니라 HTML이라 열 순서가 보장되지 않는데, **틀린 주가를 그리는 것은 주가를
안 그리는 것보다 나쁘므로** `scripts/jp_stock_history.py` 는 행을 셀 단위로 읽고 OHLC가 반드시
만족해야 하는 조건(저가 ≤ 시가·종가 ≤ 고가)을 검사해, 어긋나면 그 페이지를 통째로 버립니다.
파싱이 깨지면 "그럴듯한 틀린 값"이 아니라 "데이터 없음"으로 드러납니다.

종가는 **조정 종가**를 씁니다. 스미토모전기는 2026-06-29에 4:1 액면분할을 했고, 무수정 종가로
그리면 11,935 → 2,894 로 떨어져 있지도 않은 -76% 폭락처럼 보입니다. 분할인지 폭락인지는
데이터만으로 구분할 수 없으므로 추측해서 고치지 않고, 하루 35% 이상 급변이 남아 있으면 수집
로그에 경고를 남깁니다.

**분기 실적** — 자동 수집 경로가 없습니다. EDINET v2 API는 발급키가 필요하고 Yahoo의 재무
엔드포인트는 crumb 인증으로 막혀 있어 **직접 입력**합니다.

## 분기 실적 입력하기

`scripts/ensure_sumitomo_financials.py` 가 결산이 끝난 분기마다 빈 행을 추가해 둡니다
(3월 결산이라 `FY2025Q1` = 2025년 4~6월). 값이 들어있는 행은 절대 건드리지 않으므로,
결산단신을 보고 `data/sumitomo_financials.json` 의 해당 분기 행을 채우면 됩니다.

```json
{
  "quarter": "FY2025Q1",
  "revenue": 1234567,
  "operating_income": 89012,
  "segments": { "infocom": { "revenue": 234567, "operating_income": 23456 } },
  "source": "manual"
}
```

단위는 파일 상단의 `unit`/`unit_label`(기본 백만 엔)을 따릅니다. 하나도 채워지지 않은 동안에는
"수출·주가·실적" 지수 차트가 매출 선 없이 그려지고, 입력 방법을 안내하는 문구가 함께 나옵니다.

## 차트 규칙

단위가 다른 계열을 좌우 이중축에 겹치지 않습니다. 축을 어떻게 잡느냐에 따라 상관관계가 있어
보이게도 없어 보이게도 만들 수 있기 때문입니다. 대신 **첫 시점을 100으로 지수화**하거나
차트를 나눠 같은 단위끼리만 한 축에 둡니다. 지수 차트는 5년간 약 9배 범위를 담아야 해서
로그 눈금을 씁니다.

## 로컬에서 실행

```bash
pip install -r scripts/requirements.txt
python scripts/fetch_jp_trade_stats.py       # 선택: 실행당 요청 예산을 인자로 전달 가능
python scripts/fetch_sumitomo_stock.py
python scripts/ensure_sumitomo_financials.py
python -m http.server 8000 --directory docs  # http://localhost:8000
```

## 디렉터리 구조

```
data/                  수집 데이터 (git에 커밋됨, 직접 고쳐도 됨)
  jp_trade_categories.json   수집할 품목(HS 세번) 정의 - 설정 파일
  jp_trade_exports.json      월별 수출 (품목별·목적지별)
  sumitomo_stock.json        5802.T 일별 종가
  sumitomo_financials.json   분기 실적 - 직접 입력
docs/                  GitHub Pages 루트 (정적 대시보드)
  index.html / app.js
  data/                  data/*.json 의 배포용 사본 (스크립트가 동기화)
scripts/               수집 스크립트
.github/workflows/     매일 수집 + Pages 배포, 3시간마다 주가 재시도
```
