import os, time, telebot, ccxt, threading, re, json
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

# --- [AKILLI SCALP BOT SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'ın ticaret dehasısın. 
1. KURAL: Asla yalan söyleme. İşlem açmadıysan 'Beklemede' de.
2. EMİR: Bir fırsat gördüğünde @@[ACTION: TRADE, SEMBOL, YON, KALDIRAC, MARJIN]@@ formatını kullan.
3. ÖRNEK: @@[ACTION: TRADE, ORCA, SHORT, 10, 10]@@ -> 10 USDT marjinli 10x short emri.
"""

# --- [Pozisyon Açma + TP/SL/Trailing] ---
def execute_trade(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        if "@@[ACTION: TRADE" in decision:
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                sym_raw, side_raw, lev, amt_usdt = match.groups()
                sym = sym_raw.strip().upper()
                exact_sym = next((s for s in exch.markets if sym in s and ':USDT' in s), None)
                if exact_sym:
                    side = 'sell' if 'SHORT' in side_raw.upper() or 'SELL' in side_raw.upper() else 'buy'
                    lev_val = int(safe_num(lev))
                    amt_val = safe_num(amt_usdt)

                    try: exch.set_leverage(lev_val, exact_sym)
                    except: pass

                    ticker = exch.fetch_ticker(exact_sym)
                    last_price = safe_num(ticker['last'])
                    qty = (amt_val * lev_val) / last_price
                    qty_precision = float(exch.amount_to_precision(exact_sym, qty))

                    order = exch.create_market_order(exact_sym, side, qty_precision)
                    return f"⚔️ **İŞLEM AÇILDI!**\nSembol: {exact_sym}\nYön: {side.upper()}\nFiyat: {last_price}\nMarjin: {amt_val} USDT\nMiktar: {qty_precision}"
        return None
    except Exception as e:
        return f"⚠️ **BİTGET HATASI:** {str(e)}"

# --- [Otonom Yönetici: TP/SL/Trailing ve Kar] ---
def auto_manager():
    highest_roes = {}
    while True:
        try:
            exch = get_exch()
            pos = exch.fetch_positions()
            for p in [p for p in pos if safe_num(p.get('contracts')) > 0]:
                sym = p['symbol']
                roe = safe_num(p.get('percentage'))
                if sym not in highest_roes or roe > highest_roes[sym]: highest_roes[sym] = roe

                # Stop Loss
                if roe <= -7.0:
                    exch.create_market_order(sym, ('sell' if p['side'] == 'long' else 'buy'), safe_num(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"🛡️ **STOP LOSS:** {sym} kapatıldı.")

                # Trailing Kar Maksimizasyonu
                elif highest_roes.get(sym, 0) >= 5.0 and (highest_roes[sym] - roe) >= 2.0:
                    exch.create_market_order(sym, ('sell' if p['side'] == 'long' else 'buy'), safe_num(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"💰 **KAR ALINDI:** {sym} %{roe:.2f}")

            time.sleep(5)
        except:
            time.sleep(5)

# --- [Telegram Komutları + Sohbet Modu] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) != str(CHAT_ID):
        return

    try:
        text = message.text.lower()

        # --- Komutlar ---
        if text == '/startbot':
            bot.reply_to(message, "🤖 Bot başlatıldı, piyasayı tarıyorum.")
        elif text == '/stopbot':
            bot.reply_to(message, "🛑 Bot durduruldu.")
        elif text == '/balance':
            exch = get_exch()
            bal = exch.fetch_balance({'type':'swap'})
            free_usdt = safe_num(bal.get('USDT', {}).get('free',0))
            bot.reply_to(message, f"💰 Cüzdan bakiyesi: {free_usdt} USDT")
        elif text.startswith('scalp işlem aç'):
            bot.reply_to(message, "🤖 Analiz başlatılıyor, en iyi fırsat aranıyor...")
            exch = get_exch()
            bal = exch.fetch_balance({'type':'swap'})
            free_usdt = safe_num(bal.get('USDT', {}).get('free',0))
            prompt = f"CÜZDAN: {free_usdt} USDT\nMESAJ: {message.text}"
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            res = execute_trade(response)
            if res: bot.send_message(CHAT_ID, res)
        elif text.startswith('open'):
            exch = get_exch()
            pos = exch.fetch_positions()
            open_pos = [f"{p['symbol']} ROE:%{p.get('percentage',0):.2f}" for p in pos if safe_num(p.get('contracts')) > 0]
            bot.reply_to(message, f"📊 Açık Pozisyonlar:\n" + "\n".join(open_pos) if open_pos else "📊 Açık pozisyon yok.")
        else:
            # Sohbet modu → normal mesajla cevap
            exch = get_exch()
            bal = exch.fetch_balance({'type':'swap'})
            free_usdt = safe_num(bal.get('USDT', {}).get('free',0))
            prompt = f"CÜZDAN: {free_usdt} USDT\nMESAJ: {message.text}"
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            bot.reply_to(message, response.split("@@")[0].strip() or "İşlem kontrol ediliyor...")

    except Exception as e:
        bot.reply_to(message, f"Sistem Hatası: {str(e)}")

# --- [Ana Başlatıcı] ---
if __name__ == "__main__":
    threading.Thread(target=auto_manager, daemon=True).start()
    bot.infinity_polling()
