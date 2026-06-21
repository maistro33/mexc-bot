#!/usr/bin/env python3
"""
SADIK GPT TRADING BOT v4
Tam Otonom — GPT ile Gerçek Konuşma Hafızası
Tıpkı Claude gibi — geçmişi hatırlıyor, bağlamı biliyor
"""

import os, time, threading, logging, json
import ccxt
import pandas as pd
import numpy as np
import requests as req
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK_GPT")

# ─── CONFIG ───
TELE_TOKEN  = os.getenv("TELE_TOKEN","")
CHAT_ID     = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API  = os.getenv("BITGET_API","")
BITGET_SEC  = os.getenv("BITGET_SEC","")
BITGET_PASS = os.getenv("BITGET_PASS","")
SUPA_URL    = os.getenv("SUPABASE_URL","")
SUPA_KEY    = os.getenv("SUPABASE_KEY","")
OPENAI_KEY  = os.getenv("OPENAI_API_KEY","")
CG_KEY      = os.getenv("COINGLASS_API_KEY", os.getenv("COINGL_API_KEY",""))

# ─── PARAMETRELER ───
LEVERAGE      = 5
MARGIN        = 10.0
MAX_OPEN      = 5
SCAN_INTERVAL = 60
MIN_QUOTE_VOL = 3_000_000
MAX_PRICE     = 30
COMMISSION    = 0.0006
MAX_DAILY_LOSS = -15.0

# ─── STATE ───
positions       = {}
pos_lock        = threading.Lock()
pos_messages    = {}   # Her pozisyon için GPT konuşma geçmişi
msg_lock        = threading.Lock()
recently_closed = {}
closed_lock     = threading.Lock()
daily_pnl       = 0.0
bot_active      = True
gpt_calls_today = 0
gpt_call_lock   = threading.Lock()

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER",
    "ABNB","SHOP","SQ","PLTR","RKLB","SMCI","ARQQ",
}

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: log.warning(f"[TG] {e}")

# ─── SUPABASE ───
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        log.info("[SUPA] OK")
    except Exception as e:
        log.error(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try: supa.table("gpt_trades").insert(data).execute()
    except Exception as e: log.error(f"[SAVE] {e}")

def load_gpt_history(limit=10):
    if not supa: return "Geçmiş yok."
    try:
        r = supa.table("gpt_trades").select("symbol,signal,pnl,reason,neden").order("created_at", desc=True).limit(limit).execute()
        data = r.data or []
        if not data: return "Henüz geçmiş işlem yok."
        lines = []
        for d in data:
            icon = "✅" if float(d.get("pnl") or 0) > 0 else "❌"
            lines.append(f"{icon} {d.get('symbol','').split('/')[0]} {d.get('signal','')} → {float(d.get('pnl') or 0):+.2f} USDT | {d.get('neden','')[:50]}")
        return "\n".join(lines)
    except: return "Geçmiş yüklenemedi."

# ─── EXCHANGE ───
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})
LAST_API = 0
api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global LAST_API
    for i in range(4):
        try:
            with api_lock:
                w = 0.6 - (time.time() - LAST_API)
                if w > 0: time.sleep(w)
                LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            log.warning(f"[API {i}] {e}")
            time.sleep(2)
    return None

# ─── BTC VERİ ───
def get_btc_data():
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=24)
        if not raw: return "NEUTRAL", 0, 0
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        c = df["c"]
        e20 = float(c.ewm(span=20).mean().iloc[-1])
        price = float(c.iloc[-1])
        change_24h = (price - float(c.iloc[0])) / float(c.iloc[0]) * 100
        if price > e20 * 1.001: return "UP", price, change_24h
        if price < e20 * 0.999: return "DOWN", price, change_24h
        return "NEUTRAL", price, change_24h
    except: return "NEUTRAL", 0, 0

# ─── MARKET VERİSİ ───
def get_market_data(symbol):
    try:
        raw1 = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=30)
        if not raw1: return None
        df1 = pd.DataFrame(raw1, columns=["t","o","h","l","c","v"])

        raw5 = safe_api(exchange.fetch_ohlcv, symbol, "5m", limit=20)
        if not raw5: return None
        df5 = pd.DataFrame(raw5, columns=["t","o","h","l","c","v"])

        raw1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=10)
        if not raw1h: return None
        df1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])

        c1 = df1["c"]; v1 = df1["v"]
        price = float(c1.iloc[-1])

        # RSI
        d = c1.diff()
        g = d.clip(lower=0).rolling(14).mean()
        l = (-d.clip(upper=0)).rolling(14).mean()
        rsi = float((100 - 100/(1+g/l.replace(0,0.001))).iloc[-1])

        # EMA
        ema9   = float(c1.ewm(span=9).mean().iloc[-1])
        ema20  = float(c1.ewm(span=20).mean().iloc[-1])
        ema9_5 = float(df5["c"].ewm(span=9).mean().iloc[-1])
        ema20_5= float(df5["c"].ewm(span=20).mean().iloc[-1])
        ema20_1h = float(df1h["c"].ewm(span=20).mean().iloc[-1])

        # MACD
        ema12 = c1.ewm(span=12).mean()
        ema26 = c1.ewm(span=26).mean()
        macd_hist = float((ema12-ema26-(ema12-ema26).ewm(span=9).mean()).iloc[-1])
        macd_status = "YUKARI" if macd_hist > 0 else "ASAGI"

        # Bollinger
        bb_ma  = float(c1.rolling(20).mean().iloc[-1])
        bb_std = float(c1.rolling(20).std().iloc[-1])
        bb_upper = bb_ma + 2*bb_std
        bb_lower = bb_ma - 2*bb_std
        bb_pct = (price-bb_lower)/(bb_upper-bb_lower)*100 if bb_upper != bb_lower else 50
        bb_pos = "ÜST BANT" if bb_pct > 80 else "ALT BANT" if bb_pct < 20 else "ORTA"

        # Hacim
        vol_avg = float(v1.rolling(20).mean().iloc[-1])
        vol_ratio = float(v1.iloc[-1]) / max(vol_avg, 0.001)

        # Hareketler
        move_1  = (price - float(c1.iloc[-2])) / float(c1.iloc[-2]) * 100
        move_5  = (price - float(c1.iloc[-6])) / float(c1.iloc[-6]) * 100
        move_1h = (price - float(df1h["c"].iloc[-2])) / float(df1h["c"].iloc[-2]) * 100

        # Son 5 mum
        candles = []
        for i in range(-5, 0):
            o = float(df1["o"].iloc[i]); cc = float(df1["c"].iloc[i])
            direction = "🟢" if cc > o else "🔴"
            candles.append(f"{direction}{(cc-o)/o*100:+.2f}%")

        return {
            "symbol": symbol, "price": price,
            "rsi": rsi, "ema9": ema9, "ema20": ema20,
            "ema9_5": ema9_5, "ema20_5": ema20_5, "ema20_1h": ema20_1h,
            "macd_hist": macd_hist, "macd_status": macd_status,
            "bb_pos": bb_pos, "bb_pct": bb_pct,
            "vol_ratio": vol_ratio,
            "move_1": move_1, "move_5": move_5, "move_1h": move_1h,
            "candles": " ".join(candles),
        }
    except Exception as e:
        log.warning(f"[DATA] {symbol}: {e}")
        return None

# ─── GPT ÇAĞRI ───
def call_gpt(messages, max_tokens=300):
    global gpt_calls_today
    if not OPENAI_KEY: return None
    with gpt_call_lock:
        gpt_calls_today += 1
        if gpt_calls_today > 300:
            log.warning("[GPT] Günlük limit")
            return None
    try:
        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-4o", "max_tokens": max_tokens, "temperature": 0.2,
                  "messages": messages},
            timeout=20)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        log.warning(f"[GPT] HTTP {r.status_code}")
        return None
    except Exception as e:
        log.warning(f"[GPT] {e}")
        return None

# ─── SİSTEM PROMPT ───
SYSTEM_PROMPT = """Sen SADIK adlı bir kripto futures paper trading botusun.
Görevin: Piyasayı analiz etmek, işlem açmak, yönetmek ve kapatmak.

TEMEL KURALLAR:
- Komisyon: %0.12 (açış + kapanış) — bunu her zaman hesaba kat
- Kaldıraç: 5x | Margin: 10 USDT | Pozisyon büyüklüğü: 50 USDT
- TP her zaman SL'den büyük olmalı (minimum R:R = 1.5)
- BTC NEUTRAL ise çok dikkatli ol, genellikle PAS geç
- Günlük max zarar: -15 USDT

POZISYON YÖNETİMİ:
- Kazanç %1'i geçti ve trend zayıflıyorsa → kar al, KAPAT
- Kazanç %2'yi geçti → mutlaka bir kısmını koru, TP'yi SL olarak kullan
- Zarar %1.5'i geçti → KAPAT, daha fazla bekleme
- TP'yi 2 kereden fazla yükseltme — bir noktada kar alman lazım
- Aynı pozisyonu 60 dakikadan fazla tutma

ÖĞRENME:
- Geçmiş işlemlerini analiz et
- Hangi koşullarda kazandığını, hangilerinde kaybettiğini öğren
- Her kararında geçmiş deneyimlerini kullan

Her kararını JSON formatında ver."""

# ─── YENİ İŞLEM ANALİZİ ───
def gpt_analyze_new(symbol, data, btc_trend, btc_price, btc_change):
    history = load_gpt_history(8)
    sym = symbol.split("/")[0]

    user_msg = f"""Yeni coin analizi: {sym}/USDT

PIYASA:
BTC: {btc_trend} ${btc_price:,.0f} (24s: {btc_change:+.2f}%)

{sym} GÖSTERGELERİ:
Fiyat: {data['price']:.6f}
RSI: {data['rsi']:.1f}
EMA9/20 (1m): {'YUKARI ✅' if data['ema9'] > data['ema20'] else 'AŞAĞI ❌'}
EMA9/20 (5m): {'YUKARI ✅' if data['ema9_5'] > data['ema20_5'] else 'AŞAĞI ❌'}
EMA20 (1h): Fiyat {'üstünde ✅' if data['price'] > data['ema20_1h'] else 'altında ❌'}
MACD: {data['macd_status']} ({data['macd_hist']:+.6f})
Bollinger: {data['bb_pos']} (%{data['bb_pct']:.0f})
Hacim: {data['vol_ratio']:.1f}x
Hareketler: 1dk={data['move_1']:+.2f}% 5dk={data['move_5']:+.2f}% 1s={data['move_1h']:+.2f}%
Son 5 mum: {data['candles']}

GEÇMİŞ İŞLEMLERİM:
{history}

Bu coin için işlem açmalı mıyım?
JSON formatında cevap ver:
{{"karar": "LONG" veya "SHORT" veya "PAS", "tp_pct": 1.5, "sl_pct": 1.0, "guven": 75, "neden": "kısa analiz"}}"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg}
    ]

    yanit = call_gpt(messages, max_tokens=200)
    if not yanit: return None

    try:
        clean = yanit.replace("```json","").replace("```","").strip()
        karar = json.loads(clean)
        log.info(f"[GPT YENİ] {sym} → {karar.get('karar')} güven:{karar.get('guven')} | {karar.get('neden')}")

        # Konuşma geçmişini başlat
        if karar.get("karar") != "PAS":
            with msg_lock:
                pos_messages[symbol] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": yanit}
                ]
        return karar
    except Exception as e:
        log.warning(f"[GPT YENİ] JSON parse: {e}")
        return None

# ─── POZİSYON YÖNETİMİ ───
def gpt_manage(symbol, pos, current_price):
    """GPT konuşma geçmişiyle pozisyonu yönetir"""
    with msg_lock:
        messages = pos_messages.get(symbol, [])
    if not messages: return None

    sig   = pos["signal"]
    entry = pos["entry"]
    sure  = int((time.time() - pos["open_time"]) / 60)
    pos_size = MARGIN * LEVERAGE

    if sig == "LONG":
        pnl_pct = (current_price - entry) / entry * 100
        pnl     = (current_price - entry) / entry * pos_size - pos_size * COMMISSION
    else:
        pnl_pct = (entry - current_price) / entry * 100
        pnl     = (entry - current_price) / entry * pos_size - pos_size * COMMISSION

    sym = symbol.split("/")[0]

    # Fiyat güncellemesi — GPT'ye göster
    update_msg = f"""{sym} pozisyon güncellemesi ({sure}. dakika):

Giriş: {entry:.6f}
Şu an: {current_price:.6f}
PnL: {pnl:+.2f} USDT ({pnl_pct:+.2f}%)
Mevcut TP: %{pos['tp_pct']:.1f} | Mevcut SL: %{pos['sl_pct']:.1f}

Ne yapmalıyım? JSON:
{{"karar": "DEVAM" veya "KAPAT" veya "TP_YUKSEL" veya "SL_AYARLA", "yeni_tp_pct": 2.0, "yeni_sl_pct": 0.8, "neden": "açıklama"}}

Not: TP'yi zaten {pos.get('tp_yukselme', 0)} kez yükselttim. Kar almayı düşün."""

    # Konuşmaya ekle
    new_messages = messages + [{"role": "user", "content": update_msg}]

    yanit = call_gpt(new_messages, max_tokens=150)
    if not yanit: return None

    try:
        clean = yanit.replace("```json","").replace("```","").strip()
        karar = json.loads(clean)

        # Konuşma geçmişini güncelle (max 20 mesaj — token limiti)
        new_messages.append({"role": "assistant", "content": yanit})
        if len(new_messages) > 20:
            # Sistem promptunu koru, eski mesajları sil
            new_messages = [new_messages[0]] + new_messages[-10:]

        with msg_lock:
            pos_messages[symbol] = new_messages

        log.info(f"[GPT YÖN] {sym} → {karar.get('karar')} | {karar.get('neden')}")
        return karar
    except Exception as e:
        log.warning(f"[GPT YÖN] JSON: {e}")
        return None

# ─── PAPER AÇ ───
def open_paper(symbol, karar, data, btc_trend):
    signal = karar["karar"]
    tp_pct = max(0.010, min(float(karar.get("tp_pct", 1.5)) / 100, 0.060))
    sl_pct = max(0.005, min(float(karar.get("sl_pct", 1.0)) / 100, 0.020))
    guven  = int(karar.get("guven", 60))
    neden  = karar.get("neden", "")

    if guven < 60:
        log.info(f"[SKIP] {symbol.split('/')[0]} güven düşük: {guven}")
        return

    if tp_pct <= sl_pct:
        tp_pct = sl_pct * 1.5

    with pos_lock:
        if symbol in positions: return
        if len(positions) >= MAX_OPEN: return
        price = data["price"]
        if signal == "LONG":
            tp = price*(1+tp_pct); sl = price*(1-sl_pct)
        else:
            tp = price*(1-tp_pct); sl = price*(1+sl_pct)

        positions[symbol] = {
            "signal": signal, "entry": price,
            "tp": tp, "sl": sl,
            "tp_pct": tp_pct*100, "sl_pct": sl_pct*100,
            "tp_yukselme": 0,
            "guven": guven, "neden": neden,
            "btc_trend": btc_trend,
            "open_time": time.time(),
        }

    sym = symbol.split("/")[0]
    tg(
        f"📋 [GPT BOT] {sym} {signal}\n"
        f"Giriş: {price:.6f}\n"
        f"TP: {tp:.6f} (+%{tp_pct*100:.1f})\n"
        f"SL: {sl:.6f} (-%{sl_pct*100:.1f})\n"
        f"Güven: {guven}% | BTC:{btc_trend}\n"
        f"💬 {neden}"
    )

# ─── PAPER KAPAT ───
def close_paper(symbol, reason, exit_price=None):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    # Konuşma geçmişini temizle
    with msg_lock:
        pos_messages.pop(symbol, None)

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    sig  = pos["signal"]; entry = pos["entry"]
    pos_size = MARGIN * LEVERAGE
    commission = pos_size * COMMISSION

    if sig == "LONG":
        pnl = (exit_price-entry)/entry*pos_size - commission
    else:
        pnl = (entry-exit_price)/entry*pos_size - commission

    sure = int((time.time()-pos["open_time"])/60)

    save_trade({
        "symbol": symbol, "signal": sig,
        "pnl": round(pnl,4),
        "tp_pct": pos.get("tp_pct",0),
        "sl_pct": pos.get("sl_pct",0),
        "guven": pos.get("guven",0),
        "btc_trend": pos.get("btc_trend","NEUTRAL"),
        "sure_dk": sure, "reason": reason,
        "neden": pos.get("neden",""),
    })

    global daily_pnl, bot_active
    daily_pnl += pnl
    if daily_pnl <= MAX_DAILY_LOSS and bot_active:
        bot_active = False
        tg(f"⛔ GÜNLÜK ZARAR LİMİTİ!\nGünlük PnL: {daily_pnl:+.2f} USDT\nBot durduruldu.")

    with closed_lock:
        recently_closed[symbol] = time.time()

    sym  = symbol.split("/")[0]
    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} [GPT BOT] {sym} KAPANDI\n{reason}\nPnL: {pnl:+.2f} USDT | {sure}dk")

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(30)  # Her 30 saniyede kontrol
        try:
            with pos_lock: syms = list(positions.keys())

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = t["last"]
                sig   = pos["signal"]
                entry = pos["entry"]
                sure  = int((time.time()-pos["open_time"])/60)
                pos_size = MARGIN * LEVERAGE

                if sig == "LONG":
                    pnl_pct = (price-entry)/entry*100
                else:
                    pnl_pct = (entry-price)/entry*100

                # Zaman aşımı
                if sure > 60:
                    close_paper(symbol, "ZAMAN AŞIMI 60dk", price)
                    continue

                # GPT pozisyon yönetimi
                karar = gpt_manage(symbol, pos, price)
                if not karar: continue

                action = karar.get("karar","DEVAM")
                neden  = karar.get("neden","")
                sym    = symbol.split("/")[0]

                if action == "KAPAT":
                    close_paper(symbol, f"GPT: {neden}", price)

                elif action == "TP_YUKSEL":
                    # Max 2 kez yükselt
                    if pos.get("tp_yukselme", 0) >= 2:
                        log.info(f"[YÖN] {sym} TP max yükseltme ulaşıldı, pas")
                        continue
                    yeni_tp_pct = float(karar.get("yeni_tp_pct", pos["tp_pct"])) / 100
                    yeni_tp_pct = max(0.010, min(yeni_tp_pct, 0.060))
                    if yeni_tp_pct <= pos["tp_pct"] / 100:
                        continue  # Düşürme
                    if sig == "LONG":
                        yeni_tp = entry * (1+yeni_tp_pct)
                    else:
                        yeni_tp = entry * (1-yeni_tp_pct)
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["tp"] = yeni_tp
                            positions[symbol]["tp_pct"] = yeni_tp_pct*100
                            positions[symbol]["tp_yukselme"] = pos.get("tp_yukselme",0) + 1
                    tg(f"📈 [GPT] {sym} TP →%{yeni_tp_pct*100:.1f} ({pos.get('tp_yukselme',0)+1}/2)\n{neden}")

                elif action == "SL_AYARLA":
                    yeni_sl_pct = float(karar.get("yeni_sl_pct", pos["sl_pct"])) / 100
                    yeni_sl_pct = max(0.003, min(yeni_sl_pct, 0.020))
                    if sig == "LONG":
                        yeni_sl = entry * (1-yeni_sl_pct)
                    else:
                        yeni_sl = entry * (1+yeni_sl_pct)
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["sl"] = yeni_sl
                            positions[symbol]["sl_pct"] = yeni_sl_pct*100
                    tg(f"🛡 [GPT] {sym} SL →%{yeni_sl_pct*100:.1f}\n{neden}")

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    global bot_active, daily_pnl
    while True:
        try:
            if not bot_active:
                time.sleep(SCAN_INTERVAL); continue

            with pos_lock:
                open_count = len(positions)
                open_syms  = set(positions.keys())

            if open_count >= MAX_OPEN:
                time.sleep(30); continue

            btc_trend, btc_price, btc_change = get_btc_data()

            if btc_trend == "NEUTRAL":
                log.info("[SCAN] BTC NEUTRAL — bekleniyor")
                time.sleep(SCAN_INTERVAL); continue

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                if symbol.split("/")[0] in BLACKLIST: continue
                if symbol in open_syms: continue
                qv = ticker.get("quoteVolume") or 0
                if qv < MIN_QUOTE_VOL: continue
                price = ticker.get("last") or 0
                if not price or price > MAX_PRICE: continue
                pct = abs(ticker.get("percentage") or 0)
                if pct < 0.5: continue
                with closed_lock:
                    if symbol in recently_closed:
                        if time.time() - recently_closed[symbol] < 3600:
                            continue
                candidates.append({"symbol": symbol, "volume": qv})

            candidates.sort(key=lambda x: x["volume"], reverse=True)
            candidates = candidates[:10]
            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend}")

            for coin in candidates:
                symbol = coin["symbol"]
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in positions: continue

                data = get_market_data(symbol)
                if not data: continue

                karar = gpt_analyze_new(symbol, data, btc_trend, btc_price, btc_change)
                if not karar or karar.get("karar") == "PAS":
                    if karar: log.info(f"[PAS] {symbol.split('/')[0]}: {karar.get('neden')}")
                    continue

                open_paper(symbol, karar, data, btc_trend)
                time.sleep(3)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log.error(f"[SCANNER] {e}")
            time.sleep(10)

# ─── HEALTH ───
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(f"OK|pos:{len(positions)}|pnl:{daily_pnl:+.2f}|gpt:{gpt_calls_today}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# ─── KOMUTLAR ───
@bot.message_handler(commands=["durum","status"])
def cmd_durum(msg):
    with pos_lock:
        if not positions:
            bot.send_message(msg.chat.id,"📋 Pozisyon yok."); return
        lines=["📋 GPT BOT POZİSYONLAR\n"]
        for sym,pos in positions.items():
            t=safe_api(exchange.fetch_ticker,sym)
            if t:
                price=t["last"]; entry=pos["entry"]; signal=pos["signal"]
                pos_size=MARGIN*LEVERAGE
                pnl=(price-entry)/entry*pos_size if signal=="LONG" else (entry-price)/entry*pos_size
                sure=int((time.time()-pos["open_time"])/60)
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} {signal}\n"
                    f"Giriş:{entry:.6f}→{price:.6f}\n"
                    f"PnL:{pnl:+.2f} USDT | {sure}dk\n"
                    f"TP:%{pos['tp_pct']:.1f} SL:%{pos['sl_pct']:.1f} (TP yükseltme:{pos.get('tp_yukselme',0)}/2)\n"
                    f"💬{pos['neden'][:50]}\n"
                )
        bot.send_message(msg.chat.id,"\n".join(lines))

@bot.message_handler(commands=["istatistik","stats"])
def cmd_stats(msg):
    if not supa: bot.send_message(msg.chat.id,"Supabase yok."); return
    try:
        r=supa.table("gpt_trades").select("pnl,guven,signal,btc_trend").execute()
        data=r.data or []
        if not data: bot.send_message(msg.chat.id,"Kayıt yok."); return
        toplam=len(data)
        kazan=sum(1 for d in data if float(d.get("pnl") or 0)>0)
        net=sum(float(d.get("pnl") or 0) for d in data)
        yuksek=[d for d in data if int(d.get("guven") or 0)>=75]
        yuksek_win=[d for d in yuksek if float(d.get("pnl") or 0)>0]
        bot.send_message(msg.chat.id,
            f"📊 GPT BOT v4\n\n"
            f"Toplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
            f"Net PnL: {net:+.2f} USDT\n"
            f"Günlük PnL: {daily_pnl:+.2f} USDT\n\n"
            f"🎯 Güven ≥75: {len(yuksek)} işlem → %{len(yuksek_win)/max(len(yuksek),1)*100:.0f}\n"
            f"📞 GPT çağrısı: {gpt_calls_today}"
        )
    except Exception as e:
        bot.send_message(msg.chat.id,f"Hata: {e}")

@bot.message_handler(commands=["sor","ask","ai"])
def cmd_sor(msg):
    if not OPENAI_KEY: bot.send_message(msg.chat.id,"❌ OpenAI key yok."); return
    soru=msg.text.replace("/sor","").replace("/ask","").replace("/ai","").strip()
    if not soru: bot.send_message(msg.chat.id,"Kullanım: /sor BTC ne yapar?"); return
    bot.send_message(msg.chat.id,"🤔 Düşünüyorum...")
    try:
        btc_trend,btc_price,btc_change=get_btc_data()
        history=load_gpt_history(5)
        with pos_lock: pos_info=f"{len(positions)} açık pozisyon"
        messages=[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":f"Şu an: {pos_info} | BTC:{btc_trend} ${btc_price:,.0f} ({btc_change:+.2f}%)\nSon işlemler:\n{history}\n\nSoru: {soru}"}
        ]
        yanit=call_gpt(messages,max_tokens=300)
        bot.send_message(msg.chat.id,f"🤖 {yanit}" if yanit else "❌ GPT cevap vermedi")
    except Exception as e:
        bot.send_message(msg.chat.id,f"❌ {e}")

@bot.message_handler(commands=["kapat"])
def cmd_kapat(msg):
    text=msg.text.replace("/kapat","").strip().upper()
    if not text: bot.send_message(msg.chat.id,"Kullanım: /kapat SOL"); return
    symbol=f"{text}/USDT:USDT"
    with pos_lock:
        if symbol not in positions: bot.send_message(msg.chat.id,f"❌ {text} yok."); return
    close_paper(symbol,"MANUEL")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock: syms=list(positions.keys())
    for s in syms: close_paper(s,"MANUEL HEPSI")

# ─── MAIN ───
if __name__=="__main__":
    print("🤖 SADIK GPT TRADING BOT v4 BAŞLIYOR...")
    threading.Thread(target=health_server,daemon=True).start()
    threading.Thread(target=manage_loop,  daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    print("[OK] Health | Manage | Scanner")
    tg(
        "🤖 SADIK GPT TRADING BOT v4\n\n"
        "💬 GPT Konuşma Hafızası ile Tam Otonom!\n\n"
        "✅ Her pozisyon için ayrı konuşma\n"
        "✅ GPT geçmişi hatırlıyor\n"
        "✅ TP max 2 kez yükseltilebilir\n"
        "✅ Zarar %1.5 geçince kapat\n"
        "✅ gpt-4o — güçlü analiz\n"
        "✅ Günlük -15 USDT limit\n\n"
        f"Max {MAX_OPEN} pozisyon\n\n"
        "/durum /istatistik /sor [soru] /kapat SOL /hepsikapat"
    )
    while True:
        try: bot.infinity_polling(timeout=30,long_polling_timeout=30)
        except Exception as e:
            log.error(f"[POLLING] {e}"); time.sleep(5)
