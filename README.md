# 現在対応中の物
* 取得先のjsonが固定もので指定してる問題

# NHK News Live Stream Auto-Recorder

NHKニュースのリアルタイム配信（HLS形式）を監視し、配信が行われている間、自動的に `ffmpeg` を用いて録画（無劣化保存）を行うPythonスクリプトです。

## 概要・仕組み
NHKのライブストリーミングは、CDN（コンテンツ配信ネットワーク）によるトークン認証で保護されています。
本スクリプトは以下の手順を自動化します。

1. **メタデータ取得:** 設定用のJSONファイルにアクセスし、配信のベースURL（`.m3u8`）を取得。
2. **トークン取得:** ブラウザからエクスポートしたCookieを利用し、Token APIにアクセスして一時的なセキュリティトークン（`hdnts`）を取得。
3. **録画実行:** 完全なHLSプレイリストURLを構築し、Cookieとヘッダー情報を付与した上で `ffmpeg` を起動して `.ts` ファイルとして保存。

## 必須環境 (Requirements)
* Python 3.x
* `requests` ライブラリ (`pip install requests`)
* `ffmpeg` (環境変数 PATH に追加されていること)
* Google Chrome 拡張機能等（Netscape形式で `cookies.txt` をエクスポートできるもの）

## 使い方 (Usage)

### 1. Cookieファイルの準備
1. ChromeブラウザでNHKニュースの配信プレイヤーがあるページを開き、動画を再生状態にします。
2. 拡張機能（例: "Get cookies.txt LOCALLY"）を使用し、CookieをNetscape形式でエクスポートします。
3. エクスポートしたファイルをスクリプトと同じフォルダに保存します（例: `cookies.txt`）。

### 2. スクリプトの実行
ターミナル（またはコマンドプロンプト/PowerShell）から、引数 `-C` でCookieファイルを指定して実行します。

```bash
python main.py -C cookies.txt