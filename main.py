import os
import re
import json
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
]

active_listeners = set()
notified_items = set()
last_event_alert = {}
room_viewers = {}

REWARD_KEYWORDS = [
    "envelope", "treasure", "box", "chest", "redpacket",
    "goody", "bag", "drop", "bonus", "award", "coindrop"
]

def send_telegram(message, web_link=None):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = "https://api." + "telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "disable_web_page_preview": True}
    if web_link and web_link.startswith("http"):
        payload["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": "📱 MỞ PHÒNG LIVE TIKTOK", "url": web_link}]]})
    data = urllib.parse.urlencode(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as res:
            pass
    except Exception as e:
        print("Lỗi gửi Telegram:", e)

def build_live_url(username: str):
      return "https://" + "://tiktok.com" + "/@" + username + "/live"


def extract_open_time(obj, depth=0) -> float:
    if obj is None or depth > 4:
        return 0.0
    time_keys = ["unpack_at", "open_at", "end_time", "expire_time", "draw_time", "target_time"]
    now = time.time()
    items = obj.items() if isinstance(obj, dict) else (vars(obj).items() if hasattr(obj, "__dict__") else [])
    for k, v in items:
        if str(k).startswith("_"):
            continue
        if any(tk in str(k).lower() for tk in time_keys) and isinstance(v, (int, float)):
            ts = v / 1000.0 if v > 1e11 else float(v)
            if now < ts < now + 3600:
                return ts
        res = extract_open_time(v, depth + 1)
        if res > 0:
            return res
    return 0.0

def extract_reward_stats(obj, depth=0):
    coins, people = None, None
    if obj is None or depth > 4:
        return coins, people
    coin_keys = ["diamond_count", "coin_count", "total_diamond", "reward_amount"]
    people_keys = ["people_count", "winner_count", "total_count", "max_count", "user_count"]
    items = obj.items() if isinstance(obj, dict) else (vars(obj).items() if hasattr(obj, "__dict__") else [])
    for k, v in items:
        k_str = str(k).lower()
        if k_str.startswith("_"):
            continue
        if isinstance(v, (int, float)) and v > 0:
            if coins is None and any(ck in k_str for ck in coin_keys):
                coins = int(v)
            elif people is None and any(pk in k_str for pk in people_keys):
                people = int(v)
        elif isinstance(v, (dict, object)):
            sub_c, sub_p = extract_reward_stats(v, depth + 1)
            if coins is None:
                coins = sub_c
            if people is None:
                people = sub_p
    return coins, people

def scan_dict_for_existing_rewards(obj, found_list, depth=0):
    if obj is None or depth > 4:
        return
    items = obj.items() if isinstance(obj, dict) else (vars(obj).items() if hasattr(obj, "__dict__") else [])
    for k, v in items:
        k_str = str(k).lower()
        if k_str.startswith("_"):
            continue
        if any(rk in k_str for rk in ["envelope", "goody", "treasure", "redpacket", "box"]):
            if v and v != [] and v != {}:
                found_list.append((k_str, v))
        elif isinstance(v, (dict, list)) or hasattr(v, "__dict__"):
            if isinstance(v, list):
                for item in v[:5]:
                    scan_dict_for_existing_rewards(item, found_list, depth + 1)
            else:
                scan_dict_for_existing_rewards(v, found_list, depth + 1)

async def schedule_reward_alert(username: str, title: str, coins, slots, open_at: float):
    now = time.time()
    if open_at > 1e11:
        open_at = open_at / 1000.0
    wait_time = (open_at - ALERT_BEFORE_SECONDS) - now
    if wait_time > 0:
        print(f"[HẸN GIỜ 40S] {title} tại @{username} sẽ báo sau {int(wait_time)}s...")
        await asyncio.sleep(wait_time)
    remaining = max(0, int(open_at - time.time()))
    viewers = room_viewers.get(username, "?")
    type_icon = "🛍️" if "TÚI" in title else ("🎁" if "RƯƠNG XU" in title else "📦")
    coin_text = f"{coins}" if coins else "-"
    slots_text = f"({slots})" if slots else ""
    msg = f"{type_icon} ⏰ {remaining}s\n👤 @{username}\n💎 {coin_text} {slots_text}\n👁️ {viewers}"
    send_telegram(msg, web_link=build_live_url(username))
    print(f"[ĐÃ BÁO {remaining}S] @{username} | {coin_text} {slots_text} | View: {viewers}")

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
                existing = []
                scan_dict_for_existing_rewards(room_data, existing)
                for key_name, val in existing:
                    alert_key = f"{username}:init:{key_name}"
                    if time.time() - last_event_alert.get(alert_key, 0) < 45:
                        continue
                    last_event_alert[alert_key] = time.time()
                    title = "TÚI QUÀ" if ("goody" in key_name or "bag" in key_name) else ("RƯƠNG XU" if "envelope" in key_name else "RƯƠNG SỰ KIỆN")
                    coins, slots = extract_reward_stats(val)
                    open_at = extract_open_time(val)
                    if open_at > time.time():
                        asyncio.create_task(schedule_reward_alert(username, title, coins, slots, open_at))
                    elif coins or slots:
                        viewers = room_viewers.get(username, "?")
                        type_icon = "🛍️" if "TÚI" in title else ("🎁" if "RƯƠNG XU" in title else "📦")
                        send_telegram(f"{type_icon} ⏰ Có sẵn\n👤 @{username}\n💎 {coins or '-'} ({slots or '?'})\n👁️ {viewers}", web_link=build_live_url(username))
        except Exception as e:
            print(f"Lỗi quét dữ liệu khởi tạo @{username}: {e}")

    @client.on(RoomUserSeqEvent)
    async def on_user_seq(event: RoomUserSeqEvent):
        total = getattr(event, "total", None) or getattr(event, "viewer_count", None)
        if total is not None:
            room_viewers[username] = int(total)

    @client.on(EnvelopeEvent)
    async def on_envelope(event: EnvelopeEvent):
        try:
            info = getattr(event, "envelope_info", event)
            box_id = str(getattr(info, "envelope_id", time.time()))
            if box_id in notified_items:
                return
            notified_items.add(box_id)
            coins, slots = extract_reward_stats(info)
            open_at = float(getattr(info, "unpack_at", 0)) or extract_open_time(event)
            if open_at > 0:
                asyncio.create_task(schedule_reward_alert(username, "RƯƠNG XU", coins, slots, open_at))
            else:
                viewers = room_viewers.get(username, "?")
                send_telegram(f"🎁 ⏰ Ngay\n👤 @{username}\n💎 {coins or '-'} ({slots or '?'})\n👁️ {viewers}", web_link=build_live_url(username))
        except Exception as e:
            print(f"Lỗi rương xu @{username}: {e}")

    @client.on(UnknownEvent)
    async def on_unknown(event: UnknownEvent):
        raw_type = str(getattr(event, "type", ""))
        base_msg = getattr(event, "base_message", None)
        method_name = str(getattr(base_msg, "method", "")) if base_msg else ""
        raw_payload = str(getattr(event, "payload", b""))[:300]
        full_signature = f"{type(event).__name__} {raw_type} {method_name} {raw_payload}".lower()
        if any(k in full_signature for k in REWARD_KEYWORDS):
            sig_id = method_name or raw_type or "unknown_reward"
            alert_key = f"{username}:{sig_id}"
            now = time.time()
            if now - last_event_alert.get(alert_key, 0) < 30:
                return
            last_event_alert[alert_key] = now
            title = "TÚI QUÀ" if ("goody" in full_signature or "bag" in full_signature) else "RƯƠNG SỰ KIỆN"
            coins, slots = extract_reward_stats(event)
            open_at = extract_open_time(event)
            if open_at > 0:
                asyncio.create_task(schedule_reward_alert(username, title, coins, slots, open_at))
            else:
                viewers = room_viewers.get(username, "?")
                type_icon = "🛍️" if "TÚI" in title else "📦"
                send_telegram(f"{type_icon} ⏰ Ngay\n👤 @{username}\n💎 {coins or '-'} ({slots or '?'})\n👁️ {viewers}", web_link=build_live_url(username))

    try:
        await client.start()
    except Exception as e:
        print(f"[NGẮT KẾT NỐI] @{username}: {e}")
    finally:
        await asyncio.sleep(30)
        active_listeners.discard(username)
        room_viewers.pop(username, None)

async def main():
    print("San Ruong & Tui Qua Bot (Full Scan + Pre-dropped) started!")
    send_telegram(f"✅ Bot Bản Full (Quét cả rương/túi thả trước) đã chạy! Đang canh {len(CHANNELS)} kênh.")
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


