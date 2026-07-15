import csv
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
WINNERS_CSV = BASE_DIR / "data" / "winners.csv"

BASE_URL = "https://www.dhlottery.co.kr/wnprchsplcsrch"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/home",
}
FIELDS = ["round", "rank", "shpNm", "sido", "sigungu", "addr", "autoManual", "lat", "lot", "ltShpId"]


def new_session() -> requests.Session:
    s = requests.Session()
    s.get(f"{BASE_URL}/home", headers=HEADERS, timeout=15)
    return s


def fetch_round(session: requests.Session, round_no: int):
    """Return (rank1_rows, total) for a round. total==0 means the round has no data yet."""
    r = session.get(
        f"{BASE_URL}/selectLtWnShp.do",
        params={"srchWnShpRnk": "all", "srchLtEpsd": round_no, "srchShpLctn": ""},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json().get("data") or {}
    rows = []
    for item in data.get("list", []):
        if item.get("wnShpRnk") != 1:
            continue
        rows.append({
            "round": round_no,
            "rank": item.get("wnShpRnk"),
            "shpNm": item.get("shpNm"),
            "sido": item.get("region"),
            "sigungu": item.get("tm2ShpLctnAddr"),
            "addr": (item.get("shpAddr") or "").strip(),
            "autoManual": item.get("atmtPsvYnTxt"),
            "lat": item.get("shpLat"),
            "lot": item.get("shpLot"),
            "ltShpId": item.get("ltShpId"),
        })
    return rows, data.get("total", 0)


def load_existing_rounds():
    if not WINNERS_CSV.exists():
        return set()
    with open(WINNERS_CSV, encoding="utf-8-sig") as f:
        return {int(row["round"]) for row in csv.DictReader(f)}


def append_rows(rows):
    WINNERS_CSV.parent.mkdir(exist_ok=True)
    file_exists = WINNERS_CSV.exists()
    with open(WINNERS_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def backfill(start_round: int, end_round: int, delay: float = 0.5):
    existing = load_existing_rounds()
    session = new_session()
    total_new = 0
    for round_no in range(start_round, end_round + 1):
        if round_no in existing:
            continue
        rows, _ = fetch_round(session, round_no)
        if rows:
            append_rows(rows)
            total_new += len(rows)
        print(f"{round_no}회: 1등 {len(rows)}건 수집")
        time.sleep(delay)
    print(f"완료. 신규 저장 {total_new}건")


def update_latest(delay: float = 0.5):
    existing = load_existing_rounds()
    start = (max(existing) + 1) if existing else 1
    session = new_session()
    round_no = start
    total_new = 0
    while True:
        rows, total = fetch_round(session, round_no)
        if total == 0:
            break
        if rows:
            append_rows(rows)
            total_new += len(rows)
        print(f"{round_no}회: 1등 {len(rows)}건 수집")
        round_no += 1
        time.sleep(delay)
    print(f"업데이트 완료. 신규 회차 {round_no - start}개, 신규 저장 {total_new}건")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "update":
        update_latest()
    elif len(sys.argv) >= 3:
        backfill(int(sys.argv[1]), int(sys.argv[2]))
    else:
        print("사용법: python fetch_rounds.py <시작회차> <끝회차>  또는  python fetch_rounds.py update")
