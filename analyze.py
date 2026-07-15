import csv
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
WINNERS_CSV = BASE_DIR / "data" / "winners.csv"
OUTPUT_DIR = BASE_DIR / "output"
DOCS_DIR = BASE_DIR / "docs"  # GitHub Pages가 main 브랜치의 /docs 폴더를 서빙

ROUND1_DATE = date(2002, 12, 7)  # 로또6/45 1회차 추첨일 (매주 토요일, +7일씩 증가)


def round_to_date(round_no: int) -> date:
    return ROUND1_DATE + timedelta(weeks=round_no - 1)


def load_rows():
    with open(WINNERS_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def city_of(sigungu: str) -> str:
    """고양시 덕양구 -> 고양시 처럼, 구가 딸린 시는 시 단위로 묶는다."""
    parts = sigungu.split()
    if len(parts) >= 2 and parts[0].endswith("시") and parts[1].endswith("구"):
        return parts[0]
    return sigungu


def compute_frequency(rows):
    wins = defaultdict(int)
    stores = defaultdict(set)
    city_wins = defaultdict(lambda: defaultdict(int))
    district_wins = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # [region][city][district]
    for row in rows:
        region, sigungu = row["sido"], row["sigungu"]
        city = city_of(sigungu)
        wins[region] += 1
        stores[region].add(row["ltShpId"])
        city_wins[region][city] += 1
        if city != sigungu:  # "고양시 덕양구"처럼 구가 딸린 경우만 세부 데이터로 기록
            district_wins[region][city][sigungu] += 1

    total = sum(wins.values())
    ranked = sorted(wins.items(), key=lambda x: x[1], reverse=True)

    entries = []
    for i, (region, count) in enumerate(ranked, 1):
        cities = sorted(city_wins[region].items(), key=lambda x: x[1], reverse=True)
        city_entries = []
        for name, c in cities:
            districts = district_wins[region].get(name)
            city_entries.append({
                "name": name,
                "count": c,
                "districts": (
                    [{"name": d, "count": dc} for d, dc in sorted(districts.items(), key=lambda x: x[1], reverse=True)]
                    if districts else None
                ),
            })
        entries.append({
            "rank": i,
            "region": region,
            "count": count,
            "stores": len(stores[region]),
            "pct": count / total * 100,
            "cities": city_entries,
        })
    return entries, total


def compute_intervals(rows):
    rounds_by_region = defaultdict(set)
    for row in rows:
        rounds_by_region[row["sido"]].add(int(row["round"]))

    latest_round = max(int(row["round"]) for row in rows)

    entries = []
    for region, round_set in rounds_by_region.items():
        appearances = sorted(round_set)
        if len(appearances) < 2:
            avg_gap = None
        else:
            gaps = [b - a for a, b in zip(appearances, appearances[1:])]
            avg_gap = sum(gaps) / len(gaps)
        last_round = appearances[-1]
        since_last = latest_round - last_round
        if avg_gap:
            expected_round = round(last_round + avg_gap)
            expected_date = round_to_date(expected_round)
            overdue = expected_round <= latest_round
        else:
            expected_round = None
            expected_date = None
            overdue = False
        entries.append({
            "region": region,
            "appearances": len(appearances),
            "avg_gap": avg_gap,
            "last_round": last_round,
            "since_last": since_last,
            "expected_round": expected_round,
            "expected_date": expected_date,
            "overdue": overdue,
        })

    entries.sort(key=lambda e: (e["since_last"] - (e["avg_gap"] or 0)), reverse=True)
    return entries, latest_round


def render_frequency_text(entries, total):
    lines = [f"{'순위':<4}{'시/도':<6}{'당첨건수':>8}{'점포수':>8}{'비율':>8}   빈도 막대"]
    for e in entries:
        bar = "■" * round(e["pct"])
        lines.append(
            f"{e['rank']:<4}{e['region']:<6}{e['count']:>8}{e['stores']:>8}{e['pct']:>7.1f}%   {bar}"
        )
    lines.append("")
    lines.append(f"총 1등 당첨 건수: {total}건 / {len(entries)}개 시도")
    return "\n".join(lines)


def render_interval_text(entries, latest_round):
    lines = [f"(기준 회차: {latest_round}회 / {round_to_date(latest_round)})", ""]
    lines.append(f"{'시/도':<6}{'등장횟수':>8}{'평균간격':>10}{'마지막등장':>10}{'경과회차':>10}   예상 다음 등장")
    for e in entries:
        avg_gap_str = f"{e['avg_gap']:.1f}회" if e["avg_gap"] else "N/A"
        if e["expected_round"]:
            expect_str = f"{e['expected_round']}회 ({e['expected_date']})"
            if e["overdue"]:
                expect_str += "  <- 이미 지남"
        else:
            expect_str = "데이터 부족(1회만 등장)"
        lines.append(
            f"{e['region']:<6}{e['appearances']:>8}{avg_gap_str:>10}{e['last_round']:>10}{e['since_last']:>10}   {expect_str}"
        )
    lines.append("")
    lines.append("※ 통계적 추정일 뿐, 실제 당첨 결과를 예측하는 것이 아닙니다. 로또 추첨과 판매점 선정은 서로 독립적인 무작위 사건입니다.")
    return "\n".join(lines)


def render_html(freq_entries, total, interval_entries, latest_round, generated_at):
    def city_name_cell(c):
        if not c["districts"]:
            return c["name"]
        district_rows = "\n".join(
            f"<tr><td>{d['name'].removeprefix(c['name'] + ' ')}</td><td>{d['count']}</td></tr>"
            for d in c["districts"]
        )
        return f"""<details class="nested">
          <summary>{c['name']} (구별 보기)</summary>
          <table class="city-table">
            <tr><th>구</th><th>당첨건수</th></tr>
            {district_rows}
          </table>
        </details>"""

    def city_table(cities):
        city_rows = "\n".join(
            f"<tr><td>{city_name_cell(c)}</td><td>{c['count']}</td></tr>" for c in cities
        )
        return f"""<table class="city-table">
          <tr><th>시/군/구</th><th>당첨건수</th></tr>
          {city_rows}
        </table>"""

    freq_rows = "\n".join(
        f"""<tr>
          <td>{e['rank']}</td><td>{e['region']}</td><td>{e['count']}</td><td>{e['stores']}</td>
          <td>{e['pct']:.1f}%</td>
          <td><div class="bar" style="width:{e['pct'] * 3:.0f}px"></div></td>
        </tr>
        <tr class="detail-row">
          <td colspan="6">
            <details>
              <summary>시/군/구별 세부 보기</summary>
              {city_table(e['cities'])}
            </details>
          </td>
        </tr>"""
        for e in freq_entries
    )

    interval_rows = "\n".join(
        f"""<tr class="{'overdue' if e['overdue'] else ''}">
          <td>{e['region']}</td><td>{e['appearances']}</td>
          <td>{f"{e['avg_gap']:.1f}회" if e['avg_gap'] else 'N/A'}</td>
          <td>{e['last_round']}회</td><td>{e['since_last']}회</td>
          <td>{f"{e['expected_round']}회 ({e['expected_date']})" if e['expected_round'] else '데이터 부족'}
              {' <span class="tag">지남</span>' if e['overdue'] else ''}</td>
        </tr>"""
        for e in interval_entries
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>로또 1등 판매점 지역 통계</title>
<style>
  body {{ font-family: -apple-system, "Malgun Gothic", sans-serif; max-width: 800px; margin: 20px auto; padding: 0 16px; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2.5rem; border-bottom: 2px solid #eee; padding-bottom: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 10px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; }}
  th {{ background: #fafafa; }}
  .bar {{ height: 12px; background: #4f7cff; border-radius: 3px; }}
  tr.overdue {{ background: #fff6f0; }}
  .tag {{ background: #ff7043; color: white; font-size: 0.75rem; padding: 2px 6px; border-radius: 10px; }}
  .note {{ color: #888; font-size: 0.85rem; margin-top: 10px; }}
  .meta {{ color: #888; font-size: 0.85rem; }}
  tr.detail-row td {{ border-bottom: 2px solid #eee; padding: 4px 8px 12px; }}
  details summary {{ cursor: pointer; color: #4f7cff; font-size: 0.85rem; }}
  table.city-table {{ margin-top: 8px; font-size: 0.85rem; }}
  table.city-table th, table.city-table td {{ padding: 4px 8px; }}
  details.nested summary {{ font-size: 0.85rem; color: #333; }}
  details.nested table.city-table {{ margin-left: 12px; width: calc(100% - 12px); }}
</style>
</head>
<body>
  <h1>로또6/45 1등 당첨점포 지역 통계</h1>
  <p class="meta">기준 회차: {latest_round}회 ({round_to_date(latest_round)}) · 생성 시각: {generated_at}</p>

  <h2>시/도별 1등 배출 빈도</h2>
  <table>
    <tr><th>순위</th><th>시/도</th><th>당첨건수</th><th>점포수</th><th>비율</th><th></th></tr>
    {freq_rows}
  </table>
  <p class="note">총 {total}건 · 인구/판매점 수가 많은 지역이 당연히 높게 나옵니다.</p>

  <h2>지역별 "다음 등장" 통계</h2>
  <table>
    <tr><th>시/도</th><th>등장횟수</th><th>평균간격</th><th>마지막등장</th><th>경과회차</th><th>다음 예상</th></tr>
    {interval_rows}
  </table>
  <p class="note">※ 통계적 추정일 뿐 실제 당첨 결과를 예측하지 않습니다. 로또 추첨과 판매점 선정은 서로 독립적인 무작위 사건입니다. 재미로만 봐주세요.</p>
</body>
</html>
"""


def save(name: str, text: str, out_dir: Path = OUTPUT_DIR):
    out_dir.mkdir(exist_ok=True)
    (out_dir / name).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    rows = load_rows()

    freq_entries, total = compute_frequency(rows)
    interval_entries, latest_round = compute_intervals(rows)

    freq_text = render_frequency_text(freq_entries, total)
    interval_text = render_interval_text(interval_entries, latest_round)
    print("=== 시/도별 1등 배출 빈도 ===")
    print(freq_text)
    print()
    print("=== 시/도별 간격 통계 & 다음 등장 예상 ===")
    print(interval_text)

    save("region_frequency.txt", freq_text)
    save("region_interval.txt", interval_text)
    save("index.html", render_html(
        freq_entries, total, interval_entries, latest_round,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ), out_dir=DOCS_DIR)
