import os
import re
import json
import asyncio
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
API_KEYS = os.getenv("YOUTUBE_API_KEYS", "").split(",")

DAILY_CREDIT = 5
CACHE_TTL = 60 * 60  # 1 soat

# ================== BOT INIT =================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================== DB ======================
db = sqlite3.connect("bot.db", check_same_thread=False)
sql = db.cursor()

sql.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    credit INTEGER,
    last_reset TEXT
)
""")

sql.execute("""
CREATE TABLE IF NOT EXISTS used_links(
    user_id INTEGER,
    link_hash TEXT,
    PRIMARY KEY(user_id, link_hash)
)
""")

sql.execute("""
CREATE TABLE IF NOT EXISTS cache(
    key TEXT PRIMARY KEY,
    value TEXT,
    created INTEGER
)
""")
db.commit()

# ================== RAM CACHE ===============
RAM = {}

# ================== HELPERS =================
def now_utc():
    return datetime.now(timezone.utc)

def reset_credit_if_needed(user_id):
    sql.execute("SELECT credit,last_reset FROM users WHERE user_id=?", (user_id,))
    row = sql.fetchone()
    if not row:
        sql.execute(
            "INSERT INTO users VALUES(?,?,?,?)",
            (user_id, "", DAILY_CREDIT, now_utc().isoformat())
        )
        db.commit()
        return DAILY_CREDIT

    credit, last = row
    if now_utc() - datetime.fromisoformat(last) >= timedelta(hours=24):
        sql.execute(
            "UPDATE users SET credit=?, last_reset=? WHERE user_id=?",
            (DAILY_CREDIT, now_utc().isoformat(), user_id)
        )
        db.commit()
        return DAILY_CREDIT
    return credit

def take_credit(user_id, link):
    if user_id == ADMIN_ID:
        return True

    h = hashlib.md5(link.encode()).hexdigest()
    sql.execute(
        "SELECT 1 FROM used_links WHERE user_id=? AND link_hash=?",
        (user_id, h)
    )
    if sql.fetchone():
        return True

    credit = reset_credit_if_needed(user_id)
    if credit <= 0:
        return False

    sql.execute(
        "UPDATE users SET credit=credit-1 WHERE user_id=?",
        (user_id,)
    )
    sql.execute(
        "INSERT OR IGNORE INTO used_links VALUES(?,?)",
        (user_id, h)
    )
    db.commit()
    return True

def get_api():
    return API_KEYS[int(datetime.utcnow().timestamp()) % len(API_KEYS)]

def yt(endpoint, params):
    params["key"] = get_api()
    r = requests.get(f"https://www.googleapis.com/youtube/v3/{endpoint}", params=params, timeout=15)
    if r.status_code != 200:
        raise Exception("YT API error")
    return r.json()

def cache_get(k):
    if k in RAM:
        return RAM[k]
    sql.execute("SELECT value,created FROM cache WHERE key=?", (k,))
    r = sql.fetchone()
    if r and time.time() - r[1] < CACHE_TTL:
        RAM[k] = json.loads(r[0])
        return RAM[k]
    return None

def cache_set(k, v):
    RAM[k] = v
    sql.execute(
        "REPLACE INTO cache VALUES(?,?,?)",
        (k, json.dumps(v), int(time.time()))
    )
    db.commit()

# ================== START ===================
@dp.message(F.text == "/start")
async def start(m: Message):
    await m.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video link yuboring.\n"
        "🎟 Kredit: 5/5 (har 24 soatda yangilanadi)"
    )

# ================== VIDEO ===================
@dp.message(F.text.regexp(r"youtu"))
async def handle_video(m: Message):
    link = m.text.strip()

    if not take_credit(m.from_user.id, link):
        await m.answer("❌ Kredit tugadi. 24 soat kuting.")
        return

    await m.answer("⏳ Video analiz qilinmoqda...")

    vid = re.findall(r"(?:v=|be/)([\w-]{11})", link)
    if not vid:
        await m.answer("❌ Video topilmadi.")
        return
    vid = vid[0]

    data = yt("videos", {
        "part": "snippet,statistics",
        "id": vid
    })["items"][0]

    sn = data["snippet"]
    st = data["statistics"]

    published = datetime.fromisoformat(sn["publishedAt"].replace("Z","+00:00"))
    tz_time = published + timedelta(hours=5)

    like = int(st.get("likeCount", 0))
    view = int(st.get("viewCount", 1))
    nakrutka = "🔴 Yuqori" if like/view > 0.3 else "🟢 Normal"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 TOP KONKURENT NOMLAR", callback_data=f"top:{vid}")],
        [InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tag:{vid}")],
        [InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"ch:{vid}")]
    ])

    await m.answer_photo(
        photo=sn["thumbnails"]["high"]["url"],
        caption=(
            f"🎬 <b>{sn['title']}</b>\n\n"
            f"🕒 Yuklangan: {tz_time:%Y-%m-%d %H:%M} (Toshkent vaqti)\n"
            f"📺 Kanal: {sn['channelTitle']}\n\n"
            f"👁 {view}   👍 {like}   💬 {st.get('commentCount',0)}\n"
            f"⚠️ Likelar soni: {nakrutka}\n"
            f"🎟 Kredit: {reset_credit_if_needed(m.from_user.id)}/{DAILY_CREDIT} (har 24 soatda yangilanadi)"
        ),
        reply_markup=kb
    )

# ================== TOP TITLES ==============
@dp.callback_query(F.data.startswith("top:"))
async def top_titles(c: CallbackQuery):
    vid = c.data.split(":")[1]
    await c.answer("⏳ Olinmoqda...", show_alert=False)

    v = yt("videos", {"part":"snippet","id":vid})["items"][0]
    q = v["snippet"]["title"].split("|")[0][:50]

    res = yt("search", {
        "part":"snippet",
        "q":q,
        "type":"video",
        "order":"viewCount",
        "maxResults":10
    })["items"]

    text = "🧠 <b>TOP KONKURENT NOMLAR (30 kun)</b>\n\n"
    for i,x in enumerate(res,1):
        t = x["snippet"]["title"]
        link = f"https://youtu.be/{x['id']['videoId']}"
        text += f"{i}. <a href='{link}'>{t}</a>\n"

    await c.message.answer(text)

# ================== TAG / DESC ==============
@dp.callback_query(F.data.startswith("tag:"))
async def tags(c: CallbackQuery):
    vid = c.data.split(":")[1]
    v = yt("videos", {"part":"snippet","id":vid})["items"][0]
    sn = v["snippet"]

    tags = ", ".join(sn.get("tags", [])[:40])
    desc = sn.get("description","")[:3000]

    await c.message.answer(
        "🏷 <b>TAG / TAVSIF</b>\n\n"
        "<code>Video taglari:\n"
        f"{tags}\n\n"
        "Video description:\n"
        f"{desc}</code>"
    )

# ================== CHANNELS =================
@dp.callback_query(F.data.startswith("ch:"))
async def channels(c: CallbackQuery):
    vid = c.data.split(":")[1]
    v = yt("videos", {"part":"snippet","id":vid})["items"][0]
    title = v["snippet"]["title"].split()[0]

    res = yt("search", {
        "part":"snippet",
        "q":title,
        "type":"channel",
        "maxResults":10
    })["items"]

    txt = "📺 <b>RAQOBATCHI KANALLAR</b>\n\n"
    for i,x in enumerate(res,1):
        ch = x["snippet"]["channelTitle"]
        link = f"https://youtube.com/channel/{x['id']['channelId']}"
        txt += f"{i}. <a href='{link}'>{ch}</a>\n"

    await c.message.answer(txt)

# ================== RUN =====================
async def main():
    print("🤖 BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
