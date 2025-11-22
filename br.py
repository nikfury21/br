from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
import asyncio
import datetime
import random
import os
import time
from telethon import Button, events
from uuid import uuid4
import psycopg2

DB_URL = "postgresql://br_db_5zy6_user:9FQOy7274aI4MWOTmWqLAutn08th2hvg@dpg-d4guhlidbo4c73b583t0-a/br_db_5zy6"

conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()

def db_ban_user(user_id: int, reason: str = ""):
    cur.execute(
        "INSERT INTO banned_users (user_id, reason) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason",
        (user_id, reason)
    )

def db_unban_user(user_id: int):
    cur.execute("DELETE FROM banned_users WHERE user_id = %s", (user_id,))

def db_is_banned(user_id: int) -> bool:
    cur.execute("SELECT 1 FROM banned_users WHERE user_id = %s", (user_id,))
    return cur.fetchone() is not None

API_ID = '5581609'
API_HASH = '21e8ed894fc3eb3e40ca1d277609e114'
BOT_TOKEN = '8404918688:AAGZi_4vOphkq8Vy9jCCqHoPjUofHcUllCc'
MOD_IDS = {8353079084 ,7556899383 ,7560366347 ,8432931494, 8353079084}  # Replace with actual mod Telegram user IDs

bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

from uuid import uuid4
sessions = {}  # {chat_id: {game_id: session}}
locked_players = set()
bot_start_time = datetime.datetime.now()
joining_locks = {}


# ---------- Per-group command cooldown ----------
GLOBAL_CMD_COOLDOWN_SECONDS = 5
_last_command_time = {}          # {chat_id: timestamp}
_command_lock = asyncio.Lock()   # one lock is enough (per check)



def remove_single_session(chat_id, session):
    """
    Remove only the provided `session` (or the stored session with same game_id)
    from sessions[chat_id]. If no game remains for that chat, remove the chat entry.
    """
    sess_map = sessions.get(chat_id, {})
    game_to_remove = None
    for gid, s in list(sess_map.items()):
        if s is session or s.get('game_id') == session.get('game_id'):
            game_to_remove = gid
            break

    if game_to_remove:
        sess_map.pop(game_to_remove, None)

    if not sess_map:
        sessions.pop(chat_id, None)



async def check_and_set_group_cooldown(event):
    """
    Returns True if the command should be blocked in this group.
    Returns False if the command is allowed and timestamp updated.
    """
    global _last_command_time
    now = time.time()
    chat_id = event.chat_id

    async with _command_lock:
        last_time = _last_command_time.get(chat_id, 0)
        elapsed = now - last_time
        if elapsed < GLOBAL_CMD_COOLDOWN_SECONDS:
            remaining = int(GLOBAL_CMD_COOLDOWN_SECONDS - elapsed)
            try:
                notice = await event.reply(
                    f"⏳ Wait {remaining}s before using other commands."
                )
                await asyncio.sleep(8)
                try:
                    await notice.delete()
                except Exception:
                    pass
            except Exception:
                pass
            return True

        # update last used time for this group
        _last_command_time[chat_id] = now
        return False
# ------------------------------------------------
#hp logic 


def get_initial_hp():
    # Shared HP range for all players
    return random.randint(3, 5)

# --- Memory-based banned users ---

LOG_CHANNEL_ID = -1003043472727  # your log channel

def is_banned(user_id: int) -> bool:
    return db_is_banned(user_id)


@bot.on(events.NewMessage(pattern=r'^/bfb'))
async def ban_from_bot(event):
    if event.sender_id not in MOD_IDS:
        return

    user = None
    reason = ""

    # Case 1: reply
    if event.is_reply:
        reply_msg = await event.get_reply_message()
        user = await event.client.get_entity(reply_msg.sender_id)
        parts = event.text.split(maxsplit=1)
        reason = parts[1] if len(parts) > 1 else ""

    # Case 2: args (/bfb <id_or_username> [reason])
    else:
        parts = event.text.split(maxsplit=2)  # split into command, target, optional reason
        if len(parts) >= 2:
            arg = parts[1]
            try:
                if arg.isdigit():  # numeric user ID
                    user = await event.client.get_entity(int(arg))
                else:  # username
                    user = await event.client.get_entity(arg)
            except Exception:
                return
            reason = parts[2] if len(parts) > 2 else ""

    if not user:
        return

    # 🚫 Don't allow banning mods or bot itself
    if user.id in MOD_IDS or user.id == (await bot.get_me()).id:
        return
    if is_banned(user.id):
        return

    db_ban_user(user.id, reason)

    # DM the banned user
    try:
        text = "🚫 You have been banned from using this bot."
        if reason:
            text += f"\nReason: {reason}"
        await bot.send_message(user.id, text)
    except Exception:
        pass

    # Log
    try:
        mod = await event.get_sender()
        chat = None
        try:
            chat = await event.get_chat()
        except Exception:
            try:
                chat = await event.client.get_entity(event.chat_id)
            except Exception:
                pass

        log_text = (
            "#bfb\n"
            f"Mod: <a href='tg://user?id={mod.id}'>{mod.first_name}</a> (User ID: <code>{mod.id}</code>)\n"
            f"User: <a href='tg://user?id={user.id}'>{user.first_name}</a> (User ID: <code>{user.id}</code>)\n"
        )

        if chat:
            chat_title = getattr(chat, "title", None)
            username = getattr(chat, "username", None)

            if username:  # Public group
                log_text += f"Chat: {chat_title} (https://t.me/{username})\n"
            elif chat_title:  # Private group / supergroup
                log_text += f"Chat: {chat_title} ( <code>-100{chat.id}</code>)\n"
            else:  # Private chat with bot
                log_text += f"Chat: Private ( <code>-{chat.id}</code>)\n"

        if reason:
            log_text += f"Reason: {reason}"

        await bot.send_message(LOG_CHANNEL_ID, log_text, parse_mode="html")


    except Exception as e:
        import traceback
        print("ERROR: Failed to send ban log:", e)
        traceback.print_exc()



@bot.on(events.NewMessage(pattern=r'^/unbfb'))
async def unban_from_bot(event):
    if event.sender_id not in MOD_IDS:
        return

    user = None

    # Case 1: reply
    if event.is_reply:
        reply_msg = await event.get_reply_message()
        user = await event.client.get_entity(reply_msg.sender_id)

    # Case 2: args (/unbfb <id_or_username>)
    else:
        parts = event.text.split(maxsplit=2)  # split into command, target, optional reason
        if len(parts) >= 2:
            arg = parts[1]
            try:
                if arg.isdigit():  # numeric user ID
                    user = await event.client.get_entity(int(arg))
                else:  # username
                    user = await event.client.get_entity(arg)
            except Exception:
                return
            reason = parts[2] if len(parts) > 2 else ""

    if not user:
        return

    if not is_banned(user.id):
        return

    db_unban_user(user.id)

    # DM the unbanned user
    try:
        await bot.send_message(user.id, "✅ You have been unbanned from using this bot.")
    except Exception:
        pass

    # Log
    try:
        mod = await event.get_sender()
        chat = None
        try:
            chat = await event.get_chat()
        except Exception:
            try:
                chat = await event.client.get_entity(event.chat_id)
            except Exception:
                pass

        log_text = (
            "#unbfb\n"
            f"Mod: <a href='tg://user?id={mod.id}'>{mod.first_name}</a> (User ID: <code>{mod.id}</code>)\n"
            f"User: <a href='tg://user?id={user.id}'>{user.first_name}</a> (User ID: <code>{user.id}</code>)\n"
        )

        if chat:
            chat_title = getattr(chat, "title", None)
            username = getattr(chat, "username", None)

            if username:  # Public group
                log_text += f"Chat: {chat_title} (https://t.me/{username})\n"
            elif chat_title:  # Private group/supergroup
                log_text += f"Chat: {chat_title} ( <code>-100{chat.id}</code>)\n"
            else:  # Private chat with bot
                log_text += f"Chat: Private ( <code>{chat.id}</code>)\n"

        await bot.send_message(LOG_CHANNEL_ID, log_text, parse_mode="html")


    except Exception as e:
        import traceback
        print("ERROR: Failed to send unban log:", e)
        traceback.print_exc()




# --- Helper function for bullet generation ---
def pick_bullets(min_total=3, max_total=8):
    """
    Returns (bullets_list, alive_count, blank_count).

    Rules:
      - total bullets between 3 and 8
      - If total == 3 → allow (2+1) or (1+2)
      - If total >= 4 → at least 2 live AND 2 blank
    """
    for _ in range(50):
        total = random.randint(min_total, max_total)

        if total == 3:
            # Exception case: 2+1 or 1+2 allowed
            blank = random.randint(1, 2)
            alive = total - blank
        else:
            if total < 4:
                continue
            blank = random.randint(2, total - 2)
            alive = total - blank

        if alive >= 1 and blank >= 1:
            bullets = ['live'] * alive + ['blank'] * blank
            random.shuffle(bullets)
            return bullets, alive, blank

    # --- Fallback (balanced split) ---
    total = random.randint(3, 8)
    blank = total // 2
    alive = total - blank
    bullets = ['live'] * alive + ['blank'] * blank
    random.shuffle(bullets)
    return bullets, alive, blank


# Anywhere else in your code where you had:
#   total_bullets = random.randint(3, 8)
#   blank = random.randint(1, total_bullets - 1)
#   alive = total_bullets - blank
#   bullets = ['live'] * alive + ['blank'] * blank
#   random.shuffle(bullets)
#   session['bullet_queue'] = bullets
#
# Replace it with:
 # bullets, alive, blank = pick_bullets()
  #session['bullet_queue'] = bullets











async def show_reload_message(event, session):
    # Decide how many bullets in this reload
    bullets, alive, blank = pick_bullets()
    session['bullet_queue'] = bullets

    # Send reload message
    await event.edit(
        f"Live bullets - {alive}\n"
        f"Blank bullets - {blank}\n\n"
        "<pre> Shotgun is getting loaded...</pre>",
        parse_mode='html'
    )

    # Small pause to mimic reload time
    await asyncio.sleep(10)

async def log_points(event, player_id, action_text):
    """
    Logs points actions in the format:
    [Chat <chat_id>] <player_name> <action_text>
    Example: [Chat -1002634198761] Alice shot Bob and dealt 1⚡ using dynamic shot, gained 15 pts
    """
    player_name = (await event.client.get_entity(player_id)).first_name
    print(f"[Chat {event.chat_id}] {player_name} {action_text}")


def is_locked(event):
    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return

    return event.sender_id not in session.get("players", [])



SOLO_DROP_RATES = {
    "🍺 Beer": 11,
    "🚬 Cigarette": 7,
    "🔁 Inverter": 9,
    "🔍 Magnifier": 9,
    "🪚 Hacksaw": 8,
    "🪢 Handcuffs": 7,
    "💊 Expired Medicine": 11,
    "🧪 Adrenaline": 9,
    "📱 Burner Phone": 9
}

MULTI_DROP_RATES = {
    "🍺 Beer": 10,
    "🚬 Cigarette": 7,
    "🔁 Inverter": 7,
    "🔍 Magnifier": 9,
    "🪚 Hacksaw": 10,
    "📡 Jammer": 5,
    "💊 Expired Medicine": 11,
    "🧪 Adrenaline": 9,
    "📱 Burner Phone": 11,
    "📺 Remote": 8
}


def refill_items(session):
    # Same number of items for all players
    item_count = random.choice([2, 3])
    drop_rates = SOLO_DROP_RATES if len(session["players"]) == 2 else MULTI_DROP_RATES

    for uid in session['players']:
        # Skip dead players only if you want; here we allow everyone at game start
        current_items = session.setdefault('items', {}).setdefault(uid, [])
        if len(current_items) >= 8:
            continue  # skip if already full

        available_space = 8 - len(current_items)
        to_add = min(item_count, available_space)
        new_items = random.choices(
            population=list(drop_rates.keys()),
            weights=list(drop_rates.values()),
            k=to_add
        )
        current_items.extend(new_items)


def refill_items_on_reload(session):
    # Same number of items for all alive players
    item_count = random.choice([2, 3])
    drop_rates = SOLO_DROP_RATES if len(session["players"]) == 2 else MULTI_DROP_RATES

    for uid in session['players']:
        # Skip dead players
        if session['hps'].get(uid, 0) <= 0:
            continue

        current_items = session.setdefault('items', {}).setdefault(uid, [])
        if len(current_items) >= 8:
            continue  # skip if already full

        available_space = 8 - len(current_items)
        to_add = min(item_count, available_space)
        new_items = random.choices(
            population=list(drop_rates.keys()),
            weights=list(drop_rates.values()),
            k=to_add
        )
        current_items.extend(new_items)


def reset_items_new_round(session):
    # Clear all items and give 2-3 items per player (same per player)
    item_count = random.choice([2, 3])
    drop_rates = SOLO_DROP_RATES if len(session["players"]) == 2 else MULTI_DROP_RATES

    session['items'] = {}
    for uid in session['players']:
        to_add = min(item_count, 8)  # max 8 per player
        session['items'][uid] = random.choices(
            population=list(drop_rates.keys()),
            weights=list(drop_rates.values()),
            k=to_add
        )



@bot.on(events.NewMessage(pattern='/multiplayer'))
async def multiplayer_handler(event):
    if is_banned(event.sender_id):
        return  # silently ignore
    if await check_and_set_group_cooldown(event): return
    if event.is_private:   # 👈 ADD THIS
        await event.respond("Use this command in groups to play with friends.")
        return
    if event.sender_id in locked_players:
        await event.reply("🚫 You are already in a game! Finish it first.")
        return

    await event.reply(
        "💥 Welcome To the Buckshot roulette...!\n"
        "⚓️ Choose A mode for max players Solo Game!",
        buttons=[
            [Button.inline("⚡️ Normal", f"multi_normal:{event.sender_id}".encode()),
             Button.inline("🏆 Gamble", f"multi_gamble:{event.sender_id}".encode())]
        ]
    )




@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"multi_gamble:")))
async def multiplayer_gamble_handler(event):
    data = event.data.decode()
    try:
        _, creator_id_str = data.split(":", 1)
        creator_id = int(creator_id_str)
    except Exception:
        return await event.answer("Invalid callback data.", alert=True)

    if event.sender_id != creator_id:
        return await event.answer("Only the user who started /multiplayer can choose this.", alert=True)

    # --- rest of existing function body unchanged ---

    await event.answer("🚧 This mode is under development!", alert=True)


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"multi_normal:")))
async def multiplayer_normal_handler(event):
    data = event.data.decode()
    try:
        _, creator_id_str = data.split(":", 1)
        creator_id = int(creator_id_str)
    except Exception:
        return await event.answer("Invalid callback data.", alert=True)

    if event.sender_id != creator_id:
        return await event.answer("Only the user who started /multiplayer can choose this.", alert=True)

    # --- rest of existing function body unchanged ---

    creator = await event.get_sender()
    creator_name = f"<a href='tg://user?id={creator.id}'>{creator.first_name}</a>"

        # Setup session same as 1v3
    locked_players.add(creator.id)  # 🚫 Prevent creator from starting another game
    game_id = str(uuid4())
    sessions.setdefault(event.chat_id, {})[game_id] = {
        'creator': creator.id,
        'player_count': 4,
        'mode': "1v3",
        'players': [creator.id],
        'usernames': [f"@{creator.username}" if creator.username else creator.first_name],
        'game_id': game_id
    }



    players_text = "1. " + sessions[event.chat_id][game_id]['usernames'][0] + " ✅\n"
    players_text += "2. [ Waiting... ]\n"
    players_text += "3. [ Waiting... ]\n"
    players_text += "4. [ Waiting... ]"


    await event.edit(
        f"🪂 <b>A normal max solo match has started by {creator_name}!</b>\n\n"
        "🥊 <b>Click on \"join\" button to play with them & show your skills in game. Hurry up!</b>\n\n"
        "<b>Players Joined:</b>\n" + players_text,
        buttons=[Button.inline("Join", f"join_game:{game_id}".encode())],
        parse_mode="html"
    )






@bot.on(events.CallbackQuery(data=b"mode_gamble"))
async def unavailable_mode(event):
    await event.answer("This mode currently unavailable", alert=True)

@bot.on(events.CallbackQuery(data=b"mode_normal"))
async def choose_players(event):
    # REPLACE WITH:
    sessions.setdefault(event.chat_id, {})['creator'] = event.sender_id

    await event.edit(
        "🎮 Buckshot Roulette Multiplayer\n\nNow select a player variation to start the game!",
        buttons=[
            [Button.inline("👥 2 Players", b"players_2")],
            [Button.inline("👨‍👨‍👦‍👦 4 Players (2v2)", b"players_4_2v2")],
            [Button.inline("👨‍👨‍👦‍👦 4 Players (1v3)", b"players_4_1v3")]
            ])


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"players_")))
async def game_lobby(event):
    data = event.data.decode()
    creator = event.sender

    # Detect which button was pressed
    if data == "players_2":
        player_count = 2
        mode = "normal"
    elif data == "players_4_1v3":
        player_count = 4
        mode = "1v3"
    elif data == "players_4_2v2":
        player_count = 4
        mode = "2v2"
    else:
        return

    # 🆕 Create unique game_id and store session under it
    game_id = str(uuid4())
    sessions.setdefault(event.chat_id, {})[game_id] = {
        'player_count': player_count,
        'mode': mode,
        'creator': creator.id,
        'players': [creator.id],
        'usernames': [f"@{creator.username}" if creator.username else f"{creator.first_name}"],
        'game_id': game_id
    }

    players_text = "\n".join(
        [f"1. {sessions[event.chat_id][game_id]['usernames'][0]} ✅"] +
        [f"{i+1}. [ Waiting... ]" for i in range(1, player_count)]
    )
    
    await event.edit(
        f"🕹 A {player_count}-player game has been created. Please join to start the game!\n\nPlayers Joined:\n{players_text}",
        buttons=[Button.inline("Join game", f"join_game:{game_id}".encode())]
    )



@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"join_game:")))
async def join_game(event):
    try:
        # Extract game_id from callback data
        game_id = event.data.decode().split(":")[1]
        session = sessions.get(event.chat_id, {}).get(game_id)
        if not session or session.get("finished"):
            await event.answer("❌ This game is no longer active.", alert=True)
            return


        # ✅ Block old/finished or missing sessions
        if not session or session.get("finished"):
            await event.answer("❌ This game has already ended. Start a new one with /multiplayer or /teamgame.", alert=True)
            return

        # safe sender fetch (avoid relying on event.sender which might be empty)
        sender = await event.get_sender()
        user_id = sender.id
        if is_banned(user_id):
            await event.answer("🚫 You are banned from using this bot.", alert=True)
            return
        # quick checks (keep your existing alert behavior)
        if user_id in locked_players:
            await event.answer("🚫 You're already in a game!", alert=True)
            return

        # build username safely
        username = f"@{sender.username}" if getattr(sender, "username", None) else (sender.first_name or str(user_id))

        if user_id in session.get('players', []):
            await event.answer("You're already in the game!", alert=True)
            return

        if len(session.get('players', [])) >= session.get('player_count', 0):
            await event.answer("Game is full!", alert=True)
            return

        # --- ensure one join is processed at a time for this lobby ---
        lock = joining_locks.setdefault(event.chat_id, asyncio.Lock())

        async with lock:
            # double-check inside the lock (state might have changed while waiting)
            if user_id in session.get('players', []):
                return
            if len(session.get('players', [])) >= session.get('player_count', 0):
                return

            # ✅ Add player to session
            session.setdefault('players', []).append(user_id)
            session.setdefault('usernames', []).append(username)

            # ✅ Lock this player only after they successfully joined
            locked_players.add(user_id)

            # build players_text same as your current logic
            players_text = "\n".join([
                f"{i+1}. {session['usernames'][i]} ✅" if i < len(session['usernames']) else f"{i+1}. [ Waiting... ]"
                for i in range(session['player_count'])
            ])

            # If lobby is full now -> different buttons/messages for 2v2 vs normal
            if len(session['players']) == session['player_count']:
                if session.get("mode") == "2v2":
                    creator_name = session['usernames'][0]
                    try:
                        await event.edit(
                            f"✅ All players have joined!\n\nWaiting for {creator_name} to choose a partner...",
                            buttons=[Button.inline("🧑‍🤝‍🧑 Choose Partner", f"choose_partner:{game_id}".encode())]
                        )
                    except Exception:
                        # editing can fail if message deleted; ignore safely
                        pass
                else:
                    try:
                        await event.edit(
                            f"✅ All players have joined!\n\nWaiting for {session['usernames'][0]} to start the game.",
                            buttons=[[Button.inline("🕹 Start Game", f"start_game:{game_id}".encode())]]
                        )
                    except Exception:
                        pass
            else:
                # not full yet -> show lobby with joined players
                try:
                    creator = await event.client.get_entity(session['creator'])
                    creator_name = f"<a href='tg://user?id={creator.id}'>{creator.first_name}</a>"
                except Exception:
                    creator_name = session['usernames'][0] if session.get('usernames') else "Creator"

                if session.get("mode") == "2v2":
                    try:
                        await event.edit(
                            f"<b>🏴‍☠️ A Team Match has started by {creator_name} !</b>\n\n"
                            "<b>🔥 Use the ideas, tactics & show to your partner how smart you are to win any game.</b>\n\n"
                            "<b>🥊 Click on \"join\" button to play with them!</b>\n\n"
                            "<b>Players Joined:</b>\n" + players_text,
                            buttons=[Button.inline("Join", f"join_game:{game_id}".encode())],
                            parse_mode="html"
                        )
                    except Exception:
                        pass
                else:
                    try:
                        await event.edit(
                            f"🪂 <b>A normal max solo match has started by {creator_name}!</b>\n\n"
                            "🥊 <b>Click on \"join\" button to play with them & show your skills in game. Hurry up!</b>\n\n"
                            "<b>Players Joined:</b>\n" + players_text,
                            buttons=[Button.inline("Join", f"join_game:{game_id}".encode())],
                            parse_mode="html"
                        )
                    except Exception:
                        pass

            # ---- throttle: wait 1 second before letting the next join proceed ----
            await asyncio.sleep(1)

    except Exception as exc:
        try:
            await event.answer("An error occurred while joining. Try again.", alert=True)
        except Exception:
            pass
        import traceback
        traceback.print_exc()



@bot.on(events.NewMessage(pattern='/teamgame'))
async def team_game_handler(event):
    if is_banned(event.sender_id):
        return  # silently ignore
    if await check_and_set_group_cooldown(event): return
    if event.is_private:   # 👈 ADD THIS
        await event.respond("Use this command in groups to play with friends.")
        return
    if event.sender_id in locked_players:
        await event.reply("🚫 You are already in a game! Finish it first.")
        return

    await event.reply(
        "💥 Welcome To the Buckshot roulette...!\n"
        "⚓️ Choose A Team mode to start the game ....",
        buttons=[
            [Button.inline("⚡️ Normal", f"team_normal:{event.sender_id}".encode()),
             Button.inline("🏆 Gamble", f"team_gamble:{event.sender_id}".encode())]
        ]
    )




@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"team_gamble:")))
async def team_gamble_handler(event):
    data = event.data.decode()
    try:
        _, creator_id_str = data.split(":", 1)
        creator_id = int(creator_id_str)
    except Exception:
        return await event.answer("Invalid callback data.", alert=True)

    if event.sender_id != creator_id:
        return await event.answer("Only the user who started /teamgame can choose this.", alert=True)

    # --- rest of existing function body unchanged ---

    await event.answer("🚧 This mode is under development!", alert=True)


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"team_normal:")))
async def team_normal_handler(event):
    data = event.data.decode()
    try:
        _, creator_id_str = data.split(":", 1)
        creator_id = int(creator_id_str)
    except Exception:
        return await event.answer("Invalid callback data.", alert=True)

    if event.sender_id != creator_id:
        return await event.answer("Only the user who started /teamgame can choose this.", alert=True)

    # --- rest of existing function body unchanged ---

    creator = await event.get_sender()
    creator_name = f"<a href='tg://user?id={creator.id}'>{creator.first_name}</a>"

    # Setup session same as 2v2
      # ← make sure this import is at the top of your file

        # Setup session same as 2v2
    locked_players.add(creator.id)  # 🚫 Prevent creator from starting another game
    game_id = str(uuid4())
    sessions.setdefault(event.chat_id, {})[game_id] = {
        'creator': creator.id,
        'player_count': 4,
        'mode': "2v2",
        'players': [creator.id],
        'usernames': [f"@{creator.username}" if creator.username else creator.first_name],
        'game_id': game_id
    }



    players_text = "1. " + sessions[event.chat_id][game_id]['usernames'][0] + " ✅\n"
    players_text += "2. [ Waiting... ]\n"
    players_text += "3. [ Waiting... ]\n"
    players_text += "4. [ Waiting... ]"


    await event.edit(
        f"🏴‍☠️ <b>A Team Match has started by {creator_name}!</b>\n\n"
        "🔥 <b>Use the ideas, tactics & show to your partner how smart you are to win any game.</b>\n\n"
        "🥊 <b>Click on \"join\" button to play with them!</b>\n\n"
        "<b>Players Joined:</b>\n" + players_text,
        buttons=[Button.inline("Join", f"join_game:{game_id}".encode())],
        parse_mode="html"
    )



@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"choose_partner:")))
async def choose_partner(event):
    game_id = event.data.decode().split(":")[1]
    session = sessions.get(event.chat_id, {}).get(game_id)
    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return


    if not session or session.get("mode") != "2v2" or "players" not in session:
        return

    if event.sender_id != session["creator"]:
        return await event.answer("Only the game creator can choose a partner.", alert=True)

    partner_buttons = []
    for uid, uname in zip(session['players'][1:], session['usernames'][1:]):
        safe_uname = uname.strip() or f"Player {uid}"
        partner_buttons.append([Button.inline(safe_uname, f"set_partner_{uid}:{game_id}".encode())])

    await event.edit(
        "👥 Choose your teammate for 2v2 mode:",
        buttons=partner_buttons
    )

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"set_partner_")))
async def partner_selection(event):
    game_id = event.data.decode().split(":")[1]
    session = sessions.get(event.chat_id, {}).get(game_id)
    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return

    if not session or session.get("mode") != "2v2" or "players" not in session:
        return

    if event.sender_id != session["creator"]:
        return await event.answer("Only the game creator can choose a partner.", alert=True)

    # Extract partner UID from callback data
    try:
        chosen_uid = int(event.data.decode().split(":")[0].split("_")[2])
    except (IndexError, ValueError):
        return await event.answer("Invalid selection.", alert=True)

    players = session['players']
    if chosen_uid not in players or chosen_uid == session["creator"]:
        return await event.answer("Invalid selection.", alert=True)

    # Form teams
    team1 = [session["creator"], chosen_uid]
    team2 = [uid for uid in players if uid not in team1]
    session["teams"] = [team1, team2]

    # Team A names
    team1_names = []
    for uid in team1:
        user = await event.client.get_entity(uid)
        team1_names.append(f"<a href='tg://user?id={uid}'>{user.first_name}</a>")
    team1_names = ", ".join(team1_names)

    # Team B names
    team2_names = []
    for uid in team2:
        user = await event.client.get_entity(uid)
        team2_names.append(f"<a href='tg://user?id={uid}'>{user.first_name}</a>")
    team2_names = ", ".join(team2_names)

    # Show teams + start button
    await event.edit(
        f"✅ Teams locked for 2v2:\n\n"
        f"🔷 Team A: {team1_names}\n"
        f"♦️ Team B: {team2_names}",
        buttons=[Button.inline("🕹 Start Game", f"start_game:{game_id}".encode())],
        parse_mode="html"
    )




@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"start_game:")))
async def start_game(event):
    game_id = event.data.decode().split(":")[1]
    session = sessions.get(event.chat_id, {}).get(game_id)
    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return
    if not session or event.sender_id != session['creator']:
        await event.answer("User unaccessible", alert=True)
        return

    await event.edit("Game is starting... Hold a second while I am shuffling items.")
    await asyncio.sleep(4)

    bullets, alive, blank = pick_bullets()
    session['bullet_queue'] = bullets

    # ⬇️ Initialise point tracking for the match
    init_points_for_game(session)



    await event.edit(
        f"Ready for the showdown?\n\n⚡ Live rounds - {alive}\n🎟️ Blank shells - {blank}\n\n<pre> Starting the game...!</pre>",
        parse_mode='html' # Explicitly setting parse_mode to html
    )
    await asyncio.sleep(10)

    # Setup round
    
    session['round'] = 1

    if session.get("mode") == "2v2":
        session["last_team_win"] = None
        # keep alternating team order but randomize which team starts
        if 'teams' in session:
            team1, team2 = session['teams']
            # choose which team goes first, but keep alternating order
            if random.choice([True, False]):
                new_order = [team1[0], team2[0], team1[1], team2[1]]
            else:
                new_order = [team2[0], team1[0], team2[1], team1[1]]
            session['players'] = new_order
    else:
        # fully randomize turn order for solo modes (1v1, 1v3, normal)
        random.shuffle(session['players'])

    session['turn_index'] = 0
    session.update({
        'round': 1,
        'wins': {uid: 0 for uid in session['players']},
    })

    session['game_start_time'] = time.time()
    if session.get('round', 0) == 1 and 'round1_start_time' not in session:
         session['round1_start_time'] = time.time()

    shared_hp = get_initial_hp()
    session['hps'] = {uid: shared_hp for uid in session['players']}
    session['max_hps'] = {uid: shared_hp for uid in session['players']}  # ✅ tracks true max HP
    
    
    session['items'] = {}          # 🔁 RESET items
    refill_items(session)


    # Build player blocks
    player_blocks = []
    for idx, uid in enumerate(session['players']):
        user_entity = await event.client.get_entity(uid)  # ✅ this was missing
        is_turn = idx == session['turn_index']
        turn_label = " [Turn]" if is_turn else ""
        name_with_turn = f"{user_entity.first_name}{turn_label}"
        hp = session['hps'][uid]
        hp_emojis = "⚡" * hp
        items = session.get('items', {}).get(uid, [])
        item_line = f"├ Items: {', '.join(items) if items else 'None'}"

        block = (
            f"<blockquote><b>👤 <a href='tg://user?id={uid}'>{name_with_turn}</a></blockquote>\n"
            f"<blockquote>├ ID: {uid}\n"
            f"├ HP: {hp_emojis}\n"
            f"{item_line}</b></blockquote>\n"
        )

        player_blocks.append(block)

        

    game_board = (
        "╔══BUCKSHOT ROULETTE══╗ \n\n"
        f"                 『Round {session['round']}』\n\n" +
        "\n▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔\n".join(player_blocks) +
        "\n╚═══════════════╝"
    )
         # Get first name of target player (index 1)
    target_user = await event.client.get_entity(session['players'][1])
    target_first_name = target_user.first_name

    await show_next_turn(event, session)




# ---------- POINT SYSTEM BEGIN ----------
def init_points_for_game(session):
    session['points'] = {uid: 0 for uid in session['players']}
    session['round_points'] = {
        uid: [0 for _ in range(session.get('max_rounds', 3))]
        for uid in session['players']
    }
    session['death_order'] = []
    session['rounds_won'] = {uid: 0 for uid in session['players']}
    session['first_elimination'] = None
    # ✅ Track stats for summary
    session['damage_taken'] = {uid: 0 for uid in session['players']}
    session['damage_dealt'] = {uid: 0 for uid in session['players']}
    session['kills'] = {uid: 0 for uid in session['players']}
    session['deaths'] = {uid: 0 for uid in session['players']}



    if session.get("mode") == "2v2":
        session['max_rounds'] = 3  # Always exactly 3 rounds
    else:
        session['max_rounds'] = 3  # Other modes can be changed if needed


async def award_1v1_points(event, session, winner_id, loser_id):
    round_idx = session['round'] - 1

    # Winner gets 5000
    session['points'][winner_id] += 5000
    if 0 <= round_idx < len(session['round_points'][winner_id]):
        session['round_points'][winner_id][round_idx] += 5000
    session['rounds_won'][winner_id] += 1
    await log_points(event, winner_id, "won the round, gained 5000 pts")

    # Loser gets 1000
    session['points'][loser_id] += 1000
    if 0 <= round_idx < len(session['round_points'][loser_id]):
        session['round_points'][loser_id][round_idx] += 1000
    await log_points(event, loser_id, "lost the round, gained 1000 pts")



async def award_1v3_points(event, session, elimination_order):
    reward_mapping = [1000, 2000, 3000, 5000]
    for idx, uid in enumerate(elimination_order):
        pts = reward_mapping[idx]
        session['points'][uid] += pts
        round_idx = session['round'] - 1
        if 0 <= round_idx < len(session['round_points'][uid]):
            session['round_points'][uid][round_idx] += pts

        if idx < 3:
            await log_points(event, uid, f"died #{idx+1}, earned {pts} pts")
        else:
            await log_points(event, uid, f"won the round, gained {pts} pts")
            session['rounds_won'][uid] += 1   # ✅ mark round win
            session.setdefault("round_winners", []).append({"winner": uid})  # ✅ track round winner






async def award_2v2_points(event, session, elimination_order):
    team1, team2 = session['teams']
    round_idx = session['round'] - 1
    max_rounds = session.get('max_rounds', 3)

    def add_points(uid, pts, reason=""):
        session['points'][uid] += pts
        session.setdefault('round_points', {}).setdefault(uid, [0] * max_rounds)
        session['round_points'][uid][round_idx] += pts
        if reason:
            return log_points(event, uid, reason)
        return None

    survivors = [uid for uid in session['players'] if uid not in elimination_order]

    # 🟢 Case 1: Flawless (both survivors same team)
    if len(survivors) == 2 and (set(survivors) == set(team1) or set(survivors) == set(team2)):
        if len(elimination_order) >= 1:
            await add_points(elimination_order[0], 1000, "died 1st, earned 1000 pts")
        if len(elimination_order) >= 2:
            await add_points(elimination_order[1], 2000, "died 2nd, earned 2000 pts")

        # survivors from same team → 5k + 3k split
        if set(survivors) == set(team1):
            await add_points(team1[0], 5000, "flawless survival — earned 5000 pts")
            await add_points(team1[1], 3000, "flawless survival — earned 3000 pts")
        else:
            await add_points(team2[0], 5000, "flawless survival — earned 5000 pts")
            await add_points(team2[1], 3000, "flawless survival — earned 3000 pts")

    # 🟢 Case 2: Mixed survivors (1v1 at end)
    else:
        # Death order: 1k, 2k, 3k
        reward_mapping = [1000, 2000, 3000]
        for idx, uid in enumerate(elimination_order):
            if idx < len(reward_mapping):
                pts = reward_mapping[idx]
                await add_points(uid, pts, f"died #{idx+1}, earned {pts} pts")

        # Last survivor gets 5000
        if survivors:
            last_alive = survivors[0]
            await add_points(last_alive, 5000, "won the round — earned 5000 pts")






HEALING_PENALTY = 50  # ✅ central penalty value

def apply_healing_penalty(session, uid):
    # make sure the player has a points entry
    session['points'].setdefault(uid, 0)
    session['points'][uid] -= HEALING_PENALTY

    round_idx = session['round'] - 1
    if 0 <= round_idx < len(session['round_points'][uid]):
        session['round_points'][uid][round_idx] -= HEALING_PENALTY

    



async def award_shoot_points(event, session, shooter_id, target_id, is_live, damage, used_hacksaw=False, shot_type="dynamic shot"):
    pts_awarded = 0
    if target_id == shooter_id:
        await log_points(event, shooter_id, f"shot themselves and lost {damage}⚡️, gained 0 pts")
        return
    if is_live:
        pts_awarded = 30 if used_hacksaw else 15
        session['points'][shooter_id] += pts_awarded
        round_idx = session['round'] - 1
        if 0 <= round_idx < len(session['round_points'][shooter_id]):
            session['round_points'][shooter_id][round_idx] += pts_awarded


    await log_points(event, shooter_id,
                     f"shot {(await event.client.get_entity(target_id)).first_name} and dealt {damage}⚡️ using {shot_type}, gained {pts_awarded} pts")


async def show_final_results_1v1(event, session):
    players = session['players']
    p1, p2 = players[0], players[1]
    u1, u2 = await event.client.get_entity(p1), await event.client.get_entity(p2)

    link_name1 = f"<a href='tg://user?id={p1}'>{u1.first_name}</a>"
    link_name2 = f"<a href='tg://user?id={p2}'>{u2.first_name}</a>"

    rp = session.get('round_points', {})
    rounds_p1 = rp.get(p1, [])
    rounds_p2 = rp.get(p2, [])

    total_p1 = sum(rounds_p1)
    total_p2 = sum(rounds_p2)

    dmg_dealt = session.get("damage_dealt", {})
    hp1 = dmg_dealt.get(p1, 0)
    hp2 = dmg_dealt.get(p2, 0)

    # Determine winner
    if total_p1 > total_p2:
        winner_html = link_name1
        sorted_players = [(link_name1, total_p1, hp1, rounds_p1), (link_name2, total_p2, hp2, rounds_p2)]
    elif total_p2 > total_p1:
        winner_html = link_name2
        sorted_players = [(link_name2, total_p2, hp2, rounds_p2), (link_name1, total_p1, hp1, rounds_p1)]
    else:
        winner_html = "Draw"
        sorted_players = [(link_name1, total_p1, hp1, rounds_p1), (link_name2, total_p2, hp2, rounds_p2)]

    # Build scoreboard dynamically
    txt = f"The Solo match (1 vs 1) has been ended between {link_name1} & {link_name2}!\n\n"
    txt += "〄────────⑄───────〄\n\n"

    medals = ["🥇", "🥈"]
    for idx, (name, total, hp, rounds) in enumerate(sorted_players):
        txt += f"{medals[idx]} Player : {name}\n"
        for i, val in enumerate(rounds, start=1):
            if val > 0 or (i <= len(sorted_players[1-idx][3]) and sorted_players[1-idx][3][i-1] > 0):
                txt += f" 🎠 Round {i} : {val}\n"
        txt += "\n"

    txt += (
        "───୨୧─────୨୧─────୨୧──\n\n"
        "               🎄  P O I N T S\n\n"
    )

    for idx, (name, total, hp, _) in enumerate(sorted_players):
        txt += f"♦️ Player {idx+1} : {name}\n"
        txt += f"⚓ Points : {total}\n"
        txt += f"⚡ Hp reduced of opponent : {hp}\n\n"

    txt += "───୨୧─────୨୧─────୨୧──\n\n"
    txt += f"🏆 Winner : {winner_html}\n\n"

    # duration: from Round 1 start
    start = session.get('round1_start_time') or session.get('game_start_time') or None
    if start is None:
        duration_seconds = int((datetime.datetime.now() - bot_start_time).total_seconds())
    else:
        duration_seconds = int(time.time() - start) if isinstance(start, (int, float)) \
            else int((datetime.datetime.now() - start).total_seconds())
    duration_seconds = max(duration_seconds, 0)
    hours, rem = divmod(duration_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    duration_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes} min {seconds} sec"

    txt += f"📯 Game duration : {duration_str}\n\n〄────────⑄───────〄"

    # send
    interim = await event.edit(
        "<b>Game ended!</b>\n\n🎉 <b>Congratulations to the winners</b> 🎉\n<b>Now I'm sending the results... Hold a second</b>",
        parse_mode="html"
    )
    await asyncio.sleep(2)
    await event.respond(txt, parse_mode="html", reply_to=interim.id)

    session['finished'] = True
    for uid in session['players']:
        locked_players.discard(uid)




async def show_final_results_1v3(event, session):
    max_rounds = session.get('max_rounds', 3)

    async def get_player_name(uid):
        return (await get_name(event, uid)) if 'get_name' in globals() else str(uid)

    async def format_points_table():
        lines = []
        for uid in session['players']:
            user = await event.client.get_entity(uid)

        # Always clickable with first_name (fallback to ID if missing)
            display_name = user.first_name if user.first_name else str(uid)
            clickable_name = f"<a href='tg://user?id={uid}'>{display_name}</a>"

            round_points = session.get('round_points', {}).get(uid, [0] * max_rounds)
            line = f"♦️ Player : {clickable_name}\n\n"
            for r in range(max_rounds):
                line += f"🔫 Round {r + 1} : {round_points[r] if r < len(round_points) else 0}\n\n"
            line += f"🎋 Total : {sum(round_points)}\n"
            line += "───────────────⊱\n"
            lines.append(line)

        return "".join(lines)



    opponents = len(session['players']) - 1
    points_table = await format_points_table()
    text = f"──⊱ᴘᴏɪɴᴛꜱ ᴛᴀʙʟᴇ ( 1 ᴠs {opponents} )⊰──\n\n" + points_table

    # Step 1: notify
    imter_im = await event.edit("📢 Now bot is sending the full pointstable!", parse_mode="html")
    session["points_msg_id"] = imter_im.id

    # Step 2: wait
    await asyncio.sleep(4)
    # Step 3: show actual table
    await event.edit(text, parse_mode="html")

    # wait 3 sec then send winner summary
    await asyncio.sleep(3)
   
    if session.get("mode") == "normal" and session.get("player_count") == 2:
        await show_final_results_1v1(event, session)
    else:
        await show_final_solo_summary(event, session)
        # ✅ Mark as finished and unlock players
    session['finished'] = True
    for uid in session['players']:
        locked_players.discard(uid)







async def show_final_solo_summary(event, session):
    players = session['players']
    all_names = [f"<a href='tg://user?id={uid}'>{(await event.client.get_entity(uid)).first_name}</a>" for uid in players]


    # --- First Elimination (first death in entire game) ---
    first_elim = []
    if session.get("first_elimination"):
        first_elim_user = await event.client.get_entity(session["first_elimination"])
        first_elim = [f"<a href='tg://user?id={first_elim_user.id}'>{first_elim_user.first_name}</a>"]


    # Track stats
    damage_taken = session.get("damage_taken", {uid: 0 for uid in players})
    damage_dealt = session.get("damage_dealt", {uid: 0 for uid in players})
    kills = session.get("kills", {uid: 0 for uid in players})
    deaths = session.get("deaths", {uid: 0 for uid in players})
    round_winners = session.get("round_winners", [])

    # Most shooted (took most damage)
    most_attacked = []
    if damage_taken:
        max_taken = max(damage_taken.values())
        most_attacked = [
            f"<a href='tg://user?id={uid}'>{(await event.client.get_entity(uid)).first_name}</a>"
            for uid, v in damage_taken.items() if v == max_taken and v > 0
        ]


    # Most attacking (dealt most damage to others)
    most_attacker = []
    if damage_dealt:
        max_dealt = max(damage_dealt.values())
        most_attacker = [
            f"<a href='tg://user?id={uid}'>{(await event.client.get_entity(uid)).first_name}</a>"
            for uid, v in damage_dealt.items() if v == max_dealt and v > 0
        ]


    # Most hated (all players with 0 rounds won)
    most_hated = [
        f"<a href='tg://user?id={uid}'>{(await event.client.get_entity(uid)).first_name}</a>"
        for uid, v in session['rounds_won'].items() if v == 0
    ]


    # Winner (highest points)
    winner_uid = max(session['points'], key=lambda u: session['points'][u])
    winner_entity = await event.client.get_entity(winner_uid)
    winner_name = f"<a href='tg://user?id={winner_uid}'>{winner_entity.first_name}</a>"


    # duration: from Round 1 start (fallback to game_start_time, then bot_start_time)
    start = session.get('round1_start_time') or session.get('game_start_time') or None

    if start is None:
        # ultimate fallback: use bot_start_time (datetime)
        duration_seconds = int((datetime.datetime.now() - bot_start_time).total_seconds())
    else:
        # start might be epoch (float/int) or datetime
        if isinstance(start, (int, float)):
            duration_seconds = int(time.time() - start)
        elif isinstance(start, datetime.datetime):
            duration_seconds = int((datetime.datetime.now() - start).total_seconds())
        else:
            duration_seconds = 0

    # clamp negatives
    if duration_seconds < 0:
        duration_seconds = 0

    hours, rem = divmod(duration_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        duration_str = f"{hours}h {minutes}m {seconds}s"
    else:
        duration_str = f"{minutes} min {seconds} sec"

   
   
   
   
   
    # --- Build message ---
    txt = (
        f"🎄 The Solo match has ended between {', '.join(all_names)}!\n\n"
        "───୨୧─────୨୧─────୨୧──\n\n"
        f"🔪 First Elimination : {', '.join(first_elim) if first_elim else 'None'}\n\n"
        f"⚓ Most shooted player : {', '.join(most_attacked) if most_attacked else 'None'}\n\n"
        f"🎯 Most attacking player : {', '.join(most_attacker) if most_attacker else 'None'}\n\n"
        f"☠️ Most hated player : {', '.join(most_hated) if most_hated else 'None'}\n\n"
        "───୨୧─────୨୧─────୨୧──\n\n"
        "🔰 𝗥𝗼𝘂𝗻𝗱 𝗪𝗶𝗻𝗻𝗲𝗿𝘀 :\n"
    )

    # Round winners breakdown
    for i, rw in enumerate(round_winners, 1):
        rw_uid = rw.get("winner")
        if not rw_uid:
            continue
        rw_entity = await event.client.get_entity(rw_uid)
        name = f"<a href='tg://user?id={rw_uid}'>{rw_entity.first_name}</a>"

        txt += (
            f"\n🔫 Round {i} : {name}\n"
            f"🏴‍☠️ Kills : {kills.get(rw_uid, 0)}\n"
            f"☠️ Death : {deaths.get(rw_uid, 0)}\n"
            f"⚡ Hp reduced : {damage_dealt.get(rw_uid, 0)}\n"
        )

    txt += (
        "\n───୨୧─────୨୧─────୨୧──\n\n"
        f"🏆 Winner : {winner_name}\n\n"
        f"📯 Game duration : {duration_str}"
    )

    # prefer the saved points message id, else use event.message.id when available
    reply_to_msg_id = session.get("points_msg_id") or (event.message.id if getattr(event, "message", None) else None)

    try:
        if reply_to_msg_id:
            await event.respond(txt, parse_mode="html", reply_to=reply_to_msg_id)
        else:
            await event.respond(txt, parse_mode="html")
    except Exception as e:
        # final fallback: try sending without reply and log error if it still fails
        try:
            await event.respond(txt, parse_mode="html")
        except Exception:
            print("Failed to send final summary:", e)


        # ✅ Mark as finished and unlock players
    session['finished'] = True
    for uid in session['players']:
        locked_players.discard(uid)







async def show_final_results_2v2(event, session):
    team1, team2 = session['teams']
    max_rounds = session.get('max_rounds', 3)

    async def clickable(uid):
        user = await event.client.get_entity(uid)
        return f"<a href='tg://user?id={uid}'>{user.first_name}</a>"

    # Get round points (shoot + awards)
    def get_round_points(uid, round_idx):
        round_points = session.get('round_points', {}).get(uid, [0] * max_rounds)
        return round_points[round_idx] if round_idx < len(round_points) else 0

    # Totals
    team1_total = sum(session['points'].get(uid, 0) for uid in team1)
    team2_total = sum(session['points'].get(uid, 0) for uid in team2)

    winner_team = team1 if team1_total >= team2_total else team2
    damage_dealt = session.get("damage_dealt", {})
    motm_uid = max(session['points'], key=lambda uid: session['points'][uid])
    motm_name = await clickable(motm_uid)

    # Duration
    start = session.get('round1_start_time') or session.get('game_start_time') or None
    if start is None:
        duration_seconds = int((datetime.datetime.now() - bot_start_time).total_seconds())
    else:
        duration_seconds = int(time.time() - start) if isinstance(start, (int, float)) \
            else int((datetime.datetime.now() - start).total_seconds())
    duration_seconds = max(duration_seconds, 0)

    hours, rem = divmod(duration_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    duration_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes} min {seconds} sec"

    text = "─⊱ 🏴‍☠️ R E S U L T S ( 2 vs 2 ) ⊰─\n\n───୨୧─────୨୧─────୨୧──\n\n"

    # Team A
    text += "               ♦️ T E A M - A\n\n"
    for uid in team1:
        text += f"♦️ Player : {await clickable(uid)}\n"
        for i in range(max_rounds):
            pts = get_round_points(uid, i)
            text += f"🏮Round {i+1} : {pts}\n"
        text += "\n"
    text += f"🎏 Total : {team1_total}\n\n── ⋆⋅☆⋅⋆ ── ⋆⋅☆⋅⋆ ─── ⋆⋅☆⋅⋆ ─\n\n"

    # Team B
    text += "               🔷 T E A M - B\n\n"
    for uid in team2:
        text += f"🔷 Player : {await clickable(uid)}\n"
        for i in range(max_rounds):
            pts = get_round_points(uid, i)
            text += f"💈Round {i+1} : {pts}\n"
        text += "\n"
    text += f"🎡 Total : {team2_total}\n\n── ⋆⋅☆⋅⋆ ── ⋆⋅☆⋅⋆ ─── ⋆⋅☆⋅⋆ ─\n\n"

    # Winners
    text += "             🌇 W I N N E R S\n\n"
    for uid in winner_team:
        text += f"♦️ Player : {await clickable(uid)}\n"
        text += f"⚓ Points : {session['points'][uid]}\n"
        text += f"⚡ Hp reduced of opponent : {damage_dealt.get(uid,0)}\n\n"

    text += "── ⋆⋅☆⋅⋆ ── ⋆⋅☆⋅⋆ ─── ⋆⋅☆⋅⋆ ─\n\n"
    text += f"🧧MOTM : {motm_name}\n\n"
    text += f"📯 Game duration : {duration_str}\n"
    text += "───୨୧─────୨୧─────୨୧──"
    if "imterim" in session:
        reply_to = session["imterim"]
    else:
        reply_to = None

    await event.respond(text, parse_mode="html", reply_to=reply_to)

        # ✅ Mark as finished and unlock players
    session['finished'] = True
    for uid in session['players']:
        locked_players.discard(uid)







async def get_name(event, uid):
    user = await event.client.get_entity(uid)
    return user.first_name
# ---------- POINT SYSTEM END ----------



@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"shot_other:")))
async def handle_shot_other(event):
    if event.sender_id in locked_players:
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    game_id = event.data.decode().split(":")[1]
    session = sessions.get(event.chat_id, {}).get(game_id)
    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return
    if not session or event.sender_id != session['players'][session['turn_index']]:
        await event.answer("Not your turn!", alert=True)
        return

    shooter_idx = session['turn_index']
    target_idx = (shooter_idx + 1) % len(session['players'])

    shooter_id = session['players'][shooter_idx]
    target_id = session['players'][target_idx]
    shooter = await event.client.get_entity(shooter_id)
    target = await event.client.get_entity(target_id)

    if not session['bullet_queue']:
        bullets, alive, blank = pick_bullets()
        session['bullet_queue'] = bullets

        item_lines = []
        for uid in session['players']:
            u = await event.client.get_entity(uid)
            items = session.get('items', {}).get(uid, [])
            item_str = ", ".join(items) if items else "No items"
            item_lines.append(f"🎒 [{u.first_name}](tg://user?id={uid}): {item_str}")
        await event.edit(
            f"⚡ Live rounds - {alive}\n🎟️ Blank bullets - {blank}\n\n<pre>Shotgun is getting loaded...</pre>\n\n" + "\n".join(item_lines),
            parse_mode='html' # Explicitly setting parse_mode to html
        )
        await asyncio.sleep(10)

    bullet = session['bullet_queue'].pop(0)
    is_live = bullet == 'live'
    damage = 2 if session.get("hacksaw_user") == shooter_id else 1

    # 🪚 Hacksaw cleanup after usage
    if session.get("hacksaw_user") == shooter_id:
        session.pop("hacksaw_user", None)
        session.pop("hacksaw_pending", None)

    if is_live:
        session['hps'][target_id] -= damage
        session['hps'][target_id] = max(0, session['hps'][target_id])
        # ✅ Track damage stats
        session['damage_taken'][target_id] += damage
        session['damage_dealt'][shooter_id] += damage

        if session['hps'][target_id] <= 0:
            session['kills'][shooter_id] += 1
            session['deaths'][target_id] += 1

        if session['hps'][target_id] <= 0 and target_id not in session['death_order']:
            session['death_order'].append(target_id)

            # ✅ record first elimination across whole game
            if session.get("first_elimination") is None:
                session["first_elimination"] = target_id


        # Award points for successful hit
        await award_shoot_points(event, session, shooter_id, target_id, is_live, damage, used_hacksaw=(damage == 2), shot_type="normal shot")

        if damage == 1:  # normal live bullet
            target_link = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
            shooter_link = f'<a href="tg://user?id={shooter.id}">{shooter.first_name}</a>'
            live_messages = [
                f"And that's the critical hit! Nice shot! Reducing 1 ⚡ of {target_link}!\n\n🎟️ Moving to next player",
                f"Who cares? Hahaha ! I can still win {shooter_link} shooted a live round to {target_link}!\n\n🎟️ Moving to next player..",
                f"A bullet has no loyalty! {shooter_link} Shot a live round to {target_link} .\n\n🎟️ Moving to next player...",
                f"One bullet, two tragedies. There’s always another way. {shooter_link} Shot a live bullet to {target_link}!\n\n🎟️ Moving to next player..."
            ]
            text = random.choice(live_messages)
    
        else:  # damage == 2 (Hacksaw active)
            text = (
                f"No matter how fast you are! You can't dodge a bullet! "
                f"{shooter.first_name} shooted a combo bullet to {target.first_name}!\n"
                f"Reducing ⚡2 of {target.first_name}.\n\n"
                "🎟️ Moving to next player"
            )


    else:
        target_link = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
        blank_messages = [
            f"Oops! You shooted a blank shell.. {target_link} got no damage !\n\n🎟️ Moving to next player..",
            f"Bad luck! That bullet was blank shell.. {target_link} is laughing and waiting for their turn..!\n\n🎟️ Moving to next player.."
        ]
        text = random.choice(blank_messages)



    await event.edit(text, parse_mode='html') # Explicitly setting parse_mode to html
    await asyncio.sleep(5)
    if await check_end_of_round(event, session):
        return

    while True:
        session['turn_index'] = (session['turn_index'] + 1) % len(session['players'])
        if session['hps'].get(session['players'][session['turn_index']], 0) > 0:
            break
    await show_next_turn(event, session)




@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"shot_self:")))
async def handle_shot_self(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    game_id = event.data.decode().split(":")[1]
    session = sessions.get(event.chat_id, {}).get(game_id)
    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return
    if not session or event.sender_id != session['players'][session['turn_index']]:
        await event.answer("Not your turn!", alert=True)
        return

    idx = session['turn_index']
    user_id = session['players'][idx]
    shooter_id = user_id  # define to avoid NameError
    user = await event.client.get_entity(user_id)

    if not session['bullet_queue']:
        bullets, alive, blank = pick_bullets()

        session['bullet_queue'] = bullets
        refill_items_on_reload(session)


        item_lines = []
        for uid in session['players']:
            u = await event.client.get_entity(uid)
            items = session.get('items', {}).get(uid, [])
            item_str = ", ".join(items) if items else "No items"
            item_lines.append(f"🎒 <a href='tg://user?id={uid}'>{u.first_name}</a>: {item_str}")
        await event.edit(
            f"⚡ Live rounds - {alive}\n🎟️ Blank bullets - {blank}\n\n<pre>Shotgun is getting loaded...</pre>\n\n" + "\n".join(item_lines),
            parse_mode='html' # Explicitly setting parse_mode to html
        )
        await asyncio.sleep(10)

    bullet = session['bullet_queue'].pop(0)
    is_live = bullet == 'live'
    damage = 2 if session.get("hacksaw_user") == shooter_id and session.get("hacksaw_pending") else 1
    await award_shoot_points(event, session, shooter_id, shooter_id, is_live, damage, used_hacksaw=(damage == 2), shot_type="self-shot")

    if session.get("hacksaw_user") == shooter_id:
        session.pop("hacksaw_user", None)
        session.pop("hacksaw_pending", None)



    if is_live:
        session['hps'][user_id] -= damage
        session['hps'][user_id] = max(0, session['hps'][user_id])
        # ✅ Track self-damage
        session['damage_taken'][user_id] += damage
     

        if session['hps'][user_id] <= 0:
            session['deaths'][user_id] += 1

        if session['hps'][user_id] <= 0 and user_id not in session['death_order']:
            session['death_order'].append(user_id)

        if session.get("hacksaw_user") == shooter_id and session.get("hacksaw_pending"):
            session.pop("hacksaw_user", None)
            session.pop("hacksaw_pending", None)

        shooter_link = f"<a href='tg://user?id={user_id}'>{user.first_name}</a>"

        if damage == 1:  # Normal live bullet
            text = (
                f"You made my work easy by shooting yourself! "
                f"{shooter_link} shooted a live bullet to themselves! "
                f"reducing ⚡ of {shooter_link}\n\n"
                "🎟️ Moving to next player ..."
            )
        else:  # damage == 2 (Hacksaw active)
            text = (
                f"Patient is the key to success! Afraid to shoot others? "
                f"{shooter_link} just shooted a combo bullet -2 ⚡ to themselves!\n\n"
                "🎟️ Moving to next player.."
            )

    else:
        shooter_link = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
        text = (
            f"Only Some people put their lives at risk! Got another chance... "
            f"{shooter_link} shooted a blank shell to themselves!\n\n"
            "🎟️ Waiting for their next move.."
        )


    await event.edit(text, parse_mode='html') # Explicitly setting parse_mode to html
    await asyncio.sleep(5)
    if await check_end_of_round(event, session):
        return
    if not is_live:
        await show_next_turn(event, session)
    else:
        while True:
            session['turn_index'] = (session['turn_index'] + 1) % len(session['players'])
            if session['hps'].get(session['players'][session['turn_index']], 0) > 0:
                break
        await show_next_turn(event, session)


    
@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"shoot_")))
async def handle_dynamic_shot(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    # Extract both target_id and game_id from callback data
    # Expected format: shoot_<target_id>:<game_id>
    data_parts = event.data.decode().split(":")
    target_id = int(data_parts[0].split("_")[1])
    game_id = data_parts[1] if len(data_parts) > 1 else None

    session = sessions.get(event.chat_id, {}).get(game_id)
    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return
    if not session:
        await event.answer("❌ This game session no longer exists.", alert=True)
        return

    shooter_idx = session['turn_index']
    shooter_id = session['players'][shooter_idx]

    if event.sender_id != shooter_id:
        await event.answer("Not your turn!", alert=True)
        return

    if session['hps'].get(target_id, 0) <= 0:
        await event.answer("That player is already eliminated!", alert=True)
        return

    if not session['bullet_queue']:
        bullets, alive, blank = pick_bullets()
        session['bullet_queue'] = bullets
        refill_items_on_reload(session)



        await event.edit(
            f"⚡ Live rounds - {alive}\n🎟️ Blank bullets - {blank}\n\n<pre>Shotgun is getting loaded...</pre>",
            parse_mode='html' # Explicitly setting parse_mode to html
        )
        await asyncio.sleep(10)

    bullet = session['bullet_queue'].pop(0)
    is_live = bullet == 'live'
    shooter = await event.client.get_entity(shooter_id)
    target = await event.client.get_entity(target_id)
    damage = 2 if session.get("hacksaw_user") == shooter_id and session.get("hacksaw_pending") else 1
    await award_shoot_points(event, session, shooter_id, target_id, is_live, damage, used_hacksaw=(damage == 2), shot_type="dynamic shot")

    if session.get("hacksaw_user") == shooter_id:
        session.pop("hacksaw_user", None)
        session.pop("hacksaw_pending", None)

    if is_live:
        session['hps'][target_id] -= damage
        session['hps'][target_id] = max(0, session['hps'][target_id])
        # ✅ Track damage stats
        session['damage_taken'][target_id] += damage
        session['damage_dealt'][shooter_id] += damage

        if session['hps'][target_id] <= 0:
            session['kills'][shooter_id] += 1
            session['deaths'][target_id] += 1

        if session['hps'][target_id] <= 0 and target_id not in session['death_order']:
            session['death_order'].append(target_id)

            # ✅ record first elimination across whole game
            if session.get("first_elimination") is None:
                session["first_elimination"] = target_id


        
        target_link = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
        shooter_link = f'<a href="tg://user?id={shooter.id}">{shooter.first_name}</a>'

        if damage == 1:  
            target_link = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
            shooter_link = f'<a href="tg://user?id={shooter.id}">{shooter.first_name}</a>'
            live_messages = [
                f"And that's the critical hit! Nice shot! Reducing 1 ⚡ of {target_link}!\n\n🎟️ Moving to next player",
                f"Who cares? Hahaha ! I can still win {shooter_link} shooted a live round to {target_link}!\n\n🎟️ Moving to next player..",
                f"A bullet has no loyalty! {shooter_link} Shot a live round to {target_link} .\n\n🎟️ Moving to next player...",
                f"One bullet, two tragedies. There’s always another way. {shooter_link} Shot a live bullet to {target_link}!\n\n🎟️ Moving to next player..."
            ]
            text = random.choice(live_messages)
            
            
        else:  
            text = (
                f"No matter how fast you are! You can't dodge a bullet! "
                f"{shooter_link} shooted a combo bullet to {target_link}!\n"
                f"Reducing ⚡2 of {target_link}.\n\n"
                "🎟️ Moving to next player"
            )


    else:
        target_link = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
        blank_messages = [
            f"Oops! You shooted a blank shell.. {target_link} got no damage !\n\n🎟️ Moving to next player..",
            f"Bad luck! That bullet was blank shell.. {target_link} is laughing and waiting for their turn..!\n\n🎟️ Moving to next player.."
        ]
        text = random.choice(blank_messages)




    if session.get("hacksaw_user") == shooter_id and session.get("hacksaw_pending"):
        session.pop("hacksaw_user", None)
        session.pop("hacksaw_pending", None)


    await event.edit(text, parse_mode='html') # Explicitly setting parse_mode to html
    await asyncio.sleep(5)
    if await check_end_of_round(event, session):
        return

    while True:
        session['turn_index'] = (session['turn_index'] + 1) % len(session['players'])
        if session['hps'].get(session['players'][session['turn_index']], 0) > 0:
            break
    await show_next_turn(event, session)





async def show_next_turn(event, session):
        # 🪢 Handcuffs: support stacked skips (multiple handcuffs)
    current_uid = session['players'][session['turn_index']]
    
         # ⛔ Fix: If current player is dead, skip immediately
    if session['hps'].get(current_uid, 0) <= 0:
        session['turn_index'] = (session['turn_index'] + 1) % len(session['players'])
        return await show_next_turn(event, session)

    # Backwards-compat: convert legacy skip_turn_for (if present) into handcuff_skips count
    if session.get("skip_turn_for"):
        legacy = session.pop("skip_turn_for", None)
        if legacy:
            session.setdefault("handcuff_skips", {})
            session['handcuff_skips'][legacy] = session['handcuff_skips'].get(legacy, 0) + 1

    # If this player has handcuff skips > 0, consume one skip and advance the turn
    if session.get("handcuff_skips", {}).get(current_uid, 0) > 0:
        session['handcuff_skips'][current_uid] -= 1
        if session['handcuff_skips'][current_uid] <= 0:
            session['handcuff_skips'].pop(current_uid, None)

        # move turn forward (skipped)
        session['turn_index'] = (session['turn_index'] + 1) % len(session['players'])
        return await show_next_turn(event, session)

        
    # 📡 Skip due to Jammer (supports stacked jammers)
    if session.get("jammer_skips", {}).get(current_uid, 0) > 0:
        # decrement skip counter
        session['jammer_skips'][current_uid] -= 1
        if session['jammer_skips'][current_uid] <= 0:
            session['jammer_skips'].pop(current_uid, None)

        # 🧠 If only 2 players alive in 4-player mode, return turn to the other player
        if session.get("player_count") == 4:
            alive_players = [uid for uid in session['players'] if session['hps'].get(uid, 0) > 0]
            if len(alive_players) == 2:
                # Give turn back to the other alive player (the jammer user)
                session['turn_index'] = session['players'].index(
                    [uid for uid in alive_players if uid != current_uid][0]
                )
                return await show_next_turn(event, session)

        # Default case: advance turn normally
        session['turn_index'] = (session['turn_index'] + 1) % len(session['players'])
        return await show_next_turn(event, session)



        
    if not session['bullet_queue']:
        bullets, alive, blank = pick_bullets()
        session['bullet_queue'] = bullets
        refill_items_on_reload(session)



        await event.edit(
            f"⚡ Live rounds - {alive}\n🎟️ Blank bullets - {blank}\n\n<pre>Shotgun is getting loaded...</pre>",
            parse_mode='html' # Explicitly setting parse_mode to html
        )
        await asyncio.sleep(10)
        

    mode = session.get("mode")
    current_turn_uid = session['players'][session['turn_index']]

    # --- Prepare common buttons (Shoot, Items, End Game) ---
    shooter_id = session['players'][session['turn_index']]
    shoot_buttons = []
    game_id = session['game_id']  # ← use the game_id stored in this session

    for uid in session['players']:
        if uid != shooter_id and session['hps'].get(uid, 0) > 0:
            target = await event.client.get_entity(uid)
            shoot_buttons.append(
                Button.inline(f"Shoot ({target.first_name})", f"shoot_{uid}:{game_id}".encode())
            )

    shoot_buttons.append(Button.inline("Shoot yourself", f"shot_self:{game_id}".encode()))


    # Arrange shoot buttons (2 per row)
    button_rows = []
    row = []
    for btn in shoot_buttons:
        row.append(btn)
        if len(row) == 2:
            button_rows.append(row)
            row = []
    if row:
        button_rows.append(row)

    # Add "view items" buttons (anyone can click)
    game_id = session['game_id']  # ✅ use this game_id for all buttons

    # Add "view items" buttons (anyone can click)
    item_view_buttons = []
    for uid in session['players']:
        user = await event.client.get_entity(uid)
        item_view_buttons.append(
            Button.inline(f"🎒 {user.first_name} Items", f"items_{uid}:{game_id}".encode())
        )


    row = []
    for btn in item_view_buttons:
        row.append(btn)
        if len(row) == 2:
            button_rows.append(row)
            row = []
    if row:
        button_rows.append(row)

    # End Game button
    button_rows.append([Button.inline("❌ End Game", f"end_game:{game_id}".encode())])


    # ---- 1v1 UI ----
    if mode == "normal" and session.get("player_count") == 2:
        text  = "──⊱  ꜱᴏʟᴏ ᴍᴏᴅᴇ [ 1 vs 1 ] ⊰──\n\n"
        text += f"              『 Ｒｏｕｎｄ {session.get('round', 1)} 』\n\n"
        text += "༺═──────────────═༻\n\n"

        for i, uid in enumerate(session['players']):
            user = await event.client.get_entity(uid)
            clickable_name = f"[{user.first_name}](tg://user?id={uid})"
            turn_label = " [ current turn ]" if uid == current_turn_uid else ""
            lives = "⚡️" * session['hps'].get(uid, 0)
            items = ", ".join(session.get('items', {}).get(uid, [])) or "None"

            text += f"♦️ Player : {clickable_name}{turn_label}\n"
            text += f"✧ lives : {lives}\n"
            text += f"✧ Items : {items}\n\n"

            # Only add the thin separator between players
            if i != len(session['players']) - 1:
                text += "༺═──────────────═༻\n\n"

        # Only one footer at the very bottom
        text += "༺═────⊱◈◈◈⊰─────═༻\n"

        await event.edit(text, buttons=button_rows, parse_mode="markdown", link_preview=False)
        return


    elif mode == "1v3":
        text = "──⊱ ꜱᴏʟᴏ ᴍᴏᴅᴇ [ 1 vs 3 ] ⊰──\n\n"  # Gap after SOLO MODE
        text += f"              『 Ｒｏｕｎｄ {session.get('round', 1)} 』\n\n"  # Gap after round
        text += "༺═──────────────═༻\n\n"  # Separator before first player

        active_players = []
        eliminated_players = []

        # First collect active and eliminated separately
        for uid in session['players']:
            user = await event.client.get_entity(uid)
            clickable_name = f"[{user.first_name}](tg://user?id={uid})"
            turn_label = " [ current turn ]" if uid == current_turn_uid else ""
            lives = "⚡️" * session['hps'].get(uid, 0)
            items = ", ".join(session.get('items', {}).get(uid, [])) or "None"

            block = f"♦️ Player : {clickable_name}{turn_label}\n"
            block += f"✧ lives : {lives}\n"
            block += f"✧ Items : {items}\n\n"

            if session['hps'].get(uid, 0) > 0:
                active_players.append(block)
            else:
                eliminated_players.append(block)

        # Add separator between active players, except after last
        for i, block in enumerate(active_players):
            text += block
            if i != len(active_players) - 1:
                text += "༺═──────────────═༻\n\n"

        # Eliminated section (NO extra thin line at the bottom)
        if eliminated_players:
            text += "༺═────⊱◈◈◈⊰─────═༻\n"
            text += "                [ELIMINATED]\n\n"
            for i, block in enumerate(eliminated_players):
                text += block
                if i != len(eliminated_players) - 1:
                    text += "༺═──────────────═༻\n\n"

        # Footer
        text += "༺═────⊱◈◈◈⊰─────═༻\n"

        await event.edit(text, buttons=button_rows, parse_mode="markdown", link_preview=False)
        return

    elif mode == "2v2" and session.get("player_count") == 4 and 'teams' in session:
        text  = "──⊱ ᴅᴜᴀʟ  ᴍᴏᴅᴇ ( 2 ᴠs 2 )⊰──\n\n"
        text += f"              『 Ｒｏᴜɴᴅ {session.get('round', 1)} 』\n\n"
        text += "༺═──────────────═༻\n\n"

        team1, team2 = session['teams']
        current_turn_uid = session['players'][session['turn_index']]

        active_players = []
        eliminated_players = []

        for uid in session['players']:
            user = await event.client.get_entity(uid)
            symbol = "♦️" if uid in team1 else "🔷"
            turn_label = " [ current turn ]" if uid == current_turn_uid else ""
            lives = "⚡️" * session['hps'].get(uid, 0)
            items = ", ".join(session.get('items', {}).get(uid, [])) or ""

            block = (
                f"{symbol} Player : [{user.first_name}](tg://user?id={uid}){turn_label}\n"
                f"✧ lives : {lives}\n"
                f"✧ Items : {items}\n\n"
            )

            if session['hps'].get(uid, 0) > 0:
                active_players.append(block)
            else:
                eliminated_players.append(block)

        # Active players with separator except after last
        for i, block in enumerate(active_players):
            text += block
            if i != len(active_players) - 1:
                text += "༺═──────────────═༻\n\n"

        # Eliminated section
        if eliminated_players:
            text += "༺═────⊱◈◈◈⊰─────═༻\n\n"
            text += "             [ELIMINATED]\n\n"
            for i, block in enumerate(eliminated_players):
                text += block
                if i != len(eliminated_players) - 1:
                    text += "༺═──────────────═༻\n\n"

        # Footer
        text += "༺═────⊱◈◈◈⊰─────═༻\n\n"

        # Team mates listing
        team1_names = [f"[{(await event.client.get_entity(uid)).first_name}](tg://user?id={uid})" for uid in team1]
        team2_names = [f"[{(await event.client.get_entity(uid)).first_name}](tg://user?id={uid})" for uid in team2]

        text += "🧩 Tᴇᴀᴍ ᴍᴀᴛᴇs :\n"
        text += f"╰─🔷 : {' & '.join(team2_names)}\n"
        text += f"╰─♦️: {' & '.join(team1_names)}\n"

        await event.edit(text, buttons=button_rows, parse_mode="markdown", link_preview=False)
        return
        


    

# ---- Default UI (unchanged) ----
# paste your old active_blocks/eliminated_blocks logic here


    shooter_id = session['players'][session['turn_index']]
    shoot_buttons = []
    for uid in session['players']:
        if uid != shooter_id and session['hps'].get(uid, 0) > 0:
            target = await event.client.get_entity(uid)
            shoot_buttons.append(Button.inline(f"Shoot ({target.first_name})", f"shoot_{uid}:{game_id}".encode()))
    shoot_buttons.append(Button.inline("Shoot yourself", f"shot_self:{game_id}".encode()))
    # Everyone can view items of anyone (per row)
    



    # Organize shooting buttons
    button_rows = []
    row = []
    for btn in shoot_buttons:
        row.append(btn)
        if len(row) == 2:
            button_rows.append(row)
            row = []
    if row:
        button_rows.append(row)

    # Add item view buttons (everyone can click to view items)
    item_view_buttons = []
    for uid in session['players']:
        user = await event.client.get_entity(uid)
        item_view_buttons.append(Button.inline(f"🎒 {user.first_name} Items", f"items_{uid}:{game_id}".encode()))


    # Add item view buttons two per row
    row = []
    for btn in item_view_buttons:
        row.append(btn)
        if len(row) == 2:
            button_rows.append(row)
            row = []
    if row:
        button_rows.append(row)

    # Add End Game button center-aligned (in its own row)
    button_rows.append([Button.inline("❌ End Game", f"end_game:{game_id}".encode())])



    # Final game board update
    await event.edit(
        game_board + eliminated_board,
        buttons=button_rows,
        link_preview=False,
        parse_mode='html' # Explicitly setting parse_mode to html
    )




@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"items_")))
async def handle_item_menu(event):
    parts = event.data.decode().split(":")
    if len(parts) < 2:
        return
    game_id = parts[1]

    # 🔎 Find the session by game_id only
    session = None
    for chat_id, games in sessions.items():
        if game_id in games:
            session = games[game_id]
            break

    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return

    try:
        target_id = int(parts[0].split("_")[1])
    except ValueError:
        return

    if target_id not in session['players']:
        await event.answer("🚫 This player is no longer in this game.", alert=True)
        return

    # ✅ Restrict: You can only open other players' items if it's your turn
    current_turn_id = session['players'][session['turn_index']]
    if event.sender_id != current_turn_id:
        await event.answer("⏳ You can only view items during your turn!", alert=True)
        return

    user = await event.client.get_entity(target_id)
    item_list = session.get('items', {}).get(target_id, [])
    item_text = "\n".join([f"{i+1}. {item}" for i, item in enumerate(item_list)]) or "No items"

    buttons = []

    # Only allow using items if it's your turn AND it's your own items
    if event.sender_id == target_id:
        if "🍺 Beer" in item_list:
            buttons.append([Button.inline("🍺 Use Beer", f"use_beer_{target_id}".encode())])
        if "🚬 Cigarette" in item_list:
            buttons.append([Button.inline("🚬 Use Cigarette", f"use_cigarette_{target_id}".encode())])
        if "🔁 Inverter" in item_list:
            buttons.append([Button.inline("🔁 Use Inverter", f"use_inverter_{target_id}".encode())])
        if "🔍 Magnifier" in item_list:
            buttons.append([Button.inline("🔍 Use Magnifier", f"use_magnifier_{target_id}".encode())])
        if "🪚 Hacksaw" in item_list:
            buttons.append([Button.inline("🪚 Use Hacksaw", f"use_hacksaw_{target_id}".encode())])
        if "🧪 Adrenaline" in item_list:
            buttons.append([Button.inline("🧪 Use Adrenaline", f"use_adrenaline_{game_id}".encode())])
        if "📱 Burner Phone" in item_list:
            buttons.append([Button.inline("📱 Use Burner Phone", f"use_burner_{target_id}".encode())])
        if "💊 Expired Medicine" in item_list:
            buttons.append([Button.inline("💊 Use Expired Medicine", f"use_expired_{target_id}".encode())])
        if "🪢 Handcuffs" in item_list:
            buttons.append([Button.inline("🪢 Use Handcuffs", f"use_handcuffs_{target_id}".encode())])
        if "📡 Jammer" in item_list:
            buttons.append([Button.inline("📡 Use Jammer", f"use_jammer_{target_id}".encode())])
        if "📺 Remote" in item_list:
            buttons.append([Button.inline("📺 Use Remote", f"use_remote_{target_id}".encode())])

    # Back button
    buttons.append([Button.inline("🔙 Back", f"back_to_board:{game_id}".encode())])

    await event.edit(
        f"🎒 <b>{user.first_name}'s Items</b>\n\n{item_text}",
        buttons=buttons,
        parse_mode='html'
    )



@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"back_to_board")))
async def go_back_to_game(event):
    parts = event.data.decode().split(":")
    if len(parts) < 2:
        return
    game_id = parts[1]

    session = sessions.get(event.chat_id, {}).get(game_id)
    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return
    if not session or event.sender_id not in session.get("players", []):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    await show_next_turn(event, session)






#beer handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_beer_")))
async def use_beer_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = event.sender_id
    turn_uid = session['players'][session['turn_index']]
    if uid != turn_uid:
        await event.answer("It's not your turn!", alert=True)
        return

    if session['items'].get(uid, []).count("🍺 Beer") == 0:
        await event.answer("You have no Beer!", alert=True)
        return

    session['items'][uid].remove("🍺 Beer")
    if not session['bullet_queue']:
        await event.answer("No bullet to defuse!", alert=True)
        return

    defused = session['bullet_queue'].pop(0)

    await event.edit(
        f"🍺 <a href='tg://user?id={uid}'>{event.sender.first_name}</a> drank a Beer!\n\n"
        f"🧨 Bullet was <b>defused</b>: <pre>{defused.upper()}</pre>\n\n"
        f"🕹 Your turn continues.",
        parse_mode='html' # Explicitly setting parse_mode to html
    )
    await asyncio.sleep(6)
    await show_next_turn(event, session)



@bot.on(events.CallbackQuery(data=b"back_to_game"))
async def back_to_game_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    await show_next_turn(event, session)


#cigaratte handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_cigarette_")))
async def use_cigarette_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = event.sender_id
    turn_uid = session['players'][session['turn_index']]
    if uid != turn_uid:
        await event.answer("It's not your turn!", alert=True)
        return

    # Check if player has at least 1 cigarette
    if session['items'].get(uid, []).count("🚬 Cigarette") == 0:
        await event.answer("You have no Cigarette!", alert=True)
        return

    # Determine max HP in this round (shared at round start)
    max_hp = session['max_hps'].get(uid, session['hps'][uid])
    if session['hps'][uid] >= max_hp:
        await event.answer("Health is already full!", alert=True)
        return

    # Remove one cigarette and heal 1 HP
    session['items'][uid].remove("🚬 Cigarette")
    session['hps'][uid] += 1
    # Deduct penalty points for healing item use
    apply_healing_penalty(session, uid)
    await log_points(event, uid, f"used Cigarette, lost {HEALING_PENALTY} pts")



    await event.edit(
        f"🚬 <a href='tg://user?id={uid}'>{event.sender.first_name}</a> smoked a Cigarette and gained +1 ⚡ !",
        parse_mode='html' # Explicitly setting parse_mode to html
    )
    await asyncio.sleep(6)
    await show_next_turn(event, session)



#inverter handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_inverter_")))
async def use_inverter_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = event.sender_id
    turn_uid = session['players'][session['turn_index']]
    if uid != turn_uid:
        await event.answer("It's not your turn!", alert=True)
        return

    if session['items'].get(uid, []).count("🔁 Inverter") == 0:
        await event.answer("You have no Inverter!", alert=True)
        return

    if not session['bullet_queue']:
        await event.answer("No bullet to invert!", alert=True)
        return

    # Remove item
    session['items'][uid].remove("🔁 Inverter")

    # Flip the first bullet (current shell)
    current = session['bullet_queue'][0]
    if current == "live":
        session['bullet_queue'][0] = "blank"
    elif current == "blank":
        session['bullet_queue'][0] = "live"

    await event.edit(
        f"🔁 <a href='tg://user?id={uid}'>{event.sender.first_name}</a> used an Inverter.\n\n"
        f"The polarity of the upcoming shell has been changed",
        parse_mode='html' # Explicitly setting parse_mode to html
    )

    await asyncio.sleep(6)
    await show_next_turn(event, session)

#magnifier handler


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_magnifier_")))
async def use_magnifier_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = event.sender_id
    turn_uid = session['players'][session['turn_index']]

    if uid != turn_uid:
        await event.answer("It's not your turn!", alert=True)
        return

    if session['items'].get(uid, []).count("🔍 Magnifier") == 0:
        await event.answer("You have no Magnifier!", alert=True)
        return

    if not session['bullet_queue']:
        await event.answer("No bullets to inspect!", alert=True)
        return

    session['items'][uid].remove("🔍 Magnifier")
    bullet_type = session['bullet_queue'][0]
    readable = "💥 LIVE SHELL" if bullet_type == "live" else "😮 BLANK SHELL"

    await event.answer(f"🔍 Magnifier reveals: {readable}", alert=True)

#hacksaw handler


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_hacksaw_")))
async def use_hacksaw_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = event.sender_id
    if uid != session['players'][session['turn_index']]:
        await event.answer("It's not your turn!", alert=True)
        return

    if session['items'].get(uid, []).count("🪚 Hacksaw") == 0:
        await event.answer("You have no Hacksaw!", alert=True)
        return

    session['items'][uid].remove("🪚 Hacksaw")

    # Track the user and mark the next shell for effect
    session['hacksaw_user'] = uid
    session['hacksaw_pending'] = True

    await event.edit(
        f"🪚 <a href='tg://user?id={uid}'>{event.sender.first_name}</a> equipped a Hacksaw!\n\n"
        f"Next shell will deal <b>double damage (2⚡)</b>.",
        parse_mode='html' # Explicitly setting parse_mode to html
    )

    await asyncio.sleep(6)
    await show_next_turn(event, session)


#adrenaline handler


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_adrenaline_")))
async def use_adrenaline(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    parts = event.data.decode().split("_")
    if len(parts) < 3:
        return
    game_id = parts[2]

    session = sessions.get(event.chat_id, {}).get(game_id)
    if not session or session.get("finished"):
        await event.answer("❌ This game is no longer active.", alert=True)
        return
    if not session or event.sender_id not in session.get("players", []):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return



    uid = event.sender_id
    if uid != session['players'][session['turn_index']]:
        await event.answer("It's not your turn!", alert=True)
        return

    if session['items'].get(uid, []).count("🧪 Adrenaline") == 0:
        await event.answer("You have no Adrenaline!", alert=True)
        return

    session['items'][uid].remove("🧪 Adrenaline")
    session['adrenaline_thief'] = uid

    buttons = []
    for pid in session['players']:
        if pid != uid:  # ✅ allow stealing from all (alive or dead)

            user = await event.client.get_entity(pid)
            buttons.append([Button.inline(user.first_name, f"steal_from_{pid}".encode())])

    await event.edit("🧪 Choose a player to steal from:", buttons=buttons)



@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"steal_from_")))
async def choose_steal_target(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = session.get("adrenaline_thief")
    if uid != event.sender_id:
        return

    target_id = int(event.data.decode().split("_")[2])
    target_items = session['items'].get(target_id, [])

    valid_items = [it for it in target_items if it != "🧪 Adrenaline"]

    if not valid_items:  # opponent has only adrenaline (or nothing)
        await event.answer("⚠️ No other items left — you can’t steal Adrenaline!", alert=True)

        # 🟢 Only auto-consume in 1v1
        if session.get("player_count") == 2:
            session.pop("adrenaline_thief", None)
            session.pop("steal_target", None)
            return await show_next_turn(event, session)

        # In 1v3 / 2v2, just return so player can pick another opponent
        return

    session['steal_target'] = target_id
    buttons = [
        [Button.inline(item, f"steal_item_{target_id}_{item}".encode())] for item in set(valid_items)
    ]

    # 🔙 BACK BUTTON — go back to player selector
    buttons.append([Button.inline("🔙 Back", b"adrenaline_back")])

    await event.edit("🧪 Choose item to steal:", buttons=buttons)




@bot.on(events.CallbackQuery(data=b"adrenaline_back"))
async def back_to_steal_player(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = session.get("adrenaline_thief")
    if uid != event.sender_id:
        return

    buttons = []
    for pid in session['players']:
        if pid != uid:  # don't show yourself
            user = await event.client.get_entity(pid)
            buttons.append([Button.inline(user.first_name, f"steal_from_{pid}".encode())])


    await event.edit("🧪 Choose a player to steal from:", buttons=buttons)



@bot.on(events.NewMessage(pattern='/sologame'))
async def solo_game_handler(event):
    if is_banned(event.sender_id):
        return  # silently ignore
    if await check_and_set_group_cooldown(event):
        return
    if event.is_private:   # 👈 ADD THIS
        await event.respond("Use this command in groups to play with friends.")
        return
    if event.sender_id in locked_players:
        await event.reply("🚫 You are already in a game! Finish it first.")
        return

    await event.reply(
        "💥 Welcome To the Buckshot roulette...!\n"
        "⚓️ Choose A mode for Solo Game!",
        buttons=[
            [Button.inline("⚡️ Normal", f"solo_normal:{event.sender_id}".encode()),
             Button.inline("🏆 Gamble", f"solo_gamble:{event.sender_id}".encode())]

        ]
    )


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"solo_gamble:")))
async def solo_gamble_handler(event):
    data = event.data.decode()
    try:
        _, creator_id_str = data.split(":", 1)
        creator_id = int(creator_id_str)
    except Exception:
        return await event.answer("Invalid callback data.", alert=True)

    if event.sender_id != creator_id:
        return await event.answer("Only the user who started /sologame can choose this.", alert=True)

    # --- rest of existing function body unchanged ---

    await event.answer("🚧 This mode is under development!", alert=True)


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"solo_normal:")))
async def solo_normal_handler(event):
    data = event.data.decode()
    try:
        _, creator_id_str = data.split(":", 1)
        creator_id = int(creator_id_str)
    except Exception:
        return await event.answer("Invalid callback data.", alert=True)

    if event.sender_id != creator_id:
        return await event.answer("Only the user who started /sologame can choose this.", alert=True)

    # --- rest of existing function body unchanged ---

    creator = await event.get_sender()
    creator_name = f"<a href='tg://user?id={creator.id}'>{creator.first_name}</a>"

    # Set up the session exactly like multiplayer 2-player normal

    locked_players.add(creator.id)  # 🚫 Prevent solo creator from starting another game
    game_id = str(uuid4())
    sessions.setdefault(event.chat_id, {})[game_id] = {
        'creator': creator.id,
        'player_count': 2,
        'mode': "normal",
        'players': [creator.id],
        'usernames': [f"@{creator.username}" if creator.username else creator.first_name],
        'game_id': game_id
    }



    players_text = "1. " + sessions[event.chat_id][game_id]['usernames'][0] + " ✅\n"
    players_text += "2. [ Waiting... ]"


    await event.edit(
        f"🪂 <b>A normal solo match has started by {creator_name}!</b>\n\n"
        f"<b>Click on join button to play with them!</b>\n\n"
        f"<b>Players Joined:</b>\n{players_text}",
        buttons=[Button.inline("Join", f"join_game:{game_id}".encode())],
        parse_mode="html"
    )




@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"steal_item_")))
async def finalize_steal(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    import base64

    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = session.get("adrenaline_thief")
    if uid != event.sender_id:
        return

    parts = event.data.decode().split("_")
    target_id = int(parts[2])
    item = "_".join(parts[3:])

    if item == "🧪 Adrenaline":
        await event.answer("You cannot steal Adrenaline!", alert=True)
        return


    target_items = session['items'].get(target_id, [])

    if item not in target_items:
        await event.answer("Item no longer available!", alert=True)
        return

    
    # transfer the stolen item into the thief's inventory
    if item in session['items'].get(target_id, []):
        idx = session['items'][target_id].index(item)
        del session['items'][target_id][idx]
    thief = await event.client.get_entity(uid)


    if item == "🍺 Beer":
        if session['bullet_queue']:
            defused = session['bullet_queue'].pop(0)
            msg = f"🧪 {thief.first_name} stole 🍺 Beer and defused <pre>{defused.upper()}</pre> shell!"
        else:
            msg = f"🧪 {thief.first_name} stole 🍺 Beer but no bullet to defuse."

    elif item == "🚬 Cigarette":
        max_hp = session['max_hps'].get(uid, session['hps'][uid])
        if session['hps'][uid] < max_hp:
            session['hps'][uid] += 1
            msg = f"🧪 {thief.first_name} stole 🚬 Cigarette and healed +1 ⚡!"
        else:
            msg = f"🧪 {thief.first_name} stole 🚬 Cigarette but already full HP."

    elif item == "🔁 Inverter":
        if session['bullet_queue']:
            b = session['bullet_queue'][0]
            session['bullet_queue'][0] = "blank" if b == "live" else "live"
            msg = f"🧪 {thief.first_name} stole Inverter and changed the polarity of current shell."
        else:
            msg = f"🧪 {thief.first_name} stole Inverter but no bullet to flip."

    elif item == "🔍 Magnifier":
        if session['bullet_queue']:
            b = session['bullet_queue'][0]
            readable = '💥 LIVE' if b == 'live' else '😮 BLANK'
            await event.answer(f"🔍 Magnifier reveals: {readable} shell.", alert=True)
        else:
            await event.answer("🔍 No bullets to inspect.", alert=True)

        session.pop("adrenaline_thief", None)
        session.pop("steal_target", None)
        return await show_next_turn(event, session)

    elif item == "🪚 Hacksaw":
        session['hacksaw_user'] = uid
        session['hacksaw_pending'] = True
        msg = f"🧪 {thief.first_name} stole 🪚 Hacksaw! Next shell will deal double damage (2⚡)."


    elif item == "🪢 Handcuffs":
        if len(session['players']) == 2:
            opponent_id = [p for p in session['players'] if p != uid][0]
            session.setdefault("handcuff_skips", {})
            session['handcuff_skips'][opponent_id] = session['handcuff_skips'].get(opponent_id, 0) + 1
            opponent = await event.client.get_entity(opponent_id)
            skips = session['handcuff_skips'][opponent_id]
            plural = "turns" if skips > 1 else "turn"
            msg = f"🧪 {thief.first_name} stole 🪢 Handcuffs!\n{opponent.first_name}'s next {skips} {plural} will be skipped."
        else:
            msg = f"🧪 {thief.first_name} stole 🪢 Handcuffs but can't use — not a 2-player game."


    elif item == "📱 Burner Phone":
        if session['bullet_queue']:
            total = len(session['bullet_queue'])
            if total < (2 if len(session['players']) == 2 else 3):
                msg = f"📱 {thief.first_name} stole Burner Phone but not enough cartridges to use it."
                await event.edit(msg, parse_mode='html') # Explicitly setting parse_mode to html
            else:
                index = random.randint(1, total - 1)
                bullet_type = session['bullet_queue'][index]
                bullet_str = "Live shell." if bullet_type == "live" else "Blank shell."
                msg = f"📱 Calling...\n\nCartridge {index + 1} ... {bullet_str}"
                await event.answer(msg, alert=True)
        else:
            msg = f"📱 {thief.first_name} stole Burner Phone but no bullets left."
            await event.edit(msg, parse_mode='html') # Explicitly setting parse_mode to html

        session.pop("adrenaline_thief", None)
        session.pop("steal_target", None)
        return await show_next_turn(event, session)


    elif item == "💊 Expired Medicine":
        max_hp = session['max_hps'].get(uid, session['hps'][uid])

        chance = session.get('medic_chance',50)
        success = random.randint(1, 100) <= chance

        if success:
            prev_hp = session['hps'][uid]
            session['hps'][uid] += 2
            if session['hps'][uid] > max_hp:
                session['hps'][uid] = max_hp
            gained = session['hps'][uid] - prev_hp

            if gained > 0:
                msg = f"🧪 {thief.first_name} stole 💊 Expired Medicine and healed +{gained} ⚡ Hp!"
            else:
                msg = f"🧪 {thief.first_name} stole 💊 Expired Medicine but already at full HP."
        else:
            session['hps'][uid] -= 1
            if session['hps'][uid] < 0:
                session['hps'][uid] = 0
            msg = f"🧪 {thief.first_name} stole 💊 Expired Medicine and it took -1 ⚡ Hp!"
        # Deduct penalty points for using Expired Medicine
        apply_healing_penalty(session, uid)
        await log_points(event, uid, f"used Expired Medicine, lost {HEALING_PENALTY} pts")





    elif item == "📡 Jammer":
        session['items'].setdefault(uid, []).append("📡 Jammer")
        buttons = []
        for pid in session['players']:
            if pid != uid and session['hps'].get(pid, 0) > 0:
                user = await event.client.get_entity(pid)
                buttons.append([Button.inline(user.first_name, f"jammer_target_{pid}".encode())])
        await event.edit("📡 Who do you want to jam?", buttons=buttons)
        return



    elif item == "📺 Remote":
        if len(session['players']) == 4:
            current = session['players'][session['turn_index']]
            session['players'].reverse()
            session['turn_index'] = session['players'].index(current)
            msg = f"🧪 {thief.first_name} stole 📺 Remote! Turn order reversed!"
        else:
            msg = f"🧪 {thief.first_name} stole 📺 Remote but it's only usable in 4-player games."

    else:
        msg = f"🧪 {thief.first_name} stole {item}. (Unknown effect)"
 

    session.pop("adrenaline_thief", None)
    session.pop("steal_target", None)

    await event.edit(msg, parse_mode='html') # Explicitly setting parse_mode to html
    await asyncio.sleep(6)
    await show_next_turn(event, session)


#handcuffs handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_handcuffs_")))
async def use_handcuffs_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = event.sender_id
    if uid != session['players'][session['turn_index']]:
        await event.answer("It's not your turn!", alert=True)
        return

    if session['items'].get(uid, []).count("🪢 Handcuffs") == 0:
        await event.answer("You have no Handcuffs!", alert=True)
        return

    if len(session['players']) != 2:
        await event.answer("🪢 Can only be used in 2-player mode!", alert=True)
        return

        # Use item
    session['items'][uid].remove("🪢 Handcuffs")

    # Stack skip count for opponent (supports using multiple handcuffs)
    opponent_id = [p for p in session['players'] if p != uid][0]
    session.setdefault("handcuff_skips", {})
    session['handcuff_skips'][opponent_id] = session['handcuff_skips'].get(opponent_id, 0) + 1

    opponent = await event.client.get_entity(opponent_id)
    mention = f"<a href='tg://user?id={opponent.id}'>{opponent.first_name}</a>"
    skips = session['handcuff_skips'][opponent_id]
    plural = "turns" if skips > 1 else "turn"

    await event.edit(
        f"🪢 You used Handcuffs!\n"
        f"{mention}'s next {skips} {plural} will be skipped — you get to shoot instead.",
        parse_mode='html' # Explicitly setting parse_mode to html
    )
    await asyncio.sleep(6)
    await show_next_turn(event, session)


#burner phone handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_burner_")))
async def use_burner_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = event.sender_id
    if uid != session['players'][session['turn_index']]:
        await event.answer("It's not your turn!", alert=True)
        return

    if session['items'].get(uid, []).count("📱 Burner Phone") == 0:
        await event.answer("You have no Burner Phone!", alert=True)
        return

    # Remove the Burner Phone from inventory
    session['items'][uid].remove("📱 Burner Phone")

    # Get the current bullet queue (unfired bullets only)
    remaining = session.get("bullet_queue", [])
    total = len(remaining)

    # Check player mode
    player_count = len(session['players'])

    # ❌ Not enough cartridges to use
    if player_count == 2 and total < 3:
        await event.answer("📱 You tried to make a call...\nOops, how unfortunate. (Need at least 3 cartridges)", alert=True)
        return
    elif player_count > 2 and total < 3:
        await event.answer("📱 You tried to make a call...\nOops, how unfortunate. (Need at least 3 cartridges)" , alert=True)
        return

    # ✅ Pick a random index in the future (not the next shot)
    index = random.randint(1, total - 1)  # skip index 0 (next shot)
    bullet_type = remaining[index]  # Get real bullet type (immune to Inverter)

    bullet_str = "Live shell." if bullet_type == "live" else "Blank shell."
    msg = f"📱 Calling...\n\nCartridge {index + 1} ... {bullet_str}"

    await event.answer(msg, alert=True)
    await show_next_turn(event, session)

# ----------------------------------------
# /help handler
# ----------------------------------------
@bot.on(events.NewMessage(pattern=r'(?i)^/help(?:@\w+)?$'))
async def help_handler(event):
    user_id = event.sender_id
    if is_banned(user_id):
        return

    if await check_and_set_group_cooldown(event): return
    bot_username = (await bot.get_me()).username

    if event.is_group or event.is_channel:
        # Group/Channel → reply to /help
        await bot.send_message(
            event.chat_id,
            "ᴡᴀɴᴛ ᴛᴏ ᴋɴᴏᴡ ᴍᴏʀᴇ ᴀʙᴏᴜᴛ ɢᴀᴍᴇ? ᴄʟɪᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴋɴᴏᴡ ᴍʏ ᴀʙɪʟɪᴛɪᴇꜱ.",
            buttons=[[Button.url("📖 Commands", f"https://t.me/{bot_username}?start=help")]],
            reply_to=event.id   # ✅ reply directly to the /help message
        )
    else:
        # Private → reply with full help menu
        sender = await event.get_sender()
        clickable = f"<a href='tg://user?id={sender.id}'>{sender.first_name}</a>"

        HELP_MENU = (
            f"ʜᴇʟʟᴏ ᴛʜᴇʀᴇ {clickable}! "
            "ᴄᴏɴꜰᴜꜱᴇᴅ ᴡʜɪʟᴇ ᴜꜱɪɴɢ ᴍᴇ? "
            "ᴄʜᴇᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴋɴᴏᴡ ᴍʏ ᴀʙɪʟɪᴛɪᴇꜱ ᴀɴᴅ ᴘᴏꜱꜱɪʙʟᴇ ᴄᴏᴍᴍᴀɴᴅꜱ.\n\n"
            "Please choose an option below to explore features."
        )

        main_buttons = [
            [Button.inline("📼 Modes", b"modes"), Button.inline("🎐 Items", b"items")],
            [Button.inline("🥇 Double or Nothing", b"double_or_nothing")],
            [Button.inline("🏆 Gamble", b"gamble_mode")],
        ]

        await bot.send_message(
            event.chat_id,
            HELP_MENU,
            buttons=main_buttons,
            link_preview=False,
            reply_to=event.id,   # ✅ reply directly to the /help message
            parse_mode="html"    # ✅ enable clickable username
        )

        




# ----------------------------------------
# /start (only plain /start, no arguments)
# ----------------------------------------
from telethon import Button, events

@bot.on(events.NewMessage(pattern=r'(?i)^/start(?:@\w+)?$'))
async def start_handler(event):
    if is_banned(event.sender_id):
        return  # silently ignore
    if await check_and_set_group_cooldown(event):
        return
    caption = (
        "🌇 <b>𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐭𝐨 𝐁𝐮𝐜𝐤𝐬𝐡𝐨𝐭 𝐑𝐨𝐮𝐥𝐞𝐭𝐭𝐞 𝐁𝐨𝐭!</b>\n\n"
        "⛳ Bored of grinding in games? Don't worry — it's not like other bots where you have to grind.\n\n"
        "🗝️ A game of <b>luck</b>! Smash your opponents or get smashed by them!\n\n"
        "Use <b>/help</b> to see items and commands."
    )

    # Links
    sudos_link = "https://t.me/buckshot_roulette_updates/36"   # replace with your message link
    updates_link = "https://t.me/buckshot_roulette_updates"  # replace with your channel
    add_me_link = f"https://t.me/{(await bot.get_me()).username}?startgroup=true"

    # Buttons layout
    buttons = [
        [
            Button.url("⚡ Sudos", sudos_link),
            Button.url("📯 Updates", updates_link),
        ],
        [Button.url("➕ Add me to Your Groups", add_me_link)],
    ]

    # Reply to the /start message
    await bot.send_file(
        event.chat_id,
        "br.jpg",  # <-- replace with your photo
        caption=caption,
        buttons=buttons,
        parse_mode="html",
        reply_to=event.id   # 🔥 ensures it replies to user's /start
    )

@bot.on(events.CallbackQuery(data=b"back_main"))
async def back_to_main(event):
    user_id = event.sender_id
    if is_banned(user_id):
        await event.answer("🚫 You are banned from using this bot.", alert=True)
        return
    sender = await event.get_sender()
    clickable = f"<a href='tg://user?id={sender.id}'>{sender.first_name}</a>"

    HELP_MENU = (
        f"ʜᴇʟʟᴏ ᴛʜᴇʀᴇ {clickable}! "
        "ᴄᴏɴꜰᴜꜱᴇᴅ ᴡʜɪʟᴇ ᴜꜱɪɴɢ ᴍᴇ? "
        "ᴄʜᴇᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴋɴᴏᴡ ᴍʏ ᴀʙɪʟɪᴛɪᴇꜱ ᴀɴᴅ ᴘᴏꜱꜱɪʙʟᴇ ᴄᴏᴍᴍᴀɴᴅꜱ.\n\n"
        "Please choose an option below to explore features."
    )

    main_buttons = [
        [Button.inline("📼 Modes", b"modes"), Button.inline("🎐 Items", b"items")],
        [Button.inline("🥇 Double or Nothing", b"double_or_nothing")],
        [Button.inline("🏆 Gamble", b"gamble_mode")],
    ]

    await event.edit(HELP_MENU, buttons=main_buttons, parse_mode="html")
# ----------------------------------------
# /start help (deep-link from group button)
# ----------------------------------------
@bot.on(events.NewMessage(pattern="^/start help$"))
async def start_help_handler(event):
    user_id = event.sender_id
    if is_banned(user_id):
        return
    
    sender = await event.get_sender()
    clickable = f"<a href='tg://user?id={sender.id}'>{sender.first_name}</a>"

    HELP_MENU = (
        f"ʜᴇʟʟᴏ ᴛʜᴇʀᴇ {clickable}! "
        "ᴄᴏɴꜰᴜꜱᴇᴅ ᴡʜɪʟᴇ ᴜꜱɪɴɢ ᴍᴇ? "
        "ᴄʜᴇᴄᴋ ʙᴇʟᴏᴡ ᴛᴏ ᴋɴᴏᴡ ᴍʏ ᴀʙɪʟɪᴛɪᴇꜱ ᴀɴᴅ ᴘᴏꜱꜱɪʙʟᴇ ᴄᴏᴍᴍᴀɴᴅꜱ.\n\n"
        "Please choose an option below to explore features."
    )

    main_buttons = [
        [Button.inline("📼 Modes", b"modes"), Button.inline("🎐 Items", b"items")],
        [Button.inline("🥇 Double or Nothing", b"double_or_nothing")],
        [Button.inline("🏆 Gamble", b"gamble_mode")],
    ]

    await bot.send_message(
        event.chat_id,
        HELP_MENU,
        buttons=main_buttons,
        link_preview=False,
        reply_to=event.id,
        parse_mode="html"   # ✅ enable clickable username
    )


#expired medicines handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_expired_")))
async def use_expired_medicine_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    uid = event.sender_id
    turn_uid = session['players'][session['turn_index']]
    if uid != turn_uid:
        await event.answer("It's not your turn!", alert=True)
        return

    items = session['items'].get(uid, [])
    if items.count("💊 Expired Medicine") == 0:
        await event.answer("You have no Expired Medicine!", alert=True)
        return

    max_hp = session['max_hps'].get(uid, session['hps'][uid])

    if session['hps'][uid] >= max_hp:
        await event.answer("You can't use Expired Medicine at full health!", alert=True)
        return

    session['items'][uid].remove("💊 Expired Medicine")

    # 🎯 Customizable success chance
    chance = session.get('medic_chance', 50)  # default 50%
    success = random.randint(1, 100) <= chance

    if success:
        prev_hp = session['hps'][uid]
        session['hps'][uid] += 2
        if session['hps'][uid] > max_hp:
            session['hps'][uid] = max_hp
        gained = session['hps'][uid] - prev_hp
        msg = f"💊 <a href='tg://user?id={uid}'>{event.sender.first_name}</a> used Expired Medicine and gained +{gained} ⚡ HP!"
    else:
        session['hps'][uid] -= 1
        if session['hps'][uid] < 0:
            session['hps'][uid] = 0
        msg = f"💊 <a href='tg://user?id={uid}'>{event.sender.first_name}</a> used Expired Medicine and lost 1 ⚡ HP... 😵"

    # ✅ Deduct healing penalty points here
    apply_healing_penalty(session, uid)
    await log_points(event, uid, f"used Expired Medicine, lost {HEALING_PENALTY} pts")

    await event.edit(msg, parse_mode='html')  # Explicitly setting parse_mode to html

    await asyncio.sleep(6)

    # 🔁 Check if medicine caused a death
    if await check_end_of_round(event, session):
        return

    await show_next_turn(event, session)


#jammer handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_jammer_")))
async def use_jammer_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return
    
    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return

    
    uid = event.sender_id
    if uid != session['players'][session['turn_index']]:
        await event.answer("It's not your turn!", alert=True)
        return
    
    if session['items'].get(uid, []).count("📡 Jammer") == 0:
        await event.answer("You have no Jammer!", alert=True)
        return

    # Ask whom to target
    buttons = []
    for pid in session['players']:
        if pid != uid and session['hps'].get(pid, 0) > 0:
            user = await event.client.get_entity(pid)
            buttons.append(Button.inline(user.first_name, f"jammer_target_{pid}".encode()))
    
    # 2-column button layout
    button_rows = []
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) == 2:
            button_rows.append(row)
            row = []
    if row:
        button_rows.append(row)

    await event.edit("📡 Who do you want to use Jammer on?", buttons=button_rows)


@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"jammer_target_")))
async def apply_jammer(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return
    
    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return

    
    uid = event.sender_id
    if uid != session['players'][session['turn_index']]:
        return

    parts = event.data.decode().split("_")
    target_id = int(parts[-1])

    # Remove Jammer from user's items
    if session['items'][uid].count("📡 Jammer") == 0:
        await event.answer("You have no Jammer!", alert=True)
        return
    session['items'][uid].remove("📡 Jammer")

    # Set flag to skip target's next turn
    session.setdefault("jammer_skips", {})
    session['jammer_skips'][target_id] = session['jammer_skips'].get(target_id, 0) + 1


    target = await event.client.get_entity(target_id)
    await event.edit(f"📡 Jammer activated on <a href='tg://user?id={target_id}'>{target.first_name}</a> — their next turn will be skipped.", parse_mode='html') # Explicitly setting parse_mode to html
    await asyncio.sleep(6)
    await show_next_turn(event, session)


#remote handler
@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_remote_")))
async def use_remote_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    sess_map = sessions.get(event.chat_id, {})
    session = None
    game_id = None
    for _gid, _s in sess_map.items():
        if event.sender_id in _s.get('players', []):
            session = _s
            game_id = _s.get('game_id', _gid)
            break
    if not session:
        return


    if len(session['players']) != 4:
        await event.answer("📺 Remote can only be used in 4-player games!", alert=True)
        return

    uid = event.sender_id
    if uid != session['players'][session['turn_index']]:
        await event.answer("It's not your turn!", alert=True)
        return

    if session['items'].get(uid, []).count("📺 Remote") == 0:
        await event.answer("You have no Remote!", alert=True)
        return

    # Remove remote
    session['items'][uid].remove("📺 Remote")

    # Reverse turn order
    current_player = session['players'][session['turn_index']]
    session['players'].reverse()
    # Realign turn_index to current player's new position
    session['turn_index'] = session['players'].index(current_player)

    await event.edit(
    f"📺 <a href='tg://user?id={event.sender_id}'>{event.sender.first_name}</a> used Remote! Turn order has been reversed.",
    parse_mode='html' # Explicitly setting parse_mode to html
)
    await asyncio.sleep(6)
    await show_next_turn(event, session)



@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"end_game")))
async def end_game_vote_handler(event):
    try:
        # Extract game_id from callback data: "end_game:<gid>"
        data = event.data.decode("utf-8")
        _, gid_str = data.split(":", 1)
        game_id = gid_str


        sess_map = sessions.get(event.chat_id, {})
        session = sess_map.get(game_id)

        if not session:
            await event.answer("This game session no longer exists.", alert=True)
            return

        uid = event.sender_id

        # If user not part of this session
        if uid not in session['players']:
            await event.answer("You are not part of this game.", alert=True)
            return

        # If user is dead
        if session['hps'].get(uid, 0) <= 0:
            await event.answer("Only alive players can vote to end the game.", alert=True)
            return

        # Record the vote
        session.setdefault('end_votes', set()).add(uid)

        alive_players = [p for p in session['players'] if session['hps'].get(p, 0) > 0]

        if all(p in session['end_votes'] for p in alive_players):
            text = "❌ All players agreed to end the game.\n\nGame has been terminated by mutual decision."

            # Remove from locked_players
            for pid in session['players']:
                locked_players.discard(pid)

            # Remove only this game_id session, not all
            sess_map.pop(game_id, None)
            if not sess_map:
                remove_single_session(event.chat_id, session)


            await event.edit(text, parse_mode='html')

        else:
            remaining = len(alive_players) - len(session['end_votes'])
            await event.answer(f"Waiting for {remaining} other player(s) to end the game...", alert=True)

    except Exception as e:
        await event.answer("An error occurred while processing your vote.", alert=True)
        print("Error in end_game_vote_handler:", e)




@bot.on(events.NewMessage(pattern='/refresh'))
async def refresh_user_handler(event):
    if is_banned(event.sender_id):
        return  # silently ignore
    if event.sender_id not in MOD_IDS:
        await event.reply("🚫 You are not authorized to use this command.")
        return

    if not event.is_reply:
        await event.reply("Reply to any player in the game you want to refresh.")
        return

    reply = await event.get_reply_message()
    target_id = reply.sender_id

    # ✅ Traverse through all chats & all game sessions
    for chat_id, games in list(sessions.items()):
        for game_id, sess in list(games.items()):
            if target_id in sess.get("players", []):
                # --- Found the session ---
                affected_players = sess["players"][:]

                # Mark session finished so old buttons stop working
                sess["finished"] = True

                # Unlock all players in this session
                for uid in affected_players:
                    locked_players.discard(uid)
                    sess.get("hps", {}).pop(uid, None)
                    sess.get("items", {}).pop(uid, None)

                # Cleanup this session
                games.pop(game_id, None)
                if not games:
                    sessions.pop(chat_id, None)

                # Notify group
                await event.reply(
                    f"✅ The game session has been terminated!\n\n"
                    f"""Players: {', '.join([f'<a href="tg://user?id={uid}">{uid}</a>' for uid in affected_players])}\n\n"""
                    "🔄 They can now join new game lobby.",
                    parse_mode="html"
                )


                # Notify each player privately
                for uid in affected_players:
                    try:
                        await bot.send_message(
                            uid,
                            "🔄 A moderator has refreshed your game. You can now join a new one."
                        )
                    except:
                        pass

                return  # stop after first matching session




async def check_end_of_round(event, session):
    dead = [uid for uid, hp in session['hps'].items() if hp <= 0]
    alive_list = [uid for uid in session['players'] if session['hps'].get(uid, 0) > 0]

    if len(dead) == 0:
        return False  # No one eliminated yet

    # ❌ No one alive
    if not alive_list:
        await event.edit("❌ No players left alive. Ending game.")
        for uid in session['players']:
            locked_players.discard(uid)
        remove_single_session(event.chat_id, session)

        return True

    # ---- 2v2 mode ----
    if session['player_count'] == 4 and session.get("mode") == "2v2" and 'teams' in session:
        team1, team2 = session['teams']
        team1_alive = [uid for uid in team1 if session['hps'].get(uid, 0) > 0]
        team2_alive = [uid for uid in team2 if session['hps'].get(uid, 0) > 0]

        # ✅ Round ends ONLY when one full team is eliminated
        if len(team1_alive) == 0 or len(team2_alive) == 0:
            # Determine which team is still alive
            winning_team = team1 if len(team1_alive) > 0 else team2
            # CREATE elimination_order from death_order + last survivor
            winner_uid = winning_team[0] if winning_team else None
            if winner_uid:
                elimination_order = session['death_order'] + [winner_uid]
            else:
                elimination_order = session['death_order']

            await award_2v2_points(event, session, elimination_order)

            # Increase rounds played
            session['round'] = session.get('round', 1) + 1

            # --- Custom 2v2 round winner message ---
            winner_clickables = [
                f"[{(await event.client.get_entity(uid)).first_name}](tg://user?id={uid})"
                for uid in winning_team
            ]

            # If this was the last round → go directly to results
            if session['round'] > session.get('max_rounds', 3):
                interim = await event.edit(
                    f"♦️ Round {session['round'] - 1} ended...!!\n"
                    f"💥 {' and '.join(winner_clickables)} won this Round. Congratulations to the winning team!\n\n"
                    "All rounds ended! 🎉\n\n"
                    "📢 Therefore I am sending the results...",
                    parse_mode="markdown"
                )
                # save interim message id so results can reply to this message
                session['imterim'] = interim.id
                await asyncio.sleep(2)
                await show_final_results_2v2(interim, session)

                # REPLACE WITH:
                for uid in session['players']:
                    locked_players.discard(uid)

                # remove only this specific session (game_id) from the chat mapping
                sess_map = sessions.get(event.chat_id, {})
                game_to_remove = None
                for gid, s in list(sess_map.items()):
                    # match either by identity or by stored game_id
                    if s is session or s.get('game_id') == session.get('game_id'):
                        game_to_remove = gid
                        break

                if game_to_remove:
                    sess_map.pop(game_to_remove, None)

                # if no more game sessions in this chat, remove the chat entry entirely
                if not sess_map:
                    remove_single_session(event.chat_id, session)


                return True

            else:
                await event.edit(
                    f"♦️ Round {session['round'] - 1} ended...!!\n"
                    f"💥 {' and '.join(winner_clickables)} won this Round. "
                    f"Congratulations to the winning team ... Moving to next round!\n"
                    f"🔷 Starting Round no.{session['round']} hold a second..",
                    parse_mode="markdown"
                )
                await asyncio.sleep(5)


            # If match finished, show final scores
            if session['round'] > session.get('max_rounds', 3):
                # 🏁 show round-end summary on main game message
                interim = await event.edit(
                    f"♦️ Round {session['round'] - 1} ended...!!\n"
                    f"💥 Congratulations to the winners of the last round.\n"
                    f"All rounds ended! 🎉\n\n"
                    "📢 Therefore I am sending the results...",
                    parse_mode="html"
                )
                # save interim message id so results can reply to this message
                session['imterim'] = interim.id
                await asyncio.sleep(2)

                # 📊 reply with final scoreboard
                await show_final_results_2v2(interim, session)


                for uid in session['players']:
                    locked_players.discard(uid)
                remove_single_session(event.chat_id, session)

                return True


                        # Reset for new round (randomize player order every round)
            shared_hp = get_initial_hp()
            # restore HPs (this uses current session['players'] but we'll shuffle below)
            session['hps'] = {uid: shared_hp for uid in session['players']}
            session['max_hps'] = {uid: shared_hp for uid in session['players']}
            session['death_order'] = []
            reset_items_new_round(session)

            # 🔀 Randomize the player order each round (applies to 2v2, 1v3, 1v1)
            # Fully shuffle the player list so join order no longer determines turn order.
            if session.get("mode") == "2v2" and "teams" in session:
                team1, team2 = session['teams']
                if random.choice([True, False]):
                    session['players'] = [team1[0], team2[0], team1[1], team2[1]]
                else:
                    session['players'] = [team2[0], team1[0], team2[1], team1[1]]
            else:
                random.shuffle(session['players'])


            # Reload bullets
            bullets, alive, blank = pick_bullets()
            session['bullet_queue'] = bullets

            # Ensure turn_index points to the first alive player (safe fallback)
            session['turn_index'] = 0
            for i, uid in enumerate(session['players']):
                if session['hps'].get(uid, 0) > 0:
                    session['turn_index'] = i
                    break

            await show_reload_message(event, session)
            await show_next_turn(event, session)
            return True





    # ---- 1v3 mode ----
    # ---- 1v3 mode ----
    if session['mode'] == "1v3" and len(alive_list) == 1:
        winner_uid = alive_list[0]
    
    # Make sure session['death_order'] is fully populated:
        for uid in session['players']:
            if uid not in session['death_order'] and uid != winner_uid and session['hps'].get(uid, 0) <= 0:
                session['death_order'].append(uid)
    # Now create elimination_order:
        elimination_order = session['death_order'] + [winner_uid]
    
        await award_1v3_points(event, session, elimination_order)
    
        if session['round'] >= 3:    # or session['round'] > 3 depending on your logic
            await show_final_results_1v3(event, session)
            for uid in session['players']:
                locked_players.discard(uid)
            remove_single_session(event.chat_id, session)

            return True
        session['round'] += 1
        await asyncio.sleep(7)
        await event.edit(f" Round {session['round']} is starting...\nReshuffling health, items and bullets!")
        shared_hp = get_initial_hp()
        # reset HPs
        session['hps'] = {uid: shared_hp for uid in session['players']}
        session['max_hps'] = {uid: shared_hp for uid in session['players']}
        session['death_order'] = []
        reset_items_new_round(session)

        # 🔀 RANDOMIZE turn order each round (applies to 1v3)
        random.shuffle(session['players'])

        # reload bullets
        bullets, alive, blank = pick_bullets()
        session['bullet_queue'] = bullets

        # Ensure turn_index points to the first alive player (safety)
        session['turn_index'] = 0
        for i, uid in enumerate(session['players']):
            if session['hps'].get(uid, 0) > 0:
                session['turn_index'] = i
                break

        session['eliminated'] = []
        await show_reload_message(event, session)
        await show_next_turn(event, session)
        return True

       

 
 
    # ---- 1v1 mode ----
    if session['player_count'] == 2 and len(alive_list) == 1:
        alive = alive_list[0]
        dead_uid = dead[0]

        # Always award points first
        await award_1v1_points(event, session, alive, dead_uid)

        winner_score = session['rounds_won'][alive]
        loser_score = session['rounds_won'][dead_uid]

        session['round'] += 1

        if winner_score == 2 or session['round'] > 3:
            if session.get("mode") == "normal" and session.get("player_count") == 2:
                await show_final_results_1v1(event, session)
            elif session.get("mode") == "1v3":
                await show_final_results_1v3(event, session)
            elif session.get("mode") == "2v2":
                await show_final_results_2v2(event, session)
            else:
                await show_final_solo_summary(event, session)

            for uid in session['players']:
                locked_players.discard(uid)
            remove_single_session(event.chat_id, session)

            return True

        await asyncio.sleep(7)
        await event.edit(f" Round {session['round']} is starting...\nReshuffling health, items and bullets!")
        await asyncio.sleep(5)
        shared_hp = get_initial_hp()
        session['hps'] = {uid: shared_hp for uid in session['players']}
        session['max_hps'] = {uid: shared_hp for uid in session['players']}
        reset_items_new_round(session)

        bullets, alive, blank = pick_bullets()
        session['bullet_queue'] = bullets

        if alive in session['players']:
            session['turn_index'] = session['players'].index(alive)
        else:
            session['turn_index'] = 0
            
        await show_reload_message(event, session)
        await show_next_turn(event, session)
        return True

    return False


    

# --- Help Menu Handlers ---

@bot.on(events.CallbackQuery(data=b"modes"))
async def modes_menu(event):
    user_id = event.sender_id
    if is_banned(user_id):
        await event.answer("🚫 You are banned from using this bot.", alert=True)
        return

    
    
    text = (
        "🔰 Possible Game types :\n\n"
        "/sologame ᴛᴏ ꜱᴛᴀʀᴛ ᴀ 1 ᴠꜱ 1 ɢᴀᴍᴇ.\n"
        "/teamgame ᴛᴏ ꜱᴛᴀʀᴛ ᴀ 2 ᴠꜱ 2 ᴛᴇᴀᴍ ᴅᴇᴀᴛʜ ᴍᴀᴛᴄʜ\n"
        "/multiplayer ᴛᴏ ꜱᴛᴀʀᴛ ᴀ ᴍᴀx ꜱᴏʟᴏ ɢᴀᴍᴇ 1 ᴠꜱ 3\n\n"
        "Happy playing!"
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Back", b"back_main")]])

@bot.on(events.CallbackQuery(data=b"items"))
async def items_menu(event):
    user_id = event.sender_id
    if is_banned(user_id):
        await event.answer("🚫 You are banned from using this bot.", alert=True)
        return

    text = (
        "You're a gambler, your mission is to make money, so you risk your life by placing bets."
        "You'll get various items in the death game! use them to win the Game. You can play this game with your friends\n\n"
        "Confused with items ? Here's an explanation:\n\n"

        "<blockquote>1. Beer</blockquote>\n"
        "🍺 Beer helps to eject the current shell from the shotgun.\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>2. Cigarette</blockquote>\n"
        "🚬 Cigarette helps to regain 1⚡\n\n"
        "Note : cannot use it in full hp.\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>3. Inverter</blockquote>\n"
        "🔁 Inverter helps to change the polarity of current shell.\n\n"
        "live->blank or blank->live\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>4. Magnifier</blockquote>\n"
        "🔍 Reveals the polarity of current shell in the gun.\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>5. Hacksaw</blockquote>\n"
        "🪚 Hacksaw helps to deal double damage ⚡⚡ on live shot.\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>6. Handcuffs</blockquote>\n"
        "🪢 Restrain others in 2 player mode. Target's turns get skipped for 2 turns.\n\n"
        "Note : Mode only available in 2 player mode\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>7. Expired medicine</blockquote>\n"
        "💊 Risky heal. +2 ⚡ HP or -1⚡ HP. Use at your own risk.\n\n"
        "Note : cannot use it in full hp.\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>8. Adrenaline</blockquote>\n"
        "🧪 Adrenaline allows you to steal an item from the player or (dead) player "
        "(the stolen item automatically used immediately and you can't steal adrenaline from others)\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>9. Burner phone</blockquote>\n"
        "📱 Makes an anonymous call which tells you about an anonymous shell loaded in the shotgun.\n\n"
        "Note- In 2/4 player mode, you need at least 3 bullets loaded in shotgun to use it\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>10. Jammer</blockquote>\n"
        "📡 Jammer actually is 4 player version of handcuffs.\n\n"
        "It skips 1 turn of target user when used.\n\n"
        "Note : only available in 4 player mode.\n"
        "⊱⋅ ──────────── ⋅⊰\n"

        "<blockquote>11. Remote</blockquote>\n"
        "📟 Remote reverses the turn order in the match.\n\n"
        "Note : only available in 4 player mode"
    )
    await event.edit(text, buttons=[[Button.inline("🔙 Back", b"back_main")]], parse_mode="html")




@bot.on(events.CallbackQuery(data=b"double_or_nothing"))
async def double_or_nothing_handler(event):
    user_id = event.sender_id
    if is_banned(user_id):
        await event.answer("🚫 You are banned from using this bot.", alert=True)
        return

    await event.answer("🚧 Double or Nothing mode is under development!", alert=True)


@bot.on(events.CallbackQuery(data=b"gamble_mode"))
async def gamble_mode_handler(event):
    user_id = event.sender_id
    if is_banned(user_id):
        await event.answer("🚫 You are banned from using this bot.", alert=True)
        return

    await event.answer("🚧 Gamble mode is under development!", alert=True)



@bot.on(events.NewMessage(pattern='/ping'))
async def ping_handler(event):
    if event.sender_id not in MOD_IDS:
        return  # 🚫 Only for MOD_IDS

    start = datetime.datetime.now()
    msg = await event.reply("📡 Pinging...")
    end = datetime.datetime.now()

    # Calculate latency
    latency = (end - start).total_seconds()

    # Calculate uptime
    uptime = datetime.datetime.now() - bot_start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    await msg.edit(
        f" Pong! It took <b>{latency:.2f} seconds</b>\n"
        f"Uptime – {days}d {hours}h {minutes}m {seconds}s",
        parse_mode='html'
    )



@bot.on(events.NewMessage(pattern=r'^\.send(?:\s+(.*))?'))
async def send_message_handler(event):
    sender = await event.get_sender()
    if sender.id not in MOD_IDS:
        return

    match = event.pattern_match.group(1).strip()

    # === Case 1: In group and replying to someone ===
    if event.is_group and event.is_reply:
        reply_msg = await event.get_reply_message()
        if not match:
            await event.reply("Please provide a message to send.")
            return
        try:
            await event.delete()
        except:
            pass
        # Send anonymous reply to that user
        await bot.send_message(event.chat_id, match, reply_to=reply_msg.id)
        return

    # === Case 2: In PM, .send <chat_id> or reply to a media/text ===
    if event.is_private:
        # If replying to a message (media or text), extract chat_id from .send command
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            args = match.split(" ", 1)
            if not args:
                await event.reply("Usage: .send <chat_id> as reply to a media/text message.")
                return
            try:
                target_chat_id = int(args[0])
                # Send media or text anonymously
                if reply_msg.media:
                    await bot.send_file(target_chat_id, reply_msg.media, caption=reply_msg.text or "")
                else:
                    await bot.send_message(target_chat_id, reply_msg.text)
                await event.reply("Anonymous message sent.")
            except Exception as e:
                await event.reply(f"Failed to send message:\n{e}")
            return

        # If not a reply, expect text format: .send <chat_id> <message>
        args = match.split(" ", 1)
        if len(args) != 2:
            await event.reply("Usage:\n1. Reply to media/text: .send <chat_id>\n2. Or: .send <chat_id> <message>")
            return
        try:
            target_chat_id = int(args[0])
            message = args[1]
            await bot.send_message(target_chat_id, message)
            await event.reply("  sent.")
        except Exception as e:
            await event.reply(f"Failed to send message:\n{e}")
        return

    # Fallback
    await event.reply("Usage:\n- In group (reply): .send <message>\n- In PM:\n  • .send <chat_id> <message>\n  • reply to media/text with .send <chat_id>")
   


from telethon import events

# Replace with the group where status is allowed
ALLOWED_GROUP_ID = -1002634198761  # your target group ID

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    # Restrict to allowed group
    if event.chat_id != ALLOWED_GROUP_ID:
        return
    
    # Restrict to mods only
    if event.sender_id not in MOD_IDS:
        return
    
    # Count actual game sessions across all groups
    total_sessions = sum(len(sess_map) for sess_map in sessions.values())

    # Collect per-group session info
    group_info = {}
    for chat_id, sess_map in sessions.items():
        group_info[chat_id] = len(sess_map)

    total_groups = len(group_info)

    msg_lines = [
        "<b>Bot Status</b>\n",
        f"Total Active Sessions: <b>{total_sessions}</b>",
        f"Total Active Groups: <b>{total_groups}</b>\n"
    ]

    for i, (chat_id, count) in enumerate(group_info.items(), start=1):
        msg_lines.append(f"{i}. Chat ID: {chat_id} | Sessions: {count}")

    msg = "\n".join(msg_lines)
    await event.reply(msg, parse_mode="html")


bot.run_until_disconnected()
