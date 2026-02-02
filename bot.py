import os
import re
import asyncio
import requests
from collections import Counter, defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
YT_API_KEY = os.getenv("YT_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

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
    return [" ".join(words[i:i+n]) for i in range(len(words) - n + 1)]


# ================== YOUTUBE ==================

def yt_video(video_id):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "key": YT_API_KEY,
        "part": "snippet,statistics",
        "id": video_id
    }
    r = requests.get(url, params=params).json()
    return r["items"][0] if r.get("items") else None


def yt_search(query, max_results=30):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YT_API_KEY,
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results
    }
    return requests.get(url, params=params).json().get("items", [])


# ================== AI CORE ==================

def ai_semantic_tags(base_title):
    results = yt_search(base_title)
    pool = []

    for v in results:
        pool += clean_text(v["snippet"]["title"])
        pool += clean_text(v["snippet"].get("description", ""))

    phrases = (
        build_phrases(pool, 2) +
        build_phrases(pool, 3)
    )

    counter = Counter(phrases)
    tags = [p for p, c in counter.most_common(40)]

    return tags[:25]


def ai_titles(base_title, tags):
    base = base_title.split("|")[0].strip()

    hooks = [
        "INSANE",
        "You Won’t Believe",
        "This Changed Everything",
        "Unexpected",
        "Extreme Test",
        "People Are Shocked By"
    ]

    titles = []
    for h in hooks:
        titles.append(f"{h} {base} | {tags[0].title()}")
        if len(titles) == 5:
            break

    return titles


def competitor_analysis(base_title):
    results = yt_search(base_title, 40)
    channels = defaultdict(list)

    for r in results:
        ch = r["snippet"]["channelTitle"]
        channels[ch].append(r["snippet"]["title"])

    ranked = sorted(channels.items(), key=lambda x: len(x[1]), reverse=True)

    text = "🧲 <b>Raqobatchi kanallar (TOP)</b>\n\n"
    for i, (ch, vids) in enumerate(ranked[:5], 1):
        text += f"{i}️⃣ <b>{ch}</b>\n📹 Videolar: {len(vids)}\n\n"

    text += "📌 <i>Ko‘p video chiqargan kanallar — real raqobatchilar</i>"
    return text


# ================== HANDLERS ==================

@dp.message(F.text.startswith("http"))
async def handle_video(message: Message):
    vid = extract_video_id(message.text)
    if not vid:
        await message.answer("❌ Video havolasi noto‘g‘ri.")
        return

    info = yt_video(vid)
    if not info:
        await message.answer("❌ Video topilmadi.")
        return

    title = info["snippet"]["title"]
    channel = info["snippet"]["channelTitle"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 AI Title", callback_data=f"title:{vid}"),
            InlineKeyboardButton(text="🏷 AI Tags", callback_data=f"tags:{vid}")
        ],
        [
            InlineKeyboardButton(text="🧲 Raqobat", callback_data=f"comp:{vid}")
        ]
    ])

    await message.answer(
        f"🎬 <b>Mavjud video nomi:</b>\n{title}\n\n"
        f"📺 <b>Kanal:</b> {channel}\n\n"
        f"👇 Kerakli funksiyani tanlang",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    info = yt_video(vid)
    tags = ai_semantic_tags(info["snippet"]["title"])

    text = (
        "🏷 <b>AI tavsiya qilgan TOP TAGLAR</b>\n\n"
        "<code>" + ", ".join(tags) + "</code>\n\n"
        "📈 CTR + Search uchun mos"
    )
    await cb.message.answer(text)
    await cb.answer()


@dp.callback_query(F.data.startswith("title:"))
async def cb_titles(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    info = yt_video(vid)
    tags = ai_semantic_tags(info["snippet"]["title"])
    titles = ai_titles(info["snippet"]["title"], tags)

    text = "🧠 <b>AI tavsiya qilgan CLICKBAIT TITLAR</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)
    await cb.answer()


@dp.callback_query(F.data.startswith("comp:"))
async def cb_comp(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    info = yt_video(vid)
    text = competitor_analysis(info["snippet"]["title"])

    await cb.message.answer(text)
    await cb.answer()


# ================== START ==================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
