import os
import re
import asyncio
import requests
from collections import Counter
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.enums import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN")
YT_API_KEY = os.getenv("YT_API_KEY")

bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ===================== UTILS =====================

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


def clean_words(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if len(w) > 3]
    return words


def build_phrases(words, n=3):
    phrases = []
    for i in range(len(words) - n + 1):
        phrases.append(" ".join(words[i:i+n]))
    return phrases


# ===================== YOUTUBE =====================

def get_video_info(video_id):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "key": YT_API_KEY,
        "part": "snippet,statistics",
        "id": video_id
    }
    r = requests.get(url, params=params).json()
    if not r["items"]:
        return None
    return r["items"][0]


def youtube_search(query, max_results=30):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YT_API_KEY,
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results
    }
    return requests.get(url, params=params).json().get("items", [])


# ===================== AI CORE =====================

def generate_semantic_tags(base_title):
    search_results = youtube_search(base_title)

    pool = []
    for item in search_results:
        title = item["snippet"]["title"]
        desc = item["snippet"].get("description", "")
        pool += clean_words(title)
        pool += clean_words(desc)

    phrases = build_phrases(pool, 2) + build_phrases(pool, 3)
    counter = Counter(phrases)

    tags = []
    for phrase, count in counter.most_common(40):
        if base_title.split()[0].lower() in phrase:
            tags.append(phrase)

    return tags[:25]


def generate_ai_titles(original_title, tags):
    base = original_title.split("|")[0].strip()

    hooks = [
        "You Won’t Believe",
        "This Changed Everything",
        "INSANE",
        "Unexpected",
        "Extreme",
        "Most Realistic",
        "People Are Shocked By"
    ]

    titles = []
    for i, hook in enumerate(hooks):
        if i >= 5:
            break
        t = f"{hook} {base} | {tags[0].title()}"
        titles.append(t)

    return titles


# ===================== HANDLERS =====================

@dp.message(F.text.startswith("http"))
async def handle_video(message: Message):
    vid = extract_video_id(message.text)
    if not vid:
        await message.answer("❌ Video link noto‘g‘ri.")
        return

    info = get_video_info(vid)
    if not info:
        await message.answer("❌ Video topilmadi.")
        return

    title = info["snippet"]["title"]
    channel = info["snippet"]["channelTitle"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 AI Title", callback_data=f"title:{vid}"),
            InlineKeyboardButton(text="🏷 AI Tags", callback_data=f"tags:{vid}")
        ]
    ])

    await message.answer(
        f"🎬 <b>Mavjud video nomi:</b>\n{title}\n\n📺 <b>Kanal:</b> {channel}\n\n👇 Kerakli AI funksiyani tanlang",
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("tags:"))
async def ai_tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    info = get_video_info(vid)
    title = info["snippet"]["title"]

    tags = generate_semantic_tags(title)

    text = (
        "🏷 <b>AI tavsiya qilgan TOP TAGLAR</b>\n\n"
        "<code>" + ", ".join(tags) + "</code>\n\n"
        "📈 CTR + Search uchun mos"
    )

    await cb.message.answer(text)
    await cb.answer()


@dp.callback_query(F.data.startswith("title:"))
async def ai_titles(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    info = get_video_info(vid)
    title = info["snippet"]["title"]

    tags = generate_semantic_tags(title)
    titles = generate_ai_titles(title, tags)

    text = "🧠 <b>AI tavsiya qilgan CLICKBAIT TITLAR</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)
    await cb.answer()


# ===================== START =====================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
