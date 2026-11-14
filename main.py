import os
import time
import asyncio
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, EnvelopeEvent

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Danh sách các tài khoản TikTok cần theo dõi
CHANNELS = [
    "hongthao060",
    "violetadragomir09",
    "ellenaariette",
    "pedrogaming1k",
    "duoc.lieu.rung.397407302",
    "kgl.045",
]

# Lưu các phòng đang được bot kết nối lắng nghe
active_listeners = set()
# Lưu ID rương đã báo để tránh gửi trùng
notified_boxes = set()

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Thiếu BOT_TOKEN hoặc CHAT_ID!")
        return
    url = f"https://telegram.org{BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
    except Exception as e:
        print("Lỗi gửi Telegram:", e)

async def listen_room_for_coins(username: str):
    """Kết nối vào phòng đang live để rình sự kiện Rương Xu (EnvelopeEvent)"""
    active_listeners.add(username)
    client = TikTokLiveClient(unique_id=f"@{username}")

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"[ĐÃ VÀO PHÒNG] Đang canh rương tại @{username}")

    @client.on(EnvelopeEvent)
    async def on_envelope(event: EnvelopeEvent):
        try:
            # Lấy mã định danh của rương để chống báo trùng
            box_id = getattr(event.envelope_info, "envelope_id", str(time.time()))
            if box_id in notified_boxes:
                return
            notified_boxes.add(box_id)

            diamond_count = getattr(event.envelope_info, "diamond_count", "Không rõ")
            live_url = f"https://tiktok.com@{username}/live"
            msg = (
                f"🎁 PHÁT HIỆN RƯƠNG XU!\n"
                f"👤 Kênh: @{username}\n"
                f"💎 Tổng giá trị: {diamond_count} xu\n"
                f"👉 Vào húp ngay: {live_url}"
            )
            send_telegram(msg)
            print(f"[RƯƠNG XU] Đã bắn link từ @{username} ({diamond_count} xu)")
        except Exception as e:
            print(f"Lỗi xử lý dữ liệu rương tại @{username}: {e}")

    try:
        await client.start()
    except Exception as e:
        print(f"[NGẮT KẾT NỐI] Phòng @{username} đã tắt live hoặc bị chặn: {e}")
    finally:
        if username in active_listeners:
            active_listeners.remove(username)

async def main():
    print("San Ruong Xu Bot (Chế độ rình rương) started!")
    send_telegram(f"✅ Bot Săn Rương Xu (Chế độ bắt Rương) đã chạy! Đang theo dõi {len(CHANNELS)} kênh.")

    while True:
        for username in CHANNELS:
            if username not in active_listeners:
                try:
                    checker = TikTokLiveClient(unique_id=f"@{username}")
                    if await checker.is_live():
                        # Tạo luồng chạy ngầm chui vào phòng này để rình rương
                        asyncio.create_task(listen_room_for_coins(username))
                except Exception as e:
                    print(f"Lỗi kiểm tra live @{username}: {e}")

            await asyncio.sleep(1.5)

        # Kiểm tra lại các kênh chưa live sau mỗi 25 giây
        await asyncio.sleep(25)

if __name__ == "__main__":
    asyncio.run(main())
