import os
import requests
import pandas as pd
import numpy as np

# CẤU HÌNH TELEGRAM CỦA ANH
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ĐIỀN_TOKEN_BOT_CỦA_ANH_VÀO_ĐÂY")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ĐIỀN_CHAT_ID_CỦA_ANH_VÀO_ĐÂY")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Lỗi gửi Telegram:", e)

def get_top_100_symbols():
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    resp = requests.get(url).json()
    usdt_pairs = [x for x in resp if x['symbol'].endswith('USDT')]
    # Lấy top 100 coin có khối lượng giao dịch lớn nhất
    usdt_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)[:100]
    return [x['symbol'] for x in usdt_pairs]

def scan_symbol(symbol):
    try:
        url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&limit=60"
        data = requests.get(url, timeout=5).json()
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
        df = df.astype({'open': float, 'high': float, 'low': float, 'close': float, 'volume': float})

        # 1. Tính RSI (14) & EMA (9) của RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi_ema'] = df['rsi'].ewm(span=9, adjust=False).mean()

        # 2. Tính Ichimoku
        df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
        df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
        df['spanA'] = (df['tenkan'] + df['kijun']) / 2
        df['spanB'] = (df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2

        # Lấy nến vừa đóng (nến áp chót)
        cur = df.iloc[-2]
        prev = df.iloc[-3]

        # ĐIỀU KIỆN LỌC CHUẨN SÓNG N
        # A. RSI vừa cắt lên EMA ở vùng dưới 52
        rsi_cross = (prev['rsi'] <= prev['rsi_ema']) and (cur['rsi'] > cur['rsi_ema']) and (cur['rsi'] <= 52)
        # B. Kijun không dốc xuống
        kijun_ok = cur['kijun'] >= prev['kijun']
        # C. Mây tương lai xanh (Span A > Span B)
        cloud_green = cur['spanA'] > cur['spanB']
        # D. Giá nằm trên Kijun hoặc vừa cắt lên Tenkan, nến xanh
        price_ok = (cur['close'] >= cur['kijun'] or cur['close'] > cur['tenkan']) and (cur['close'] > cur['open'])

        if rsi_cross and kijun_ok and cloud_green and price_ok:
            # Đáy râu nến nhịp chỉnh (5 nến gần nhất)
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
    symbols = get_top_100_symbols()
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
        send_telegram(msg)
    else:
        print("Không có cặp nào thỏa điều kiện trong giờ này.")

if __name__ == "__main__":
    main()
