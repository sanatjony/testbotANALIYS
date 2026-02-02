import os, re, asyncio, requests
from difflib import SequenceMatcher

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ================= YOUTUBE API =================
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

# ================= TEXT UTILS =================
def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def clean_title(t):
    return re.sub(r"[^\w\s]", "", t).strip()

# ================= SEARCH & TITLE ANALYSIS =================
def search_titles(keyword):
    data = yt("search", {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "maxResults": 30
    })
    return [v["snippet"]["title"] for v in data.get("items", [])]

def ctr_boost(title):
    """
    CTR oshirish uchun kichik optimizatsiya
    """
    if "?" not in title and len(title) < 65:
        return title + "?"
    return title

def generate_top_titles(original_title):
    base = clean_title(original_title)
    search_results = search_titles(base)

    results = []
    for t in search_results:
        t_clean = clean_title(t)

        # juda o‘xshash bo‘lsa tashlab yuboramiz
        if similarity(base, t_clean) > 0.85:
            continue

        # juda uzun bo‘lsa kesamiz
        if len(t_clean) > 75:
            t_clean = t_clean[:72] + "..."

        t_clean = ctr_boost(t_clean)

        # yana bir xil chiqmasligi uchun
        if all(similarity(t_clean, r) < 0.8 for r in results):
            results.append(t_clean)

        if len(results) >= 5:
            break

    return results

# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video havolasini yuboring.\n\n"
        "Men sizga:\n"
        "🧠 TOP NOMLAR (YouTube Search asosida)\n"
        "🏷 TOP TAGLAR\n"
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
                )
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{title}</b>\n\n"
        "👇 TOP NOMLARNI olish uchun tugmani bosing:",
        reply_markup=kb
    )

# ================= CALLBACK =================
@dp.callback_query(F.data.startswith("title:"))
async def cb_title(cb: CallbackQuery):
    vid = cb.data.split(":")[1]
    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]

    original_title = data["snippet"]["title"]
    titles = generate_top_titles(original_title)

    if not titles:
        await cb.message.answer("⚠️ Yetarli o‘xshash nomlar topilmadi.")
        await cb.answer()
        return

    text = "🧠 <b>YouTube Search asosida TOP NOMLAR:</b>\n\n"
    for i, t in enumerate(titles, 1):
        text += f"{i}. {t}\n"

    await cb.message.answer(text)
    await cb.answer()

# ================= RUN =================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
