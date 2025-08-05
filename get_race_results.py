#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
実行日（日本時間）のボートレース払戻結果を取得して JSON 保存
usage:
    python get_today_results.py            # ← 当日を自動判定
    python get_today_results.py 20250805   # ← 任意の日付を指定（YYYYMMDD）
"""
import requests
from bs4 import BeautifulSoup
import time
import json
import re
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))  # 日本標準時

# ──────────────────────────────────────────────
#  払戻取得
# ──────────────────────────────────────────────
def get_race_result(date_str: str, place_code: str, race_num: str):
    url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={race_num}&jcd={place_code}&hd={date_str}"
    try:
        res = requests.get(url, timeout=(5, 30))
        res.raise_for_status()
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")

        result = {"race_num": race_num, "payouts": {}}

        # 優先：is-payout
        section = soup.find("div", class_="table1 is-payout")
        # 代替探索
        if not section:
            for div in soup.find_all("div", class_="table1"):
                if re.search(r"単勝|複勝|2連単|3連複", div.get_text()):
                    section = div
                    break

        if not section:
            print(f"    → 払戻情報が見つかりませんでした: {place_code} {race_num}R")
            return None

        for row in section.find_all("tr"):
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 3:
                continue
            bet_type, combo, payout = cols[0], cols[1], cols[2].replace(",", "")
            if bet_type in ["単勝", "複勝", "2連単", "2連複", "3連単", "3連複", "拡連複"]:
                result["payouts"].setdefault(bet_type, []).append(
                    {"combination": combo, "payout": payout}
                )

        return result if result["payouts"] else None

    except Exception as e:
        print(f"    → エラー取得中: {e}")
        return None


# ──────────────────────────────────────────────
#  開催場・R番号一覧取得
# ──────────────────────────────────────────────
def get_race_list_for_date(date_str: str):
    url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str}"
    resp = requests.get(url, timeout=(5, 30))
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")
    races = []
    for tbody in soup.select("div.table1 tbody"):
        img = tbody.find("img")
        a = tbody.find("a", href=lambda h: h and "raceindex" in h)
        if img and a:
            code = a["href"].split("jcd=")[1].split("&")[0]
            races.append({"date": date_str, "place_code": code, "place_name": img.get("alt", "")})
    return races


def get_races_for_place(date_str: str, place_code: str):
    url = f"https://www.boatrace.jp/owpc/pc/race/raceindex?jcd={place_code}&hd={date_str}"
    resp = requests.get(url, timeout=(5, 30))
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")
    return [td.get_text(strip=True).replace("R", "") for td in soup.select("div.table1 td.is-fBold a")]


# ──────────────────────────────────────────────
#  メイン処理
# ──────────────────────────────────────────────
def main():
    # 1) 日付決定（引数 > 今日[JST] の順）
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    else:
        target_date = datetime.now(JST).strftime("%Y%m%d")

    output_file = f"race_results_{target_date}.json"
    all_results = []

    places = get_race_list_for_date(target_date)
    if not places:
        print(f"❌ {target_date} は開催場なし（または未確定）")
        return

    for place in places:
        print(f"\n🏟️ {place['place_name']}({place['place_code']}) 調査中...")
        nums = get_races_for_place(target_date, place["place_code"])
        if not nums:
            print("    → 未開催スキップ")
            continue

        skip_remaining = False
        for rn in nums:
            if skip_remaining:
                print(f"    🚫 {rn}R スキップ(1R失敗)")
                continue

            print(f"    🔎 {rn}R 結果取得中...")
            res = get_race_result(target_date, place["place_code"], rn)
            if res:
                res.update(place)
                all_results.append(res)
            else:
                if rn == "1":
                    print("    ⚠️ 1R 払戻失敗のため残りスキップ")
                    skip_remaining = True
            time.sleep(1)  # polite crawling

    if all_results:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 保存完了: {output_file}")
    else:
        print("⚠️ 有効な払戻データなし")


if __name__ == "__main__":
    main()
