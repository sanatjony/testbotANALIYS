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

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= CONSTANTS =================
BANNED = {"hack", "crack", "cheat", "free download", "mod apk"}

TRIGGERS = [
    "vs", "challenge", "experiment", "gameplay",
    "insane", "crazy", "unexpected", "extreme",
    "realistic physics"
]

# ================= HELPERS =================
def get_video_id(url: str):
    m = re.search(r"(v=|youtu\.be/|/live/)([^&?/]+)", url)
    return m.group(2) if m else None

def yt_video(video_id: str):
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,statistics&id={video_id}&key={YOUTUBE_API_KEY}"
    )
    r = requests.get(url, timeout=10).json()
    return r["items"][0] if r.get("items") else None

def yt_search(query: str, limit=40):
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&type=video&q={query}"
        f"&maxResults={limit}&key={YOUTUBE_API_KEY}"
    )
    return requests.get(url, timeout=10).json().get("items", [])

def extract_phrases(title: str):
    words = re.findall(r"[A-Za-z0-9]{3,}", title)
    phrases = []
    for size in (2, 3, 4):
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i+size])
            if not any(b in phrase.lower() for b in BANNED):
                phrases.append(phrase)
    return phrases

# ================= START =================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "🧪 *YouTube Analyser — TEST*\n\n"
        "📌 YouTube video link yuboring\n"
        "✍️ AI Title + 🏷 AI Tag generator",
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

    sn = video["snippet"]
    st = video["statistics"]

    title = sn["title"]
    channel = sn["channelTitle"]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ AI Title",
                    callback_data=f"titleai:{vid}"
                ),
                InlineKeyboardButton(
                    text="🏷 AI Tags",
                    callback_data=f"tagai:{vid}"
                )
            ]
        ]
    )

    await message.answer(
        f"🎬 *Mavjud video nomi:*\n{title}\n\n"
        f"📺 Kanal: {channel}\n\n"
        "👇 Kerakli AI funksiyani tanlang",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ================= AI TITLE =================
@dp.callback_query(F.data.startswith("titleai:"))
async def title_ai_cb(call: types.CallbackQuery):
    vid = call.data.split("titleai:", 1)[1]
    video = yt_video(vid)

    base_title = video["snippet"]["title"]
    items = yt_search(base_title)

    phrases = []
    for i in items:
        phrases.extend(extract_phrases(i["snippet"]["title"]))

    if not phrases:
        phrases = extract_phrases(base_title)

    core = [p for p, _ in Counter(phrases).most_common(6)]

    titles = []
    for c in core:
        for t in TRIGGERS:
            new = f"{c} {t} | {base_title.split('|')[0]}"
            if 45 <= len(new) <= 90:
                titles.append(new)
            if len(titles) >= 5:
                break
        if len(titles) >= 5:
            break

    text = "✍️ *AI tavsiya qilgan clickbait titlelar*\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n\n"

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= AI TAGS =================
@dp.callback_query(F.data.startswith("tagai:"))
async def tag_ai_cb(call: types.CallbackQuery):
    vid = call.data.split("tagai:", 1)[1]
    video = yt_video(vid)

    base_title = video["snippet"]["title"]
    items = yt_search(base_title)

    tags = []
    for i in items:
        tags.extend(extract_phrases(i["snippet"]["title"]))

    tags = [t for t, _ in Counter(tags).most_common(20)]

    text = (
        "🏷 *AI tavsiya qilgan top taglar*\n\n"
        "```\n" + ", ".join(tags) + "\n```\n\n"
        "📈 CTR + Search uchun mos"
    )

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# ================= RUN =================
async def main():
    print("TEST bot ishga tushdi (CTR MODE)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
