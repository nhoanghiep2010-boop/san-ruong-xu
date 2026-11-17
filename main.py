import os
import re
import time
import random
import asyncio
import logging
import urllib.request
import urllib.parse
from TikTokLive import TikTokLiveClient, events
from TikTokLive.events import ConnectEvent, EnvelopeEvent, RoomUserSeqEvent

logging.basicConfig(level=logging.CRITICAL)
logging.getLogger("TikTokLive").setLevel(logging.CRITICAL)
logging.getLogger("betterproto").setLevel(logging.CRITICAL)

RAW_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "").strip()

match = re.search(r"\d+:[A-Za-z0-9_-]+", RAW_TOKEN)
BOT_TOKEN = match.group(0).lstrip(":") if match else RAW_TOKEN.strip().lstrip(":")

ALERT_BEFORE_SECONDS = 40

CHANNELS = [
    "hongthao060",
    "violetadragomir09",
    "ellenaariette",
    "pedrogaming1k",
    "duoc.lieu.rung.397407302",
    "kgl.045",
    "nazzywuzzyyyy",
    "sorry_to_bother.you",
    "ropinoe.an",
    "marius21.02.1992",
    "eri17.06.15",
    "vic.nguyen68",
    "luxagency6",
    "bsd5555sg",
    "tribalchief503",
    "the_dreamer104",
    "umid.geldi.zirvee",
    "manaro47",
]

active_listeners = set()
scheduled_keys = set()
room_viewers = {}

def send_telegram(message, web_link=None):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = "https://api." + "telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    full_text = f"{message}\n🔗 {web_link}" if web_link else message
    payload = {
        "chat_id": CHAT_ID,
        "text": full_text,
        "disable_web_page_preview": True
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as res:
                if res.status == 200:
                    print("[TELEGRAM OK] Đã gửi tin nhắn thành công!")
                    return
        except Exception as e:
            print(f"Lỗi gửi Telegram (lần {attempt + 1}):", e)
            time.sleep(2)

def build_live_url(username: str):
    domain = ".".join(["www", "tiktok", "com"])
    return "https://" + domain + "/@" + username + "/live"

def parse_envelope_details(obj):
    open_at = 0.0
    coins = None
    slots = None
    now = time.time()

    def walk(item, depth=0):
        nonlocal open_at, coins, slots
        if item is None or depth > 4:
            return
        time_keys = ("unpack_at", "open_at", "end_time", "expire_time")
        coin_keys = ("diamond_count", "coin_count", "total_diamond", "reward_amount")
        people_keys = ("people_count", "winner_count", "total_count", "max_count")

        entries = item.items() if isinstance(item, dict) else (vars(item).items() if hasattr(item, "__dict__") else ())
        for k, v in entries:
            k_str = str(k).lower()
            if k_str.startswith("_"):
                continue
            if isinstance(v, (int, float)) and v > 0:
                if open_at == 0.0 and any(tk in k_str for tk in time_keys):
                    ts = v / 1000.0 if v > 1e11 else float(v)
                    if now + 5 < ts < now + 1800:
                        open_at = ts
                elif coins is None and any(ck in k_str for ck in coin_keys):
                    coins = int(v)
                elif slots is None and any(pk in k_str for pk in people_keys):
                    slots = int(v)
            else:
                walk(v, depth + 1)

    walk(obj)
    return open_at, coins, slots

async def schedule_reward_alert(username: str, type_icon: str, coins, slots, open_at: float):
    try:
        if open_at > 1e11:
            open_at = open_at / 1000.0

        unique_key = f"{username}:{int(open_at // 10)}"
        if unique_key in scheduled_keys:
            return
        scheduled_keys.add(unique_key)

        now = time.time()
        seconds_left = open_at - now
        if seconds_left < 8:
            return

        wait_time = seconds_left - ALERT_BEFORE_SECONDS
        if wait_time > 0:
            print(f"[HẸN GIỜ 40S] {type_icon} @{username} ({coins} xu / {slots} suất) báo sau {int(wait_time)}s...")
            end_wait = time.time() + wait_time
            while time.time() < end_wait:
                await asyncio.sleep(min(1.0, end_wait - time.time()))

        remaining = max(0, int(round(open_at - time.time())))
        viewers = room_viewers.get(username, "?")

        msg = (
            f"{type_icon} ⏰ {remaining}s\n"
            f"👤 @{username}\n"
            f"💎 {coins} ({slots})\n"
            f"👁️ {viewers}"
        )
        print(f"[ĐANG BÁO {remaining}S] @{username} | {coins} ({slots}) | View: {viewers}")
        await asyncio.to_thread(send_telegram, msg, build_live_url(username))
    except Exception as e:
        print(f"[LỖI HẸN GIỜ] @{username}: {e}")

async def listen_room_for_coins(username: str):
    active_listeners.add(username)
    client = TikTokLiveClient(unique_id=f"@{username}")

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"[ĐÃ VÀO PHÒNG] Đang canh Rương & Túi tại @{username}")
        try:
            room_data = getattr(client, "room_info", None)
            if room_data:
                user_count = room_data.get("user_count") if isinstance(room_data, dict) else getattr(room_data, "user_count", None)
                if user_count:
                    room_viewers[username] = int(user_count)
        except Exception:
            pass

    @client.on(RoomUserSeqEvent)
    async def on_user_seq(event: RoomUserSeqEvent):
        total = getattr(event, "total", None) or getattr(event, "viewer_count", None)
        if total is not None:
            room_viewers[username] = int(total)

    @client.on(EnvelopeEvent)
    async def on_envelope(event: EnvelopeEvent):
        try:
            info = getattr(event, "envelope_info", event)
            open_at, coins, slots = parse_envelope_details(info)
            if open_at > time.time() + 8 and coins and slots:
                asyncio.create_task(schedule_reward_alert(username, "🎁", coins, slots, open_at))
        except Exception as e:
            print(f"Lỗi rương xu @{username}: {e}")

    # Bắt Sóng Trực Tiếp: Gửi ngay mọi gói tin sự kiện/túi quà mới xuất hiện trong phòng về Telegram
    @client.on(events.Event)
    async def on_catch_all_bags(event):
        ev_name = type(event).__name__
        b_msg = getattr(event, "base_message", None)
        m_name = str(getattr(b_msg, "method", "")) if b_msg else ""
        sig = f"{ev_name} {m_name}".lower()

        # Loại bỏ các sự kiện tương tác thông thường để chỉ giữ lại gói tin Túi Quà / Sự Kiện
        normal_events = (
            "like", "chat", "member", "social", "roomuser", "gift",
            "follow", "share", "emote", "envelope", "connect", "disconnect",
            "linklayer", "linkmic", "fan", "rank", "poll", "question",
            "websocket", "proto", "heartbeat", "ping", "pong", "control"
        )
        if any(w in sig for w in normal_events):
            return

        # Khóa chống spam 180 giây cho mỗi loại sự kiện trong cùng phòng
        bag_key = f"{username}:{ev_name}:{m_name}:{int(time.time() // 180)}"
        if bag_key in scheduled_keys:
            return
        scheduled_keys.add(bag_key)

        viewers = room_viewers.get(username, "?")
        tag = m_name if m_name else ev_name
        msg = (
            f"🛍️ ⏰ Mới thả ({tag})\n"
            f"👤 @{username}\n"
            f"👁️ {viewers}"
        )
        print(f"[BẮT ĐƯỢC SỰ KIỆN/TÚI] @{username} -> {tag}")
        await asyncio.to_thread(send_telegram, msg, build_live_url(username))

    try:
        await client.start()
    except Exception as e:
        print(f"[NGẮT KẾT NỐI] @{username}: {e}")
    finally:
        await asyncio.sleep(30)
        active_listeners.discard(username)
        room_viewers.pop(username, None)

async def main():
    print("San Ruong & Bat Song Tui Qua Bot (18 Kenh) started!")
    send_telegram(f"✅ Bot Bắt Sóng Túi Quà & Rương Xu đã khởi động! Đang canh {len(CHANNELS)} kênh.")
    while True:
        for username in CHANNELS:
            if username not in active_listeners:
                try:
                    checker = TikTokLiveClient(unique_id=f"@{username}")
                    if await checker.is_live():
                        asyncio.create_task(listen_room_for_coins(username))
                except Exception as e:
                    if "Expecting value" in str(e):
                        await asyncio.sleep(10)
                    else:
                        print(f"Lỗi kiểm tra @{username}: {e}")
            await asyncio.sleep(random.uniform(2.5, 4.0))
        await asyncio.sleep(20)

if __name__ == "__main__":
    asyncio.run(main())




