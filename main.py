import ccxt
import telebot
import time
import os
import threading
from datetime import datetime

API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')
TELE_TOKEN = os.getenv('TELE_TOKEN')
MY_CHAT_ID = os.getenv('MY_CHAT_ID')

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'options': {'defaultType': 'swap', 'hedged': True},
    'enableRateLimit': True
})

bot = telebot.TeleBot(TELE_TOKEN)

CONFIG = {
    'entry_usdt': 20.0,
    'leverage': 10,
    'tp1_ratio': 0.75,
    'max_active_trades': 4,
    'rr_target': 1.3,
    'timeframe': '5m'
}

active_trades = {}
scanned_list = []

def place_pos_tpsl(symbol, plan_type, trigger_price, hold_side, qty):
    try:
        params = {
            'marginCoin': 'USDT',
            'symbol': symbol.replace('/', '').replace(':USDT', 'USDT'),
            'planType': plan_type,
            'triggerPrice': str(trigger_price),
            'triggerType': 'mark_price',
            'holdSide': hold_side,
            'size': str(qty),
            'executePrice': '0'
        }
        result = ex.private_mix_post_order_place_pos_tpsl(params)
        bot.send_message(MY_CHAT_ID, f"✅ {plan_type} eklendi → {symbol}")
        return result
    except Exception as e:
        bot.send_message(MY_CHAT_ID, f"❌ TPSL Hatası {plan_type} {symbol}: {str(e)}")
        return None

@bot.message_handler(commands=['testlong'])
def test_long(message):
    symbol = 'BTC/USDT:USDT'
    try:
        ex.set_leverage(CONFIG['leverage'], symbol)
        ticker = ex.fetch_ticker(symbol)
        entry = ticker['last']
        stop = entry * 0.985
        tp1 = entry + (entry - stop) * CONFIG['rr_target']
        
        amount = ex.amount_to_precision(symbol, (CONFIG['entry_usdt'] * CONFIG['leverage']) / entry)
        
        ex.create_order(symbol, 'market', 'buy', amount, params={
            'posSide': 'long',
            'tradeSide': 'open',
            'marginCoin': 'USDT'
        })
        time.sleep(5)
        
        positions = ex.fetch_positions([symbol])
        if not positions or float(positions[0]['contracts']) <= 0:
            bot.reply_to(message, "Pozisyon oluşmadı!")
            return
        
        place_pos_tpsl(symbol, 'pos_loss', stop, 'long', amount)
        tp1_qty = ex.amount_to_precision(symbol, float(amount) * CONFIG['tp1_ratio'])
        place_pos_tpsl(symbol, 'pos_profit', tp1, 'long', tp1_qty)
        
        active_trades[symbol] = True
        bot.reply_to(message, f"TEST LONG AÇILDI\n{symbol}\nEntry: {entry}\nStop: {stop}\nTP: {tp1}")
    except Exception as e:
        bot.reply_to(message, f"Hata: {str(e)}")

if __name__ == "__main__":
    ex.load_markets()
    ex.set_position_mode(True)
    bot.infinity_polling()
