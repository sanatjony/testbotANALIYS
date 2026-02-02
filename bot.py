import os
import re
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

YOUTUBE_VIDEO_API = "https://www.googleapis.com/youtube/v3/videos"

# ================== HELPERS ==================
def extract_video_id(url: str) -> str | None:
    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


async def fetch_video(video_id: str):
    params = {
        "part": "snippet,statistics",
        "id": video_id,
        "key": YOUTUBE_API_KEY
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.get(YOUTUBE_VIDEO_API, params=params) as r:
            if r.status != 200:
                return None
            data = await r.json()
            if not data.get("items"):
                return None
            return data["items"][0]


# ================== AI LOGIC ==================
def generate_titles(title: str):
    base = title.split("|")[0].strip()
    return [
        f"{base} 😱 INSANE Result!",
        f"{base} | You Won’t Believe This",
        f"{base} 🚨 CRAZY Experiment",
        f"{base} 🔥 Unexpected Outcome",
        f"{base} (SHOCKING)"
    ]


def generate_tags(title: str):
    title = title.lower()
    tags = set()

    if "mcqueen" in title or "cars" in title:
        tags.update([
            "pixar cars", "lightning mcqueen", "disney cars",
            "cars toys", "cars gameplay"
        ])

    if "truck" in title:
        tags.update([
            "truck gameplay", "flatbed truck",
            "truck challenge", "truck experiment"
        ])

    if "beamng" in title:
        tags.update([
            "beamng drive", "beamng crash",
            "beamng gameplay", "beamng mods"
        ])

    tags.update([
        "gaming", "simulation", "experiment",
        "viral gameplay", "satisfying"
    ])

    return list(tags)[:25]


# ================== HANDLERS ==================
@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 <b>TOP NOMLAR</b>\n"
        "🏷 <b>TOP TAGLAR</b>\n"
        "📊 Video statistikasini chiqarib beraman."
    )


@dp.message(F.text.startswith("http"))
async def handle_video(message: Message):
    video_id = extract_video_id(message.text)
    if not video_id:
        await message.answer("❌ Video havolasi noto‘g‘ri.")
        return

    await message.answer("⏳ Video analiz qilinmoqda...")

    video = await fetch_video(video_id)
    if not video:
        await message.answer("❌ Video topilmadi yoki vaqtinchalik cheklov.")
        return

    snippet = video["snippet"]
    stats = video.get("statistics", {})

    title = snippet["title"]
    views = stats.get("viewCount", "0")
    likes = stats.get("likeCount", "0")
    comments = stats.get("commentCount", "0")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 TOP NOMLAR", callback_data=f"title:{video_id}"),
            InlineKeyboardButton(text="🏷 TOP TAGLAR", callback_data=f"tags:{video_id}")
        ]
    ])

    await message.answer(
        f"🎬 <b>{title}</b>\n\n"
        f"👁 View: {views}\n"
        f"👍 Like: {likes}\n"
        f"💬 Comment: {comments}\n\n"
        f"👇 Kerakli funksiyani tanlang:",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("title:"))
async def cb_title(call):
    video_id = call.data.split(":")[1]
    video = await fetch_video(video_id)
    if not video:
        await call.message.answer("❌ Ma’lumot topilmadi.")
        return

    titles = generate_titles(video["snippet"]["title"])
    text = "<b>🧠 TOP CLICKBAIT NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await call.message.answer(text)


@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(call):
    video_id = call.data.split(":")[1]
    video = await fetch_video(video_id)
    if not video:
        await call.message.answer("❌ Ma’lumot topilmadi.")
        return

    tags = generate_tags(video["snippet"]["title"])
    text = "<b>🏷 TOP TAGLAR (copy–paste):</b>\n\n<code>" + ", ".join(tags) + "</code>"
    await call.message.answer(text)


# ================== RUN ==================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
