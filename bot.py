import os
import json
import asyncio
import threading
import urllib.request
from datetime import datetime, timedelta
from collections import defaultdict

from flask import Flask
from baleRobot import AsyncBaleClient, Update, run_polling, InlineKeyboardMarkup
import aqipy

# ─── ۱. دانلود خودکار دیتای شهرها (در صورت نبود فایل) ───
CITIES_FILE = "cities.json"

def setup_cities():
    if os.path.exists(CITIES_FILE):
        return
    print("⬇️ در حال دانلود دیتای استان‌ها و شهرها...")
    try:
        p_url = "https://raw.githubusercontent.com/sajaddp/list-of-cities-in-Iran/main/dist/json/provinces.json"
        c_url = "https://raw.githubusercontent.com/sajaddp/list-of-cities-in-Iran/main/dist/json/cities.json"
        
        with urllib.request.urlopen(p_url) as r:
            provinces = json.loads(r.read().decode())
        with urllib.request.urlopen(c_url) as r:
            cities = json.loads(r.read().decode())

        prov_map = {p["id"]: p["name"] for p in provinces}
        result = {name: [] for name in prov_map.values()}
        
        for city in cities:
            pid = city.get("province_id")
            if pid in prov_map:
                cname = city.get("name", "").strip()
                if cname and cname not in result[prov_map[pid]]:
                    result[prov_map[pid]].append(cname)

        for p in result:
            result[p].sort()

        with open(CITIES_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("✅ فایل cities.json با موفقیت ساخته شد.")
    except Exception as e:
        print(f"❌ خطا در دانلود شهرها: {e}")
        # لیست پشتیبان در صورت قطعی اینترنت سرور
        fallback = {"تهران": ["تهران", "شهریار", "اسلامشهر", "ورامین"], "اصفهان": ["اصفهان", "کاشان", "خمینی‌شهر"], "خراسان رضوی": ["مشهد", "نیشابور", "سبزوار"]}
        with open(CITIES_FILE, "w", encoding="utf-8") as f:
            json.dump(fallback, f, ensure_ascii=False)

setup_cities()

with open(CITIES_FILE, "r", encoding="utf-8") as f:
    PROVINCES = json.load(f)

# ─── ۲. وب‌سرور Flask برای بیدار نگه داشتن Render ───
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ─── ۳. تنظیمات ربات بله ───
BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("❌ متغیر محیطی BALE_BOT_TOKEN تنظیم نشده است.")

history = defaultdict(list)
client = AsyncBaleClient(BOT_TOKEN)

def aqi_level(aqi: int) -> tuple[str, str]:
    if aqi <= 50:    return "🟢 پاک", "هوا سالم است."
    if aqi <= 100:   return "🟡 قابل قبول", "برای اکثر افراد بی‌خطر است."
    if aqi <= 150:   return "🟠 ناسالم برای گروه‌های حساس", "کودکان، سالمندان و بیماران مراقب باشند."
    if aqi <= 200:   return "🔴 ناسالم", "همه افراد فعالیت طولانی در فضای باز را کاهش دهند."
    if aqi <= 300:   return "🟣 بسیار ناسالم", "از فعالیت در فضای باز خودداری کنید."
    return "⚫ خطرناک", "در خانه بمانید."

def fetch_aqi(city: str) -> dict | None:
    try:
        c = aqipy.AQIClient()
        data = c.fetch_city_aqi_data(city)
        if isinstance(data, list): data = data[0] if data else None
        return data
    except Exception as e:
        print(f"[AQI ERROR] {city}: {e}")
        return None

def record_and_average(city: str, today_aqi: int) -> float | None:
    today = datetime.now().date().isoformat()
    if not any(d == today for d, _ in history[city]):
        history[city].append((today, today_aqi))
    cutoff = (datetime.now().date() - timedelta(days=7)).isoformat()
    history[city] = [(d, a) for d, a in history[city] if d >= cutoff]
    if len(history[city]) >= 2:
        return sum(a for _, a in history[city]) / len(history[city])
    return None

def provinces_keyboard() -> InlineKeyboardMarkup:
    buttons, row = [], []
    for prov in PROVINCES.keys():
        row.append((prov, f"prov:{prov}"))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup.quick(buttons)

def cities_keyboard(province: str) -> InlineKeyboardMarkup:
    buttons, row = [], []
    for city in PROVINCES.get(province, []):
        row.append((city, f"city:{city}"))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([("🔙 بازگشت به استان‌ها", "back")])
    return InlineKeyboardMarkup.quick(buttons)

async def handle(update: Update) -> None:
    msg = update.effective_message
    cb = update.callback_query
    
    if msg and msg.text:
        if msg.text == "/start":
            await client.send_message(msg.chat_id, "🌍 **بات کیفیت هوا**\n\nاستان مورد نظر را انتخاب کنید:", reply_markup=provinces_keyboard())
        else:
            await client.send_message(msg.chat_id, "برای شروع /start را بزنید.")
        return
        
    if cb:
        data = cb.data
        if data == "back":
            await client.edit_message_text(cb.message.chat_id, cb.message.message_id, "استان مورد نظر را انتخاب کنید:", reply_markup=provinces_keyboard())
        elif data.startswith("prov:"):
            prov = data.split(":", 1)[1]
            await client.edit_message_text(cb.message.chat_id, cb.message.message_id, f"📍 استان **{prov}**\nشهر مورد نظر را انتخاب کنید:", reply_markup=cities_keyboard(prov))
        elif data.startswith("city:"):
            city = data.split(":", 1)[1]
            await client.answer_callback_query(cb.id, text=f"در حال دریافت {city}...")
            await client.edit_message_text(cb.message.chat_id, cb.message.message_id, f"⏳ در حال دریافت اطلاعات {city}...")
            
            today = fetch_aqi(city)
            if not today:
                await client.edit_message_text(cb.message.chat_id, cb.message.message_id, f"❌ داده‌ای برای **{city}** یافت نشد.")
                return
                
            today_aqi = int(today.get("aqi") or today.get("AQI") or 0)
            if today_aqi == 0:
                await client.edit_message_text(cb.message.chat_id, cb.message.message_id, f"❌ داده معتبری برای **{city}** دریافت نشد.")
                return
                
            level, advice = aqi_level(today_aqi)
            avg7 = record_and_average(city, today_aqi)
            
            text = f"📊 **کیفیت هوای {city}**\n🗓 {datetime.now().strftime('%Y/%m/%d')}\n\n**امروز:** {today_aqi} — {level}\n💡 {advice}\n"
            if avg7: 
                text += f"\n📈 **میانگین ۷ روز اخیر:** {avg7:.0f}\n"
                
            kb = InlineKeyboardMarkup.quick([[("🔙 منوی اصلی", "back")]])
            await client.edit_message_text(cb.message.chat_id, cb.message.message_id, text, reply_markup=kb)
            
        await client.answer_callback_query(cb.id)

if __name__ == "__main__":
    # روشن کردن وب‌سرور در پس‌زمینه
    threading.Thread(target=run_flask, daemon=True).start()
    print("✅ وب‌سرور فعال شد. ربات در حال اتصال به بله...")
    # اجرای ربات
    asyncio.run(run_polling(client, handle, skip_pending=True))
