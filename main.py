import requests
import subprocess
import time
import argparse
import os
from datetime import datetime

# ==========================================
# 設定エリア
# ==========================================
JSON_URL = "https://news.web.nhk/n-data/conf/realtime/movie/player_rt0012666_02_v3.json"
TOKEN_URL = "https://mediatoken.web.nhk/v1/token"


# サーバーに弾かれないよう、ブラウザと完全に同じヘッダーを偽装する
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www3.nhk.or.jp/",
    "Origin": "https://www3.nhk.or.jp", # これが追加されると通るケースが多いです
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
}

CHECK_INTERVAL = 15 # 15秒ごとに取得

# ==========================================
# 関数: cookies.txt (Netscape形式) の読み込み
# ==========================================
def parse_netscape_cookies(filepath):
    """
    Chrome拡張機能等で出力されたNetscape形式のcookie.txtを読み込み、
    "key=value; key2=value2" の文字列に変換します。
    """
    cookie_dict = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            # HttpOnlyのクッキーは先頭に #HttpOnly_ が付くので除去して処理
            if line.startswith("#HttpOnly_"):
                line = line[10:]
            
            # その他のコメント行や空行はスキップ
            if line.startswith("#") or not line.strip():
                continue
                
            parts = line.split("\t")
            # 正しいNetscape形式は7列（ドメイン, フラグ, パス, セキュア, 有効期限, 名前, 値）
            if len(parts) >= 7:
                # ドメインでフィルタリング（NHK関連のみ抽出）
                domain = parts[0]
                if "nhk" in domain:
                    name = parts[5]
                    value = parts[6].strip()
                    cookie_dict[name] = value

    # dict を "key=value; key2=value" の文字列に変換
    cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
    return cookie_string

# ==========================================
# 処理メイン
# ==========================================
def check_and_download(cookie_string):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 配信状況をチェックしています...")

    try:
        # 1. JSONを取得してベースURLを確認
        res_json = requests.get(JSON_URL, headers=HEADERS, timeout=10)
        res_json.raise_for_status()
        data = res_json.json()
        
        base_url = data.get("mediaResource", {}).get("url")
        if not base_url:
            print("現在アクティブな配信URLが見つかりません。")
            return False

        # 2. Token APIを叩いてカギを取得
        headers_with_cookie = HEADERS.copy()
        headers_with_cookie["Cookie"] = cookie_string

        print("ベースURLを発見。セキュリティトークンを取得します...")
        res_token = requests.get(TOKEN_URL, headers=headers_with_cookie, timeout=10)
        res_token.raise_for_status()
        
        # 1. APIのレスポンスをJSONとしてパースして、中身の値だけを取り出す
        token_data = res_token.json()
        token_value = token_data.get("token", "")
        
        # 2. 正しいパラメータ名（?hdnts=）を付けて合体させる
        full_m3u8_url = f"{base_url}?hdnts={token_value}"
        print(f"再生URL生成完了: {full_m3u8_url}")

        # 3. ffmpegを起動してダウンロード
        output_filename = f"nhk_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"

        # ffmpegのコマンド構築
        cmd = [
            "ffmpeg",
            "-y",
            "-headers", f"Cookie: {cookie_string}\r\nUser-Agent: {HEADERS['User-Agent']}\r\nReferer: {HEADERS['Referer']}\r\n",
            "-i", full_m3u8_url,
            "-c", "copy",
            output_filename
        ]

        print(f"ffmpegで録画を開始します: {output_filename}")
        subprocess.run(cmd)
        
        print("ffmpegのプロセスが終了しました（配信終了または切断）。")
        return True

    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return False

# ==========================================
# 実行処理
# ==========================================
if __name__ == "__main__":
    # コマンドライン引数の設定
    parser = argparse.ArgumentParser(description="NHKストリーミング自動録画スクリプト")
    parser.add_argument("-C", "--cookie", required=True, help="Chrome拡張で出力した cookies.txt のパス")
    args = parser.parse_args()

    # Cookieファイルの存在確認とパース
    if not os.path.exists(args.cookie):
        print(f"エラー: 指定されたCookieファイルが見つかりません ({args.cookie})")
        exit(1)

    # Netscape形式のファイルをパースして文字列化
    parsed_cookie_string = parse_netscape_cookies(args.cookie)

    if not parsed_cookie_string:
        print(f"エラー: {args.cookie} からNHKの有効なCookieを抽出できませんでした。")
        exit(1)

    print(f"Cookieファイル ({args.cookie}) を読み込みました。監視を開始します。")

    # 15秒間隔の無限ループ
    while True:
        check_and_download(parsed_cookie_string)
        print(f"{CHECK_INTERVAL}秒後に再チェックします...\n")
        time.sleep(CHECK_INTERVAL)