# Boat Race Results Fetcher

`get_race_results.py` はボートレースの結果データを取得し、日付ごとの JSON に保存するスクリプトです。

## セットアップ

```bash
pip install requests beautifulsoup4
```

## ローカル実行

当日分を取得します。

```bash
python get_race_results.py
```

過去 3 日分を `results_test` に保存して動作確認します。

```bash
python get_race_results.py --days 3 --end-date 20260322 --output-dir results_test
```

過去 1 年分を取得し、既に存在する JSON は飛ばします。

```bash
python get_race_results.py --days 365 --skip-existing
```

期間を指定して取得することもできます。

```bash
python get_race_results.py --start-date 20240801 --end-date 20250731 --skip-existing
```

## テスト手順

最初は 3 日分程度で確認するのがおすすめです。

```bash
python get_race_results.py --days 3 --end-date 20260322 --output-dir results_test
```

確認ポイント:

- `results_test/` に `race_results_YYYYMMDD.json` が作成される
- JSON に `date`, `place_code`, `place_name`, `race_num`, `payouts` が含まれる
- 同じコマンドを `--skip-existing` 付きで再実行すると既存ファイルをスキップする

## GitHub Actions

`.github/workflows/race_results.yml` で GitHub Actions 実行に対応しています。

- 定期実行: 毎日 JST 23:00 に当日分を取得
- 手動実行: `Actions` から `Boat Race Results` を選び、`Run workflow` を実行

手動実行のおすすめ設定:

- `mode`: `backfill`
- `days`: `3` で試験、問題なければ `365`
- `end_date`: 空欄、または `YYYYMMDD`
- `skip_existing`: `true`

成功すると `results/*.json` がコミットされます。

## 出力先

デフォルトの保存先は `results/` です。ローカル確認時は `--output-dir results_test` のように分けて使うと安全です。
