import os
import requests
import pandas as pd
import numpy as np

# Thong tin Telegram cua anh Vu
TELEGRAM_TOKEN = "8603164997:AAFPDAbj7Fx9vj9N2QSHBUm-hbGVI_qQXqE"
TELEGRAM_CHAT_ID = "1718796081"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        print("Telegram status:", res.status_code)
    except Exception as e:
        print("Telegram error:", e)

def get_top_100_symbols():
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        resp = requests.get(url, timeout=10).json()
        ticker_list = resp.get("result", {}).get("list", [])
        usdt_pairs = [x for x in ticker_list if x.get("symbol", "").endswith("USDT")]
        usdt_pairs = sorted(usdt_pairs, key=lambda x: float(x.get("turnover24h", 0)), reverse=True)[:100]
        return [x["symbol"] for x in usdt_pairs]
    except Exception as e:
        print("Error getting symbols:", e)
        return []

def scan_symbol(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=60&limit=65"
        resp = requests.get(url, timeout=5).json()
        raw_list = resp.get("result", {}).get("list", [])
        if not raw_list or len(raw_list) < 55:
            return None

        raw_list.reverse()
        
        df = pd.DataFrame(raw_list)
        df = df.iloc[:, 1:6]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        df = df.astype(float)

        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi_ema'] = df['rsi'].ewm(span=9, adjust=False).mean()

        df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
        df['kijun']  = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
        df['spanA']  = (df['tenkan'] + df['kijun']) / 2
        df['spanB']  = (df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2

        cur  = df.iloc[-2]
        prev = df.iloc[-3]

        # 1. Keo chuan kich hoat (RSI cat len EMA)
        rsi_cross = (prev['rsi'] <= prev['rsi_ema']) and (cur['rsi'] > cur['rsi_ema']) and (cur['rsi'] <= 52)
        kijun_ok = cur['kijun'] >= prev['kijun']
        cloud_green = cur['spanA'] > cur['spanB']
        price_ok = (cur['close'] >= cur['kijun'] or cur['close'] > cur['tenkan']) and (cur['close'] > cur['open'])

        if rsi_cross and kijun_ok and cloud_green and price_ok:
            wick_low = df['low'].iloc[-6:-1].min()
            return {
                "type": "TRIGGER",
                "symbol": symbol,
                "price": cur['close'],
                "sl": wick_low,
                "rsi": round(cur['rsi'], 1)
            }

        # 2. Keo tiem nang (Dang nhung day 38-50 cho cat len)
        if (38 <= cur['rsi'] <= 50) and (cur['close'] > cur['kijun']) and cloud_green:
            return {
                "type": "WATCHLIST",
                "symbol": symbol,
                "price": cur['close'],
                "rsi": round(cur['rsi'], 1)
            }

    except Exception:
        return None
    return None

def main():
    print("Scanning top 100 crypto pairs...")
    symbols = get_top_100_symbols()
    
    triggers = []
    watchlists = []
    
    for s in symbols:
        res = scan_symbol(s)
        if res:
            if res["type"] == "TRIGGER":
                triggers.append(res)
            elif res["type"] == "WATCHLIST":
                watchlists.append(res)

    # 1. Neu co keo chuan -> Ban tin hieu ngay
    if triggers:
        msg = f"🔔 *CẢNH BÁO VÀO LỆNH SÓNG N (1H)*\nPhát hiện *{len(triggers)}* cặp thỏa mãn:\n\n"
        for m in triggers:
            msg += f"• *{m['symbol']}*\n"
            msg += f"   Giá: `{m['price']}` | Gợi ý SL: `{m['sl']}` | RSI: `{m['rsi']}`\n\n"
        msg += "👉 _Mở TradingView kiểm tra lại trước khi vào lệnh!_"
        send_telegram(msg)

    # 2. Neu chua co keo chuan -> Gui danh sach coin dang nhung day dep nhat (Watchlist)
    elif watchlists:
        msg = f"⏱ *BÁO CÁO QUÉT TOP 100 COIN (1H)*\n"
        msg += f"Chưa có điểm cắt qua, nhưng có *{len(watchlists)}* coin đang nhúng đáy đẹp (Watchlist):\n\n"
        for w in watchlists[:5]:
            msg += f"• *{w['symbol']}* | Giá: `{w['price']}` | RSI: `{w['rsi']}`\n"
        msg += "\n👉 _Canh nến 1H đóng tiếp theo xem có tín hiệu bật tăng!_"
        send_telegram(msg)

    # 3. Neu khong co coin nao -> Gui bao cao nhip dap
    else:
        msg = "⏱ *BÁO CÁO (1H)*: Đã quét 100 coin trên Bybit. Thị trường chưa có setup đẹp. Bot tiếp tục canh nến tiếp theo!"
        send_telegram(msg)

if __name__ == "__main__":
    main()
