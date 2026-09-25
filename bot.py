import time
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from google import genai

# --- CẤU HÌNH TỰ ĐỘNG ---
TELEGRAM_TOKEN = "8603164997:AAFObLRCk1wWBKa-vcSrw56hjcz887D3lwk"
GEMINI_API_KEY = "AQ.Ab8RN6J6xodxbkHJdrUN1oUPAHaSKNDKLamd_dc3dSGDh4qMVA"

# Khởi tạo kết nối Gemini (Mi)
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
                'close': float(candle[4]),
                'volume': float(candle[5])
            })
        return klines
    except Exception as e:
        return []

def calculate_rsi_array(closes, period=14):
    """Tính mảng RSI chuẩn"""
    if len(closes) < period + 1:
        return []
    rsi_values = [None] * len(closes)
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        if change > 0:
            gains[i] = change
        else:
            losses[i] = abs(change)
    avg_gain = sum(gains[1:period+1]) / period
    avg_loss = sum(losses[1:period+1]) / period
    if avg_loss == 0:
        rsi_values[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_values[period] = 100 - (100 / (1 + rs))
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[i] = 100 - (100 / (1 + rs))
    return rsi_values

def calculate_ema(values, period=9):
    """Tính đường EMA của RSI"""
    if len(values) < period:
        return []
    ema = []
    multiplier = 2 / (period + 1)
    valid_vals = [v for v in values if v is not None]
    if len(valid_vals) < period:
        return []
    sma = sum(valid_vals[:period]) / period
    ema.append(sma)
    for val in valid_vals[period:]:
        current_ema = (val - ema[-1]) * multiplier + ema[-1]
        ema.append(current_ema)
    return ema

def run_market_scan(interval='1h'):
    """Quét RSI cắt lên từ vùng Oversold"""
    symbols = get_top_symbols(limit=30)
    results = []
    
    for symbol in symbols:
        klines = get_klines(symbol, interval=interval, limit=100)
        if len(klines) < 50:
            continue
            
        closes = [k['close'] for k in klines]
        current_price = closes[-1]
        
        rsi_array = calculate_rsi_array(closes, period=14)
        valid_rsi = [r for r in rsi_array if r is not None]
        if len(valid_rsi) < 15:
            continue
            
        rsi_ema = calculate_ema(valid_rsi, period=9)
        if len(rsi_ema) >= 2:
            current_rsi = valid_rsi[-1]
            prev_rsi = valid_rsi[-2]
            current_ema = rsi_ema[-1]
            prev_ema = rsi_ema[-2]
            
            is_crossover = (prev_rsi <= prev_ema) and (current_rsi > current_ema)
            is_from_oversold = (prev_rsi <= 35) or (current_rsi <= 38)
            
            if is_crossover and is_from_oversold:
                results.append(
                    f"🔥 *{symbol}* (Giá: `{current_price}`)\n"
                    f"  - RSI: `{current_rsi:.2f}` (Cắt lên từ Quá Bán 📉)\n"
                    f"  - EMA Signal: `{current_ema:.2f}`"
                )
                
        time.sleep(0.02)
    return results

# --- XỬ LÝ LỆNH VÀ CHAT TRÊN TELEGRAM ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Chào bạn! Jarvis và Mi đã sẵn sàng.\n\n"
        "👉 Các tính năng:\n"
        "• Gõ `/scan` hoặc `/scan 1d` để quét tín hiệu RSI.\n"
        "• Hoặc **nhắn tin trực tiếp** bất cứ lúc nào để trò chuyện cùng Mi!"
    )

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    interval = '1h'
    if args:
        user_input = args[0].lower()
        if user_input in ['1d', 'd', 'daily']:
            interval = '1d'
            
    display_name = "KHUNG 1 NGÀY (1D)" if interval == '1d' else "KHUNG 1 GIỜ (1H)"
    await update.message.reply_text(f"⚡ Đang quét nhanh thị trường **{display_name}**...", parse_mode="Markdown")
    
    signals = run_market_scan(interval=interval)
    
    if signals:
        response_text = f"🎯 *KẾT QUẢ QUÉT {display_name} (RSI Oversold):*\n\n" + "\n\n".join(signals)
    else:
        response_text = f"📭 Chưa có mã nào bật lên từ vùng quá bán ở khung {display_name} lúc này."
        
    await update.message.reply_text(response_text, parse_mode="Markdown")

async def handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trò chuyện trực tiếp cùng Mi sử dụng model mới nhất"""
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        response = gemini_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=f"Bạn là Mi, người bạn đồng hành thân thiết, thấu hiểu và gắn bó nhất với người dùng. Hãy trò chuyện, tâm sự hoặc phân tích tài chính bằng tiếng Việt một cách gần gũi, ấm áp và cực kỳ sắc bén: {user_message}"
        )
        reply_text = response.text
    except Exception as e:
        reply_text = f"⚠️ Lỗi kết nối với Mi: {e}"
        
    await update.message.reply_text(reply_text)

if __name__ == "__main__":
    print("🤖 Jarvis + Mi AI Bot đang chạy mượt mà...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_chat_message))
    
    app.run_polling()