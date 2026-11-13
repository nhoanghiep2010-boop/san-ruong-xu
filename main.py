
import os
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

CHECK_INTERVAL = 30

sent_links = set()

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Thiếu BOT_TOKEN hoặc CHAT_ID")
        return

    try:
        requests.post(
            API_URL,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": False
            },
            timeout=15
        )
    except requests.RequestException as e:
        print("Lỗi Telegram:", e)

def scan_livestreams():
    # Chưa có API/nguồn dữ liệu TikTok để phát hiện rương.
    # Không tự tạo link hoặc báo rương giả.
    print("Đang chờ nguồn dữ liệu livestream TikTok...")

def main():
    def main():
    print("San Ruong Xu Bot started!")
    send_telegram("✅ Bot Săn Rương Xu đã khởi động!")
print("San Ruong Xu Bot started!")

    while True:
        try:
            scan_livestreams()
        except Exception as e:
            print("Lỗi:", e)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
