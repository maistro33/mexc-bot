import os, time, telebot, ccxt, threading, re
from google import genai

# --- [BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [AUTONOMOUS SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Tüm borsayı tarayan otonom bir scalp yöneticisisin.
Görevin: Fırsatı bulmak, risk analizini yapmak ve MİKTAR ile KALDIRACI belirlemek.

KARAR FORMATI (KESİN):
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@

Kurallar:
1. LEVERAGE: 1 ile 50 arasında bir değer seç. (Riskli coinde düşük, emin olduğunda yüksek).
2. USDT_AMOUNT: Toplam USDT bakiyesinin %20'sinden fazlasını tek işleme sokma.
3. Analizini çok kısa yap ve tetiği çek.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *GEMINI OTONOM:* \n{msg}", parse_mode="Markdown")
    except: pass

def execute_autonomous_trade(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            # Regex ile formatı güvenli oku
            pattern = r"@@\[ACTION: TRADE, (.*?), (.*?), (.*?), (.*?)\]@@"
            match = re.search(pattern, decision)
            if not match: return "❌ Format hatası, işlem yapılamadı."
            
            sym = match.group(1).strip().replace("/", "") + ":USDT"
            side = 'buy' if 'buy' in match.group(2).lower() or 'long' in match.group(2).lower() else 'sell'
            lev = int(float(match.group(3).strip()))
            amt = float(match.group(4).strip())
            
            # 1. Kaldıraç Ayarla
            try: exch.set_leverage(lev, sym)
            except: pass
            
            # 2. Miktar Hesapla
            ticker = exch.fetch_ticker(sym)
            price = ticker['last']
            qty = (amt * lev) / price
            qty = float(exch.amount_to_precision(sym, qty))
            
            # 3. Emri Gönder
            if qty > 0:
                order = exch.create_order(sym, 'market', side, qty)
                return f"✅ *İŞLEM AÇILDI*\nSembol: {sym}\nYön: {side.upper()}\nKaldıraç: {lev}x\nMiktar: {amt} USDT"
            else:
                return "⚠️ Miktar hesaplanamadı (Yetersiz bakiye veya limit altı)."
                
    except Exception as e:
        return f"🚨 İşlem Hatası: {str(e)}"

def scanner_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            
            # Tüm marketten en hacimli ve hareketli 30'u al
            market_data = []
            for s, d in tickers.items():
                if ':USDT' in s:
                    market_data.append({'s': s, 'c': d.get('percentage', 0), 'v': d.get('quoteVolume', 0)})
            
            top_list = sorted(market_data, key=lambda x: abs(x['c']), reverse=True)[:30]
            market_summary = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in top_list])

            prompt = f"Bakiye: {balance} USDT\n\nMarket Durumu:\n{market_summary}\n\nFırsat varsa kaldıraç ve miktarı belirleyip @@[ACTION: TRADE...]@@ komutunu ver!"
            
            response = ai_client.models.generate_content(
                model="gemini-2.0-flash", 
                contents=[SYSTEM_SOUL, prompt]
            ).text
            
            if "@@" in response:
                trade_result = execute_autonomous_trade(response)
                safe_send(f"{response.split('@@')[0]}\n\n{trade_result}")
            
            time.sleep(30)
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    safe_send("🚀 Gemini 3 Otonom Scalper Başladı.\nKaldıraç ve Miktar yönetimi tamamen yapay zekadadır.")
    threading.Thread(target=scanner_loop, daemon=True).start()
    bot.infinity_polling()
