import os, re, asyncio, requests
from datetime import datetime, timedelta
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

# ================= YOUTUBE =================
def yt(endpoint, params):
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=20
    )
    r.raise_for_status()
    return r.json()

def extract_video_id(url):
    for p in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

# ================= HELPERS =================
def clean(text):
    return re.sub(r"[^\w\s]", "", text).strip()

def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def is_within_days(date_str, days):
    d = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
    return d >= datetime.utcnow() - timedelta(days=days)

# ================= CORE =================
def competitor_top_titles(base_title):
    base_clean = clean(base_title)
    words = base_clean.split()

    queries = list(dict.fromkeys([
        base_clean,
        " ".join(words[:5]),
        " ".join(words[:4]),
        " ".join(words[:3]),
        words[0] + " mcqueen",
        words[0] + " beamng",
        words[0] + " truck",
        "mcqueen beamng",
        "flatbed truck mcqueen",
        "pothole vs car beamng"
    ]))

    results = []

    for days_limit in [60, 90]:
        for q in queries:
            search = yt("search", {
                "part": "snippet",
                "q": q,
                "type": "video",
                "order": "viewCount",
                "maxResults": 50
            })

            for item in search.get("items", []):
                vid = item["id"]["videoId"]
                snip = item["snippet"]

                if not is_within_days(snip["publishedAt"], days_limit):
                    continue

                v = yt("videos", {
                    "part": "statistics,snippet",
                    "id": vid
                })["items"]

                if not v:
                    continue

                stats = v[0].get("statistics", {})
                views = int(stats.get("viewCount", 0))

                if views < 50:
                    continue

                title = clean(v[0]["snippet"]["title"])

                if any(similarity(title, r["title"]) > 0.70 for r in results):
                    continue

                results.append({
                    "title": v[0]["snippet"]["title"],
                    "views": views
                })

                if len(results) >= 10:
                    return sorted(results, key=lambda x: x["views"], reverse=True)

    return sorted(results, key=lambda x: x["views"], reverse=True)

# ================= HANDLERS =================
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer(
        "👋 <b>Salom!</b>\n\n"
        "YouTube video linkini yuboring.\n\n"
        "🧠 Konkurentlar asosida:\n"
        "• OXIRGI 60–90 KUN\n"
        "• TOP 10 NOM\n"
        "• 👁 Ko‘rishlar bilan\n"
        "• CTR’ga mos"
    )

@dp.message(F.text.startswith("http"))
async def handle_video(msg: Message):
    vid = extract_video_id(msg.text)
    if not vid:
        await msg.answer("❌ Link noto‘g‘ri.")
        return

    try:
        data = yt("videos", {"part": "snippet", "id": vid})["items"][0]
    except:
        await msg.answer("❌ Video topilmadi yoki API cheklangan.")
        return

    title = data["snippet"]["title"]

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 TOP NOMLAR (Konkurent)",
                    callback_data=f"top:{vid}"
                )
            ]
        ]
    )

    await msg.answer(
        f"🎬 <b>{title}</b>\n\n"
        "👇 Konkurentlar asosida TOP nomlarni olish:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("top:"))
async def cb_top(cb: CallbackQuery):
    vid = cb.data.split(":")[1]

    loading = await cb.message.answer("⏳ Analiz olinmoqda, biroz kuting...")

    data = yt("videos", {"part": "snippet", "id": vid})["items"][0]
    base_title = data["snippet"]["title"]

    tops = competitor_top_titles(base_title)

    await loading.delete()

    if len(tops) < 3:
        await cb.message.answer("⚠️ Konkurentlardan yetarli ma’lumot topilmadi.")
        await cb.answer()
        return

    text = "🧠 <b>OXIRGI 60–90 KUN — KONKURENTLAR TOP NOMLARI:</b>\n\n"
    for i, t in enumerate(tops, 1):
        text += f"{i}. {t['title']}\n   👁 {t['views']:,}\n\n"

    await cb.message.answer(text)
    await cb.answer()

# ================= RUN =================
async def main():
    print("🤖 TEST BOT ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
