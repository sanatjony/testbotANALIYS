import os, re, asyncio, requests
from collections import Counter

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
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

# ================== YOUTUBE API ==================
def yt(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=8
    )
    r.raise_for_status()
    return r.json()

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def words(text):
    return re.findall(r"[a-zA-Z]{3,}", text.lower())

# ================== REAL SEARCH ANALYSIS ==================
def search_titles(keyword):
    data = yt("search", {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": 20
    })
    return [v["snippet"]["title"] for v in data.get("items", [])]

def extract_hooks(titles):
    hooks = []
    for t in titles:
        hooks += words(t)
    common = Counter(hooks).most_common(15)
    return [w for w, _ in common]

# ================== SMART TITLE GENERATOR ==================
def generate_titles_from_search(original_title):
    search_results = search_titles(original_title)
    hooks = extract_hooks(search_results)

    base = original_title.split("|")[0].strip()

    templates = [
        "I Tried {base} – {hook} Happened",
        "{base} – Nobody Expected This",
        "This {base} Was a Mistake",
        "{base} – You Won’t Believe What Happened",
        "What Happens When {base} Goes Wrong?"
    ]

    titles = []
    for i, tpl in enumerate(templates):
        hook = hooks[i % len(hooks)] if hooks else "Something Crazy"
        titles.append(tpl.format(base=base, hook=hook.capitalize()))

    return titles

# ================== TAGS ==================
def generate_tags(title, hooks):
    tags = list(dict.fromkeys(words(title) + hooks))
    return ", ".join(tags[:30])

# ================== HANDLERS ==================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video linkini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP NOMLAR (real search asosida)\n"
        "🏷 TOP TAGLAR\n"
        "📊 Raqobatchi kanallar\n"
        "chiqarib beraman."
    )

@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Link noto‘g‘ri.")
        return

    try:
        data = yt("videos", {"part": "snippet,statistics", "id": vid})["items"][0]
    except:
        await msg.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    title = data["snippet"]["title"]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 TOP NOMLAR",
                    callback_data=f"title:{vid}"
                ),
                InlineKeyboardButton(
                    text="🏷 TOP TAGLAR",
                    callback_data=f"tags:{vid}"
                )
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{title}</b>\n\n"
        "👇 Kerakli funksiyani tanlang:",
        reply_markup=kb
    )

# ================== CALLBACKS ==================
@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    title = data["snippet"]["title"]
    titles = generate_titles_from_search(title)

    text = "🧠 <b>ANALIZ ASOSIDA TOP NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)
    await cb.answer()

@dp.callback_query(F.data.startswith("tags:"))
async def cb_tags(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    title = data["snippet"]["title"]
    search = search_titles(title)
    hooks = extract_hooks(search)

    tags = generate_tags(title, hooks)

    await cb.message.answer(
        "🏷 <b>TOP TAGLAR (copy–paste):</b>\n\n"
        f"<code>{tags}</code>"
    )
    await cb.answer()

# ================== RUN ==================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
