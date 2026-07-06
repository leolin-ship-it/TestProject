"""從 API 匯出 JSON，供 GitHub Pages 風控分析頁上傳使用。"""
import json
import sys
from pathlib import Path

import requests

from api_config import get_api_urls, mask_api_url

BASE_DIR = Path(__file__).resolve().parent.parent


def fetch_all_rows(source_input: str) -> list:
    source_list = [s.strip() for s in source_input.replace(",", " ").split() if s.strip()]
    all_rows = []
    for source in source_list:
        if not source.startswith(("http://", "https://")):
            print(f"⚠️ 跳過非 URL 來源：{source}")
            continue
        print(f"🔄 正在從 API 獲取：{mask_api_url(source)}")
        try:
            resp = requests.get(source, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"❌ 失敗：{e}")
            continue
        rows = data.get("rows", data) if isinstance(data, dict) else data
        if isinstance(rows, list):
            all_rows.extend(rows)
            print(f"   ✅ {len(rows)} 筆")
    return all_rows


def main() -> None:
    source = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else get_api_urls()
    rows = fetch_all_rows(source)
    if not rows:
        print("❌ 未取得任何資料")
        sys.exit(1)

    out_dir = BASE_DIR / "docs" / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    out_path = out_dir / f"export_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已匯出 {len(rows)} 筆至：{out_path}")
    print("💡 請將此 JSON 上傳至 GitHub Pages 分析頁，或在本機開啟 docs/index.html 測試")


if __name__ == "__main__":
    main()
