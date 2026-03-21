#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ボートレースのレース結果を取得して JSON で保存する。

Usage:
    python get_race_results.py
    python get_race_results.py 20250805
    python get_race_results.py 20250801,20250805,20250810
    python get_race_results.py --start-date 20240801 --end-date 20250731
    python get_race_results.py --days 365 --skip-existing
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
BET_TYPES = ["単勝", "複勝", "2連単", "2連複", "3連単", "3連複", "拡連複"]
REQUEST_INTERVAL_SECONDS = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ボートレース結果を取得して保存します。")
    parser.add_argument(
        "dates",
        nargs="?",
        help="取得対象日。YYYYMMDD またはカンマ区切りの複数日付。",
    )
    parser.add_argument("--start-date", help="開始日 (YYYYMMDD)")
    parser.add_argument("--end-date", help="終了日 (YYYYMMDD)。未指定時は本日(JST)")
    parser.add_argument(
        "--days",
        type=int,
        help="終了日からさかのぼって取得する日数。365 を指定すると過去1年分。",
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="JSON の保存先ディレクトリ。デフォルトは results",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="同名ファイルが既に存在する日付はスキップする",
    )
    args = parser.parse_args()

    if args.dates and (args.start_date or args.end_date or args.days):
        parser.error("位置引数の dates は --start-date / --end-date / --days と同時に使えません。")
    if args.start_date and args.days:
        parser.error("--start-date と --days は同時に使えません。")
    if args.days is not None and args.days <= 0:
        parser.error("--days には 1 以上を指定してください。")

    return args


def parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y%m%d").date()


def build_target_dates(args: argparse.Namespace) -> list[str]:
    if args.dates:
        raw_dates = [value.strip() for value in args.dates.split(",") if value.strip()]
        if not raw_dates:
            raise ValueError("dates が空です。")
        return raw_dates

    today = datetime.now(JST).date()
    end_date = parse_date(args.end_date) if args.end_date else today

    if args.start_date:
        start_date = parse_date(args.start_date)
    elif args.days:
        start_date = end_date - timedelta(days=args.days - 1)
    else:
        start_date = today

    if start_date > end_date:
        raise ValueError("開始日は終了日以前にしてください。")

    date_count = (end_date - start_date).days + 1
    return [
        (start_date + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(date_count)
    ]


def build_output_path(output_dir: Path, date_str: str) -> Path:
    return output_dir / f"race_results_{date_str}.json"


def get_race_result(session: requests.Session, date_str: str, place_code: str, race_num: str):
    url = (
        "https://www.boatrace.jp/owpc/pc/race/raceresult"
        f"?rno={race_num}&jcd={place_code}&hd={date_str}"
    )
    try:
        response = session.get(url, timeout=(5, 30))
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")

        result = {"race_num": race_num, "payouts": {}}

        section = soup.find("div", class_="table1 is-payout")
        if not section:
            for div in soup.find_all("div", class_="table1"):
                if re.search(r"単勝|複勝|2連単|2連複|3連単|3連複|拡連複", div.get_text()):
                    section = div
                    break

        if not section:
            print(f"    払戻情報が見つかりませんでした: {place_code} {race_num}R")
            return None

        for row in section.find_all("tr"):
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 3:
                continue

            bet_type, combo, payout = cols[0], cols[1], cols[2].replace(",", "")
            if bet_type in BET_TYPES:
                result["payouts"].setdefault(bet_type, []).append(
                    {"combination": combo, "payout": payout}
                )

        return result if result["payouts"] else None
    except Exception as exc:
        print(f"    レース結果取得中にエラー: {exc}")
        return None


def get_race_list_for_date(session: requests.Session, date_str: str) -> list[dict[str, str]]:
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    response = session.get(url, timeout=(5, 30))
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    races = []
    for tbody in soup.select("div.table1 tbody"):
        img = tbody.find("img")
        anchor = tbody.find("a", href=lambda href: href and "raceindex" in href)
        if img and anchor and "jcd=" in anchor["href"]:
            code = anchor["href"].split("jcd=")[1].split("&")[0]
            races.append(
                {
                    "date": date_str,
                    "place_code": code,
                    "place_name": img.get("alt", ""),
                }
            )

    return races


def get_races_for_place(session: requests.Session, date_str: str, place_code: str) -> list[str]:
    url = f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={place_code}&hd={date_str}"
    response = session.get(url, timeout=(5, 30))
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    return [
        anchor.get_text(strip=True).replace("R", "")
        for anchor in soup.select("div.table1 td.is-fBold a")
    ]


def collect_results_for_date(session: requests.Session, date_str: str) -> list[dict]:
    print(f"\n[{date_str}] の結果取得を開始します...")
    places = get_race_list_for_date(session, date_str)
    if not places:
        print(f"{date_str} は開催がありませんでした。")
        return []

    daily_results = []

    for place in places:
        print(f"\n  {place['place_name']}({place['place_code']}) を取得中...")
        race_numbers = get_races_for_place(session, date_str, place["place_code"])
        if not race_numbers:
            print("    レース一覧を取得できませんでした。")
            continue

        skip_remaining = False
        for race_num in race_numbers:
            if skip_remaining:
                print(f"    {race_num}R はスキップしました (1R 不成立)。")
                continue

            print(f"    {race_num}R を取得中...")
            result = get_race_result(session, date_str, place["place_code"], race_num)
            if result:
                result.update(place)
                daily_results.append(result)
            elif race_num == "1":
                print("    1R の取得に失敗したため、この場の日付は残りをスキップします。")
                skip_remaining = True

            time.sleep(REQUEST_INTERVAL_SECONDS)

    return daily_results


def save_results(output_path: Path, results: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)


def main() -> None:
    args = parse_args()
    target_dates = build_target_dates(args)
    output_dir = Path(args.output_dir)

    print(f"対象日数: {len(target_dates)} 日")
    print(f"保存先: {output_dir.resolve()}")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
    )

    saved_count = 0
    skipped_count = 0

    for date_str in target_dates:
        output_path = build_output_path(output_dir, date_str)
        if args.skip_existing and output_path.exists():
            print(f"\n[{date_str}] は既存ファイルがあるためスキップします: {output_path}")
            skipped_count += 1
            continue

        try:
            results = collect_results_for_date(session, date_str)
        except Exception as exc:
            print(f"\n[{date_str}] の取得中にエラーが発生しました: {exc}")
            continue

        if not results:
            print(f"[{date_str}] は保存対象データがありませんでした。")
            continue

        save_results(output_path, results)
        saved_count += 1
        print(f"[{date_str}] を保存しました: {output_path}")

    print(
        "\n完了:"
        f" 保存 {saved_count} 日,"
        f" 既存スキップ {skipped_count} 日,"
        f" 対象合計 {len(target_dates)} 日"
    )


if __name__ == "__main__":
    main()
