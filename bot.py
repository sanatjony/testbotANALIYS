import asyncio
import re
import hashlib
import sqlite3
import time

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.filters import Command

# ================= CONFIG =================
BOT_TOKEN = "YOUR_BOT_TOKEN"
DB_NAME = "bot.db"
# =========================================


# ================= DATABASE ===============
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
    """callback_data uchun xavfsiz ID (10 belgi)"""
    return hashlib.md5(text.encode()).hexdigest()[:10]


def fake_top5(video_id: str):
    """Fake TOP 5 konkurentlar"""
    return [
        f"{video_id}_competitor_1",
        f"{video_id}_competitor_2",
        f"{video_id}_competitor_3",
        f"{video_id}_competitor_4",
        f"{video_id}_competitor_5",
    ]
# =========================================


# ================= BOT ====================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Xush kelibsiz!\n\n"
        "📊 YouTube video analiz:\n"
        "/analyze <youtube_url>"
    )


@dp.message(Command("analyze"))
async def analyze(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❗ YouTube link yuboring")
        return

    video_id = extract_video_id(args[1])
    if not video_id:
        await message.answer("❌ Noto‘g‘ri YouTube link")
        return

    sid = short_id(video_id)

    # Cache tekshirish
    cursor.execute("SELECT top5 FROM videos WHERE sid=?", (sid,))
    row = cursor.fetchone()

    if not row:
        top5 = fake_top5(video_id)
        cursor.execute(
            "INSERT INTO videos VALUES (?,?,?,?)",
            (sid, video_id, "|".join(top5), int(time.time()))
        )
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
        f"📊 Analiz tayyor\n\n"
        f"👇 TOP 5 ni ko‘rish:",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("top5:"))
async def show_top5(callback: CallbackQuery):
    sid = callback.data.split(":")[1]

    cursor.execute("SELECT top5 FROM videos WHERE sid=?", (sid,))
    row = cursor.fetchone()

    if not row:
        await callback.answer("❌ Ma’lumot topilmadi", show_alert=True)
        return

    top5 = row[0].split("|")

    text = "🏆 TOP 5 KONKURENT VIDEO:\n\n"
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
