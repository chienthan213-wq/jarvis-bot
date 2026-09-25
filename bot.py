import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

# Thiết lập logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

def get_top_symbols(limit=30):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        usdt_pairs = [item for item in data if item['symbol'].endswith('USDT')]
        usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        return [item['symbol'] for item in usdt_pairs[:limit]]
    except Exception:
        return []

def get_klines(symbol, interval='1h', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        return [{
            'open': float(c[1]), 'high': float(c[2]), 'low': float(c[3]), 'close': float(c[4]), 'volume': float(c[5])
        } for c in data]
    except Exception:
        return []

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(1, period + 1):
        chg = closes[i] - closes[i-1]
        if chg > 0: gains += chg
        else: losses -= chg
    avg_gain, avg_loss = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        chg = closes[i] - closes[i-1]
        gain = chg if chg > 0 else 0
        loss = -chg if chg < 0 else 0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0: return 100
    return 100 - (100 / (1 + (avg_gain / avg_loss)))

def calculate_ema(closes, period=9):
    if len(closes) < period: return None
    mult = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for p in closes[period:]:
        ema = (p - ema) * mult + ema
    return ema

def calculate_ichimoku_cloud(klines):
    try:
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        span_a = ((max(highs[-9:]) + min(lows[-9:])) / 2 + (max(highs[-26:]) + min(lows[-26:])) / 2) / 2
        span_b = (max(highs[-52:]) + min(lows[-52:])) / 2
        return span_a, span_b
    except Exception:
        return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Jarvis & Mi đã sẵn sàng! Gõ /scan hoặc /scan 1d để quét tín hiệu LONG.")

async def scan_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    timeframe = args[0] if args else '1h'
    await update.message.reply_text(f"🔍 Đang rà soát thị trường KHUNG {timeframe.upper()}...")
    
    symbols = get_top_symbols(limit=30)
    matched = []
    
    for symbol in symbols:
        klines = get_klines(symbol, timeframe, limit=100)
        if not klines or len(klines) < 60: continue
        closes = [k['close'] for k in klines]
        
        rsi_c = calculate_rsi(closes)
        ema_c = calculate_ema(closes, 9)
        rsi_p = calculate_rsi(closes[:-1])
        ema_p = calculate_ema(closes[:-1], 9)
        
        if None in (rsi_c, ema_c, rsi_p, ema_p): continue
        
        if (rsi_p <= ema_p) and (rsi_c > ema_c):
            span_a, span_b = calculate_ichimoku_cloud(klines)
            if span_a and span_b and closes[-1] > max(span_a, span_b):
                matched.append(f"🔥 **{symbol}** (Giá: `{closes[-1]}`)\n  - RSI: `{rsi_c:.2f}` (Cắt EMA) | Trên Mây ✅")

    if matched:
        await update.message.reply_text(f"🎯 **TÍN HIỆU LONG KHUNG {timeframe.upper()}**:\n\n" + "\n\n".join(matched[:10]), parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⏳ Chưa có mã nào thỏa mãn ở khung {timeframe.upper()} lúc này.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = gemini_client.models.generate_content(model='gemini-2.5-flash', contents=update.message.text)
        await update.message.reply_text(res.text)
    except Exception as e:
        await update.message.reply_text(f"Lỗi AI: {e}")

def main():
    if not TELEGRAM_TOKEN: return
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan_market))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
