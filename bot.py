import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from google import genai
import ccxt

# Thiết lập logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Lấy các biến môi trường (API Key bạn cấu hình bên Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Khởi tạo Gemini client (sử dụng SDK mới google-genai)
genai_client = genai.Client(api_key=GEMINI_API_KEY)

# Khởi tạo kết nối Binance để lấy dữ liệu thị trường
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# Hàm tính toán RSI đơn giản
async def calculate_rsi(symbol, timeframe='1h', limit=50):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        closes = [x[4] for x in ohlcv]
        
        # Tính toán thay đổi giá
        gains = []
        losses = []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
                
        # RSI 14 kỳ chuẩn
        period = 14
        if len(gains) < period:
            return None, None
            
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
        # Lấy RSI cây nến trước và nến hiện tại để check chiều cắt lên
        # Tính sơ bộ nến trước đó
        prev_avg_gain = (avg_gain * (period - 1) - gains[-1] + (gains[-2] if len(gains) > 1 else 0)) / period # (đơn giản hóa tương đối)
        # Trả về rsi hiện tại và rsi trước đó
        return rsi, closes[-1]
    except Exception as e:
        logging.error(f"Lỗi tính RSI cho {symbol}: {e}")
        return None, None

# Lệnh /start
async def start(command_update: Update, context: ContextTypes.DEFAULT_TYPE):
    await command_update.message.reply_text(
        "🤖 Chào bạn! Jarvis & Mi đã sẵn sàng.\n"
        "Gõ /scan hoặc /scan 1d để quét thị trường theo điều kiện RSI mới nhé!"
    )

# Lệnh /scan (Hỗ trợ quét khung thời gian linh hoạt: /scan hoặc /scan 1d, /scan 4h...)
async def scan_market(command_update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lấy tham số khung thời gian người dùng nhập, mặc định là '1h' nếu bỏ trống
    args = context.args
    timeframe = args[0] if args else '1h'
    
    await command_update.message.reply_text(f"🔍 Đang quét nhanh thị trường ở KHUNG {timeframe.upper()}...")
    
    try:
        # Lấy danh sách các cặp giao dịch USDT phổ biến trên Binance
        markets = exchange.load_markets()
        symbols = [s for s in markets.keys() if s.endswith('/USDT') and not 'UP' in s and not 'DOWN' in s]
        
        # Giới hạn quét top một số đồng chính để bot chạy nhanh và không bị timeout
        top_symbols = symbols[:40] 
        matched_signals = []
        
        for symbol in symbols[:30]: # Quét mẫu 30 đồng tiêu biểu trước cho nhanh
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=20)
                if not ohlcv or len(ohlcv) < 15:
                    continue
                    
                closes = [x[4] for x in ohlcv]
                
                # Tính RSI đơn giản 14 kỳ
                gains, losses = [], []
                for i in range(1, len(closes)):
                    chg = closes[i] - closes[i-1]
                    gains.append(chg if chg > 0 else 0)
                    losses.append(abs(chg) if chg < 0 else 0)
                    
                period = 14
                avg_g = sum(gains[:period]) / period
                avg_l = sum(losses[:period]) / period
                
                # RSI hiện tại
                rs = avg_g / avg_l if avg_l != 0 else 0
                current_rsi = 100 - (100 / (1 + rs))
                
                # RSI cây nến trước đó (để check có đang hướng lên không)
                prev_rs = (avg_g * 0.9 + gains[-1]) / (avg_l * 0.9 + losses[-1]) if (avg_l * 0.9 + losses[-1]) != 0 else 0
                prev_rsi = 100 - (100 / (1 + prev_rs))

                # ĐIỀU KIỆN MỚI ĐÃ ĐƯỢC NỚI LỎNG:
                # RSI nằm trong khoảng từ 20 đến 70 VÀ có xu hướng nhích tăng lên (current_rsi > prev_rsi)
                if 20 <= current_rsi <= 70 and current_rsi > prev_rsi:
                    matched_signals.append(f"🟢 **{symbol}** | RSI: `{current_rsi:.1f}` (Đang hướng lên)")
            except Exception:
                continue

        if matched_signals:
            response_text = f"✨ **TÍN HIỆU QUÉT KHUNG {timeframe.upper()}** ✨\n\n" + "\n".join(matched_signals[:10])
        else:
            response_text = f"⏳ Chưa có mã nào thực sự bứt phá rõ rệt trong biên độ RSI [20-70] ở khung {timeframe.upper()} lúc này."
            
        await command_update.message.reply_text(response_text, parse_mode="Markdown")
        
    except Exception as e:
        await command_update.message.reply_text(f"❌ Có lỗi xảy ra khi quét thị trường: {e}")

# Xử lý chat trò chuyện AI thông thường với Gemini
async def handle_message(command_update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = command_update.message.text
    try:
        # Gọi Gemini phản hồi chat
        response = genai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_text,
        )
        await command_update.message.reply_text(response.text)
    except Exception as e:
        await command_update.message.reply_text(f"Mi đang bận chút xíu, lỗi kết nối AI: {e}")

def main():
    if not TELEGRAM_TOKEN:
        print("Lỗi: Thiếu TELEGRAM_TOKEN!")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Đăng ký các lệnh
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan_market))
    
    # Đăng ký nhận tin nhắn chat thông thường
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🤖 Bot đang chạy...")
    app.run_polling()

if __name__ == '__main__':
    main()
