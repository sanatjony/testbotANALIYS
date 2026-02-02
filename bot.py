import os
import re
import asyncio
import requests
from datetime import datetime
from collections import Counter

import pytz
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

# ================= FILTERS =================
KIDS_WORDS = {
    "kids", "kid", "children", "toy", "toys", "cartoon", "baby", "nursery"
}

BANNED_WORDS = {
    "free", "download", "hack", "cheat", "crack", "mod apk"
}

TRIGGER_WORDS = [
    "vs", "challenge", "crash test", "experiment", "gameplay",
    "realistic", "physics", "simulation", "insane", "extreme"
]

# ================= HELPERS =================
def get_video_id(url: str):
    m = re.search(r"(v=|youtu\.be/|/live/)([^&?/]+)", url)
    return m.group(2) if m else None

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

def clean_words(words):
    out = []
    for w in words:
        lw = w.lower()
        if lw in KIDS_WORDS or lw in BANNED_WORDS:
            continue
        if len(w) < 4:
            continue
        out.append(w)
    return out

def extract_phrases(title):
    words = re.findall(r"[A-Za-z]{4,}", title)
    words = clean_words(words)
    phrases = []
    for i in range(len(words) - 1):
        phrases.append(f"{words[i]} {words[i+1]}")
    return phrases

# ================= START =================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 *YouTube Analyser TEST*\n\n"
        "📌 YouTube video link yuboring.\n"
        "✍️ AI optimal video nomlarini tavsiya qiladi.",
        parse_mode="Markdown"
    )

# ================= MAIN =================
@dp.message()
async def handle_video(message: types.Message):
    url = (message.text or "").strip()
    vid = get_video_id(url)

    if not vid:
        await message.answer("❌ YouTube link noto‘g‘ri.")
        return

    video = yt_video(vid)
    if not video:
        await message.answer("❌ Video topilmadi.")
        return

    title = video["snippet"]["title"]
    channel = video["snippet"]["channelTitle"]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Title AI",
                    callback_data=f"titleai:{vid}"
                )
            ]
        ]
    )

    await message.answer(
        f"🎬 *Mavjud video nomi:*\n{title}\n\n"
        f"📺 Kanal: {channel}\n\n"
        f"✍️ Yangi, optimal nomlar olish uchun tugmani bosing.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ================= AI TITLE =================
@dp.callback_query(F.data.startswith("titleai:"))
async def title_ai_cb(call: types.CallbackQuery):
    video_id = call.data.split("titleai:", 1)[1]
    video = yt_video(video_id)

    if not video:
        await call.message.answer("❌ Video topilmadi.")
        await call.answer()
        return

    base_title = video["snippet"]["title"]
    search_items = yt_search(base_title, limit=40)

    phrases = []
    for item in search_items:
        phrases.extend(extract_phrases(item["snippet"]["title"]))

    if not phrases:
        await call.message.answer("⚠️ Yetarli ma’lumot topilmadi.")
        await call.answer()
        return

    phrase_counter = Counter(phrases)
    core_phrases = [p for p, _ in phrase_counter.most_common(5)]

    titles = []
    for cp in core_phrases:
        for trig in TRIGGER_WORDS:
            t = f"{cp} {trig.title()} | {base_title.split('|')[0]}"
            if 50 <= len(t) <= 75:
                titles.append(t)
            if len(titles) >= 5:
                break
        if len(titles) >= 5:
            break

    if not titles:
        titles = [f"{cp} Gameplay | {base_title}" for cp in core_phrases[:5]]

    text = "✍️ *AI tavsiya qilgan optimal video nomlari*\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n\n"

    text += (
        "📌 *Izoh:*\n"
        "• SEO + trendga mos\n"
        "• Optimal uzunlik (55–70)\n"
        "• NoKids, qoidaga mos\n"
        "• CTR oshirishga yo‘naltirilgan"
    )

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= RUN =================
async def main():
    print("TEST bot ishga tushdi (AI Title Generator)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
