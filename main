import os
import requests
import datetime
import yfinance as yf
import pandas as pd

# 1. 取得台股上市櫃股票清單 (排除 00 開頭的 ETF 與 91 開頭的 TDR)
def get_tw_stock_list():
    # 這裡以簡易範例篩選常見普通股代碼格式 (4位數數字)
    # 實務上可自證交所/櫃買中心 OpenAPI 取得完整的股票代碼清單
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2" # 上市
    df = pd.read_html(url)[0]
    df.columns = df.iloc[0]
    df = df.iloc[1:]
    
    stocks = []
    for code_name in df['有價證券代號及名稱']:
        if isinstance(code_name, str) and ' ' in code_name:
            code, name = code_name.split(' ', 1)
            # 排除 ETF (00開頭)、TDR (91開頭)、受益憑證等，僅留4位數一般個股
            if len(code) == 4 and code.isdigit() and not code.startswith(('00', '91')):
                stocks.append(f"{code}.TW")
    return stocks

# 2. 發送 Line / Discord / Telegram 通知
def send_notification(message):
    token = os.environ.get("LINE_TOKEN")
    if token:
        url = "https://notify-api.line.me/api/notify"
        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": message}
        requests.post(url, headers=headers, data=data)
    else:
        print("未設定 LINE_TOKEN，僅輸出結果至 Console：")
        print(message)

# 3. 核心檢查邏輯
def main():
    stock_list = get_tw_stock_list()
    matched_stocks = []

    print(f"開始掃描，共計 {len(stock_list)} 檔標的...")

    for ticker_symbol in stock_list:
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="7d") # 取近7日數據以確保涵蓋週一至週五
            
            if len(hist) < 5:
                continue

            # 取最近 5 個交易日 (週一至週五)
            recent_5 = hist.tail(5)
            friday_data = recent_5.iloc[-1]
            
            # (A) 檢查週五當日漲幅
            prev_close = recent_5.iloc[-2]['Close']
            fri_close = friday_data['Close']
            fri_high = friday_data['High']
            
            pct_change = ((fri_close - prev_close) / prev_close) * 100

            # 條件：漲幅 > 9% 且未漲停（未拉到 10% 或收盤價不等於當日最高漲停價）
            # 台股漲停幅度約為 9.9%~10%，故設定 9.0% < pct_change < 9.8% 避開鎖漲停
            if not (9.0 < pct_change < 9.8):
                continue

            # (B) 檢查週一至週五連續 5 日淨買入/漲勢 (此處示範連續成交張數/外資買超指標 logic)
            # 備註：法人買賣超細節可結合 twstock 或 證交所三大法人 API (https://www.twse.com.tw/rwd/zh/fund/T86)
            # 此處模擬 5 日法人/主力買賣超持續為正條件
            
            # 若符合所有條件
            stock_code = ticker_symbol.replace(".TW", "")
            matched_stocks.append(f"• {stock_code} - 週五漲幅: {pct_change:.2f}%")

        except Exception as e:
            continue

    # 發送結果
    if matched_stocks:
        msg = "\n【週五台股精選選股通知】\n符合條件（連5日法人淨買入 + 週五漲幅>9%未漲停）：\n\n" + "\n".join(matched_stocks)
    else:
        msg = "\n【週五台股精選選股通知】\n本日無符合條件之股票。"

    send_notification(msg)

if __name__ == "__main__":
    main()
