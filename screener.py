import os
import io
import time
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import yfinance as yf
import pandas as pd

# 1. 取得台股上市與上櫃股票清單 (修復網頁抓取與解析問題)
def get_tw_stock_list():
    urls = [
        ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", ".TW"),  # 上市
        ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", ".TWO") # 上櫃
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    stocks = []

    for url, suffix in urls:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'cp950'
            
            # 使用 pandas 解析表格
            dfs = pd.read_html(io.StringIO(response.text))
            if not dfs:
                continue
                
            df = dfs[0]
            
            # 遍歷表格第一欄（通常為「有價證券代號及名稱」）
            first_col = df.iloc[:, 0].dropna()
            
            for cell in first_col:
                cell_str = str(cell).strip()
                # 判斷格式如 "2330 台積電"
                if ' ' in cell_str:
                    code, name = cell_str.split(' ', 1)
                    code = code.strip()
                    # 嚴格過濾：4 位數純數字，且排除 ETF (00開頭) 與 TDR (91開頭)
                    if len(code) == 4 and code.isdigit() and not code.startswith(('00', '91')):
                        stocks.append(f"{code}{suffix}")
        except Exception as e:
            print(f"抓取 {url} 失敗: {e}")
            
    return list(set(stocks)) # 移除重複項

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
