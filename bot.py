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

def get_macro_trend():
    # Kiem tra dong tien vi mo BTC 4H tren Bybit (tuong duong nghich dao USDT.D)
    url = "https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=240&limit=60"
    try:
        resp = requests.get(url, timeout=5).json()
        raw_list = resp.get("result", {}).get("list", [])
        if not raw_list or len(raw_list) < 55:
            return True, True
        raw_list.reverse()
        closes = [float(x[4]) for x in raw_list]
        s = pd.Series(closes)
        ema50 = s.ewm(span=50, adjust=False).mean().iloc[-1]
        last_close = closes[-1]
        is_bullish = last_close >= ema50
        return is_bullish, not is_bullish
    except Exception:
        return True, True

def scan_symbol(symbol, macro_long_ok, macro_short_ok):
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=60&limit=70"
    try:
        resp = requests.get(url, timeout=5).json()
    except Exception:
        return None

    raw_list = resp.get("result", {}).get("list", [])
    if not raw_list or len(raw_list) < 60:
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

    weights = np.arange(1, 46)
    df['rsi_wma'] = df['rsi'].rolling(45).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun']  = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    df['spanA']  = (df['tenkan'] + df['kijun']) / 2
    df['spanB']  = (df['high'].rolling(52).max() + df['low'].rolling(52).min()) / 2

    cur  = df.iloc[-2]
    prev = df.iloc[-3]

    rsi_cross_up   = (prev['rsi'] <= prev['rsi_ema']) and (cur['rsi'] > cur['rsi_ema'])
    rsi_cross_down = (prev['rsi'] >= prev['rsi_ema']) and (cur['rsi'] < cur['rsi_ema'])

    wick_low  = df['low'].iloc[-6:-1].min()
    wick_high = df['high'].iloc[-6:-1].max()

    # --- 1. TÍN HIỆU LONG ---
    if macro_long_ok:
        was_oversold  = df['rsi'].iloc[-7:-1].min() <= 35
        cloud_twisted_up = (prev['spanA'] <= prev['spanB']) and (cur['spanA'] > cur['spanB'])
        cloud_pinched_up = (cur['spanA'] <= cur['spanB']) and (abs(cur['spanA'] - cur['spanB']) / cur['close'] < 0.012)
        candle_green  = (cur['close'] > cur['tenkan']) and (cur['close'] > cur['open'])

        if was_oversold and (cloud_twisted_up or cloud_pinched_up) and rsi_cross_up and candle_green:
            return {
                "side": "LONG",
                "title": "🟢 [LONG] 🚀 BẮT ĐÁY XOẮN MÂY",
                "symbol": symbol,
                "price": cur['close'],
                "sl": wick_low,
                "rsi": round(cur['rsi'], 1)
            }

        cloud_green  = cur['spanA'] > cur['spanB']
        kijun_ok_up  = cur['kijun'] >= prev['kijun']
        tested_wma_up= df['rsi'].iloc[-5:-1].min() <= (cur['rsi_wma'] + 2.5)
        bounced_up   = rsi_cross_up and (cur['rsi'] >= cur['rsi_wma'])
        price_ok_up  = (cur['close'] >= cur['kijun'] or cur['close'] > cur['tenkan']) and (cur['close'] > cur['open'])

        if cloud_green and kijun_ok_up and tested_wma_up and bounced_up and price_ok_up:
            return {
                "side": "LONG",
                "title": "🟢 [LONG] 📈 TIẾP DIỄN SÓNG N",
                "symbol": symbol,
                "price": cur['close'],
                "sl": wick_low,
                "rsi": round(cur['rsi'], 1)
            }

    # --- 2. TÍN HIỆU SHORT ---
    if macro_short_ok:
        was_overbought = df['rsi'].iloc[-7:-1].max() >= 65
        cloud_twisted_down = (prev['spanA'] >= prev['spanB']) and (cur['spanA'] < cur['spanB'])
        cloud_pinched_down = (cur['spanA'] >= cur['spanB']) and (abs(cur['spanA'] - cur['spanB']) / cur['close'] < 0.012)
        candle_red = (cur['close'] < cur['tenkan']) and (cur['close'] < cur['open'])

        if was_overbought and (cloud_twisted_down or cloud_pinched_down) and rsi_cross_down and candle_red:
            return {
                "side": "SHORT",
                "title": "🔴 [SHORT] 🔻 BẮT ĐỈNH XOẮN MÂY",
                "symbol": symbol,
                "price": cur['close'],
                "sl": wick_high,
                "rsi": round(cur['rsi'], 1)
            }

        cloud_red      = cur['spanA'] < cur['spanB']
        kijun_ok_down  = cur['kijun'] <= prev['kijun']
        tested_wma_down= df['rsi'].iloc[-5:-1].max() >= (cur['rsi_wma'] - 2.5)
        rejected_down  = rsi_cross_down and (cur['rsi'] <= cur['rsi_wma'])
        price_ok_down  = (cur['close'] <= cur['kijun'] or cur['close'] < cur['tenkan']) and (cur['close'] < cur['open'])

        if cloud_red and kijun_ok_down and tested_wma_down and rejected_down and price_ok_down:
            return {
                "side": "SHORT",
                "title": "🔴 [SHORT] 📉 TIẾP DIỄN SÓNG N GIẢM",
                "symbol": symbol,
                "price": cur['close'],
                "sl": wick_high,
                "rsi": round(cur['rsi'], 1)
            }

    return None

def main():
    print("Checking macro flow...")
    macro_long_ok, macro_short_ok = get_macro_trend()
    print(f"Macro status: Long={macro_long_ok}, Short={macro_short_ok}")

    print("Scanning top 100 crypto pairs...")
    symbols = get_top_100_symbols()
    print(f"Loaded {len(symbols)} coins.")

    matches = []
    for s in symbols:
        res = scan_symbol(s, macro_long_ok, macro_short_ok)
        if res:
            matches.append(res)

    if matches:
        msg = f"🔔 *CẢNH BÁO TÍN HIỆU GIAO DỊCH (1H)*\n"
        msg += f"Phát hiện *{len(matches)}* cơ hội đạt chuẩn:\n\n"
        for m in matches:
            sl_text = "SL đáy râu" if m["side"] == "LONG" else "SL đỉnh râu"
            msg += f"{m['title']}\n"
            msg += f"• *{m['symbol']}*\n"
            msg += f"   Giá: `{m['price']}` | {sl_text}: `{m['sl']}` | RSI: `{m['rsi']}`\n\n"
        msg += "👉 _Mở TradingView soi lại cấu trúc trước khi vào lệnh!_"
        print(msg)
        send_telegram(msg)
    else:
        trend_desc = "Thuận Long (Tăng)" if macro_long_ok else "Thuận Short (Giảm)"
        msg = f"⏱ *BÁO CÁO 1H*: Đã quét 100 coin Bybit.\n• Xu hướng vĩ mô: *{trend_desc}*\n• Hiện tại chưa có điểm vào đạt chuẩn. Bot tiếp tục canh nến tiếp theo!"
        print(msg)
        send_telegram(msg)

if __name__ == "__main__":
    main()
