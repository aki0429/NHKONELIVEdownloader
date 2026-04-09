import requests
import subprocess
import time
import argparse
import os
import re
import threading
from datetime import datetime
from dotenv import load_dotenv

# ==========================================
# 環境変数 (.env) の読み込み
# ==========================================
# スクリプトがあるフォルダのパスを取得して、確実に行う
basedir = os.path.dirname(__file__)
env_path = os.path.join(basedir, '.env')

# .envが存在するかチェックしてロード
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
else:
    print(f"【警告】.env ファイルが {env_path} に見つかりません。")

# 値の取得と判定
COOKIE_CHECK_ENABLED = str(os.getenv("COOKIE_CHECK_ENABLED", "true")).strip().lower() == "true"
WEBHOOK_ENABLED = str(os.getenv("WEBHOOK_ENABLED", "false")).strip().lower() == "true"
WEBHOOK_URL = str(os.getenv("WEBHOOK_URL", "")).strip()
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
KEEP_ALIVE_INTERVAL = 600  # トークン空叩きの間隔 (秒) = 10分

notified_expired = False

# ==========================================
# 関数: Cookie失効時の処理
# ==========================================
def handle_cookie_expiration():
    global notified_expired
    if not COOKIE_CHECK_ENABLED:
        return

    msg = "【警告】NHKトークン取得用のCookieが失効しているか、無効になっています！ブラウザから再取得してください。"
    
    print(f"\n{msg}\n")

    if WEBHOOK_ENABLED and WEBHOOK_URL and not notified_expired:
        try:
            payload = {"content": msg, "text": msg}
            res = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            res.raise_for_status()
            print("→ Webhookで失効通知を送信しました。")
            notified_expired = True
        except Exception as e:
            print(f"→ Webhook通知の送信に失敗しました: {e}")

# ==========================================
# 関数: セッション維持用のバックグラウンド処理 (10分に1回叩く)
# ==========================================
def keep_alive_loop(cookie_string):
    while True:
        time.sleep(KEEP_ALIVE_INTERVAL)
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] セッション維持のためトークンAPIを空叩きします...")
        try:
            headers_with_cookie = HEADERS.copy()
            headers_with_cookie["Cookie"] = cookie_string
            res = requests.get(TOKEN_URL, headers=headers_with_cookie, timeout=10)
            res.raise_for_status()
            print("→ セッション維持のアクセスに成功しました。")
            
            # 失効フラグが立っていた場合、成功したなら回復したとみなしてリセット
            global notified_expired
            notified_expired = False 
            
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in [400, 401, 403]:
                handle_cookie_expiration()
            else:
                print(f"→ セッション維持アクセスで通信エラー: {e}")
        except Exception as e:
            print(f"→ セッション維持アクセスでエラー: {e}")

# ==========================================
# 関数: 動的にJSONのURLとページタイトルを取得する
# ==========================================
def get_dynamic_json_url():
    try:
        print(f"【STEP 1】トップページにアクセスします:\n  -> {START_PAGE_URL}")
        res_top = requests.get(START_PAGE_URL, headers=HEADERS, timeout=10)
        res_top.raise_for_status()
        
        pattern_live = r'href="(/newsweb/live/rt\d+)"'
        match_live = re.search(pattern_live, res_top.text)
        
        if not match_live:
            print("【エラー】トップページから LIVE ページのリンク(/newsweb/live/...)が見つかりませんでした。")
            return None, None
            
        live_page_path = match_live.group(1)
        live_page_url = f"https://news.web.nhk{live_page_path}"
        
        print(f"【STEP 2】LIVE ページを発見！アクセスします:\n  -> {live_page_url}")
        res_live = requests.get(live_page_url, headers=HEADERS, timeout=10)
        res_live.raise_for_status()

        page_title = "nhk_live"
        raw_title = ""
        
        match_span = re.search(r'<span class="stmlc48">(.*?)</span>', res_live.text)
        if match_span:
            raw_title = match_span.group(1)
        else:
            match_title = re.search(r'<title>(.*?)</title>', res_live.text)
            if match_title:
                raw_title = match_title.group(1).split('|')[0]
        
        if raw_title:
            raw_title = raw_title.strip()
            sanitized_title = re.sub(r'[\\/:*?"<>|]+', '_', raw_title)
            if sanitized_title:
                page_title = sanitized_title
        
        print(f"【STEP 3】配信タイトルを取得しました:\n  -> {page_title}")
        
        pattern_player = r'(player_rt[0-9_]+v[0-9]+\.html)'
        match_player = re.search(pattern_player, res_live.text)
        
        if not match_player:
            print("【エラー】LIVE ページ内に 'player_rt...html' が見つかりませんでした。")
            return None, None
            
        player_html = match_player.group(1)
        print(f"【STEP 4】動画プレイヤーのHTMLを発見しました:\n  -> {player_html}")
        
        player_json = player_html.replace(".html", ".json")
        final_json_url = f"https://news.web.nhk/n-data/conf/realtime/movie/{player_json}"
        
        print(f"【STEP 5】最終的なJSON URLが完成しました！:\n  -> {final_json_url}")
        
        return final_json_url, page_title
        
    except Exception as e:
        print(f"【エラー】JSON URLの取得中にエラーが発生しました: {e}")
        return None, None

# ==========================================
# 関数: cookies.txt の読み込み
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
    global notified_expired
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配信状況をチェックしています...")

    try:
        json_url, page_title = get_dynamic_json_url()
        
        if not json_url:
            print("→ 配信ページ情報が取得できないため、今回のチェックをスキップします。")
            return False

        print("→ JSON URLから配信データ（ベースURL）を取得します...")
        res_json = requests.get(json_url, headers=HEADERS, timeout=10)
        res_json.raise_for_status()
        data = res_json.json()
        
        base_url = data.get("mediaResource", {}).get("url")
        if not base_url:
            print("→ JSON内に現在アクティブな配信URLが見つかりません。")
            return False
            
        print(f"【URL確認】JSONからベースURL(m3u8)を取得しました:\n  -> {base_url}")

        headers_with_cookie = HEADERS.copy()
        headers_with_cookie["Cookie"] = cookie_string

        print("→ トークンAPIにアクセスしてセキュリティカギを取得します...")
        res_token = requests.get(TOKEN_URL, headers=headers_with_cookie, timeout=10)
        res_token.raise_for_status()
        
        notified_expired = False 
        
        token_data = res_token.json()
        token_value = token_data.get("token", "")
        
        full_m3u8_url = f"{base_url}?hdnts={token_value}"
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"{page_title}_{timestamp}.ts"

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
        if e.response is not None and e.response.status_code in [400, 401, 403]:
            handle_cookie_expiration()
        else:
            print(f"【通信エラー】アクセスが拒否されました: {e}")
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
    print(f"Cookieチェック機能: {'ON' if COOKIE_CHECK_ENABLED else 'OFF'}")
    print(f"Webhook通知機能: {'ON' if WEBHOOK_ENABLED else 'OFF'}")

    # バックグラウンドでセッション維持スレッドを起動 (daemon=True にするとメイン処理終了時に一緒に終了します)
    keep_alive_thread = threading.Thread(target=keep_alive_loop, args=(parsed_cookie_string,), daemon=True)
    keep_alive_thread.start()

    while True:
        check_and_download(parsed_cookie_string)
        print(f"{CHECK_INTERVAL}秒後に再チェックします...")
        time.sleep(CHECK_INTERVAL)