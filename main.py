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

# --- [EXCHANGE BAĞLANTISI] ---
def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY,
        'secret': API_SEC,
        'password': PASSPHRASE,
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })

def safe_num(val):
    try:
        if val is None: return 0.0
        clean = re.sub(r'[^0-9.]', '', str(val).replace(',', '.'))
        return float(clean) if clean else 0.0
    except: return 0.0

# --- [AI BOT KURALI] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash ticaret dehasısın.
- Tüm USDT paritelerini analiz et: pump/dump, hacim artışı, balina hareketleri.
- Marjin ve kaldıracı mevcut bakiyeye göre otomatik ayarla.
- Stop-loss ve trailing kar seviyelerini gerçek USDT bazlı optimize et.
- Telegram'a net mesaj ver: açtıysa ⚔️ İşlem açıldı, açılamadıysa sebebini yaz.
- Sadece yüksek kâr potansiyeli taşıyan işlemleri aç.
"""

# --- [EMİR İNFAZI: OTOMATİK BAKİYE VE KALDIRAÇ] ---
def execute_trade(decision, force=False, symbol=None, side=None):
    try:
        exch = get_exch()
        exch.load_markets()
        bal = exch.fetch_balance({'type':'swap'})
        free_usdt = safe_num(bal.get('USDT', {}).get('free',0))

        if force and symbol and side:
            sym = symbol.upper()
            exact_sym = next((s for s in exch.markets if sym in s and ':USDT' in s), None)
            if not exact_sym:
                return f"⚠️ **İŞLEM AÇILAMADI:** {sym} borsada bulunamadı"
            side_order = 'sell' if 'short' in side.lower() else 'buy'
            if free_usdt < 1:
                return f"⚠️ **İŞLEM AÇILAMADI:** Bakiye yetersiz ({free_usdt:.2f} USDT)"
            
            lev_val = 10 if free_usdt>=10 else max(1, int(free_usdt/1))
            amt_val = min(10, free_usdt)
            
            try: exch.set_leverage(lev_val, exact_sym)
            except: pass
            ticker = exch.fetch_ticker(exact_sym)
            last_price = safe_num(ticker['last'])
            qty = (amt_val * lev_val) / last_price
            min_qty = exch.markets[exact_sym]['limits']['amount']['min']
            qty = max(qty, min_qty)
            qty_precision = float(exch.amount_to_precision(exact_sym, qty))
            try:
                order = exch.create_market_order(exact_sym, side_order, qty_precision)
                return f"⚔️ **İŞLEM AÇILDI!**\nSembol: {exact_sym}\nYön: {side_order.upper()}\nFiyat: {last_price}\nMarjin: {amt_val} USDT\nID: {order['id']}"
            except Exception as e:
                return f"⚠️ **İŞLEM AÇILAMADI:** {str(e)}"
        return None
    except Exception as e:
        return f"⚠️ **BİTGET HATASI:** {str(e)}"

# --- [OTOMATİK YÖNETİCİ: GERÇEK USDT BAZLI TRAILING STOP] ---
def auto_manager():
    highest_profits = {}
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in [p for p in pos if safe_num(p.get('contracts'))>0]:
                sym = p['symbol']
                amt_val = safe_num(p.get('margin'))
                side = p['side']
                ticker = exch.fetch_ticker(sym)
                last_price = safe_num(ticker['last'])
                qty = safe_num(p.get('contracts'))
                entry_price = safe_num(p.get('entryPrice'))

                profit = (last_price - entry_price) * qty if side=='long' else (entry_price - last_price)*qty
                if sym not in highest_profits or profit > highest_profits[sym]:
                    highest_profits[sym] = profit

                if profit <= -0.07*amt_val*10:
                    exch.create_market_order(sym, ('sell' if side=='long' else 'buy'), qty, params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ **STOP LOSS:** {sym} kapatıldı. Zararı: {profit:.2f} USDT")
                elif highest_profits.get(sym,0) >= 0.5 and (highest_profits[sym]-profit)>=0.2:
                    exch.create_market_order(sym, ('sell' if side=='long' else 'buy'), qty, params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"💰 **KAR ALINDI:** {sym} {profit:.2f} USDT")
            time.sleep(5)
        except: time.sleep(5)

# --- [TELEGRAM KOMUTLARI & AI MESAJLARI] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) != str(CHAT_ID): return
    try:
        exch = get_exch()
        bal = exch.fetch_balance({'type':'swap'})
        free_usdt = safe_num(bal.get('USDT', {}).get('free',0))
        pos = exch.fetch_positions()
        active_p = [f"{p['symbol']} KAR:{safe_num(p.get('contracts')):.2f}" for p in pos if safe_num(p.get('contracts'))>0]

        time.sleep(1.5)
        prompt = f"CÜZDAN: {free_usdt} USDT\nPOZİSYONLAR: {active_p}\nMESAJ: {message.text}"
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL,prompt]).text
        bot.reply_to(message, response.split("@@")[0].strip() or "Beklemede...")

        if 'ac' in message.text.lower():
            parts = message.text.lower().split()
            coin = parts[0].upper() if len(parts)>0 else None
            side = 'long' if 'long' in message.text.lower() else ('short' if 'short' in message.text.lower() else 'long')
            res = execute_trade(response, force=True, symbol=coin, side=side)
            if res: bot.send_message(CHAT_ID,res)
        else:
            res = execute_trade(response)
            if res: bot.send_message(CHAT_ID,res)
    except Exception as e:
        bot.reply_to(message,f"Sistem: {e}")

# --- [MARKET SCANNER: TÜM COINLER, ÇOKLU FIRSAT] ---
def market_scanner():
    while True:
        try:
            exch = get_exch()
            markets = [m['symbol'] for m in exch.load_markets().values() if ':USDT' in m['symbol']]
            scores = []
            for sym in markets:
                ticker = exch.fetch_ticker(sym)
                change_pct = safe_num(ticker.get('percentage',0))
                volume = safe_num(ticker.get('quoteVolume',0))
                # Normalize edilmiş skor
                score = (change_pct*0.7) + (volume/1000*0.3)
                scores.append((score,sym))
            scores.sort(reverse=True)
            top_opportunities = scores[:3]  # En iyi 3 fırsat
            for s,sym in top_opportunities:
                bot.send_message(CHAT_ID,f"🤖 Analiz: {sym}, değişim skoru {s:.2f}")
            time.sleep(10)
        except: time.sleep(10)

# --- [BOT BAŞLAT] ---
if __name__ == "__main__":
    threading.Thread(target=auto_manager,daemon=True).start()
    threading.Thread(target=market_scanner,daemon=True).start()
    bot.infinity_polling()
