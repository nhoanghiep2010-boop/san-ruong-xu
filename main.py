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
