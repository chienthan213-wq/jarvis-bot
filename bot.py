import os
import requests
import pandas as pd
import numpy as np

# ==========================================
# CẤU HÌNH TELEGRAM CỦA ANH VŨ (ĐÃ ĐIỀN ĐỦ)
# ==========================================
TELEGRAM_TOKEN = "8603164997:AAFPDAbj7Fx9vj9N2QSHBUm-hbGVI_qQXqE"
TELEGRAM_CHAT_ID = "1718796081"


def send_telegram(message):
    """Gửi tin nhắn cảnh báo về Telegram của anh Vũ"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("Đã gửi tin nhắn Telegram thành công!")
        else:
            print(f"Lỗi gửi Telegram (Mã {res.status_code}):", res.text)
    except Exception as e:
        print("Lỗi kết nối Telegram:", e)


def get_top_100_symbols():
    """Lấy danh sách Top 100 coin có khối lượng giao dịch lớn nhất từ sàn Bybit"""
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        resp = requests.get(url, timeout=10).json()
        ticker_list = resp.get("result", {}).get("list", [])
        
        # Lọc các cặp USDT
        usdt_pairs = [x for x in ticker_list if x.get("symbol", "").endswith("USDT")]
        
        # Sắp xếp theo khối lượng 24h giảm dần và lấy Top 100
        usdt_pairs = sorted(usdt_pairs, key=lambda x: float(x.get("turnover24h", 0)), reverse=True)[:100]
        return [x["symbol"] for x in usdt_pairs]
    except Exception as e:
        print("Lỗi khi lấy danh sách coin:", e)
        return []


def scan_symbol(symbol):
    """Quét dữ liệu nến 1H và kiểm tra bộ lọc chuẩn Sóng N +
