import os
import re
import time
import random
import asyncio
import logging
import urllib.request
import urllib.parse
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, EnvelopeEvent, RoomUserSeqEvent, UnknownEvent

logging.getLogger("TikTokLive").setLevel(logging.CRITICAL)

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
]

active_listeners = set()
scheduled_keys = set()
room_viewers = {}

REWARD_KEYWORDS = [
    "envelope", "treasure", "box", "chest", "redpacket",
    "goody", "bag", "drop", "bonus", "award", "coindrop"
]

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
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as res:
            pass
    except Exception as e:
        print("Lỗi gửi Telegram:", e)

def build_live_url(username: str):
    domain = ".".join(["www", "tiktok", "com"])
    return "https://" + domain + "/@" + username + "/live"

def decode_varints_from_bytes(raw_bytes):
    if not isinstance(raw_bytes, (bytes, bytearray)):
        return []
    numbers = []
    i = 0
    n = len(raw_bytes)
    while i < n:
        val = 0
        shift = 0
        start = i
        while i < n and shift < 64:
            b = raw_bytes[i]
            i += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80):
                if val > 0:
                    numbers.append(val)
                break
            shift += 7
        else:
            i = start + 1
    return numbers

def parse_reward_details(obj):
    open_at = 0.0
    coins = None
    slots = None
    now = time.time()

    def walk(item, depth=0):
        nonlocal open_at, coins, slots
        if item is None or depth > 4:
            return
        if isinstance(item, (bytes, bytearray)):
            nums = decode_varints_from_bytes(item)
            small_nums = []
            for num in nums:
                ts = num / 1000.0 if num > 1e11 else float(num)
                if now + 5 < ts < now + 1800 and open_at == 0.0:
                    open_at = ts
                elif 1 <= num <= 50000:
                    small_nums.append(num)
            if coins is None and len(small_nums) >= 2:
                candidates = sorted(set(small_nums), reverse=True)
                for c in candidates:
                    for s in candidates:
                        if c >= s and 1 <= s <= 500 and c <= 20000:
                            coins, slots = c, s
                            break
                    if coins is not None:
                        break
            return

        time_keys = ["unpack_at", "open_at", "end_time", "expire_time", "draw_time", "target_time"]
        coin_keys = ["diamond_count", "coin_count", "total_diamond", "reward_amount"]
        people_keys = ["people_count", "winner_count", "total_count", "max_count", "user_count"]

        entries = item.items() if isinstance(item, dict) else (vars(item).items() if hasattr(item, "__dict__") else [])
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
    """Hẹn giờ về 40s; nếu rương/túi đã trôi qua 40s (còn từ 8s - 39s) thì gửi ngay lập tức"""
    if open_at > 1e11:
        open_at = open_at / 1000.0

    unique_key = f"{username}:{int(open_at // 10)}"
    if unique_key in scheduled_keys:
        return
    scheduled_keys.add(unique_key)

    now = time.time()
    seconds_left = open_at - now

    # Nếu còn quá ít thời gian (dưới 8 giây) thì bỏ qua vì bấm vào không kịp húp
    if seconds_left < 8:
        return

    wait_time = seconds_left - ALERT_BEFORE_SECONDS
    if wait_time > 0:
        print(f"[HẸN GIỜ 40S] {type_icon} @{username} ({coins} xu / {slots} suất) báo sau {int(wait_time)}s...")
        await asyncio.sleep(wait_time)

    remaining = max(0, int(round(open_at - time.time())))
    viewers = room_viewers.get(username, "?")

    msg = (
        f"{type_icon} ⏰ {remaining}s\n"
        f"👤 @{username}\n"
        f"💎 {coins} ({slots})\n"
        f"👁️ {viewers}"
    )
    send_telegram(msg, web_link=build_live_url(username))
    print(f"[ĐÃ BÁO {remaining}S] @{username} | {coins} ({slots}) | View: {viewers}")

async def listen_room_for_coins(username: str):
    active_listeners.add(username)
    client = TikTokLiveClient(unique_id=f"@{username}")

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"[ĐÃ VÀO PHÒNG] Đang canh tại @{username}")
        try:
            room_data = getattr(client, "room_info", None)
            if room_data:
                user_count = room_data.get("user_count") if isinstance(room_data, dict) else getattr(room_data, "user_count", None)
                if user_count:
                    room_viewers[username] = int(user_count)

                # Quét rương/túi đã thả sẵn từ trước (kể cả khi chỉ còn 10s - 39s)
                def scan_init(node, depth=0):
                    if node is None or depth > 4:
                        return
                    entries = node.items() if isinstance(node, dict) else (vars(node).items() if hasattr(node, "__dict__") else [])
                    for k, v in entries:
                        k_str = str(k).lower()
                        if k_str.startswith("_"):
                            continue
                        if any(rk in k_str for rk in ["envelope", "goody", "treasure", "redpacket", "box"]) and v:
                            open_at, coins, slots = parse_reward_details(v)
                            if open_at > time.time() + 8 and coins and slots:
                                icon = "🛍️" if ("goody" in k_str or "bag" in k_str) else ("🎁" if "envelope" in k_str else "📦")
                                asyncio.create_task(schedule_reward_alert(username, icon, coins, slots, open_at))
                        elif isinstance(v, (dict, list)) or hasattr(v, "__dict__"):
                            for sub in (v[:5] if isinstance(v, list) else [v]):
                                scan_init(sub, depth + 1)

                scan_init(room_data)
        except Exception as e:
            print(f"Lỗi quét khởi tạo @{username}: {e}")

    @client.on(RoomUserSeqEvent)
    async def on_user_seq(event: RoomUserSeqEvent):
        total = getattr(event, "total", None) or getattr(event, "viewer_count", None)
        if total is not None:
            room_viewers[username] = int(total)

    @client.on(EnvelopeEvent)
    async def on_envelope(event: EnvelopeEvent):
        try:
            info = getattr(event, "envelope_info", event)
            open_at, coins, slots = parse_reward_details(info)
            if open_at > time.time() + 8 and coins and slots:
                asyncio.create_task(schedule_reward_alert(username, "🎁", coins, slots, open_at))
        except Exception as e:
            print(f"Lỗi rương xu @{username}: {e}")

    @client.on(UnknownEvent)
    async def on_unknown(event: UnknownEvent):
        raw_type = str(getattr(event, "type", ""))
        base_msg = getattr(event, "base_message", None)
        method_name = str(getattr(base_msg, "method", "")) if base_msg else ""
        raw_payload = str(getattr(event, "payload", b""))[:300]
        full_sig = f"{type(event).__name__} {raw_type} {method_name} {raw_payload}".lower()

        if any(k in full_sig for k in REWARD_KEYWORDS):
            open_at, coins, slots = parse_reward_details(event)
            if open_at > time.time() + 8 and coins and slots:
                icon = "🛍️" if ("goody" in full_sig or "bag" in full_sig) else "📦"
                asyncio.create_task(schedule_reward_alert(username, icon, coins, slots, open_at))

    try:
        await client.start()
    except Exception as e:
        print(f"[NGẮT KẾT NỐI] @{username}: {e}")
    finally:
        await asyncio.sleep(30)
        active_listeners.discard(username)
        room_viewers.pop(username, None)

async def main():
    print("San Ruong & Tui Qua Bot (17 Kenh - 40s & 10-39s Immediate) started!")
    send_telegram(f"✅ Bot 17 Kênh đã khởi động! Báo ở mốc 40s (hoặc báo ngay nếu còn 10s-39s).")
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




