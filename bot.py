import os
import re
import asyncio
import requests
from datetime import datetime
from io import BytesIO
from collections import Counter

import pytz
import matplotlib.pyplot as plt
from pytrends.request import TrendReq

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not BOT_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("ENV xato")

TZ = pytz.timezone("Asia/Tashkent")

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= CACHE =================
TREND_CACHE = {}
CACHE_TTL = 1800  # 30 min

# ================= FILTERS =================
KIDS_WORDS = {
    "kids", "kid", "children", "child", "toy", "toys", "cartoon",
    "nursery", "baby", "toddler", "learn colors"
}

BANNED_WORDS = {
    "free", "download", "hack", "cheat", "crack", "mod apk"
}

# ================= HELPERS =================
def get_video_id(url: str):
    m = re.search(r"(v=|youtu\.be/|/live/)([^&?/]+)", url)
    return m.group(2) if m else None

def extract_keyword(title: str):
    words = title.split()
    return " ".join(words[:3]) if len(words) >= 3 else title

def clean_words(words):
    result = []
    for w in words:
        lw = w.lower()
        if lw in KIDS_WORDS:
            continue
        if lw in BANNED_WORDS:
            continue
        if len(w) < 4:
            continue
        result.append(w)
    return result

# ================= YOUTUBE API =================
def yt_video(video_id: str):
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,statistics"
        f"&id={video_id}"
        f"&key={YOUTUBE_API_KEY}"
    )
    r = requests.get(url, timeout=10).json()
    return r["items"][0] if r.get("items") else None

def yt_search(keyword: str, limit=30):
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&type=video"
        f"&q={keyword}"
        f"&maxResults={limit}"
        f"&key={YOUTUBE_API_KEY}"
    )
    return requests.get(url, timeout=10).json().get("items", [])

# ================= START =================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 *YouTube Analyser TEST*\n\n"
        "📌 YouTube video link yuboring.\n"
        "🏷 Trendga mos, xavfsiz taglar ham beriladi.",
        parse_mode="Markdown"
    )

# ================= MAIN =================
@dp.message()
async def handle_video(message: types.Message):
    url = (message.text or "").strip()
    video_id = get_video_id(url)

    if not video_id:
        await message.answer("❌ YouTube link noto‘g‘ri.")
        return

    video = yt_video(video_id)
    if not video:
        await message.answer("❌ Video topilmadi.")
        return

    sn = video["snippet"]
    st = video["statistics"]

    title = sn["title"]
    channel = sn["channelTitle"]
    published = datetime.fromisoformat(
        sn["publishedAt"].replace("Z", "+00:00")
    ).astimezone(TZ)

    views = int(st.get("viewCount", 0))
    likes = int(st.get("likeCount", 0))
    comments = int(st.get("commentCount", 0))

    keyword = extract_keyword(title)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏷 Top Tags",
                    callback_data=f"tags:{keyword}"
                )
            ]
        ]
    )

    text = (
        f"🎬 *{title}*\n"
        f"📺 Kanal: {channel}\n\n"
        f"🕒 {published.strftime('%d.%m.%Y %H:%M')} (UTC+5)\n\n"
        f"📊 *Statistika*\n"
        f"👁 View: {views}\n"
        f"👍 Like: {likes}\n"
        f"💬 Comment: {comments}\n\n"
        f"🔑 Mavzu: *{keyword}*"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

# ================= TOP TAGS =================
@dp.callback_query(F.data.startswith("tags:"))
async def tags_cb(call: types.CallbackQuery):
    keyword = call.data.split("tags:", 1)[1]
    items = yt_search(keyword, limit=40)

    words = []

    for i in items:
        title = i["snippet"]["title"]
        found = re.findall(r"[A-Za-z]{4,}", title)
        words.extend(clean_words(found))

    if not words:
        await call.message.answer("⚠️ Mos taglar topilmadi.")
        await call.answer()
        return

    counter = Counter(words)
    top_tags = [w for w, _ in counter.most_common(15)]

    text = "🏷 *Top trend & safe taglar*\n\n"
    text += "```\n"
    text += ", ".join(top_tags)
    text += "\n```\n\n"
    text += (
        "✅ NoKids\n"
        "✅ YouTube qoidalariga mos\n"
        "📈 Trendga yaqin\n\n"
        "📌 *Tavsiya:* video va kanal taglariga qo‘shing."
    )

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= RUN =================
async def main():
    print("TEST bot ishga tushdi (Top Tags)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
