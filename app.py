import os
import re
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 初始化 Flask App
app = Flask(__name__)

# --- 環境變數設定 (保持不變) ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

# 檢查憑證是否已設定
if LINE_CHANNEL_ACCESS_TOKEN is None or LINE_CHANNEL_SECRET is None:
    print("錯誤：請設定 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 環境變數。")
    pass 

# 初始化 LineBotApi 和 WebhookHandler
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 外部 API 函式 (使用 NOAA 純文字 URL，無需 API Key) ---
def get_aviation_weather(icao_code):
    """
    從 NOAA FTP 鏡像服務 (tgftp.nws.noaa.gov) 取得指定 ICAO 代碼的 METAR 和 TAF 純文字資料。
    """
    # **METAR 和 TAF 的穩定純文字 URL 格式**
    METAR_URL = f"https://tgftp.nws.noaa.gov/data/observations/metar/stations/{icao_code}.TXT"
    TAF_URL = f"https://tgftp.nws.noaa.gov/data/forecasts/taf/stations/{icao_code}.TXT"
    
    # 標準 User-Agent 標頭
    headers = {
        "User-Agent": "AviationWeatherBot (Python Requests)" 
    }
    
    metar_data = ""
    taf_data = ""
    
    try:
        # --- 獲取 METAR ---
        metar_response = requests.get(METAR_URL, headers=headers, timeout=10)
        metar_response.raise_for_status() 
        # 報告內容在第二行開始
        metar_lines = metar_response.text.strip().split('\n')
        if len(metar_lines) > 1:
            metar_data = metar_lines[1] 
        
        # --- 獲取 TAF ---
        taf_response = requests.get(TAF_URL, headers=headers, timeout=10)
        taf_response.raise_for_status()
        # 報告內容在第二行開始
        taf_lines = taf_response.text.strip().split('\n')
        if len(taf_lines) > 1:
            taf_data = taf_lines[1]
            
        # 檢查是否都找不到
        if not metar_data and not taf_data:
            return None, f"找不到 {icao_code} 的 METAR/TAF 資料。請確認代碼是否正確。"
            
        return metar_data, taf_data
        
    except requests.exceptions.HTTPError as e:
        # 如果收到 404 (Not Found)，表示該機場沒有資料
        if e.response.status_code == 404:
            return None, f"找不到 {icao_code} 的氣象報告。該 ICAO 代碼可能沒有提供 METAR/TAF 報告。"
        
        print(f"API 請求錯誤: {e}")
        return None, f"連線至氣象 API 時發生錯誤：{e.__class__.__name__}"
    except Exception as e:
        print(f"程式內部錯誤: {e}")
        return None, f"處理氣象資料時發生未預期的錯誤：{e.__class__.__name__}"

# --- Flask 路由設定 (保持不變) ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/secret.")
        abort(400)

    return 'OK'

# --- 訊息事件處理 (保持不變) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text.strip()
    
    # 1. 驗證：檢查輸入是否為 4 個字母 ICAO 代碼
    if not re.fullmatch(r'^[A-Z]{4}$', user_input.upper()):
        reply_text = (
            "⚠️ 格式錯誤！\n"
            "請輸入一個 **4 碼 ICAO 機場代碼**（例如：**RCTP**、**RJAA**、**KLAX**）。"
        )
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    icao_code = user_input.upper()

    # 2. 呼叫 get_aviation_weather 函式
    metar, taf = get_aviation_weather(icao_code)

    # 3. 格式化回覆
    if metar or taf:
        response_lines = [
            f"✈️ **{icao_code}** 航空氣象報告 (Aviation Weather Report)\n"
        ]
        
        # METAR
        response_lines.append("--- 觀測報告 (METAR) ---")
        if metar:
            response_lines.append(metar)
        else:
            response_lines.append(f"❌ 找不到 {icao_code} 的最新 METAR 資料。")
            
        # TAF
        response_lines.append("\n--- 預報 (TAF) ---")
        if taf:
            response_lines.append(taf)
        else:
            response_lines.append(f"❌ 找不到 {icao_code} 的最新 TAF 資料。")
            
        final_reply = "\n".join(response_lines)
    else:
        final_reply = f"🚨 查詢失敗：\n{taf}"
    
    # 回覆訊息
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=final_reply)
    )

# --- 啟動 Flask 伺服器 (保持不變) ---
if __name__ == "__main__":
    port = 5001 
    app.run(host='0.0.0.0', port=port)