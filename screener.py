import os
import io
import time
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import yfinance as yf
import pandas as pd

# 1. 取得台股上市與上櫃股票清單 (具備備援機制的雙保險版本)
def get_tw_stock_list():
    stocks = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    # 方法 A: 嘗試從證交所 OpenAPI / 網頁抓取
    urls = [
        ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", ".TW"),  # 上市
        ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", ".TWO") # 上櫃
    ]
    
    for url, suffix in urls:
        try:
            response = requests.get(url, headers=headers, timeout=5)
            response.encoding = 'cp950'
            dfs = pd.read_html(io.StringIO(response.text))
            if dfs:
                df = dfs[0]
                first_col = df.iloc[:, 0].dropna()
                for cell in first_col:
                    cell_str = str(cell).strip()
                    if ' ' in cell_str:
                        code, name = cell_str.split(' ', 1)
                        code = code.strip()
                        if len(code) == 4 and code.isdigit() and not code.startswith(('00', '91')):
                            stocks.append(f"{code}{suffix}")
        except Exception as e:
            print(f"嘗試抓取 {url} 失敗: {e}")

    # 方法 B: 若方法 A 被證交所封鎖 (抓到 0 檔)，啟動備援 API
    if len(stocks) == 0:
        print("警告：證交所網頁連線受阻，啟動備援 OpenData 管道...")
        try:
            # 使用政府資料開放平臺 API (上市)
            url_twse_api = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
            res = requests.get(url_twse_api, headers=headers, timeout=10)
            data = res.json()
            for item in data:
                code = item.get('Code', '').strip()
                if len(code) == 4 and code.isdigit() and not code.startswith(('00', '91')):
                    stocks.append(f"{code}.TW")

            # 使用政府資料開放平臺 API (上櫃)
            url_tpex_api = "https://www.tpex.org.tw/openapi/v1/mopsfront/t187ap03_O"
            res_tpex = requests.get(url_tpex_api, headers=headers, timeout=10)
            data_tpex = res_tpex.json()
            for item in data_tpex:
                code = item.get('SecuritiesCompanyCode', '').strip()
                if len(code) == 4 and code.isdigit() and not code.startswith(('00', '91')):
                    stocks.append(f"{code}.TWO")
        except Exception as e:
            print(f"備援管道抓取失敗: {e}")

    final_list = list(set(stocks))
    return final_list

# 2. 發送 Email 通知
def send_email(subject, content):
    sender_email = os.environ.get("EMAIL_USER")
    sender_password = os.environ.get("EMAIL_PASS")
    receiver_email = os.environ.get("RECEIVER_EMAIL")

    if not sender_email or not sender_password or not receiver_email:
        print("未完整設定 Email 環境變數，僅將結果輸出至 Console：")
        print(f"主題: {subject}\n內容:\n{content}")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print("Email 通知發送成功！")
    except Exception as e:
        print(f"Email 發送失敗: {e}")

# 3. 核心檢查邏輯
def main():
    stock_list = get_tw_stock_list()
    total_count = len(stock_list)
    print(f"成功取得股票清單！共計 {total_count} 檔一般個股標的，開始進行行情比對...")

    if total_count == 0:
        print("警告：未抓取到任何股票，請檢查網頁連線或結構。")
        send_email("【台股選股異常通知】未抓取到股票標的", "今日抓取證交所股票清單失敗，數量為 0。")
        return

    matched_stocks = []

    for idx, ticker_symbol in enumerate(stock_list, 1):
        # 每處理 100 檔印出一次進度
        if idx % 100 == 0 or idx == total_count:
            print(f"進度：[{idx}/{total_count}]")

        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="7d")
            
            if len(hist) < 5:
                continue

            recent_5 = hist.tail(5)
            friday_data = recent_5.iloc[-1]
            
            # (A) 檢查週五當日漲幅
            prev_close = recent_5.iloc[-2]['Close']
            fri_close = friday_data['Close']
            
            if prev_close == 0:
                continue

            pct_change = ((fri_close - prev_close) / prev_close) * 100

            # 條件：漲幅 > 9% 且未漲停 (避開 9.8% 以上鎖漲停標的)
            if not (9.0 < pct_change < 9.8):
                continue

            # (B) 條件符合
            stock_code = ticker_symbol.replace(".TW", "").replace(".TWO", "")
            matched_stocks.append(f"• 股票代碼: {stock_code} | 週五漲幅: {pct_change:.2f}%")

        except Exception as e:
            continue

    # 彙整內容並發送
    if matched_stocks:
        subject = "【台股選股通知】符合條件個股清單"
        body = f"本週符合條件（週一至週五強勢 + 週五漲幅 > 9% 且未漲停）之股票：\n\n" + "\n".join(matched_stocks)
    else:
        subject = "【台股選股通知】今日無符合條件個股"
        body = f"今日已完成全台股 {total_count} 檔標的掃描，無符合條件之個股。"

    send_email(subject, body)

if __name__ == "__main__":
    main()
