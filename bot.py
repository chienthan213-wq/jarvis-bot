import os
import requests
import pandas as pd
import numpy as np

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
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=60&limit=65"
    try:
        resp = requests.get(url, timeout=5).json()
    except Exception:
        return None

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

    rsi_cross = (prev['rsi'] <= prev['rsi_ema']) and (cur['rsi'] > cur['rsi_ema'])
    wick_low  = df['low'].iloc[-6:-1].min()

    # 1. Bat day Xoan may (Hop 1)
    was_deep_oversold = df['rsi'].iloc[-7:-1].min() <= 35
    cloud_twisted = (prev['spanA'] <= prev['spanB']) and (cur['spanA'] > cur['spanB'])
    cloud_pinched = (cur['spanA'] <= cur['spanB']) and (abs(cur['spanA'] - cur['spanB']) / cur['close'] < 0.012)
    cross_tenkan = (cur['close'] > cur['tenkan']) and (cur['close'] > cur['open'])

    if was_deep_oversold and (cloud_twisted or cloud_pinched) and rsi_cross and cross_tenkan:
        return {
            "type": "REVERSAL",
            "title": "🚀 BẮT ĐÁY XOẮN MÂY (CHÂN SÓNG)",
            "symbol": symbol,
            "price": cur['close'],
            "sl": wick_low,
            "rsi": round(cur['rsi'], 1)
        }

    # 2. Tiep dien Song N tren may (Hop 2 & 3)
    cloud_green = cur['spanA'] > cur['spanB']
    kijun_ok    = cur['kijun'] >= prev['kijun']
    price_above = (cur['close'] >= cur['kijun'] or cur['close'] > cur['tenkan']) and (cur['close'] > cur['open'])
    rsi_pullback = rsi_cross and (cur['rsi'] <= 52)

    if cloud_green and kijun_ok and price_above and rsi_pullback:
        return {
            "type": "TREND",
            "title": "📈 TIẾP DIỄN SÓNG N (TRÊN MÂY)",
            "symbol": symbol,
            "price": cur['close'],
            "sl": wick_low,
            "rsi": round(cur['rsi'], 1)
        }

    return None

def main():
    print("Scanning top 100 crypto pairs...")
    symbols = get_top_100_symbols()
    print(f"Loaded {len(symbols)} coins.")

    reversals = []
    trends    = []

    for s in symbols:
        res = scan_symbol(s)
        if res:
            if res["type"] == "REVERSAL":
                reversals.append(res)
            elif res["type"] == "TREND":
                trends.append(res)

    all_matches = reversals + trends

    if all_matches:
        msg = f"🔔 *CẢNH BÁO CƠ HỘI GIAO DỊCH (1H)*\n"
        msg += f"Phát hiện *{len(all_matches)}* coin có setup đẹp:\n\n"
        for m in all_matches:
            msg += f"{m['title']}\n"
            msg += f"• *{m['symbol']}*\n"
            msg += f"   Giá: `{m['price']}` | SL đáy râu: `{m['sl']}` | RSI: `{m['rsi']}`\n\n"
        msg += "👉 _Mở TradingView soi lại cấu trúc trước khi vào lệnh!_"
        print(msg)
        send_telegram(msg)
    else:
        msg = "⏱ *BÁO CÁO 1H*: Đã quét 100 coin Bybit. Chưa có điểm bắt đáy Xoắn mây hay Sóng N nào. Bot tiếp tục canh nến tiếp theo!"
        print(msg)
        send_telegram(msg)

if __name__ == "__main__":
    main()
