from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
import datetime
import random
import os
import threading
import asyncio
import asyncio
import uvicorn
from fastapi import FastAPI



API_ID = '5581609'
API_HASH = '21e8ed894fc3eb3e40ca1d277609e114'
BOT_TOKEN = '8074351087:AAE656jg51zZ9tA4pwREjb0Gd9qG6Jyw7oI'
MOD_IDS = {7556899383, 7038303029, 1716686899, 7663874497, 7735193452}  # Replace with actual mod Telegram user IDs

bot = TelegramClient("bot", API_ID, API_HASH)


sessions = {}
locked_players = set()
bot_start_time = datetime.datetime.now()



from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def home():
    return {"status": "ok"}


async def show_reload_message(event, session):
    # Decide how many bullets in this reload
    total_bullets = random.randint(3, 8)
    blank = random.randint(1, total_bullets - 1)
    alive = total_bullets - blank

    # Prepare bullet order
    bullets = ['live'] * alive + ['blank'] * blank
    random.shuffle(bullets)
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
    session = sessions.get(event.chat_id)
    if not session:
        return True
    return event.sender_id not in session.get("players", [])

def refill_items(session):
    item_count = random.choice([2, 3])
    item_pool = ["🍺 Beer", "🚬 Cigarette", "🔁 Inverter", "🔍 Magnifier", "🪚 Hacksaw", "🧪 Adrenaline", "📱 Burner Phone", "💊 Expired Medicine"]
    if len(session["players"]) == 2:
        item_pool.append("🪢 Handcuffs")
    if len(session["players"]) == 4:
        item_pool.extend(["📡 Jammer", "📺 Remote"])

    for uid in session['players']:
        count = min(item_count, 8)
        session['items'][uid] = random.choices(item_pool, k=count)



def refill_items_on_reload(session):
    item_pool = [
        "🍺 Beer", "🚬 Cigarette", "🔁 Inverter", "🔍 Magnifier",
        "🪚 Hacksaw", "🧪 Adrenaline", "📱 Burner Phone", "💊 Expired Medicine"
    ]
    if len(session["players"]) == 2:
        item_pool.append("🪢 Handcuffs")
    if len(session["players"]) == 4:
        item_pool.extend(["📡 Jammer", "📺 Remote"])

    give = random.randint(2, 3)

    for uid in session['players']:
        # ✅ Skip if player is dead (HP ≤ 0)
        if session['hps'].get(uid, 0) <= 0:
            continue

        current_items = session.setdefault('items', {}).setdefault(uid, [])
        available_space = 8 - len(current_items)
        if available_space <= 0:
            continue

        to_add = min(give, available_space)
        new_items = random.choices(item_pool, k=to_add)
        current_items.extend(new_items)




def reset_items_new_round(session):
    item_pool = [
        "🍺 Beer", "🚬 Cigarette", "🔁 Inverter", "🔍 Magnifier",
        "🪚 Hacksaw", "🧪 Adrenaline", "📱 Burner Phone", "💊 Expired Medicine"
    ]
    if len(session["players"]) == 2:
        item_pool.append("🪢 Handcuffs")
    if len(session["players"]) == 4:
        item_pool.extend(["📡 Jammer", "📺 Remote"])

    session['items'] = {}
    for uid in session['players']:
        count = random.randint(2, 3)
        session['items'][uid] = random.choices(item_pool, k=count)



@bot.on(events.NewMessage(pattern='/multiplayer'))
async def multiplayer_handler(event):
    if event.sender_id in locked_players:
        await event.reply("🚫 You are already in a game! Finish it or wait for a mod to refresh you.")
        return

    await event.respond(
        "Choose which mode you want to play?!",
        buttons=[
            [Button.inline("⚡️Normal", b"mode_normal"), Button.inline("🏆Gamble", b"mode_gamble")]
        ]
    )




@bot.on(events.CallbackQuery(data=b"mode_gamble"))
async def unavailable_mode(event):
    await event.answer("This mode currently unavailable", alert=True)

@bot.on(events.CallbackQuery(data=b"mode_normal"))
async def choose_players(event):
    sessions[event.chat_id] = {'creator': event.sender_id}
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

    sessions[event.chat_id].update({
        'player_count': player_count,
        'mode': mode,
        'creator': creator.id,
        'players': [creator.id],
        'usernames': [f"@{creator.username}" if creator.username else f"{creator.first_name}"]
    })

    players_text = "\n".join([f"1. {sessions[event.chat_id]['usernames'][0]} ✅"] + [
        f"{i+1}. [ Waiting... ]" for i in range(1, player_count)
    ])
    
    await event.edit(
        f"🕹 A {player_count}-player game has been created. Please join to start the game!\n\nPlayers Joined:\n{players_text}",
        buttons=[Button.inline("Join game", b"join_game")]
    )


@bot.on(events.CallbackQuery(data=b"join_game"))
async def join_game(event):
    if event.sender_id in locked_players:
        await event.answer("🚫 You're already in a game!", alert=True)
        return

    session = sessions.get(event.chat_id)
    if not session:
        return

    user_id = event.sender_id
    username = f"@{event.sender.username}" if event.sender.username else event.sender.first_name

    if user_id in session['players']:
        await event.answer("You're already in the game!", alert=True)
        return

    if len(session['players']) >= session['player_count']:
        await event.answer("Game is full!", alert=True)
        return

    # Add player to session
    session['players'].append(user_id)
    session['usernames'].append(username)

    players_text = "\n".join([
        f"{i+1}. {session['usernames'][i]} ✅" if i < len(session['usernames']) else f"{i+1}. [ Waiting... ]"
        for i in range(session['player_count'])
    ])

    if len(session['players']) == session['player_count']:
        if session.get("mode") == "2v2":
            creator_name = session['usernames'][0]
            await event.edit(
                f"✅ All players have joined!\n\nWaiting for {creator_name} to choose a partner...",
                buttons=[Button.inline("🧑‍🤝‍🧑 Choose Partner", b"choose_partner")]
            )
        else:
            await event.edit(
                f"✅ All players have joined!\n\nWaiting for {session['usernames'][0]} to start the game.",
                buttons=[Button.inline("🕹 Start Game", b"start_game")]
            )
    else:
        await event.edit(
            f"🕹 A {session['player_count']}-player game has been created. Please join to start the game!\n\nPlayers Joined:\n{players_text}",
            buttons=[Button.inline("Join game", b"join_game")]
        )

@bot.on(events.CallbackQuery(data=b"choose_partner"))
async def choose_partner_handler(event):
    session = sessions.get(event.chat_id)
    if not session or session.get("mode") != "2v2" or "players" not in session:
        return

    if event.sender_id != session["creator"]:
        return await event.answer("Only the game creator can choose a partner.", alert=True)

    partner_buttons = []
    for uid, uname in zip(session['players'][1:], session['usernames'][1:]):
        safe_uname = uname.strip() or f"Player {uid}"
        partner_buttons.append([Button.inline(safe_uname, f"set_partner_{uid}".encode())])

    await event.edit(
        "👥 Choose your teammate for 2v2 mode:",
        buttons=partner_buttons
    )

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"set_partner_")))
async def partner_selection(event):
    session = sessions.get(event.chat_id)
    if not session or session.get("mode") != "2v2" or "players" not in session:
        return

    if event.sender_id != session["creator"]:
        return await event.answer("Only the game creator can choose a partner.", alert=True)

    # Extract partner UID from callback data
    try:
        chosen_uid = int(event.data.decode().split("_")[2])
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
        buttons=[Button.inline("🕹 Start Game", b"start_game")],
        parse_mode="html"
    )



@bot.on(events.CallbackQuery(data=b"start_game"))
async def start_game(event):
    session = sessions.get(event.chat_id)
    if not session or event.sender_id != session['creator']:
        await event.answer("User unaccessible", alert=True)
        return
    await event.edit("Game is starting... Hold a second while I am shuffling items.")
    await asyncio.sleep(4)

    total_bullets = random.randint(3, 8)
    blank = random.randint(1, total_bullets - 1)
    alive = total_bullets - blank
    bullets = ['live'] * alive + ['blank'] * blank
    random.shuffle(bullets)
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
        # 🔄 Arrange players in alternating-team order for the game start
        if 'teams' in session:
            team1, team2 = session['teams']
            new_order = []
            for i in range(len(team1)):
                new_order.append(team1[i])
                new_order.append(team2[i])
            session['players'] = new_order

    session['turn_index'] = 0
    session.update({
        'round': 1,
        'wins': {uid: 0 for uid in session['players']},
    })

    shared_hp = random.randint(1, 2)
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
    for uid in session['players']:
        locked_players.add(uid)



# ---------- POINT SYSTEM BEGIN ----------
def init_points_for_game(session):
    session['points'] = {uid: 0 for uid in session['players']}
    session['round_points'] = {
        uid: [0 for _ in range(session.get('max_rounds', 3))]
        for uid in session['players']
    }
    session['death_order'] = []
    session['rounds_won'] = {uid: 0 for uid in session['players']}

    if session.get("mode") == "2v2":
        session['max_rounds'] = 3  # Always exactly 3 rounds
    else:
        session['max_rounds'] = 3  # Other modes can be changed if needed


async def award_1v1_points(event, session, winner_id, loser_id):
    session['points'][winner_id] += 5000
    session['points'][loser_id] += 1000
    session['rounds_won'][winner_id] += 1
    await log_points(event, winner_id, "won the round, gained 5000 pts")
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




async def award_2v2_points(event, session, elimination_order):
    """
    2v2 Scoring Rules:
    - Normal case:
        1st dead  -> 1k
        2nd dead  -> 2k
        3rd dead  -> 3k
        Last alive -> 5k
    - Flawless case (both survivors from same team):
        Eliminated players -> 1k and 2k
        Winners -> one gets 5k, other gets 3k
    """
    team1, team2 = session['teams']
    survivors = [uid for uid in session['players'] if uid not in elimination_order]

    # Flawless case
    if len(survivors) == 2 and (set(survivors) == set(team1) or set(survivors) == set(team2)):
        # Award eliminated players
        if len(elimination_order) >= 1:
            session['points'][elimination_order[0]] += 1000
            await log_points(event, elimination_order[0], "died 1st, earned 1000 pts")
        if len(elimination_order) >= 2:
            session['points'][elimination_order[1]] += 2000
            await log_points(event, elimination_order[1], "died 2nd, earned 2000 pts")

        # Flawless win: fixed 5k / 3k split for same-team survivors
        if set(survivors) == set(team1):
             session['points'][team1[0]] += 5000
             session['points'][team1[1]] += 3000
        elif set(survivors) == set(team2):
             session['points'][team2[0]] += 5000
             session['points'][team2[1]] += 3000

        await log_points(event, survivors[0], "flawless survival — earned 5000 pts")
        await log_points(event, survivors[1], "flawless survival — earned 3000 pts")


    else:
        # Normal round scoring
        reward_mapping = [1000, 2000, 3000]  # last alive handled separately
        for idx, uid in enumerate(elimination_order):
            pts = reward_mapping[idx] if idx < len(reward_mapping) else 0
            session['points'][uid] += pts
            await log_points(event, uid, f"died #{idx+1}, earned {pts} pts")

        if survivors:
            last_alive = survivors[0]
        else:
    # Last alive is the final one in elimination_order
            last_alive = elimination_order[-1]

        session['points'][last_alive] += 5000
        await log_points(event, last_alive, "won the round — earned 5000 pts")





HEALING_PENALTY = 10  # ✅ central penalty value

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


async def show_final_results_1v3(event, session):
    max_rounds = session.get('max_rounds', 3)

    async def get_player_name(uid):
        return (await get_name(event, uid)) if 'get_name' in globals() else str(uid)

    async def format_points_table():
        lines = []
        for uid in session['players']:
            user = await event.client.get_entity(uid)
            clickable_name = f"[{user.first_name}](tg://user?id={uid})"
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
    await event.edit("📢 Now bot is sending the full pointstable!", parse_mode="html")
    # Step 2: wait
    await asyncio.sleep(4)
    # Step 3: show actual table
    await event.edit(text, parse_mode="html")
    # wait 3 sec then send winner summary
    await asyncio.sleep(3)
    await show_final_solo_summary(event, session)





async def show_final_solo_summary(event, session):
    players = session['players']
    all_names = [f"[{(await event.client.get_entity(uid)).first_name}](tg://user?id={uid})" for uid in players]

    # --- First Elimination (first death in entire game) ---
    first_elim = []
    if session.get("death_order"):
        first_elim_user = await event.client.get_entity(session['death_order'][0])
        first_elim = [f"[{first_elim_user.first_name}](tg://user?id={first_elim_user.id})"]

    # Track stats
    damage_taken = session.get("damage_taken", {uid: 0 for uid in players})
    damage_dealt = session.get("damage_dealt", {uid: 0 for uid in players})
    kills = session.get("kills", {uid: 0 for uid in players})
    deaths = session.get("deaths", {uid: 0 for uid in players})
    round_winners = session.get("round_winners", [])

    # Most attacked
    most_attacked = []
    if damage_taken:
        max_taken = max(damage_taken.values())
        most_attacked = [f"[{(await event.client.get_entity(uid)).first_name}](tg://user?id={uid})"
                         for uid, v in damage_taken.items() if v == max_taken and v > 0]

    # Most aggressive
    most_attacker = []
    if damage_dealt:
        max_dealt = max(damage_dealt.values())
        most_attacker = [f"[{(await event.client.get_entity(uid)).first_name}](tg://user?id={uid})"
                         for uid, v in damage_dealt.items() if v == max_dealt and v > 0]

    # Most hated (players with 0 rounds won)
    most_hated = [f"[{(await event.client.get_entity(uid)).first_name}](tg://user?id={uid})"
                  for uid, v in session['rounds_won'].items() if v == 0]

    # Winner (highest points)
    winner_uid = max(session['points'], key=lambda u: session['points'][u])
    winner_entity = await event.client.get_entity(winner_uid)
    winner_name = f"[{winner_entity.first_name}](tg://user?id={winner_uid})"

    # Game duration
    duration = datetime.datetime.now() - session.get("game_start_time", bot_start_time)
    minutes, seconds = divmod(duration.seconds, 60)

    # --- Build message ---
    txt = f"""
🎄 The Solo match has ended between {', '.join(all_names)}!

───୨୧─────୨୧─────୨୧──

🔪 First Elimination : {', '.join(first_elim) if first_elim else "None"}

⚓ Most shooted player : {', '.join(most_attacked) if most_attacked else "None"}

🎯 Most attacking player : {', '.join(most_attacker) if most_attacker else "None"}

☠️ Most hated player : {', '.join(most_hated) if most_hated else "None"}

───୨୧─────୨୧─────୨୧──

🔰 𝗥𝗼𝘂𝗻𝗱 𝗪𝗶𝗻𝗻𝗲𝗿𝘀 :
"""

    for i, rw in enumerate(round_winners, 1):
        rw_uid = rw.get("winner")
        if not rw_uid: continue
        rw_entity = await event.client.get_entity(rw_uid)
        name = f"[{rw_entity.first_name}](tg://user?id={rw_uid})"
        txt += (f"\n🔫 Round {i} : {name}\n"
                f"🏴‍☠️ Kills : {kills.get(rw_uid,0)}\n"
                f"☠️ Death : {deaths.get(rw_uid,0)}\n"
                f"⚡ Hp reduced : {damage_dealt.get(rw_uid,0)}\n")

    txt += f"""

───୨୧─────୨୧─────୨୧──

🏆 Winner : {winner_name}

📯 Game duration : {minutes} min {seconds} sec
"""

    await event.respond(txt, parse_mode="markdown")




async def show_final_results_2v2(event, session):
    team1, team2 = session['teams']
    team1_total = sum(session['points'][uid] for uid in team1)
    team2_total = sum(session['points'][uid] for uid in team2)

    winner_team = "Team A" if team1_total > team2_total else "Team B"

    team1_share = team1_total // 2
    team2_share = team2_total // 2

    t1_names = " + ".join([await get_name(event, uid) for uid in team1])
    t2_names = " + ".join([await get_name(event, uid) for uid in team2])

    text = (
        "🏆 Final Results (2v2 Best of 3)\n\n"
        f"Team A - ({t1_names}) = {team1_total} pts\n"
        f"Team B - ({t2_names}) = {team2_total} pts\n\n"
        f"Winner Team: {winner_team}\n\n"
        "Points distributed to each player:\n"
        f"{await get_name(event, team1[0])}: {team1_share} pts\n"
        f"{await get_name(event, team1[1])}: {team1_share} pts\n"
        f"{await get_name(event, team2[0])}: {team2_share} pts\n"
        f"{await get_name(event, team2[1])}: {team2_share} pts"
    )
    await event.edit(text, parse_mode="html")



async def get_name(event, uid):
    user = await event.client.get_entity(uid)
    return user.first_name
# ---------- POINT SYSTEM END ----------



@bot.on(events.CallbackQuery(data=b"shot_other"))
async def handle_shot_other(event):
    if event.sender_id in locked_players:
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    session = sessions.get(event.chat_id)
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
        total_bullets = random.randint(3, 8)
        blank = random.randint(1, total_bullets - 1)
        alive = total_bullets - blank
        bullets = ['live'] * alive + ['blank'] * blank
        random.shuffle(bullets)
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
        if session['hps'][target_id] <= 0 and target_id not in session['death_order']:
            session['death_order'].append(target_id)

        # Award points for successful hit
        await award_shoot_points(event, session, shooter_id, target_id, is_live, damage, used_hacksaw=(damage == 2), shot_type="normal shot")

        if damage == 1:  # normal live bullet
            target_link = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
            shooter_link = f'<a href="tg://user?id={shooter.id}">{shooter.first_name}</a>'
            live_messages = [
                f"And that's the critical hit! Nice shot! Reducing 1 ⚡ of {target_link}!\n\n🎟️ Moving to next player",
                f"Who cares? Hahaha ! I can still win {shooter_link} shooted a live round to {target_link}!\n\n🎟️ Moving to next player.."
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




@bot.on(events.CallbackQuery(data=b"shot_self"))
async def handle_shot_self(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    session = sessions.get(event.chat_id)
    if not session or event.sender_id != session['players'][session['turn_index']]:
        await event.answer("Not your turn!", alert=True)
        return

    idx = session['turn_index']
    user_id = session['players'][idx]
    shooter_id = user_id  # define to avoid NameError
    user = await event.client.get_entity(user_id)

    if not session['bullet_queue']:
        total_bullets = random.randint(3, 8)
        blank = random.randint(1, total_bullets - 1)
        alive = total_bullets - blank
        bullets = ['live'] * alive + ['blank'] * blank
        random.shuffle(bullets)
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


    session = sessions.get(event.chat_id)
    if not session:
        return

    shooter_idx = session['turn_index']
    shooter_id = session['players'][shooter_idx]

    if event.sender_id != shooter_id:
        await event.answer("Not your turn!", alert=True)
        return

    target_id = int(event.data.decode().split("_")[1])
    if session['hps'].get(target_id, 0) <= 0:
        await event.answer("That player is already eliminated!", alert=True)
        return

    if not session['bullet_queue']:
        total_bullets = random.randint(3, 8)
        blank = random.randint(1, total_bullets - 1)
        alive = total_bullets - blank
        bullets = ['live'] * alive + ['blank'] * blank
        random.shuffle(bullets)
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
        if session['hps'][target_id] <= 0 and target_id not in session['death_order']:
            session['death_order'].append(target_id)

        
        target_link = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
        shooter_link = f'<a href="tg://user?id={shooter.id}">{shooter.first_name}</a>'

        if damage == 1:  
            target_link = f'<a href="tg://user?id={target.id}">{target.first_name}</a>'
            shooter_link = f'<a href="tg://user?id={shooter.id}">{shooter.first_name}</a>'
            live_messages = [
                f"And that's the critical hit! Nice shot! Reducing 1 ⚡ of {target_link}!\n\n🎟️ Moving to next player",
                f"Who cares? Hahaha ! I can still win {shooter_link} shooted a live round to {target_link}!\n\n🎟️ Moving to next player.."
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
    # 🪢 Check if current player should be skipped due to Handcuffs
    current_uid = session['players'][session['turn_index']]
    if session.get("skip_turn_for") == current_uid:
        session.pop("skip_turn_for")
        session['turn_index'] = (session['turn_index'] + 1) % len(session['players'])
        return await show_next_turn(event, session)
        
    # 📡 Skip due to Jammer
    if session.get("jammer_skips", {}).get(current_uid):
                   session['jammer_skips'].pop(current_uid)

                   # 🧠 If only 2 players alive in 4-player mode, return turn to other player
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
        total_bullets = random.randint(3, 8)
        blank = random.randint(1, total_bullets - 1)
        alive = total_bullets - blank
        bullets = ['live'] * alive + ['blank'] * blank
        random.shuffle(bullets)
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
    for uid in session['players']:
        if uid != shooter_id and session['hps'].get(uid, 0) > 0:
            target = await event.client.get_entity(uid)
            shoot_buttons.append(Button.inline(f"Shoot ({target.first_name})", f"shoot_{uid}".encode()))
    shoot_buttons.append(Button.inline("Shoot yourself", b"shot_self"))

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
    item_view_buttons = []
    for uid in session['players']:
        user = await event.client.get_entity(uid)
        item_view_buttons.append(Button.inline(f"🎒 {user.first_name} Items", f"items_{uid}".encode()))

    row = []
    for btn in item_view_buttons:
        row.append(btn)
        if len(row) == 2:
            button_rows.append(row)
            row = []
    if row:
        button_rows.append(row)

    # End Game button
    button_rows.append([Button.inline("❌ End Game", b"end_game")])

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
            shoot_buttons.append(Button.inline(f"Shoot ({target.first_name})", f"shoot_{uid}".encode()))
    shoot_buttons.append(Button.inline("Shoot yourself", b"shot_self"))
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
        item_view_buttons.append(Button.inline(f"🎒 {user.first_name} Items", f"items_{uid}".encode()))

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
    button_rows.append([Button.inline("❌ End Game", b"end_game")])



    # Final game board update
    await event.edit(
        game_board + eliminated_board,
        buttons=button_rows,
        link_preview=False,
        parse_mode='html' # Explicitly setting parse_mode to html
    )





@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"items_")))
async def handle_item_menu(event):
    session = sessions.get(event.chat_id)
    if not session or event.sender_id not in session.get("players", []):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    # ❌ Not your turn? Deny ANY item bag clicks
    if event.sender_id != session['players'][session['turn_index']]:
        await event.answer("⏳ You can only view item menus during your own turn!", alert=True)
        return

    parts = event.data.decode().split("_")
    if len(parts) < 2:
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        return

    if target_id not in session['players']:
        await event.answer("🚫 This player is no longer in this game.", alert=True)
        return

    is_self = event.sender_id == target_id
    user = await event.client.get_entity(target_id)
    item_list = session.get('items', {}).get(target_id, [])
    item_text = "\n".join([f"{i+1}. {item}" for i, item in enumerate(item_list)]) or "No items"

    buttons = []
    if is_self:
        # Only current-turn player can see and use their own items
        if item_list.count("🍺 Beer") > 0:
            buttons.append([Button.inline("🍺 Use Beer", f"use_beer_{target_id}".encode())])
        if item_list.count("🚬 Cigarette") > 0:
            buttons.append([Button.inline("🚬 Use Cigarette", f"use_cigarette_{target_id}".encode())])
        if item_list.count("🔁 Inverter") > 0:
            buttons.append([Button.inline("🔁 Use Inverter", f"use_inverter_{target_id}".encode())])
        if item_list.count("🔍 Magnifier") > 0:
            buttons.append([Button.inline("🔍 Use Magnifier", f"use_magnifier_{target_id}".encode())])
        if item_list.count("🪚 Hacksaw") > 0:
            buttons.append([Button.inline("🪚 Use Hacksaw", f"use_hacksaw_{target_id}".encode())])
        if item_list.count("🧪 Adrenaline") > 0:
            buttons.append([Button.inline("🧪 Use Adrenaline", f"use_adrenaline_{target_id}".encode())])
        if item_list.count("🪢 Handcuffs") > 0 and len(session['players']) == 2:
            buttons.append([Button.inline("🪢 Use Handcuffs", f"use_handcuffs_{target_id}".encode())])
        if item_list.count("📱 Burner Phone") > 0:
            buttons.append([Button.inline("📱 Use Burner Phone", f"use_burner_{target_id}".encode())])
        if item_list.count("💊 Expired Medicine") > 0:
            buttons.append([Button.inline("💊 Use Expired Medicine", f"use_expired_{target_id}".encode())])
        if item_list.count("📡 Jammer") > 0:
            buttons.append([Button.inline("📡 Use Jammer", f"use_jammer_{target_id}".encode())])
        if item_list.count("📺 Remote") > 0:
            buttons.append([Button.inline("📺 Use Remote", f"use_remote_{target_id}".encode())])

    buttons.append([Button.inline("🔙 Back", b"back_to_board")])

    await event.edit(
        f"🎒 <b>{user.first_name}'s Items</b>\n\n{item_text}",
        buttons=buttons,
        parse_mode='html'
    )




@bot.on(events.CallbackQuery(data=b"back_to_board"))
async def go_back_to_game(event):
    session = sessions.get(event.chat_id)
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


    session = sessions.get(event.chat_id)
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


    session = sessions.get(event.chat_id)
    if not session:
        return

    await show_next_turn(event, session)


#cigaratte handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_cigarette_")))
async def use_cigarette_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    session = sessions.get(event.chat_id)
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


    session = sessions.get(event.chat_id)
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


    session = sessions.get(event.chat_id)
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

    session = sessions.get(event.chat_id)
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


    session = sessions.get(event.chat_id)
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

    session = sessions.get(event.chat_id)
    if not session:
        return

    uid = session.get("adrenaline_thief")
    if uid != event.sender_id:
        return

    target_id = int(event.data.decode().split("_")[2])
    target_items = session['items'].get(target_id, [])

    if not target_items:
        await event.answer("Target has no items to steal!", alert=True)
        await show_next_turn(event, session)
        return

    session['steal_target'] = target_id
    buttons = [
        [Button.inline(item, f"steal_item_{target_id}_{item}".encode())] for item in set(target_items)
    ]

    # 🔙 BACK BUTTON — go back to player selector
    buttons.append([Button.inline("🔙 Back", b"adrenaline_back")])

    await event.edit("🧪 Choose item to steal:", buttons=buttons)



@bot.on(events.CallbackQuery(data=b"adrenaline_back"))
async def back_to_steal_player(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    session = sessions.get(event.chat_id)
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




@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"steal_item_")))
async def finalize_steal(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return

    import base64

    session = sessions.get(event.chat_id)
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

    session['items'][target_id].remove(item)
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
            session['skip_turn_for'] = opponent_id
            opponent = await event.client.get_entity(opponent_id)
            msg = f"🧪 {thief.first_name} stole 🪢 Handcuffs!\n{opponent.first_name}'s next turn will be skipped."
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

    session = sessions.get(event.chat_id)
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

    # Set skip turn flag
    opponent_id = [p for p in session['players'] if p != uid][0]
    session['skip_turn_for'] = opponent_id
    
    opponent = await event.client.get_entity(opponent_id)
    mention = f"<a href='tg://user?id={opponent.id}'>{opponent.first_name}</a>"
    
    await event.edit(
    f"🪢 You used Handcuffs!\n"
    f"{mention}'s next turn will be skipped — you get to shoot twice!",
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

    session = sessions.get(event.chat_id)
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


#expired medicines handler

@bot.on(events.CallbackQuery(data=lambda d: d.startswith(b"use_expired_")))
async def use_expired_medicine_handler(event):
    if is_locked(event):
        await event.answer("🚫 You are no longer part of this game.", alert=True)
        return


    session = sessions.get(event.chat_id)
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
    
    session = sessions.get(event.chat_id)
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
    
    session = sessions.get(event.chat_id)
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
    session.setdefault("jammer_skips", {})[target_id] = True

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

    session = sessions.get(event.chat_id)
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





@bot.on(events.CallbackQuery(data=b"end_game"))
async def end_game_vote_handler(event):
    session = sessions.get(event.chat_id)
    if not session:
        return

    uid = event.sender_id
    if uid not in session['players'] or session['hps'].get(uid, 0) <= 0:
        await event.answer("Only alive players can vote to end the game.", alert=True)
        return

    session.setdefault('end_votes', set()).add(uid)

    alive_players = [uid for uid in session['players'] if session['hps'].get(uid, 0) > 0]
    if all(p in session['end_votes'] for p in alive_players):
        text = "❌ All players agreed to end the game.\n\nGame has been terminated by mutual decision."
    
        # Remove from locked_players
        for uid in session['players']:
            locked_players.discard(uid)

        sessions.pop(event.chat_id, None)
        await event.edit(text, parse_mode='html') # Explicitly setting parse_mode to html

    else:
        remaining = len(alive_players) - len(session['end_votes'])
        await event.answer(f"Waiting for {remaining} other player(s) to end the game...", alert=True)



@bot.on(events.NewMessage(pattern='/refresh'))
async def refresh_user_handler(event):
    if event.sender_id not in MOD_IDS:
        await event.reply("🚫 You are not authorized to use this command.")
        return

    if not event.is_reply:
        await event.reply("Reply to the player you want to refresh.")
        return

    reply = await event.get_reply_message()
    target_id = reply.sender_id

    for chat_id, sess in list(sessions.items()):
        if target_id in sess.get("players", []):
            idx_to_remove = sess["players"].index(target_id)
            sess["players"].pop(idx_to_remove)
            if "usernames" in sess and idx_to_remove < len(sess["usernames"]):
                sess["usernames"].pop(idx_to_remove)
            sess["hps"].pop(target_id, None)
            sess["items"].pop(target_id, None)

            if not sess["players"]:
                sessions.pop(chat_id, None)

    locked_players.discard(target_id)

    await event.reply(f"✅ Refreshed <a href='tg://user?id={target_id}'>{reply.sender.first_name}</a>. They can now join new games.", parse_mode='html') # Explicitly setting parse_mode to html

    try:
        await bot.send_message(target_id, "🔄 You have been refreshed by a mod. You can now join a new game.")
    except:
        pass  # Bot can't DM unless user has /start'd







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
        sessions.pop(event.chat_id, None)
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
                await show_final_results_2v2(event, session)
                for uid in session['players']:
                    locked_players.discard(uid)
                sessions.pop(event.chat_id, None)
                return True

            # Reset for new round
            shared_hp = random.randint(1, 2)
            session['hps'] = {uid: shared_hp for uid in session['players']}
            session['max_hps'] = {uid: shared_hp for uid in session['players']}
            session['death_order'] = []
            reset_items_new_round(session)

            # 🔄 Keep alternating team order each round
            team1, team2 = session['teams']
            new_order = []
            for i in range(len(team1)):
                new_order.append(team1[i])
                new_order.append(team2[i])
            session['players'] = new_order

            # Reload bullets
            total_bullets = random.randint(3, 8)
            blank = random.randint(1, total_bullets - 1)
            alive = total_bullets - blank
            bullets = ['live'] * alive + ['blank'] * blank
            random.shuffle(bullets)
            session['bullet_queue'] = bullets
            session['turn_index'] = 0

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
            sessions.pop(event.chat_id, None)
            return True
        session['round'] += 1
        await asyncio.sleep(7)
        await event.edit(f" Round {session['round']} is starting...\nReshuffling health, items and bullets!")
        shared_hp = random.randint(1, 2)
        session['hps'] = {uid: shared_hp for uid in session['players']}
        session['max_hps'] = {uid: shared_hp for uid in session['players']}
        session['death_order'] = []
        reset_items_new_round(session)
        total_bullets = random.randint(3, 8)
        blank = random.randint(1, total_bullets - 1)
        alive = total_bullets - blank
        bullets = ['live'] * alive + ['blank'] * blank
        random.shuffle(bullets)
        session['bullet_queue'] = bullets
        session['turn_index'] = 0
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
            await show_final_results(event, session)
            for uid in session['players']:
                locked_players.discard(uid)
            sessions.pop(event.chat_id, None)
            return True

        await asyncio.sleep(7)
        await event.edit(f" Round {session['round']} is starting...\nReshuffling health, items and bullets!")
        await asyncio.sleep(5)
        shared_hp = random.randint(1, 2)
        session['hps'] = {uid: shared_hp for uid in session['players']}
        session['max_hps'] = {uid: shared_hp for uid in session['players']}
        reset_items_new_round(session)

        total_bullets = random.randint(3, 8)
        blank = random.randint(1, total_bullets - 1)
        alive_bullets = total_bullets - blank
        bullets = ['live'] * alive_bullets + ['blank'] * blank
        random.shuffle(bullets)
        session['bullet_queue'] = bullets

        if alive in session['players']:
            session['turn_index'] = session['players'].index(alive)
        else:
            session['turn_index'] = 0
            
        await show_reload_message(event, session)
        await show_next_turn(event, session)
        return True

    return False


    

# --- Constants ---
HELP_MENU = """
🤖 Welcome to Buckshot Roulette help menu!

Please choose an option below to explore features.
"""

# --- Buttons Layout ---
main_buttons = [
    [Button.inline("🎮 Multiplayer", b"mp_menu"), Button.inline("❗️ Items", b"items")],
    [Button.inline("🎲 Double or Nothing", b"double_or_nothing")],[Button.inline("Gamble mode", b"gamble_mode")],
]



items_buttons = [
    [Button.inline("🍺 Beer", b"beer"), Button.inline("🚬 Cigarette", b"cigarette")],
    [Button.inline(" 🔁 Inverter", b"inverter"), Button.inline("🔍 Magnifier", b"magnifier")],
    [Button.inline("🪚 Hacksaw", b"hacksaw"), Button.inline("🪢 Handcuffs", b"handcuffs")],
    [Button.inline("💊 Expired Medicines", b"expired_meds"), Button.inline("🧪 Adrenaline", b"adrenaline")],
    [Button.inline("📱 Burner Phone", b"burner_phone"), Button.inline("📡 Jammer", b"jammer")],
    [Button.inline("🎮 Remote", b"remote")],
    [Button.inline("🔙 Back", b"back_main")],
]

# --- Descriptions for Each Item ---
item_descriptions = {
    "beer": "🍺 Beer helps to eject the current shell from the shotgun.",
    "cigarette": "🚬 Cigarette helps to regain 1⚡\n\nNote- cant use it in full hp.",
    "inverter": " 🔁 Inverter helps to change the polarity of current shell.\n\nlive->blank or blank->live",
    "magnifier": "🔍 Reveals the polarity of current shell in the gun.",
    "hacksaw": "🪚 Hacksaw helps to deal double damage ⚡⚡ on live shot.",
    "handcuffs": "🪢 Restrain others in 2 player mode. Target's turns get skipped for 2 turns.\n\nNote- Mode only available in 2 player mode",
    "expired_meds": "💊 Risky heal. +2 ⚡ HP or -1⚡ HP. Use at your own risk.\n\nNote- cant use it in full hp.",
    "adrenaline": "🧪 Adrenaline allows you to steal an item from the player or (dead) player (the stolen item automatically used immediately and you cant steal adrenaline from others)",
    "burner_phone": "📱 Makes an anonymous call which tells you about and anonymous shell loaded in the shotgun.\n\nNote-  In 2/4 player mode, you need atleast 3 bullets loaded in shotgun to use it ",
    "jammer": "📡 Jammer actually is 4 player  version of handcuffs.\n\nIt skips 1 turn of target user when used.\n\nNote- only available in 4 player mode.",
    "remote": "Remote reverses the turn order in the match.\n\nNote- only available in 4 player mode",
}

# --- /help Command ---
@bot.on(events.NewMessage(pattern="/help"))
async def help_handler(event):
    if event.is_group or event.is_channel:
        await event.reply("❌ /help is not available in group chats. Please DM the bot to use this command.")
    else:
        await event.respond(HELP_MENU, buttons=main_buttons, link_preview=False)











# --- Callback Handlers ---
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    await asyncio.sleep(0.1)  # flood wait for spam protection

    data = event.data.decode("utf-8")

    if data == "mp_menu":
        await event.edit("ℹ️ Multiplayer Modes:\n1. 2 player~ Play a game having 2 players with it's own game rules.\n2. 4 player~ Play a game having 4 players with it's own game rules.\n\nWhat rules?  well  no specific rules..you can play individual or as a pair of 2 player as team..all depends on you!😁.\n\nJoin vc with your friends to talk ,for better game experience!✨", buttons=[Button.inline("🔙 Back", b"back_main")])

    elif data == "items":
        await event.edit("🧠 Choose an item to learn more:", buttons=items_buttons)

    elif data in item_descriptions:
        desc = item_descriptions[data]
        await event.edit(f" {desc}", buttons=[Button.inline("🔙 Back to Items", b"items")])

    elif data == "double_or_nothing":
        await event.edit("🎲 Double or Nothing mode is currently under development.", buttons=[Button.inline("🔙 Back", b"back_main")])
    elif data == "gamble_mode":
    	await event.edit("Gamble mode is currently under development.", buttons=[Button.inline("🔙 Back", b"back_main")])
    elif data == "back_main":
        await event.edit(HELP_MENU, buttons=main_buttons) 


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


@bot.on(events.NewMessage(pattern='/revealall'))
async def reveal_all_shells(event):
    session = sessions.get(event.chat_id)
    if not session or event.sender_id not in session.get("players", []):
        await event.reply("🚫 You're not in an active game.")
        return

    queue = session.get('bullet_queue', [])
    if not queue:
        await event.reply("🪖 The bullet queue is empty or not initialized yet.")
        return

    emoji_queue = ["💥" if b == "live" else "😮" for b in queue]
    await event.reply(f"📦 Full Bullet Queue:\n{' '.join(emoji_queue)}")


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


async def start_telethon_bot():
    await bot.start(bot_token=BOT_TOKEN)
    print("🤖 Bot started")
    await bot.run_until_disconnected()

async def start_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=10000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    # run both bot and server together
    await asyncio.gather(start_telethon_bot(), start_server())

if __name__ == "__main__":
    asyncio.run(main())




   
    
    
# Run bot
bot.run_until_disconnected()

# Start the bot
client.start(bot_token=BOT_TOKEN)
client.run_until_disconnected()
