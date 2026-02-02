import asyncio
import re
import hashlib
import sqlite3
import time
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

BOT_TOKEN = BOT_TOKEN.strip()
# =====================================


# ================= DATABASE ============
DB = "bot.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    credit INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS videos (
    sid TEXT PRIMARY KEY,
    video_id TEXT,
    top5 TEXT,
    created_at INTEGER
)
""")

conn.commit()
# =====================================


# ================= HELPERS =============
YOUTUBE_REGEX = r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)"

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def short_id(text):
    return hashlib.md5(text.encode()).hexdigest()[:10]

def fake_top5(vid):
    return [f"{vid}_competitor_{i}" for i in range(1, 6)]
# =====================================


bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ============ USERS ====================
def get_user(uid):
    cur.execute("SELECT credit FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def add_user(uid):
    cur.execute("INSERT OR IGNORE INTO users VALUES (?, ?)", (uid, 5))
    conn.commit()

def update_credit(uid, v):
    cur.execute("UPDATE users SET credit = credit + ? WHERE user_id=?", (v, uid))
    conn.commit()
# =====================================


@dp.message(Command("start"))
async def start(m: Message):
    add_user(m.from_user.id)
    await m.answer(
        "👋 Xush kelibsiz!\n"
        "🎁 5 kredit berildi\n\n"
        "👉 YouTube linkni yuboring"
    )


@dp.message(Command("balance"))
async def balance(m: Message):
    u = get_user(m.from_user.id)
    await m.answer(f"💳 Balans: {u[0]} kredit")


# ====== ANALIZ CORE ======
async def process_video(m: Message, url: str):
    uid = m.from_user.id
    user = get_user(uid)

    if not user or user[0] <= 0:
        await m.answer("❌ Kredit tugagan")
        return

    vid = extract_video_id(url)
    if not vid:
        return

    sid = short_id(vid)
    cur.execute("SELECT top5 FROM videos WHERE sid=?", (sid,))
    row = cur.fetchone()

    if not row:
        top5 = fake_top5(vid)
        cur.execute(
            "INSERT INTO videos VALUES (?,?,?,?)",
            (sid, vid, "|".join(top5), int(time.time()))
        )
        update_credit(uid, -1)
        conn.commit()
    else:
        top5 = row[0].split("|")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("🏆 TOP 5 KONKURENT", callback_data=f"top5:{sid}")]
        ]
    )

    await m.answer(
        f"🎬 Video ID: {vid}\n"
        f"📊 Analiz tayyor",
        reply_markup=kb
    )


@dp.message(Command("analyze"))
async def analyze_cmd(m: Message):
    if len(m.text.split()) > 1:
        await process_video(m, m.text.split(maxsplit=1)[1])


@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze_text(m: Message):
    url = re.search(YOUTUBE_REGEX, m.text).group(1)
    await process_video(m, url)


@dp.callback_query(F.data.startswith("top5:"))
async def top5(c: CallbackQuery):
    sid = c.data.split(":")[1]
    cur.execute("SELECT top5 FROM videos WHERE sid=?", (sid,))
    row = cur.fetchone()

    text = "🏆 TOP 5 KONKURENT:\n\n"
    for i, v in enumerate(row[0].split("|"), 1):
        text += f"{i}. {v}\n"

    await c.message.answer(text)
    await c.answer()


# ===== ADMIN =====
@dp.message(Command("addcredit"))
async def add_credit(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    _, uid, val = m.text.split()
    update_credit(int(uid), int(val))
    await m.answer("✅ Kredit qo‘shildi")


# ============== RUN ==============
async def main():
    print("🤖 FINAL BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
