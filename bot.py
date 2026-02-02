import asyncio
import re
import hashlib
import sqlite3
import time
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.filters import Command

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN topilmadi (Railway Variables ni tekshir)")

BOT_TOKEN = BOT_TOKEN.strip()
# =====================================


# ================= DATABASE ============
DB_NAME = "bot.db"
conn = sqlite3.connect(DB_NAME)
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

def extract_video_id(url: str):
    patterns = [
        r"v=([^&]+)",
        r"youtu\.be/([^?]+)",
        r"shorts/([^?]+)"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def short_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:10]


def fake_top5(video_id: str):
    return [f"{video_id}_competitor_{i}" for i in range(1, 6)]
# =====================================


# ================= BOT =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
# =====================================


# ================= USERS ===============
def get_user(uid: int):
    cur.execute("SELECT credit FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()


def add_user(uid: int):
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, credit) VALUES (?, ?)",
        (uid, 5)
    )
    conn.commit()


def update_credit(uid: int, value: int):
    cur.execute(
        "UPDATE users SET credit = credit + ? WHERE user_id=?",
        (value, uid)
    )
    conn.commit()
# =====================================


@dp.message(Command("start"))
async def start(message: Message):
    add_user(message.from_user.id)
    await message.answer(
        "👋 Xush kelibsiz!\n\n"
        "🎁 Sizga 5 ta bepul kredit berildi\n\n"
        "👉 YouTube linkni shunchaki yuboring.\n"
        "Bot o‘zi analiz qiladi 🚀"
    )


@dp.message(Command("balance"))
async def balance(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        add_user(message.from_user.id)
        user = (5,)
    await message.answer(f"💳 Balansingiz: {user[0]} kredit")


# ============== CORE ANALIZ =============
async def process_video(message: Message, url: str):
    uid = message.from_user.id
    user = get_user(uid)

    if not user:
        add_user(uid)
        user = (5,)

    if user[0] <= 0:
        await message.answer("❌ Kredit tugagan")
        return

    video_id = extract_video_id(url)
    if not video_id:
        await message.answer("❌ YouTube linkni taniy olmadim")
        return

    sid = short_id(video_id)

    cur.execute("SELECT top5 FROM videos WHERE sid=?", (sid,))
    row = cur.fetchone()

    if not row:
        top5 = fake_top5(video_id)
        cur.execute(
            "INSERT INTO videos VALUES (?,?,?,?)",
            (sid, video_id, "|".join(top5), int(time.time()))
        )
        update_credit(uid, -1)
        conn.commit()
    else:
        top5 = row[0].split("|")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 TOP 5 KONKURENT",
                    callback_data=f"top5:{sid}"
                )
            ]
        ]
    )

    await message.answer(
        f"🎬 Video ID: {video_id}\n"
        f"📊 Analiz tayyor",
        reply_markup=keyboard
    )
# =====================================


@dp.message(Command("analyze"))
async def analyze_cmd(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❗ YouTube link yuboring")
        return
    await process_video(message, parts[1])


@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze_from_text(message: Message):
    match = re.search(YOUTUBE_REGEX, message.text)
    if match:
        await process_video(message, match.group(1))


@dp.callback_query(F.data.startswith("top5:"))
async def show_top5(callback: CallbackQuery):
    sid = callback.data.split(":")[1]

    cur.execute("SELECT top5 FROM videos WHERE sid=?", (sid,))
    row = cur.fetchone()

    if not row:
        await callback.answer("❌ Ma’lumot topilmadi", show_alert=True)
        return

    top5 = row[0].split("|")

    text = "🏆 TOP 5 KONKURENT:\n\n"
    for i, v in enumerate(top5, 1):
        text += f"{i}. {v}\n"

    await callback.message.answer(text)
    await callback.answer()


# ============== ADMIN ===================
@dp.message(Command("addcredit"))
async def add_credit(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❗ Format: /addcredit user_id amount")
        return

    uid = int(parts[1])
    amount = int(parts[2])
    update_credit(uid, amount)
    await message.answer("✅ Kredit qo‘shildi")
# =====================================


# ================= RUN ==================
async def main():
    print("🤖 FINAL BOT ISHGA TUSHDI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
