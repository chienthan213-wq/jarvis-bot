import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

# --- CẤU HÌNH TỰ ĐỘNG ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Khởi tạo tạo kết nối Gemini (Mi)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

def get_top_symbols(limit=30):
    """Lấy danh sách top các cặp giao dịch USDT"""
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        usdt_pairs = [item for item in data if item['symbol'].endswith('USDT')]
        usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        return [item['symbol'] for item in usdt_pairs[:limit]]
    except Exception as e:
        return []

def get_klines(symbol, interval='1h', limit=100):
    """Lấy dữ liệu nến từ Binance"""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        klines = []
        for candle in data:
            klines.append({
                'open': float(candle[1]),
                'high': float(candle[2]),
                'low': float(candle[3]),
                'close': float(candle[4]),
                'volume': float(candle[5])
            })
        return klines
    except Exception as e:
        return []

def calculate_rsi(closes, period=14):
    """Tính toán chỉ báo RSI"""
    if len(closes) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(1, period + 1):
        change = closes[i] - closes[i-1]
        if change > 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i-1]
        gain = change if change > 0 else 0
        loss = -change if change < 0 else 0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_ema(closes, period=9):
    """Tính đường trung bình động EMA"""
    if len(closes) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_ichimoku_cloud(klines):
    """Tính toán mây Ichimoku (Senkou Span A và Senkou Span B)"""
    try:
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        
        # Tenkan-sen (9 periods)
        tenkan = (max(highs[-9:]) + min(lows[-9:])) / 2
        # Kijun-sen (26 periods)
        kijun = (max(highs[-26:]) + min(lows[-26:])) / 2
        
        # Senkou Span A (Leading Span A)
        span_a = (tenkan + kijun) / 2
        # Senkou Span B (Leading Span B, 52 periods)
        span_b = (max(highs[-52:]) + min(lows[-52:])) / 2
        
        return span_a, span_b
    except Exception:
        return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Chào bạn! Jarvis & Mi đã sẵn sàng.\n"
        "Gõ /scan hoặc /scan 1d để quét tín hiệu LONG đỉnh cao (RSI cắt EMA + Trên mây Kumo)!"
    )

async def scan_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    timeframe = args[0] if args else '1h'
    
    await update.message.reply_text(f"🔍 Đang rà soát thị trường ở KHUNG {timeframe.upper()} theo chiến thuật RSI + Ichimoku...")
    
    symbols = get_top_symbols(limit=40)
    matched_signals = []
    
    for symbol in symbols:
        klines = get_klines(symbol, timeframe, limit=100)
        if not klines or len(klines) < 60:
            continue
            
        closes = [k['close'] for k in klines]
        
        # Tính RSI và EMA của nến hiện tại và nến trước
        rsi_current = calculate_rsi(closes)
        ema_current = calculate_ema(closes, period=9)
        
        closes_prev = closes[:-1]
        rsi_prev = calculate_rsi(closes_prev)
        ema_prev = calculate_ema(closes_prev, period=9)
        
        if rsi_current is None or ema_current is None or rsi_prev is None or ema_prev is None:
            continue
            
        # Kiểm tra điều kiện RSI cắt lên trên đường EMA
        rsi_cross_up = (rsi_prev <= ema_prev) and (rsi_current > ema_current)
        
        # Kiểm tra điều kiện giá đứng TRÊN Mây Kumo (Ichimoku)
        span_a, span_b = calculate_ichimoku_cloud(klines)
        if span_a is None or span_b is None:
            continue
            
        kumo_top = max(span_a, span_b)
        current_price = closes[-1]
        is_above_kumo = current_price > kumo_top
        
        # Lọc các đồng coin thỏa mãn toàn bộ điều kiện chiến thuật
        if rsi_cross_up and is_above_kumo:
            matched_signals.append(
                f"🔥 **{symbol}** (Giá: `{current_price}`)\n"
                f"  - RSI: `{rsi_current:.2f}` (Cắt lên EMA)\n"
                f"  - Xu hướng: Trên Mây Kumo ✅"
            )

    if matched_signals:
        response_text = f"🎯 **KẾT QUẢ QUÉT TÍN HIỆU LONG ĐẸP (Khung {timeframe.upper()}):**\n\n" + "\n\n".join(matched_signals[:10])
    else:
        response_text = f"⏳ Chưa có mã nào thỏa mãn điều kiện (RSI cắt lên EMA + Trên mây Kumo) ở khung {timeframe.upper()} lúc này."
        
    await update.message.reply_text(response_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        response = genai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_text,
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Mi đang bận chút xíu, lỗi kết nối AI: {e}")

def main():
    if not TELEGRAM_TOKEN:
        print("Lỗi: Thiếu TELEGRAM_TOKEN!")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan_market))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🤖 Bot đang chạy...")
    app.run_polling()

if __name__ == '__main__':
    main()
