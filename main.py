import os, time, telebot, ccxt, threading, re, json
from google import genai

# --- [BAGLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI ZİHNİ: TİCARET DEHASI] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget'te uzman bir Scalper'sın.
1. Canlı verilere bakarak somut parite önerileri sun.
2. İşlem formatı: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
3. Samimi ve zeki ol. "Riskler şöyledir" diye vakit kaybetme, fırsatı söyle ve tetiğe bas.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

# --- [1. MODÜL: AKILLI BEKÇİ (TRAILING STOP)] ---
def position_manager():
    highest_prices = {}
    while True:
        try:
            exch = get_exch()
            positions = exch.fetch_positions()
            active_p = [p for p in positions if float(p.get('contracts', 0)) > 0]

            for p in active_p:
                sym = p['symbol']
                side = p['side']
                curr_price = float(p['last'])
                pnl_pct = float(p.get('percentage', 0)) # ROE %

                if sym not in highest_prices: highest_prices[sym] = curr_price

                # Zirve fiyat takibi
                if side == 'long' and curr_price > highest_prices[sym]:
                    highest_prices[sym] = curr_price
                elif side == 'short' and curr_price < highest_prices[sym]:
                    highest_prices[sym] = curr_price

                # TRAILING: ROE %3'ü geçtiyse ve zirveden %2 geri çekilirse karı al
                drop_from_peak = abs(highest_prices[sym] - curr_price) / highest_prices[sym] * 100
                if pnl_pct > 3.0 and drop_from_peak >= 2.0:
                    side_to_close = 'sell' if side == 'long' else 'buy'
                    exch.create_market_order(sym, 'market', side_to_close, float(p['contracts']), params={'reduceOnly': True})
                    bot.send_message(CHAT_ID, f"💰 **KAR CEBE YAKIŞTI:** {sym} zirveden döndü, işlemi kapattım. Kar: %{pnl_pct:.2f}")
                    if sym in highest_prices: del highest_prices[sym]
            
            time.sleep(15) # 15 saniyede bir kontrol (Scalp için en iyisi)
        except Exception as e:
            time.sleep(10)

# --- [2. MODÜL: OPERATÖR (İŞLEM YÜRÜTÜCÜ)] ---
def execute_trade(decision):
    try:
        if "@@[ACTION: TRADE" in decision:
            exch = get_exch()
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                raw_sym, side_raw, lev_raw, amt_raw = match.groups()
                side = 'buy' if any(x in side_raw.upper() for x in ['BUY', 'LONG']) else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', lev_raw)))
                amt = float(re.sub(r'[^0-9.]', '', amt_raw))
                
                exch.load_markets()
                exact_sym = next((s for s in exch.markets if raw_sym.strip().upper() in s and ':USDT' in s), None)
                
                if exact_sym:
                    # Bakiye kontrolü
                    balance = exch.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 0))
                    if free_usdt < 5: return "⚠️ Bakiye yetersiz, dostum cephane bitti!"
                    
                    final_amt = min(amt, free_usdt * 0.95)
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (final_amt * lev) / ticker['last']
                    # Miktar hassasiyeti (En kritik hata düzeltmesi)
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        exch.create_market_order(exact_sym, 'market', side, qty)
                        return f"🚀 **İŞLEM BAŞARILI:** {exact_sym} | {side.upper()} | {lev}x"
        return None
    except Exception as e:
        return f"⚠️ Borsa Hatası: {str(e)}"

# --- [3. MODÜL: SOHBET VE ANALİZ] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == str(CHAT_ID):
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            # En hareketli 15 pariteyi hazırla
            active = sorted([{'s': s, 'p': d['percentage'], 'v': d['quoteVolume']} for s, d in tickers.items() if ':USDT' in s], key=lambda x: abs(x['p']), reverse=True)[:15]
            market_data = "CANLI VERİLER:\n" + "\n".join([f"{x['s']}: %{x['p']} Vol:{x['v']:.0f}" for x in active])
            
            prompt = f"{market_data}\n\nKullanıcı: '{message.text}'\n\nVerilere bak, dostunla konuş ve gerekiyorsa tetiğe bas."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            bot.reply_to(message, response.split("@@")[0].strip())
            res = execute_trade(response)
            if res: bot.send_message(CHAT_ID, res)
        except Exception as e:
            bot.reply_to(message, f"Ufak bir aksilik: {e}")

if __name__ == "__main__":
    # Bekçi (Trailing Stop) arka planda başlar
    threading.Thread(target=position_manager, daemon=True).start()
    print("Gemini 3 Flash: Savaş Modu Aktif!")
    bot.infinity_polling()
