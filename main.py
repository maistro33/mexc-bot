# === SADIK SNIPER BOT ===

bot_active = False
current_trade = None

# --- SNIPER FIRSAT BULUCU ---
def find_sniper_trade():
    exch = get_exch()
    markets = [m['symbol'] for m in exch.load_markets().values()
               if ':USDT' in m['symbol']
               and all(x not in m['symbol'] for x in ['BTC','ETH','SOL'])]

    best = None
    best_score = 0

    for sym in markets[:30]:  # ilk 30 coin
        try:
            ticker = exch.fetch_ticker(sym)
            change = safe_num(ticker.get('percentage',0))
            vol = safe_num(ticker.get('quoteVolume',0))

            # Dip fırsatı
            if change < -8 and vol > 5000:
                score = abs(change) * 1.5
                side = 'long'

            # Tepe fırsatı
            elif change > 8 and vol > 5000:
                score = abs(change) * 1.5
                side = 'short'
            else:
                continue

            if score > best_score:
                best_score = score
                best = (sym, side)

        except:
            continue

    return best


# --- SNIPER İŞLEM AÇ ---
def open_sniper_trade(sym, side):
    exch = get_exch()
    bal = exch.fetch_balance({'type':'swap'})
    free_usdt = safe_num(bal.get('USDT', {}).get('free',0))

    if free_usdt < 5:
        bot.send_message(CHAT_ID, "❌ Bakiye çok düşük")
        return None

    amt_val = free_usdt * 0.5  # yarısıyla gir
    lev = 5

    exch.set_leverage(lev, sym)

    ticker = exch.fetch_ticker(sym)
    price = safe_num(ticker['last'])
    qty = (amt_val * lev) / price

    order = exch.create_market_order(sym,
             'buy' if side=='long' else 'sell',
             float(exch.amount_to_precision(sym, qty)))

    bot.send_message(CHAT_ID,
        f"🎯 SNIPER VURDU!\n{sym}\nYön: {side.upper()}\nMarjin: {amt_val:.2f} USDT")

    return {
        'symbol': sym,
        'side': side,
        'entry': price,
        'qty': qty,
        'peak': 0
    }


# --- KAR SÖMÜRME (TRAILING) ---
def manage_sniper():
    global current_trade

    while True:
        if not bot_active or not current_trade:
            time.sleep(3)
            continue

        try:
            exch = get_exch()
            sym = current_trade['symbol']
            ticker = exch.fetch_ticker(sym)
            price = safe_num(ticker['last'])

            entry = current_trade['entry']
            side = current_trade['side']
            qty = current_trade['qty']

            profit = (price-entry)*qty if side=='long' else (entry-price)*qty

            # zirve güncelle
            if profit > current_trade['peak']:
                current_trade['peak'] = profit

            # zarar kes
            if profit <= -0.6:
                exch.create_market_order(sym,
                    'sell' if side=='long' else 'buy',
                    qty, params={'reduceOnly':True})
                bot.send_message(CHAT_ID,"🛡️ Stop loss")
                current_trade = None

            # trailing kar
            elif current_trade['peak'] > 1 and \
                 (current_trade['peak'] - profit) > 0.4:
                exch.create_market_order(sym,
                    'sell' if side=='long' else 'buy',
                    qty, params={'reduceOnly':True})
                bot.send_message(CHAT_ID,
                    f"💰 KAR ALINDI {profit:.2f} USDT")
                current_trade = None

        except:
            pass

        time.sleep(2)


# --- AV MODU ---
def sniper_hunter():
    global bot_active, current_trade

    while True:
        if bot_active and not current_trade:
            trade = find_sniper_trade()
            if trade:
                current_trade = open_sniper_trade(trade[0], trade[1])
        time.sleep(10)


# --- TELEGRAM KOMUTLARI ---
@bot.message_handler(func=lambda m: True)
def sniper_commands(message):
    global bot_active, current_trade

    if str(message.chat.id) != str(CHAT_ID):
        return

    txt = message.text.lower()

    if txt == "startbot":
        bot_active = True
        bot.reply_to(message,"🐋 Av başladı")

    elif txt == "stopbot":
        bot_active = False
        bot.reply_to(message,"🛑 Bot durdu")

    elif txt == "durum":
        if current_trade:
            bot.reply_to(message,
                f"Açık işlem: {current_trade['symbol']}")
        else:
            bot.reply_to(message,"İşlem yok")

    elif txt == "kapat" and current_trade:
        exch = get_exch()
        exch.create_market_order(
            current_trade['symbol'],
            'sell' if current_trade['side']=='long' else 'buy',
            current_trade['qty'],
            params={'reduceOnly':True})
        bot.reply_to(message,"İşlem kapatıldı")
        current_trade = None

    elif txt == "islem ara":
        trade = find_sniper_trade()
        if trade:
            bot.reply_to(message,
                f"Fırsat: {trade[0]} {trade[1]}")
        else:
            bot.reply_to(message,"Fırsat yok")


# --- THREADLER ---
threading.Thread(target=sniper_hunter, daemon=True).start()
threading.Thread(target=manage_sniper, daemon=True).start()

bot.infinity_polling()
