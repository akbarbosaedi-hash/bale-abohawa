import os
import json
import threading
import urllib.request
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Flask
import aqipy

pyrobale
from pyrobale import Client
from pyrobale.objects import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

CITIES_FILE = "cities.json"
if not os.path.exists(CITIES_FILE):
    try:
        p_url = "https://raw.githubusercontent.com/sajaddp/list-of-cities-in-Iran/main/dist/json/provinces.json"
        c_url = "https://raw.githubusercontent.com/sajaddp/list-of-cities-in-Iran/main/dist/json/cities.json"
        with urllib.request.urlopen(p_url) as r: provinces = json.loads(r.read().decode())
        with urllib.request.urlopen(c_url) as r: cities = json.loads(r.read().decode())
        prov_map = {p["id"]: p["name"] for p in provinces}
        result = {name: [] for name in prov_map.values()}
        for city in cities:
            pid = city.get("province_id")
            if pid in prov_map:
                cname = city.get("name", "").strip()
                if cname and cname not in result[prov_map[pid]]:
                    result[prov_map[pid]].append(cname)
        for p in result: result[p].sort()
        with open(CITIES_FILE, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        with open(CITIES_FILE, "w", encoding="utf-8") as f:
            json.dump({"تهران": ["تهران", "شهریار"], "اصفهان": ["اصفهان", "کاشان"]}, f, ensure_ascii=False)

with open(CITIES_FILE, "r", encoding="utf-8") as f:
    PROVINCES = json.load(f)

history = defaultdict(list)

def aqi_level(aqi: int):
    if aqi <= 50: return "🟢 پاک", "هوا سالم است."
    if aqi <= 100: return "🟡 قابل قبول", "برای اکثر افراد بی‌خطر است."
    if aqi <= 150: return "🟠 ناسالم برای گروه‌های حساس", "کودکان، سالمندان و بیماران مراقب باشند."
    if aqi <= 200: return "🔴 ناسالم", "همه افراد فعالیت طولانی در فضای باز را کاهش دهند."
    if aqi <= 300: return "🟣 بسیار ناسالم", "از فعالیت در فضای باز خودداری کنید."
    return "⚫ خطرناک", "در خانه بمانید."

def fetch_aqi(city: str):
    try:
        c = aqipy.AQIClient()
        data = c.fetch_city_aqi_data(city)
        if isinstance(data, list): data = data[0] if data else None
        return data
    except Exception: return None

def provinces_keyboard():
    buttons = []
    keys = list(PROVINCES.keys())
    for i in range(0, len(keys), 2):
        row = [InlineKeyboardButton(text=keys[i], callback_data=f"prov:{keys[i]}")]
        if i + 1 < len(keys):
            row.append(InlineKeyboardButton(text=keys[i+1], callback_data=f"prov:{keys[i+1]}"))
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cities_keyboard(province: str):
    buttons = []
    cities = PROVINCES.get(province, [])
    for i in range(0, len(cities), 2):
        row = [InlineKeyboardButton(text=cities[i], callback_data=f"city:{cities[i]}")]
        if i + 1 < len(cities):
            row.append(InlineKeyboardButton(text=cities[i+1], callback_data=f"city:{cities[i+1]}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
bot = Client(BOT_TOKEN)

@bot.on_message()
async def handle_message(bot: Client, message: Message):
    if message.text == "/start":
        await bot.send_message(message.chat.id, "🌍 **بات کیفیت هوا**\n\nاستان را انتخاب کنید:", reply_markup=provinces_keyboard())

@bot.on_callback_query()
async def handle_callback(bot: Client, query: CallbackQuery):
    await bot.answer_callback_query(query.id)
    data = query.data
    chat_id = query.message.chat.id
    msg_id = query.message.message_id

    if data == "back":
        await bot.edit_message_text(chat_id, msg_id, "استان را انتخاب کنید:", reply_markup=provinces_keyboard())
    elif data.startswith("prov:"):
        prov = data.split(":", 1)[1]
        await bot.edit_message_text(chat_id, msg_id, f"📍 استان **{prov}**\nشهر را انتخاب کنید:", reply_markup=cities_keyboard(prov))
    elif data.startswith("city:"):
        city = data.split(":", 1)[1]
        await bot.edit_message_text(chat_id, msg_id, f"⏳ در حال دریافت {city}...")
        
        today = fetch_aqi(city)
        if not today or (today.get("aqi") or today.get("AQI")) is None:
            await bot.edit_message_text(chat_id, msg_id, f"❌ داده‌ای برای **{city}** یافت نشد.")
            return
            
        today_aqi = int(today.get("aqi") or today.get("AQI") or 0)
        level, advice = aqi_level(today_aqi)
        
        text = f"📊 **کیفیت هوای {city}**\n🗓 {datetime.now().strftime('%Y/%m/%d')}\n\n**امروز:** {today_aqi} — {level}\n💡 {advice}\n"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="back")]])
        await bot.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("🚀 Starting bot...")
    bot.run()
