import os
import requests
import pandas as pd
import numpy as np

# CẤU HÌNH TELEGRAM CỦA ANH
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ĐIỀN_TOKEN_BOT_CỦA_ANH_VÀO_ĐÂY")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ĐIỀN_CHAT_ID_CỦA_ANH_VÀO_ĐÂY")

def send_telegram(message):
    if "ĐIỀN_TOKEN" in TELEGRAM_TOKEN:
        print("Chưa cấu hình Telegram Token!")
        print("Nội dung tin nhắn dự kiến:\n", message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        print("Kết quả gửi Telegram:", res.status_code)
    except Exception as e:
        print("Lỗi gửi Telegram:", e)

def get_top_100_symbols():
    try:
        # Lấy từ sàn Bybit (Không bị chặn trên máy chủ GitHub Cloud)
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        resp = requests.get(url, timeout=10).json()
        ticker_list = resp.get("result", {}).get("list", [])
        
        # Lọc các cặp USDT
        usdt_pairs = [x for x in ticker_list if x.get("symbol", "").endswith("USDT")]
        # Sắp xếp theo khối lượng 24h lớn nhất
        usdt_pairs = sorted(usdt_pairs, key=lambda x: float(x.get("turnover24h", 0)), reverse=True)[:100]
        return [x["symbol"] for x in usdt_pairs]
    except Exception as e:
        print("Lỗi lấy danh sách coin:", e)
        return []

def scan_symbol(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=60&limit=60"
        resp = requests.get(url, timeout=5).json()
        raw_list = resp.get("result", {}).get("list", [])
        if not raw_list or len(raw_list) < 55:
            return None

        # Đảo ngược dữ liệu từ cũ đến mới
        raw_list = raw_list[::-1]
        
        # Lấy các cột giá: open, high, low, close, volume
        df = pd.DataFrame(raw_list)
        df = df.iloc]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        df = df.astype(float)

        # 1. Tính RSI (14) & EMA (9) của RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi_ema'] = df['rsi'].ewm(span=9, adjust=False).mean()

        # 2. Tính Ichimoku
        df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
        df['kijun']  = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
        df['spanA']  = (df['tenkan'] + df['kijun']) / 2
        df['spanB']  = (df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2

        # Lấy cây nến vừa đóng cửa
        cur  = df.iloc[-2]
        prev = df.iloc[-3]

        # ĐIỀU KIỆN LỌC SÓNG N
        # 1. RSI cắt lên EMA ở vùng dưới 52
        rsi_cross = (prev['rsi'] <= prev['rsi_ema']) and (cur['rsi'] > cur['rsi_ema']) and (cur['rsi'] <= 52)
        # 2. Kijun không dốc xuống
        kijun_ok = cur['kijun'] >= prev['kijun']
        # 3. Mây tương lai xanh (Span A > Span B)
        cloud_green = cur['spanA'] > cur['spanB']
        # 4. Giá nằm trên Kijun hoặc vừa cắt lên Tenkan, nến xanh
        price_ok = (cur['close'] >= cur['kijun'] or cur['close'] > cur['tenkan']) and (cur['close'] > cur['open'])

        if rsi_cross and kijun_ok and cloud_green and price_ok:
            wick_low = df['low'].iloc[-6:-1].min()
            return {
                "symbol": symbol,
                "price": cur['close'],
                "sl": wick_low,
                "rsi": round(cur['rsi'], 1)
            }
    except Exception:
        return None
    return None

def main():
    print("Bắt đầu quét Top 100 coin...")
    symbols = get_top_100_symbols()
    print(f"Đã lấy thành công {len(symbols)} cặp coin.")
    
    matches = []
    for s in symbols:
        res = scan_symbol(s)
        if res:
            matches.append(res)

    if matches:
        msg = f"🔔 *CẢNH BÁO SETUP SÓNG N (NẾN 1H)*\nPhát hiện *{len(matches)}* cặp thỏa mãn:\n\n"
        for m in matches:
            msg += f"• *{m['symbol']}*\n   Giá: `{m['price']}` | SL đáy râu: `{m['sl']}` | RSI: `{m['rsi']}`\n\n"
        msg += "👉 _Mở TradingView kiểm tra cấu trúc trước khi vào lệnh!_"
        print(msg)
        send_telegram(msg)
    else:
        print("Không có cặp nào thỏa mãn điều kiện trong giờ này.")

if __name__ == "__main__":
    main()
