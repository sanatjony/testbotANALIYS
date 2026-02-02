import os
import re
import asyncio
import requests
from collections import Counter, defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pytrends.request import TrendReq

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, FSInputFile
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
YT_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

pytrends = TrendReq(hl="en-US", tz=360)

# ================== UTILS ==================

def extract_video_id(url: str):
    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"/shorts/([a-zA-Z0-9_-]{11})"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def clean_text(text: str):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return [w for w in text.split() if len(w) > 3]


def build_phrases(words, n):
    return [
        " ".join(words[i:i+n])
        for i in range(len(words) - n + 1)
    ]

# ================== YOUTUBE API ==================

def yt_video(video_id: str):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "key": YT_API_KEY,
        "part": "snippet,statistics",
        "id": video_id
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
    except Exception:
        return None

    if not data.get("items"):
        return None

    return data["items"][0]


def yt_search(query: str, max_results=30):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YT_API_KEY,
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json().get("items", [])
    except Exception:
        return []

# ================== AI CORE ==================

def ai_semantic_tags(base_title: str):
    results = yt_search(base_title, 40)
    pool = []

    for v in results:
        pool += clean_text(v["snippet"]["title"])
        pool += clean_text(v["snippet"].get("description", ""))

    phrases = build_phrases(pool, 2) + build_phrases(pool, 3)
    counter = Counter(phrases)

    return [p for p, _ in counter.most_common(25)]


def ai_titles(base_title: str, tags: list[str]):
    base = base_title.split("|")[0].strip()
    hooks = [
        "INSANE",
        "You Won’t Believe",
        "Unexpected",
        "Extreme Test",
        "People Are Shocked By"
    ]

    titles = []
    for h in hooks:
        titles.append(f"{h} {base} | {tags[0].title()}")
    return titles


def competitor_analysis(base_title: str):
    results = yt_search(base_title, 40)
    channels = defaultdict(int)

    for r in results:
        channels[r["snippet"]["channelTitle"]] += 1

    ranked = sorted(channels.items(), key=lambda x: x[1], reverse=True)

    text = "🧲 <b>Raqobatchi kanallar (TOP)</b>\n\n"
    for i, (ch, count) in enumerate(ranked[:5], 1):
        text += f"{i}️⃣ <b>{ch}</b>\n📹 O‘xshash video: {count}\n\n"

    return text

# ================== GLOBAL TREND ==================

def build_trend(keyword: str):
    pytrends.build_payload([keyword], timeframe="today 3-m")
    df = pytrends.interest_over_time()

    if df.empty:
        return None, None

    values = df[keyword]
    trend_status = "🟢 O‘sish" if values.iloc[-1] > values.mean() else "🟡 Barqaror"

    # grafik
    plt.figure(figsize=(7, 3))
    plt.plot(df.index, values)
    plt.title(f"Global trend: {keyword}")
    plt.tight_layout()

    filename = f"/tmp/trend_{int(datetime.now().timestamp())}.png"
    plt.savefig(filename)
    plt.close()

    return filename, trend_status

# ================== HANDLERS ==================

@dp.message(F.text == "/start")
async def start_cmd(message: Message):
    await message.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "• 🧠 TOP NOMLAR\n"
        "• 🏷 TOP TAGLAR\n"
        "• 🧲 Raqobatchi analiz\n"
        "• 📈 Global trend\n\n"
        "chiqarib beraman."
    )


@dp.message(F.text.startswith("http"))
async def handle_video(message: Message):
    vid = extract_video_id(message.text)
    if not vid:
        await message.answer("❌ YouTube link noto‘g‘ri.")
        return

    info = yt_video(vid)
    if not info:
        await message.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    title = info["snippet"]["title"]
    channel = info["snippet"]["channelTitle"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 TOP NOMLAR", callback_data=f"title:{vid}"),
            InlineKeyboardButton(text="🏷 TOP TAGLAR", callback_data=f"tags:{vid}")
        ],
        [
            InlineKeyboardButton(text="🧲 Raqobatchi analiz", callback_data=f"comp:{vid}"),
            InlineKeyboardButton(text="📈 Global trend", callback_data=f"trend:{vid}")
        ]
    ])

    await message.answer(
        f"🎬 <b>Mavjud video nomi:</b>\n{title}\n\n"
        f"📺 <b>Kanal:</b> {channel}\n\n"
        "👇 Funksiyani tanlang:",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("trend:"))
async def cb_trend(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    info = yt_video(vid)

    if not info:
        await cb.message.answer("❌ Trendni olishda xatolik.")
        await cb.answer()
        return

    keyword = info["snippet"]["title"].split("|")[0].strip()
    await cb.message.answer("📈 Global trend olinmoqda, biroz kuting...")

    try:
        img, status = build_trend(keyword)
    except Exception:
        await cb.message.answer("❌ Trend ma’lumot topilmadi.")
        await cb.answer()
        return

    if not img:
        await cb.message.answer("❌ Trend ma’lumot topilmadi.")
        await cb.answer()
        return

    await cb.message.answer_photo(
        photo=FSInputFile(img),
        caption=(
            f"📈 <b>Global trend</b>\n\n"
            f"🔑 Keyword: <b>{keyword}</b>\n"
            f"🕒 Oxirgi 3 oy\n"
            f"📊 Natija: {status}"
        )
    )
    await cb.answer()


# ================== START ==================

async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
