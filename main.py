import os
import re
import time
import asyncio
import urllib.request
import urllib.parse
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, EnvelopeEvent

RAW_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "").strip()

match = re.search(r"\d+:[A-Za-z0-9_-]+", RAW_TOKEN)
BOT_TOKEN = match.group(0).lstrip(":") if match else RAW_TOKEN.strip().lstrip(":")

# Thời gian báo trước khi mở thưởng (40 giây cho cả 3 loại)
ALERT_BEFORE_SECONDS = 40

CHANNELS = [
    "hongthao060",
    "violetadragomir09",
    "ellenaariette",
    "pedrogaming1k",
    "duoc.lieu.rung.397407302",
    "kgl.045",
    "nazzywuzzyyyy",
]

active_listeners = set()
notified_items = set()
last_event_alert = {}

REWARD_KEYWORDS = [
    "envelope",     # Rương xu / Lì xì
    "treasure",     # Rương kho báu
    "box",          # Rương sự kiện / Hộp quà
    "chest",        # Rương báu vật
    "redpacket",    # Hồng bao / Lì xì đỏ
    "goody",        # Túi may mắn (Goody Bag)
    "bag",          # Túi quà
    "drop",         # Rơi quà sự kiện
    "bonus",        # Rương thưởng
    "award",        # Quà sự kiện
]

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Thiếu BOT_TOKEN hoặc CHAT_ID!")
        return

    url = "https://api." + "telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": "false",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as res:
            if res.status != 200:
                print("Telegram báo lỗi:", res.read().decode("utf-8"))
    except Exception as e:
        print("Lỗi gửi Telegram:", e)

def extract_open_time(obj, depth=0) -> float:
    """Tự động tìm mốc thời gian mở thưởng bên trong gói tin Rương / Túi Quà"""
    if obj is None or depth > 3:
        return 0.0

    time_keys = ["unpack_at", "open_at", "end_time", "expire_time", "draw_time", "target_time"]
    now = time.time()

    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(tk in str(k).lower() for tk in time_keys) and isinstance(v, (int, float)):
                ts = v / 1000.0 if v > 1e11 else float(v)
                if now < ts < now + 3600:
                    return ts
            res = extract_open_time(v, depth + 1)
            if res > 0:
                return res
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            if k.startswith("_"):
                continue
            if any(tk in str(k).lower() for tk in time_keys) and isinstance(v, (int, float)):
                ts = v / 1000.0 if v > 1e11 else float(v)
                if now < ts < now + 3600:
                    return ts
            res = extract_open_time(v, depth + 1)
            if res > 0:
                return res
    return 0.0

async def schedule_reward_alert(username: str, title: str, detail_line: str, open_at: float):
    """Đợi đến khi còn đúng 40 giây mới gửi thông báo về Telegram"""
    now = time.time()
    if open_at > 1e11:
        open_at = open_at / 1000.0

    wait_time = (open_at - ALERT_BEFORE_SECONDS) - now

    if wait_time > 0:
        print(f"[HẸN GIỜ 40S] {title} tại @{username} sẽ báo sau {int(wait_time)} giây...")
        await asyncio.sleep(wait_time)

    remaining = max(0, int(open_at - time.time()))
    live_url = f"https://tiktok.com@{username}/live"

    msg = (
        f"⏰ {title} (CÒN {remaining} GIÂY)!\n"
        f"👤 Kênh: @{username}\n"
        f"{detail_line}\n"
        f"👉 Vào húp ngay: {live_url}"
    )
    send_telegram(msg)
    print(f"[ĐÃ BÁO 40S] Bắn link {title} tại @{username}")

async def listen_room_for_coins(username: str):
    active_listeners.add(username)
    client = TikTokLiveClient(unique_id=f"@{username}")

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"[ĐÃ VÀO PHÒNG] Đang canh Rương Xu + Rương Sự Kiện + Túi Quà tại @{username}")

    # 1. Xử lý Rương Xu / Lì Xì (EnvelopeEvent)
    @client.on(EnvelopeEvent)
    async def on_envelope(event: EnvelopeEvent):
        try:
            info = getattr(event, "envelope_info", event)
            box_id = str(getattr(info, "envelope_id", time.time()))
            if box_id in notified_items:
                return
            notified_items.add(box_id)

            diamond_count = getattr(info, "diamond_count", "Không rõ")
            open_at = float(getattr(info, "unpack_at", 0))
            if open_at <= 0:
                open_at = extract_open_time(event)

            print(f"[RƯƠNG XU] @{username} | Xu: {diamond_count} | Open_at: {open_at}")

            if open_at > 0:
                asyncio.create_task(
                    schedule_reward_alert(username, "SẮP MỞ RƯƠNG XU", f"💎 Giá trị: {diamond_count} xu", open_at)
                )
            else:
                live_url = f"https://tiktok.com@{username}/live"
                send_telegram(f"🎁 PHÁT HIỆN RƯƠNG XU tại @{username} ({diamond_count} xu)!\n👉 Vào ngay: {live_url}")
        except Exception as e:
            print(f"Lỗi xử lý rương xu tại @{username}: {e}")

    # 2. Xử lý Rương Quà Sự Kiện và Túi Quà (GoodyBag)
    @client.on("*")
    async def on_any_event(event):
        event_name = type(event).__name__
        if event_name == "EnvelopeEvent":
            return

        raw_type = str(getattr(event, "type", ""))
        full_signature = f"{event_name} {raw_type}".lower()

        if any(k in full_signature for k in REWARD_KEYWORDS):
            alert_key = f"{username}:{event_name}:{raw_type}"
            now = time.time()
            if now - last_event_alert.get(alert_key, 0) < 30:
                return
            last_event_alert[alert_key] = now

            if "goody" in full_signature or "bag" in full_signature:
                title = "🛍️ SẮP MỞ TÚI QUÀ"
            else:
                title = "🎁 SẮP MỞ RƯƠNG SỰ KIỆN"

            detail = raw_type if raw_type else event_name
            open_at = extract_open_time(event)

            print(f"[{title}] @{username} | Loại: {detail} | Open_at: {open_at}")

            if open_at > 0:
                asyncio.create_task(
                    schedule_reward_alert(username, title, f"📦 Loại: {detail}", open_at)
                )
            else:
                live_url = f"https://tiktok.com@{username}/live"
                send_telegram(
                    f"{title} XUẤT HIỆN!\n"
                    f"👤 Kênh: @{username}\n"
                    f"📦 Loại: {detail}\n"
                    f"👉 Vào phòng ngay: {live_url}"
                )

    try:
        await client.start()
    except Exception as e:
        print(f"[NGẮT KẾT NỐI] Phòng @{username}: {e}")
    finally:
        if username in active_listeners:
            active_listeners.remove(username)

async def main():
    print(f"San Ruong & Tui Qua Bot (Báo trước {ALERT_BEFORE_SECONDS}s) started!")
    send_telegram(
        f"✅ Bot Săn Rương & Túi Quà đã khởi động!\n"
        f"⏱ Chế độ: Báo Rương Xu + Rương Sự Kiện + Túi Quà khi còn {ALERT_BEFORE_SECONDS} giây\n"
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

        await asyncio.sleep(15)

if __name__ == "__main__":
    asyncio.run(main())
