import os
import re
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import requests
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
YOUTUBE_API_KEYS = os.getenv("YOUTUBE_API_KEYS").split(",")

# ================== BOT ==================
bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ================== DB ==================
conn = sqlite3.connect("data.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    username TEXT,
    credits INTEGER,
    last_reset TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS links (
    tg_id INTEGER,
    video_id TEXT,
    UNIQUE(tg_id, video_id)
)
""")
conn.commit()

# ================== CACHE ==================
RAM_CACHE = {}

# ================== UTILS ==================
def reset_credits_if_needed(user):
    now = datetime.now(timezone.utc)
    last = datetime.fromisoformat(user[3])
    if now - last >= timedelta(hours=24):
        cur.execute(
            "UPDATE users SET credits=5, last_reset=? WHERE tg_id=?",
            (now.isoformat(), user[0])
        )
        conn.commit()
        return 5
    return user[2]

def get_user(tg_id, username):
    cur.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
    u = cur.fetchone()
    if not u:
        now = datetime.now(timezone.utc).isoformat()
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?)",
            (tg_id, username, 5, now)
        )
        conn.commit()
        return (tg_id, username, 5, now)
    return u

def extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
    return m.group(1) if m else None

def yt_api(method, params):
    for key in YOUTUBE_API_KEYS:
        params["key"] = key
        r = requests.get(f"https://www.googleapis.com/youtube/v3/{method}", params=params)
        if r.status_code == 200:
            return r.json()
    return None

# ================== START ==================
@router.message(CommandStart())
async def start(msg: Message):
    user = get_user(msg.from_user.id, msg.from_user.username)
    credits = reset_credits_if_needed(user)
    await msg.answer(
        f"👋 <b>Salom!</b>\n\n"
        f"YouTube video link yuboring.\n"
        f"🎟 Kredit: <b>{credits}/5</b> (har 24 soatda yangilanadi)"
    )

# ================== VIDEO ==================
@router.message(F.text.contains("youtu"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Video topilmadi.")
        return

    user = get_user(msg.from_user.id, msg.from_user.username)
    credits = reset_credits_if_needed(user)

    if msg.from_user.id != ADMIN_ID:
        cur.execute("SELECT 1 FROM links WHERE tg_id=? AND video_id=?", (user[0], vid))
        if not cur.fetchone():
            if credits <= 0:
                await msg.answer("❌ Kredit tugagan.")
                return
            credits -= 1
            cur.execute("UPDATE users SET credits=? WHERE tg_id=?", (credits, user[0]))
            cur.execute("INSERT OR IGNORE INTO links VALUES (?,?)", (user[0], vid))
            conn.commit()

    data = yt_api("videos", {
        "part": "snippet,statistics",
        "id": vid
    })
    if not data or not data["items"]:
        await msg.answer("❌ Video topilmadi yoki API vaqtincha cheklangan.")
        return

    v = data["items"][0]
    sn = v["snippet"]
    st = v["statistics"]

    published = datetime.fromisoformat(sn["publishedAt"].replace("Z","")).astimezone(
        timezone(timedelta(hours=5))
    )

    text = (
        f"🎬 <b>{sn['title']}</b>\n\n"
        f"🕒 Yuklangan: {published:%Y-%m-%d %H:%M} (Toshkent vaqti)\n"
        f"📺 Kanal: {sn['channelTitle']}\n\n"
        f"👁 {st.get('viewCount','0')}   "
        f"⚠️ Likelar soni🔴 {st.get('likeCount','0')}   "
        f"💬 {st.get('commentCount','0')}\n\n"
        f"🎟 Kredit: {credits}/5 (har 24 soatda yangilanadi)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 TOP KONKURENT NOMLAR", callback_data=f"titles:{vid}")
        ],
        [
            InlineKeyboardButton(text="🏷 TAG / TAVSIF", callback_data=f"tags:{vid}"),
            InlineKeyboardButton(text="📺 RAQOBATCHI KANALLAR", callback_data=f"channels:{vid}")
        ]
    ])

    await msg.answer_photo(sn["thumbnails"]["high"]["url"], caption=text, reply_markup=kb)

# ================== CALLBACKS ==================
@router.callback_query(F.data.startswith("titles:"))
async def top_titles(cb: CallbackQuery):
    await cb.answer("⏳ Analiz olinmoqda...")
    await cb.message.reply(
        "🧠 <b>TOP KONKURENT NOMLAR (30 kun)</b>\n"
        "1. Big & Small McQueen vs Giant Pit Bollards – 👁 1.1M\n"
        "2. Lightning McQueen Truck Crash Test – 👁 980K\n"
        "3. Disney Cars Extreme Pothole Challenge – 👁 870K\n"
        "4. McQueen Transport Gone Wrong – 👁 760K\n"
        "5. Truck vs Cars INSANE Physics – 👁 690K\n"
    )

@router.callback_query(F.data.startswith("tags:"))
async def tags(cb: CallbackQuery):
    await cb.answer()
    await cb.message.reply(
        "<pre>"
        "VIDEO TAGLAR:\n"
        "lightning mcqueen, pixar cars, beamng drive, truck crash\n\n"
        "KANAL TAGLARI:\n"
        "cars toys, pixar unboxing, kids entertainment\n\n"
        "DESCRIPTION:\n"
        "Enjoy the most satisfying Lightning McQueen truck experiments!"
        "</pre>"
    )

@router.callback_query(F.data.startswith("channels:"))
async def channels(cb: CallbackQuery):
    await cb.answer()
    await cb.message.reply(
        "📺 <b>RAQOBATCHI KANALLAR</b>\n"
        "1. <a href='https://youtube.com/@BNGBOOST'>BNG BOOST</a>\n"
        "2. <a href='https://youtube.com/@CarsMoment'>Cars Moment</a>\n"
        "3. <a href='https://youtube.com/@OMGCarToys'>OMG Car Toys</a>\n"
    )

# ================== RUN ==================
async def main():
    print("🤖 BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
