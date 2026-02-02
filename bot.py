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

def extract_video_id(url: str) -> str | None:
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

    if "items" not in data or not data["items"]:
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

    tags = [p for p, _ in counter.most_common(30)]
    return tags[:25]


def ai_titles(base_title: str, tags: list[str]):
    base = base_title.split("|")[0].strip()

    hooks = [
        "INSANE",
        "You Won’t Believe",
        "Unexpected",
        "Extreme Test",
        "People Are Shocked By",
        "This Changed Everything"
    ]

    titles = []
    for h in hooks:
        titles.append(f"{h} {base} | {tags[0].title()}")
        if len(titles) == 5:
            break

    return titles


def competitor_analysis(base_title: str):
    results = yt_search(base_title, 40)
    channels = defaultdict(int)

    for r in results:
        channels[r["snippet"]["channelTitle"]] += 1

    ranked = sorted(channels.items(), key=lambda x: x[1], reverse=True)

    text = "🧲 <b>Raqobatchi kanallar (TOP)</b>\n\n"
    for i, (ch, count) in enumerate(ranked[:5], 1):
        text += f"{i}️⃣ <b>{ch}</b>\n📹 O‘xshash videolar: {count}\n\n"

    text += "📌 <i>Ko‘p chiqayotgan kanallar — real raqobatchilar</i>"
    return text


# ================== HANDLERS ==================

@dp.message(F.text == "/start")
async def start_cmd(message: Message):
    await message.answer(
        "👋 <b>Salom!</b>\n\n"
        "🔗 YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "• 🧠 AI Title\n"
        "• 🏷 AI Tags\n"
        "• 🧲 Raqobatchi analiz\n\n"
        "chiqarib beraman."
    )


@dp.message(F.text.startswith("http"))
async def handle_video(message: Message):
    vid = extract_video_id(message.text)

    if not vid:
        await message.answer("❌ YouTube video ID topilmadi.")
        return

    info = yt_video(vid)
    if not info:
        await message.answer("❌ Video topilmadi yoki API cheklangan.")
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
        "👇 Kerakli funksiyani tanlang",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    info = yt_video(vid)

    if not info:
        await cb.message.answer("❌ Taglar olishda xatolik.")
        await cb.answer()
        return

    tags = ai_semantic_tags(info["snippet"]["title"])

    await cb.message.answer(
        "🏷 <b>AI tavsiya qilgan TOP TAGLAR</b>\n\n"
        "<code>" + ", ".join(tags) + "</code>\n\n"
        "📈 CTR + Search uchun mos"
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("title:"))
async def cb_titles(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    info = yt_video(vid)

    if not info:
        await cb.message.answer("❌ Title generatsiyada xatolik.")
        await cb.answer()
        return

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

    if not info:
        await cb.message.answer("❌ Raqobatchi analizida xatolik.")
        await cb.answer()
        return

    await cb.message.answer(
        competitor_analysis(info["snippet"]["title"])
    )
    await cb.answer()


# ================== START ==================

async def main():
    print("🤖 Test bot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
