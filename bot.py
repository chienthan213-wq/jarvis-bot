import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

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

        # 1. Kèo chuẩn kích hoạt (RSI vừa cắt lên EMA)
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

        # 2. Kèo tiềm năng (Đang nhúng đáy hỗ trợ 38-50 chuẩn bị nảy)
        in_pullback_zone = 38 <= cur['rsi'] <= 50
        trend_strong = cur['close'] > cur['kijun'] and cloud_green
        if in_pullback_zone and trend_strong:
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
    print(f"Loaded {len(symbols)} coins.")
    
    triggers = []
    watchlists = []
    
    for s in symbols:
        res = scan_symbol(s)
        if res:
            if res["type"] == "TRIGGER":
                triggers.append(res)
            elif res["type"] == "WATCHLIST":
                watchlists.append(res)

    now_str = datetime.utcnow().strftime("%H:%M UTC")

    # Kịch bản gửi tin nhắn
    if triggers:
        msg = f"🔔 *CẢNH BÁO VÀO LỆNH SÓNG N ({now_str})*\n"
        msg += f"Phát hiện *{len(triggers)}* cặp thỏa mãn điểm vào:\n\n"
        for m in triggers:
            msg += f"• *{m['symbol']}*\n"
            msg += f"   Giá: `{m['price']}` | Gợi ý SL: `{m['sl']}` | RSI: `{m['rsi']}`\n\n"
        msg += "👉 _Mở TradingView soi lại cấu trúc trước khi vào lệnh!_"
        send_telegram(msg)

    elif watchlists:
        # Nếu chưa có kèo kích hoạt ngay, gửi danh sách coin đang chờ đẹp nhất (tối đa 5 coin)
        msg = f"⏱ *BÁO CÁO THỊ TRƯỜNG ({now_str})*\n"
        msg += f"Chưa có kèo cắt qua, nhưng có *{len(watchlists)}* coin đang nhúng đáy đẹp (Watchlist):\n\n"
        for w in watchlists[:5]:
            msg += f"• *{w['symbol']}* - Giá: `{w['price']}` | RSI: `{w['rsi']}`\n"
        msg += "\n👉 _Canh nến 1H tiếp theo đóng cửa xem có tín hiệu bật tăng!_"
        send_telegram(msg)

    else:
        # Báo cáo nhịp đập để anh biết bot vẫn đang làm việc
        msg = f"⏱ *BÁO CÁO ({now_str})*: Đã quét 100 coin. Thị trường chưa có setup đẹp. Bot tiếp tục canh nến tiếp theo!"
        send_telegram(msg)

if __name__ == "__main__":
    main()
