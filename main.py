import os
import time
import asyncio
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, EnvelopeEvent

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Số giây còn lại trước khi mở rương thì bot mới gửi thông báo
ALERT_BEFORE_SECONDS = 45

# Danh sách các tài khoản TikTok cần theo dõi
CHANNELS = [
    "hongthao060",
    "violetadragomir09",
    "ellenaariette",
    "pedrogaming1k",
    "duoc.lieu.rung.397407302",
    "kgl.045",
]

active_listeners = set()
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

async def schedule_box_alert(username: str, diamond_count, unpack_at: int):
    """Đợi đến khi rương còn đúng 45 giây mới gửi thông báo về Telegram"""
    now = time.time()
    # Tính thời gian cần đợi = (Mốc mở rương - 45 giây) - Thời điểm hiện tại
    wait_time = (unpack_at - ALERT_BEFORE_SECONDS) - now

    if wait_time > 0:
        print(f"[HẸN GIỜ] Rương tại @{username} ({diamond_count} xu) sẽ báo sau {int(wait_time)} giây nữa...")
        await asyncio.sleep(wait_time)

    # Tính lại số giây thực tế còn lại ngay lúc gửi
    remaining = max(0, int(unpack_at - time.time()))
    live_url = f"https://tiktok.com@{username}/live"

    msg = (
        f"⏰ SẮP MỞ RƯƠNG XU (CÒN {remaining} GIÂY)!\n"
        f"👤 Kênh: @{username}\n"
        f"💎 Giá trị: {diamond_count} xu\n"
        f"👉 Vào húp ngay: {live_url}"
    )
    send_telegram(msg)
    print(f"[ĐÃ BÁO 45S] Bắn link @{username} ({diamond_count} xu)")

async def listen_room_for_coins(username: str):
    """Kết nối vào phòng đang live để rình sự kiện Rương Xu"""
    active_listeners.add(username)
    client = TikTokLiveClient(unique_id=f"@{username}")

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"[ĐÃ VÀO PHÒNG] Đang canh rương tại @{username}")

    @client.on(EnvelopeEvent)
    async def on_envelope(event: EnvelopeEvent):
        try:
            box_id = getattr(event.envelope_info, "envelope_id", str(time.time()))
            if box_id in notified_boxes:
                return
            notified_boxes.add(box_id)

            diamond_count = getattr(event.envelope_info, "diamond_count", "Không rõ")
            unpack_at = getattr(event.envelope_info, "unpack_at", 0)

            if unpack_at and unpack_at > time.time():
                # Chạy tác vụ hẹn giờ ngầm để không làm nghẽn việc bắt các rương khác
                asyncio.create_task(schedule_box_alert(username, diamond_count, unpack_at))
            else:
                # Nếu không lấy được mốc thời gian mở thì báo ngay lập tức
                live_url = f"https://tiktok.com@{username}/live"
                msg = (
                    f"🎁 PHÁT HIỆN RƯƠNG XU!\n"
                    f"👤 Kênh: @{username}\n"
                    f"💎 Giá trị: {diamond_count} xu\n"
                    f"👉 Vào ngay: {live_url}"
                )
                send_telegram(msg)
        except Exception as e:
            print(f"Lỗi xử lý rương tại @{username}: {e}")

    try:
        await client.start()
    except Exception as e:
        print(f"[NGẮT KẾT NỐI] Phòng @{username} đã tắt live hoặc bị chặn: {e}")
    finally:
        if username in active_listeners:
            active_listeners.remove(username)

async def main():
    print("San Ruong Xu Bot (Báo trước 45s) started!")
    send_telegram(
        f"✅ Bot Săn Rương Xu đã khởi động!\n"
        f"⏱ Chế độ: Báo trước khi mở {ALERT_BEFORE_SECONDS} giây\n"
        f"📋 Đang theo dõi {len(CHANNELS)} kênh."
    )

    while True:
        for username in CHANNELS:
            if username not in active_listeners:
                try:
                    checker = TikTokLiveClient(unique_id=f"@{username}")
                    if await checker.is_live():
                        asyncio.create_task(listen_room_for_coins(username))
                except Exception as e:
                    print(f"Lỗi kiểm tra live @{username}: {e}")

            await asyncio.sleep(1.5)

        await asyncio.sleep(25)

if __name__ == "__main__":
    asyncio.run(main())
