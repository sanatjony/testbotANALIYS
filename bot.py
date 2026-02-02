import os, re, asyncio, requests
from collections import Counter, defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ------------------ UTILS ------------------
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

def clean_words(text):
    return re.findall(r"[a-zA-Z]{3,}", text.lower())

# ------------------ VIDEO TYPE DETECTION ------------------
TYPE_KEYWORDS = {
    "music": ["lyrics", "song", "remix", "audio", "music"],
    "gaming": ["gameplay", "vs", "challenge", "beamng", "gaming"],
    "review": ["review", "unboxing", "test"],
    "education": ["how", "tutorial", "guide"],
    "viral": ["short", "tiktok", "viral"],
    "kids": ["kids", "children", "baby"]
}

def detect_video_type(title, desc, competitor_titles):
    score = defaultdict(int)
    text = " ".join([title, desc] + competitor_titles).lower()

    for t, words in TYPE_KEYWORDS.items():
        for w in words:
            if w in text:
                score[t] += 1

    if not score:
        return "general"

    return max(score, key=score.get)

# ------------------ COMPETITOR ANALYSIS ------------------
def get_competitor_titles(keyword):
    data = yt("search", {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": 20
    })
    return [i["snippet"]["title"] for i in data.get("items", [])]

def extract_patterns(titles):
    words = []
    for t in titles:
        words.extend(clean_words(t))
    return [w for w, _ in Counter(words).most_common(10)]

# ------------------ TITLE GENERATOR ------------------
def generate_titles(original, vtype, patterns):
    base = original.split("|")[0].strip()

    if vtype == "music":
        return [
            f"{base} | English Lyrics",
            f"{base} | TikTok Viral Song",
            f"{base} Lyrics (Trending)",
            f"{base} | Emotional Version",
            f"{base} Lyrics + Meaning"
        ]

    if vtype == "gaming":
        return [
            f"{base} – INSANE Gameplay",
            f"{base} | Unexpected Result",
            f"{base} Challenge (SHOCKING)",
            f"{base} vs Reality",
            f"{base} | Viral Gameplay"
        ]

    if vtype == "review":
        return [
            f"{base} – Honest Review",
            f"{base} | Is It Worth It?",
            f"{base} Review After Testing",
            f"{base} – Full Breakdown",
            f"{base} | Pros & Cons"
        ]

    if vtype == "education":
        return [
            f"How to {base}",
            f"{base} Explained Simply",
            f"{base} – Step by Step Guide",
            f"Learn {base} in Minutes",
            f"{base} Tutorial for Beginners"
        ]

    # GENERAL (dynamic)
    return [
        f"{base} | {patterns[0].title()}",
        f"{base} – {patterns[1].title()} Explained",
        f"{base} | What You Need to Know",
        f"{base} – Full Experience",
        f"{base} | Trending Now"
    ]

# ------------------ TAG GENERATOR ------------------
def generate_tags(original, patterns):
    base = clean_words(original)
    tags = list(dict.fromkeys(base + patterns))
    return ", ".join(tags[:30])

# ------------------ HANDLERS ------------------
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video linkini yuboring.\n"
        "Men <b>har qanday video</b> uchun:\n"
        "🧠 TOP NOMLAR\n"
        "🏷 TOP TAGLAR\n"
        "ni real analiz asosida chiqaraman."
    )

@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Link noto‘g‘ri.")
        return

    try:
        data = yt("videos", {"part": "snippet", "id": vid})["items"][0]
    except Exception:
        await msg.answer("❌ Video topilmadi.")
        return

    title = data["snippet"]["title"]
    desc = data["snippet"].get("description", "")

    competitors = get_competitor_titles(title)
    vtype = detect_video_type(title, desc, competitors)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧠 TOP NOMLAR", callback_data=f"title:{vid}"),
                InlineKeyboardButton(text="🏷 TOP TAGLAR", callback_data=f"tags:{vid}")
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{title}</b>\n"
        f"📂 Aniqlangan tur: <b>{vtype.upper()}</b>\n\n"
        "👇 Funksiyani tanlang:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    title = data["snippet"]["title"]
    desc = data["snippet"].get("description", "")

    competitors = get_competitor_titles(title)
    patterns = extract_patterns(competitors)
    vtype = detect_video_type(title, desc, competitors)

    titles = generate_titles(title, vtype, patterns)

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
    competitors = get_competitor_titles(title)
    patterns = extract_patterns(competitors)

    tags = generate_tags(title, patterns)

    await cb.message.answer(
        "🏷 <b>TOP TAGLAR (copy-paste):</b>\n\n"
        f"<code>{tags}</code>"
    )
    await cb.answer()

# ------------------ RUN ------------------
async def main():
    print("🤖 UNIVERSAL TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
