import os
from pyrobale.client import Client

BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("❌ توکن پیدا نشد! متغیر محیطی BALE_BOT_TOKEN رو چک کن.")
print("✅ توکن پیدا شد. در حال اتصال به بله...")

bot = Client(BOT_TOKEN)
print("✅ کلاینت ساخته شد. در حال تست اتصال...")

try:
    # یه تست ساده برای اینکه ببینیم به بله وصل میشه یا نه
    import requests
    r = requests.get(f"https://tapi.bale.ai/bot{BOT_TOKEN}/getMe")
    print("پاسخ بله:", r.json())
except Exception as e:
    print("خطا در اتصال:", e)

print("✅ تست تمام شد. ربات باید آماده باشه.")
