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

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi (Railway Variables ni tekshir)")

BOT_TOKEN = BOT_TOKEN.strip()
# ======================================


# ================= DATABASE ===============
DB_NAME = "bot.db"
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS videos (
    sid TEXT PRIMARY KEY,
    video_id TEXT,
    top5 TEXT,
    created_at INTEGER
)
""")
conn.commit()
# =========================================


# ================= HELPERS ================
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
# =========================================


# ================= BOT ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Xush kelibsiz!\n\n"
        "📊 YouTube analiz bot\n\n"
        "👉 Shunchaki YouTube linkni yuboring.\n"
        "Bot o‘zi analiz qiladi 🚀"
    )


# ---------- ANALIZ FUNKSIYA (UMUMIY) ----------
async def process_video(message: Message, url: str):
    video_id = extract_video_id(url)
    if not video_id:
        await message.answer("❌ YouTube linkni taniy olmadim")
        return

    sid = short_id(video_id)

    cursor.execute("SELECT top5 FROM videos WHERE sid=?", (sid,))
    row = cursor.fetchone()

    if not row:
        top5 = fake_top5(video_id)
        cursor.execute(
            "INSERT INTO videos VALUES (?,?,?,?)",
            (sid, video_id, "|".join(top5), int(time.time()))
        )
        conn.commit()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🏆 TOP 5 KONKURENT",
                callback_data=f"top5:{sid}"
            )
        ]]
    )

    await message.answer(
        f"🎬 Video ID: {video_id}\n"
        f"📊 Analiz tayyor\n\n"
        f"👇 Natijani ko‘rish:",
        reply_markup=keyboard
    )


# ---------- /analyze QOLADI ----------
@dp.message(Command("analyze"))
async def analyze_cmd(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❗ YouTube link yuboring")
        return
    await process_video(message, args[1])


# ---------- ODDIY LINK YUBORILGANDA ----------
@dp.message(F.text.regexp(YOUTUBE_REGEX))
async def analyze_from_text(message: Message):
    match = re.search(YOUTUBE_REGEX, message.text)
    if match:
        await process_video(message, match.group(1))


# ---------- CALLBACK ----------
@dp.callback_query(F.data.startswith("top5:"))
async def show_top5(callback: CallbackQuery):
    sid = callback.data.split(":")[1]

    cursor.execute("SELECT top5 FROM videos WHERE sid=?", (sid,))
    row = cursor.fetchone()

    if not row:
        await callback.answer("❌ Ma’lumot topilmadi", show_alert=True)
        return

    top5 = row[0].split("|")

    text = "🏆 TOP 5 KONKURENT:\n\n"
    for i, v in enumerate(top5, 1):
        text += f"{i}. {v}\n"

    await callback.message.answer(text)
    await callback.answer()


# ================= RUN ====================
async def main():
    print("🤖 Bot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
