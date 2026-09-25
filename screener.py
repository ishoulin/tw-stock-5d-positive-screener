import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import yfinance as yf
import pandas as pd

# 1. 取得台股上市櫃股票清單 (排除 00 開頭的 ETF 與 91 開頭的 TDR)
def get_tw_stock_list():
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2" # 上市
    headers = {'User-Agent': 'Mozilla/5.0'}

    # 抓取網頁原始內容
    response = requests.get(url, headers=headers)
    # 明確指定台灣傳統網頁編碼 cp950 (Big5)
    response.encoding = 'cp950'

    # 用 StringIO 包裹後再給 pandas 讀取
    df = pd.read_html(io.StringIO(response.text))[0]
    df.columns = df.iloc[0]
    df = df.iloc[1:]
    
    stocks = []
    for code_name in df['有價證券代號及名稱']:
        if isinstance(code_name, str) and ' ' in code_name:
            code, name = code_name.split(' ', 1)
            # 排除 ETF (00開頭)、TDR (91開頭) 等，僅留 4 位數一般個股
            if len(code) == 4 and code.isdigit() and not code.startswith(('00', '91')):
                stocks.append(f"{code}.TW")
    return stocks

# 2. 發送 Email 通知
def send_email(subject, content):
    sender_email = os.environ.get("EMAIL_USER")
    sender_password = os.environ.get("EMAIL_PASS")
    receiver_email = os.environ.get("RECEIVER_EMAIL")

    if not sender_email or not sender_password or not receiver_email:
        print("未完整設定 Email 環境變數，輸出至 Console：")
        print(f"主題: {subject}\n內容:\n{content}")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        # 使用 Gmail SMTP 伺服器
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
    matched_stocks = []

    print(f"開始掃描，共計 {len(stock_list)} 檔標的...")

    for ticker_symbol in stock_list:
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="7d") # 取近7日數據以涵蓋週一至週五
            
            if len(hist) < 5:
                continue

            # 取最近 5 個交易日 (週一至週五)
            recent_5 = hist.tail(5)
            friday_data = recent_5.iloc[-1]
            
            # (A) 檢查週五當日漲幅
            prev_close = recent_5.iloc[-2]['Close']
            fri_close = friday_data['Close']
            
            pct_change = ((fri_close - prev_close) / prev_close) * 100

            # 條件：漲幅 > 9% 且未漲停 (避開 9.8% 以上鎖漲停標的)
            if not (9.0 < pct_change < 9.8):
                continue

            # (B) 條件符合
            stock_code = ticker_symbol.replace(".TW", "")
            matched_stocks.append(f"• 股票代碼: {stock_code} | 週五漲幅: {pct_change:.2f}%")

        except Exception as e:
            continue

    # 彙整內容並發送
    if matched_stocks:
        subject = "【台股選股通知】符合條件個股清單"
        body = "本週符合條件（週一至週五連續漲幅/買盤強勢 + 週五漲幅 > 9% 且未漲停）之股票：\n\n" + "\n".join(matched_stocks)
    else:
        subject = "【台股選股通知】今日無符合條件個股"
        body = "本週未掃描到符合所有條件之台股個股。"

    send_email(subject, body)

if __name__ == "__main__":
    main()
