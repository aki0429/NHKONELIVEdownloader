import requests
import subprocess
import time
import argparse
import os
import re
from datetime import datetime

# ==========================================
# 設定エリア
# ==========================================
START_PAGE_URL = "https://news.web.nhk/newsweb" 
TOKEN_URL = "https://mediatoken.web.nhk/v1/token"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www3.nhk.or.jp/",
    "Origin": "https://www3.nhk.or.jp",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
}

CHECK_INTERVAL = 15

# ==========================================
# 関数: 動的にJSONのURLを取得する（2段階アクセス完全版）
# ==========================================
def get_dynamic_json_url():
    try:
        # 【STEP 1】トップページから LIVE ページのURLを取得
        print(f"【STEP 1】トップページにアクセスします:\n  -> {START_PAGE_URL}")
        res_top = requests.get(START_PAGE_URL, headers=HEADERS, timeout=10)
        res_top.raise_for_status()
        
        # 「/newsweb/live/rt○○」のようなLIVEページへのリンクを探す
        pattern_live = r'href="(/newsweb/live/rt\d+)"'
        match_live = re.search(pattern_live, res_top.text)
        
        if not match_live:
            print("【エラー】トップページから LIVE ページのリンク(/newsweb/live/...)が見つかりませんでした。")
            return None
            
        live_page_path = match_live.group(1)
        live_page_url = f"https://news.web.nhk{live_page_path}"
        
        # 【STEP 2】LIVE ページにアクセスして player_rt...html を探す
        print(f"【STEP 2】LIVE ページを発見！アクセスします:\n  -> {live_page_url}")
        res_live = requests.get(live_page_url, headers=HEADERS, timeout=10)
        res_live.raise_for_status()
        
        # スラッシュのエスケープ(\/)などに惑わされないよう、ファイル名のコア部分だけを強引に抽出
        pattern_player = r'(player_rt[0-9_]+v[0-9]+\.html)'
        match_player = re.search(pattern_player, res_live.text)
        
        if not match_player:
            print("【エラー】LIVE ページ内に 'player_rt...html' が見つかりませんでした。")
            # 念のためデバッグ用に保存
            with open("debug_live_page.html", "w", encoding="utf-8") as f:
                f.write(res_live.text)
            return None
            
        player_html = match_player.group(1)
        print(f"【STEP 3】動画プレイヤーのHTMLを発見しました:\n  -> {player_html}")
        
        # 【STEP 4】 .html を .json に書き換えて最終的なURLを組み立てる
        player_json = player_html.replace(".html", ".json")
        final_json_url = f"https://news.web.nhk/n-data/conf/realtime/movie/{player_json}"
        
        print(f"【STEP 4】最終的なJSON URLが完成しました！:\n  -> {final_json_url}")
        return final_json_url
        
    except Exception as e:
        print(f"【エラー】JSON URLの取得中にエラーが発生しました: {e}")
        return None
# ==========================================
# 関数: cookies.txt (Netscape形式) の読み込み
# ==========================================
def parse_netscape_cookies(filepath):
    cookie_dict = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#HttpOnly_"):
                line = line[10:]
            if line.startswith("#") or not line.strip():
                continue
                
            parts = line.split("\t")
            if len(parts) >= 7:
                domain = parts[0]
                if "nhk" in domain:
                    name = parts[5]
                    value = parts[6].strip()
                    cookie_dict[name] = value

    return "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

# ==========================================
# 処理メイン
# ==========================================
def check_and_download(cookie_string):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配信状況をチェックしています...")

    try:
        json_url = get_dynamic_json_url()
        if not json_url:
            print("→ JSON URLが取得できないため、今回のチェックをスキップします。")
            return False

        print("→ JSON URLから配信データ（ベースURL）を取得します...")
        res_json = requests.get(json_url, headers=HEADERS, timeout=10)
        res_json.raise_for_status()
        data = res_json.json()
        
        base_url = data.get("mediaResource", {}).get("url")
        if not base_url:
            print("→ JSON内に現在アクティブな配信URLが見つかりません。")
            return False
            
        print(f"【URL確認 4】JSONからベースURL(m3u8)を取得しました:\n  -> {base_url}")

        headers_with_cookie = HEADERS.copy()
        headers_with_cookie["Cookie"] = cookie_string

        print("→ トークンAPIにアクセスしてセキュリティカギを取得します...")
        res_token = requests.get(TOKEN_URL, headers=headers_with_cookie, timeout=10)
        res_token.raise_for_status()
        
        token_data = res_token.json()
        token_value = token_data.get("token", "")
        
        full_m3u8_url = f"{base_url}?hdnts={token_value}"
        print(f"【URL確認 5】最終的な録画用URL(トークン付き)が完成しました:\n  -> {full_m3u8_url}")

        output_filename = f"nhk_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"

        cmd = [
            "ffmpeg",
            "-y",
            "-headers", f"Cookie: {cookie_string}\r\nUser-Agent: {HEADERS['User-Agent']}\r\nReferer: {HEADERS['Referer']}\r\n",
            "-i", full_m3u8_url,
            "-c", "copy",
            output_filename
        ]

        print(f"→ ffmpegで録画を開始します: {output_filename}")
        subprocess.run(cmd)
        
        print("→ ffmpegのプロセスが終了しました（配信終了または切断）。")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"【通信エラー】アクセスが拒否されました (404 Not Found など): {e}")
        return False
    except Exception as e:
        print(f"【エラー】一連の処理中に問題が発生しました: {e}")
        return False

# ==========================================
# 実行処理
# ==========================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NHKストリーミング自動録画スクリプト")
    parser.add_argument("-C", "--cookie", required=True, help="Chrome拡張で出力した cookies.txt のパス")
    args = parser.parse_args()

    if not os.path.exists(args.cookie):
        print(f"【エラー】指定されたCookieファイルが見つかりません: {args.cookie}")
        exit(1)

    parsed_cookie_string = parse_netscape_cookies(args.cookie)

    if not parsed_cookie_string:
        print(f"【エラー】{args.cookie} から有効なCookieを抽出できませんでした。")
        exit(1)

    print(f"Cookieファイル ({args.cookie}) を読み込みました。監視を開始します。")

    while True:
        check_and_download(parsed_cookie_string)
        print(f"{CHECK_INTERVAL}秒後に再チェックします...")
        time.sleep(CHECK_INTERVAL)