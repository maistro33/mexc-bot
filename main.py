#!/usr/bin/env python3
"""
SADIK GPT TRADING BOT v5
- 10 coini birden GPT'ye gönder, karşılaştırarak seç
- Analiz: gpt-4o | Yönetim: gpt-4o-mini
- Konuşma hafızası ile tam otonom
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
LEVERAGE       = 5
MARGIN         = 10.0
MAX_OPEN       = 5
SCAN_INTERVAL  = 90    # 10 coini analiz etmek zaman alır
MIN_QUOTE_VOL  = 3_000_000
MAX_PRICE      = 30
COMMISSION     = 0.0006
MAX_DAILY_LOSS = -15.0

# ─── STATE ───
positions       = {}
pos_lock        = threading.Lock()
pos_messages    = {}
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
        r = supa.table("gpt_trades").select("symbol,signal,pnl,neden,reason").order("created_at", desc=True).limit(limit).execute()
        data = r.data or []
        if not data: return "Henüz geçmiş işlem yok."
        lines = []
        for d in data:
            icon = "[OK]" if float(d.get("pnl") or 0) > 0 else "[ERR]"
            lines.append(f"{icon} {d.get('symbol','').split('/')[0]} {d.get('signal','')} {float(d.get('pnl') or 0):+.2f}$ | Kapanış:{d.get('reason','')} | {d.get('neden','')[:40]}")
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

# ─── TEK COİN VERİSİ ───
def get_coin_data(symbol):
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
        ema9    = float(c1.ewm(span=9).mean().iloc[-1])
        ema20   = float(c1.ewm(span=20).mean().iloc[-1])
        ema9_5  = float(df5["c"].ewm(span=9).mean().iloc[-1])
        ema20_5 = float(df5["c"].ewm(span=20).mean().iloc[-1])
        ema20_1h= float(df1h["c"].ewm(span=20).mean().iloc[-1])

        # MACD
        ema12 = c1.ewm(span=12).mean()
        ema26 = c1.ewm(span=26).mean()
        macd_hist = float((ema12-ema26-(ema12-ema26).ewm(span=9).mean()).iloc[-1])

        # Bollinger
        bb_ma  = float(c1.rolling(20).mean().iloc[-1])
        bb_std = float(c1.rolling(20).std().iloc[-1])
        bb_upper = bb_ma + 2*bb_std
        bb_lower = bb_ma - 2*bb_std
        bb_pct = (price-bb_lower)/(bb_upper-bb_lower)*100 if bb_upper!=bb_lower else 50

        # Hacim
        vol_avg = float(v1.rolling(20).mean().iloc[-1])
        vol_ratio = float(v1.iloc[-1]) / max(vol_avg, 0.001)

        # Hareketler
        move_1  = (price-float(c1.iloc[-2]))/float(c1.iloc[-2])*100
        move_5  = (price-float(c1.iloc[-6]))/float(c1.iloc[-6])*100
        move_1h = (price-float(df1h["c"].iloc[-2]))/float(df1h["c"].iloc[-2])*100

        # Son 5 mum özeti
        candles = []
        for i in range(-5,0):
            o=float(df1["o"].iloc[i]); cc=float(df1["c"].iloc[i])
            candles.append("[+]" if cc>o else "[-]")

        return {
            "symbol": symbol,
            "price": price,
            "rsi": rsi,
            "ema_1m": "YUKARI" if ema9>ema20 else "ASAGI",
            "ema_5m": "YUKARI" if ema9_5>ema20_5 else "ASAGI",
            "ema_1h": "ÜSTÜNDE" if price>ema20_1h else "ALTINDA",
            "macd": "POZ" if macd_hist>0 else "NEG",
            "bb_pct": bb_pct,
            "vol_ratio": vol_ratio,
            "move_1": move_1,
            "move_5": move_5,
            "move_1h": move_1h,
            "candles": "".join(candles),
        }
    except Exception as e:
        log.warning(f"[DATA] {symbol}: {e}")
        return None

# ─── GPT ÇAĞRI ───
def call_gpt(messages, model="gpt-4o-mini", max_tokens=500):
    global gpt_calls_today
    if not OPENAI_KEY: return None
    with gpt_call_lock:
        gpt_calls_today += 1
        if gpt_calls_today > 400:
            log.warning("[GPT] Günlük limit")
            return None
    try:
        r = req.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "temperature": 0.2,
                  "messages": messages},
            timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        log.warning(f"[GPT] HTTP {r.status_code}")
        return None
    except Exception as e:
        log.warning(f"[GPT] {e}")
        return None

# ─── SİSTEM PROMPT ───
SYSTEM_PROMPT = """Sen SADIK adlı bir kripto futures paper trading botusun.
Görevin: Piyasayı analiz et, en iyi işlemi seç, yönet, kapat.

TEMEL KURALLAR:
- Komisyon: %0.12 (açış+kapanış) — her zaman hesaba kat
- Kaldıraç: 5x | Margin: 10 USDT | Pozisyon: 50 USDT
- TP her zaman SL'den büyük olmalı (min R:R = 1.5)
- BTC NEUTRAL ise çok dikkatli ol
- Günlük max zarar: -15 USDT

POZİSYON YÖNETİMİ KURALLARI:
- Zarar %1.5 geçtiyse → MUTLAKA KAPAT
- Zarar %1 + trend aleyhine → KAPAT
- Kazanç %1+ ve trend zayıflıyorsa → KAPAT, karı al
- Kazanç %2+ → TP yükselt veya KAPAT
- TP'yi max 2 kez yükselt, sonra kar al
- 60 dakika üstü → KAPAT

ÖĞRENME:
- Geçmiş işlemlerini analiz et
- Hangi koşullarda kazandığını öğren
- Aynı hatayı tekrar yapma"""

# ─── 10 COİNİ BİRDEN ANALİZ ET ───
def gpt_analyze_batch(candidates_data, btc_trend, btc_price, btc_change):
    """10 coini tek seferde GPT'ye gönder, en iyisini seçsin"""

    history = load_gpt_history(8)

    # Tüm coinlerin özetini hazırla
    coins_summary = ""
    for i, d in enumerate(candidates_data, 1):
        sym = d["symbol"].split("/")[0]
        coins_summary += f"""
{i}. {sym}:
   Fiyat:{d['price']:.6f} | RSI:{d['rsi']:.0f} | Hacim:{d['vol_ratio']:.1f}x
   EMA(1m):{d['ema_1m']} EMA(5m):{d['ema_5m']} EMA(1h):{d['ema_1h']}
   MACD:{d['macd']} | BB:%{d['bb_pct']:.0f}
   Hareket: 1dk={d['move_1']:+.2f}% 5dk={d['move_5']:+.2f}% 1s={d['move_1h']:+.2f}%
   Son 5 mum: {d['candles']}"""

    user_msg = f"""Piyasa analizi yap ve en iyi işlemi seç.

BTC: {btc_trend} | ${btc_price:,.0f} | 24s:{btc_change:+.2f}%

ANALİZ EDİLECEK COİNLER:
{coins_summary}

GEÇMİŞ İŞLEMLERİM (öğren):
{history}

Yukarıdaki {len(candidates_data)} coini karşılaştır.
En iyi 1-2 işlem fırsatını seç. Eğer hiçbiri uygun değilse PAS de.

JSON formatında cevap ver (liste olarak):
[
  {{"symbol": "AVAX/USDT:USDT", "karar": "LONG", "tp_pct": 2.0, "sl_pct": 1.0, "guven": 80, "neden": "kısa analiz"}},
  {{"symbol": "SOL/USDT:USDT", "karar": "SHORT", "tp_pct": 1.5, "sl_pct": 1.0, "guven": 70, "neden": "kısa analiz"}}
]

E�er hiçbiri uygun değilse: []"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg}
    ]

    # Analiz için gpt-4o kullan
    yanit = call_gpt(messages, model="gpt-4o", max_tokens=500)
    if not yanit: return []

    try:
        clean = yanit.replace("```json","").replace("```","").strip()
        kararlar = json.loads(clean)
        if not isinstance(kararlar, list): return []

        log.info(f"[GPT BATCH] {len(kararlar)} işlem seçildi")

        # Her seçilen coin için konuşma başlat
        for k in kararlar:
            symbol = k.get("symbol","")
            if symbol and k.get("karar") != "PAS":
                with msg_lock:
                    pos_messages[symbol] = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": yanit}
                    ]

        return kararlar

    except Exception as e:
        log.warning(f"[GPT BATCH] JSON: {e} | {yanit[:200]}")
        return []

# ─── POZİSYON YÖNETİMİ ───
def gpt_manage(symbol, pos, current_price):
    """gpt-4o-mini ile pozisyon yönet — ucuz ve hızlı"""
    with msg_lock:
        messages = list(pos_messages.get(symbol, []))
    if not messages:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    sig   = pos["signal"]
    entry = pos["entry"]
    sure  = int((time.time()-pos["open_time"])/60)
    pos_size = MARGIN * LEVERAGE

    if sig == "LONG":
        pnl_pct = (current_price-entry)/entry*100
        pnl     = (current_price-entry)/entry*pos_size - pos_size*COMMISSION
    else:
        pnl_pct = (entry-current_price)/entry*100
        pnl     = (entry-current_price)/entry*pos_size - pos_size*COMMISSION

    sym = symbol.split("/")[0]
    max_pnl = pos.get("max_pnl_pct", 0)

    update_msg = f"""{sym} {sig} — {sure}. dakika güncelleme:
Giriş:{entry:.6f} → Şu an:{current_price:.6f}
PnL: {pnl:+.2f} USDT ({pnl_pct:+.2f}%)
TP:%{pos['tp_pct']:.1f} | SL:%{pos['sl_pct']:.1f}
TP daha önce {tp_yukselme} kez yükseltildi.

Karar ver. JSON:
{{"karar":"DEVAM","neden":"..."}} veya
{{"karar":"KAPAT","neden":"..."}} veya  
{{"karar":"TP_YUKSEL","yeni_tp_pct":2.5,"neden":"..."}} veya
{{"karar":"SL_AYARLA","yeni_sl_pct":0.5,"neden":"..."}}"""

    new_messages = messages + [{"role": "user", "content": update_msg}]

    # Yönetim için gpt-4o-mini kullan
    yanit = call_gpt(new_messages, model="gpt-4o-mini", max_tokens=150)
    if not yanit: return None

    try:
        clean = yanit.replace("```json","").replace("```","").strip()
        karar = json.loads(clean)

        # Konuşmayı güncelle (max 16 mesaj)
        new_messages.append({"role": "assistant", "content": yanit})
        if len(new_messages) > 16:
            new_messages = [new_messages[0]] + new_messages[-8:]
        with msg_lock:
            pos_messages[symbol] = new_messages

        log.info(f"[GPT YÖN] {sym} → {karar.get('karar')} | {karar.get('neden','')[:50]}")
        return karar
    except Exception as e:
        log.warning(f"[GPT YÖN] JSON: {e}")
        return None

# ─── PAPER AÇ ───
def open_paper(symbol, karar, price, btc_trend):
    signal = karar.get("karar","")
    if signal not in ["LONG","SHORT"]: return
    tp_pct = max(0.010, min(float(karar.get("tp_pct",1.5))/100, 0.060))
    sl_pct = max(0.005, min(float(karar.get("sl_pct",1.0))/100, 0.020))
    guven  = int(karar.get("guven",60))
    neden  = karar.get("neden","")

    if guven < 50: return
    if tp_pct <= sl_pct: tp_pct = sl_pct * 1.5

    with pos_lock:
        if symbol in positions: return
        if len(positions) >= MAX_OPEN: return
        if signal == "LONG":
            tp = price*(1+tp_pct); sl = price*(1-sl_pct)
        else:
            tp = price*(1-tp_pct); sl = price*(1+sl_pct)
        positions[symbol] = {
            "signal":signal,"entry":price,"tp":tp,"sl":sl,
            "tp_pct":tp_pct*100,"sl_pct":sl_pct*100,
            "tp_yukselme":0,"guven":guven,"neden":neden,
            "btc_trend":btc_trend,"open_time":time.time(),
        }

    sym = symbol.split("/")[0]
    tg(f"[POS] [GPT] {sym} {signal}\nGiriş:{price:.6f}\nTP:+%{tp_pct*100:.1f} | SL:-%{sl_pct*100:.1f}\nGüven:{guven}% BTC:{btc_trend}\n[>]{neden}")

# ─── PAPER KAPAT ───
def close_paper(symbol, reason, exit_price=None):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return
    with msg_lock:
        pos_messages.pop(symbol, None)

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    sig = pos["signal"]; entry = pos["entry"]
    pos_size = MARGIN*LEVERAGE
    if sig == "LONG":
        pnl = (exit_price-entry)/entry*pos_size - pos_size*COMMISSION
    else:
        pnl = (entry-exit_price)/entry*pos_size - pos_size*COMMISSION

    sure = int((time.time()-pos["open_time"])/60)

    save_trade({
        "symbol":symbol,"signal":sig,"pnl":round(pnl,4),
        "tp_pct":pos.get("ref_tp",0),"sl_pct":pos.get("ref_sl",0),
        "guven":pos.get("guven",0),"btc_trend":pos.get("btc_trend",""),
        "sure_dk":sure,"reason":reason,"neden":pos.get("neden",""),
    })

    global daily_pnl, bot_active
    daily_pnl += pnl
    if daily_pnl <= MAX_DAILY_LOSS and bot_active:
        bot_active = False
        tg(f"[STOP] GÜNLÜK LİMİT! {daily_pnl:+.2f} USDT — Bot durduruldu.")

    with closed_lock:
        recently_closed[symbol] = time.time()

    icon = "[+]" if pnl>=0 else "[-]"
    tg(f"{icon} [GPT] {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL:{pnl:+.2f} USDT | {sure}dk")

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(30)
        try:
            with pos_lock: syms = list(positions.keys())
            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = t["last"]
                sure  = int((time.time()-pos["open_time"])/60)

                if sure > 60:
                    close_paper(symbol, "ZAMAN AŞIMI 60dk", price)
                    continue

                karar = gpt_manage(symbol, pos, price)
                if not karar: continue

                action = karar.get("karar","DEVAM")
                neden  = karar.get("neden","")
                sym    = symbol.split("/")[0]

                if action == "KAPAT":
                    # Minimum kar kontrolu — %1.2 altinda kapatma
                    if pnl_pct > 0 and pnl_pct < 1.2:
                        log.info(f"[YON] {symbol.split('/')[0]} GPT KAPAT dedi ama kar az (%{pnl_pct:.2f}), DEVAM")
                        continue
                    close_paper(symbol, f"GPT:{neden[:50]}", price)

                elif action == "TP_YUKSEL":
                    if pos.get("tp_yukselme",0) >= 2:
                        log.info(f"[YÖN] {sym} max TP yükseltme — pas")
                        continue
                    yeni = max(0.010, min(float(karar.get("yeni_tp_pct", pos["tp_pct"]))/100, 0.060))
                    if yeni <= pos["tp_pct"]/100: continue
                    sig = pos["signal"]
                    yeni_tp = pos["entry"]*(1+yeni) if sig=="LONG" else pos["entry"]*(1-yeni)
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["tp"] = yeni_tp
                            positions[symbol]["tp_pct"] = yeni*100
                            positions[symbol]["tp_yukselme"] = pos.get("tp_yukselme",0)+1
                    tg(f"[UP] [GPT] {sym} TP→%{yeni*100:.1f} ({pos.get('tp_yukselme',0)+1}/2)\n{neden}")

                elif action == "SL_AYARLA":
                    yeni = max(0.003, min(float(karar.get("yeni_sl_pct", pos["sl_pct"]))/100, 0.020))
                    sig = pos["signal"]
                    yeni_sl = pos["entry"]*(1-yeni) if sig=="LONG" else pos["entry"]*(1+yeni)
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["sl"] = yeni_sl
                            positions[symbol]["sl_pct"] = yeni*100
                    tg(f"[SL] [GPT] {sym} SL→%{yeni*100:.1f}\n{neden}")

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

            # Tüm tickerları çek
            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            # Filtrele — en iyi 10 aday
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
                        if time.time()-recently_closed[symbol] < 3600:
                            continue
                candidates.append({"symbol":symbol,"volume":qv,"pct":pct})

            # Hacme göre sırala, top 10
            candidates.sort(key=lambda x: x["volume"], reverse=True)
            candidates = candidates[:10]
            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend}")

            if not candidates:
                time.sleep(SCAN_INTERVAL); continue

            # Her aday için veri topla
            candidates_data = []
            for coin in candidates:
                data = get_coin_data(coin["symbol"])
                if data:
                    candidates_data.append(data)
                time.sleep(0.5)

            if not candidates_data:
                time.sleep(SCAN_INTERVAL); continue

            # 10 coini GPT'ye gönder — karşılaştırarak seçsin
            kararlar = gpt_analyze_batch(candidates_data, btc_trend, btc_price, btc_change)

            for karar in kararlar:
                symbol = karar.get("symbol","")
                if not symbol: continue
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in positions: continue

                # Fiyatı al
                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = t["last"]

                open_paper(symbol, karar, price, btc_trend)
                time.sleep(1)

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
        def log_message(self,*a): pass
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# ─── KOMUTLAR ───
@bot.message_handler(commands=["durum","status"])
def cmd_durum(msg):
    with pos_lock:
        if not positions:
            bot.send_message(msg.chat.id,"[POS] Pozisyon yok."); return
        lines=["[POS] GPT BOT POZİSYONLAR\n"]
        for sym,pos in positions.items():
            t=safe_api(exchange.fetch_ticker,sym)
            if t:
                price=t["last"]; entry=pos["entry"]; signal=pos["signal"]
                pos_size=MARGIN*LEVERAGE
                pnl=(price-entry)/entry*pos_size if signal=="LONG" else (entry-price)/entry*pos_size
                sure=int((time.time()-pos["open_time"])/60)
                lines.append(
                    f"{'[+]' if pnl>=0 else '[-]'} {sym.split('/')[0]} {signal}\n"
                    f"Giriş:{entry:.6f}→{price:.6f}\n"
                    f"PnL:{pnl:+.2f} | {sure}dk\n"
                    f"TP:%{pos['tp_pct']:.1f} SL:%{pos['sl_pct']:.1f} (TP:{pos.get('tp_yukselme',0)}/2)\n"
                )
        bot.send_message(msg.chat.id,"\n".join(lines))

@bot.message_handler(commands=["istatistik","stats"])
def cmd_stats(msg):
    if not supa: bot.send_message(msg.chat.id,"Supabase yok."); return
    try:
        r=supa.table("gpt_trades").select("pnl,guven,signal").execute()
        data=r.data or []
        if not data: bot.send_message(msg.chat.id,"Kayıt yok."); return
        toplam=len(data)
        kazan=sum(1 for d in data if float(d.get("pnl") or 0)>0)
        net=sum(float(d.get("pnl") or 0) for d in data)
        yuksek=[d for d in data if int(d.get("guven") or 0)>=75]
        yuksek_win=[d for d in yuksek if float(d.get("pnl") or 0)>0]
        bot.send_message(msg.chat.id,
            f"[STAT] GPT BOT v5\n\n"
            f"Toplam:{toplam} | Kazanan:{kazan}(%{kazan/toplam*100:.0f})\n"
            f"Net PnL:{net:+.2f} USDT\n"
            f"Günlük PnL:{daily_pnl:+.2f} USDT\n\n"
            f"[TP] Güven≥75: {len(yuksek)} işlem → %{len(yuksek_win)/max(len(yuksek),1)*100:.0f}\n"
            f"[TEL] GPT çağrısı:{gpt_calls_today}"
        )
    except Exception as e:
        bot.send_message(msg.chat.id,f"Hata:{e}")

@bot.message_handler(commands=["sor","ask","ai"])
def cmd_sor(msg):
    if not OPENAI_KEY: bot.send_message(msg.chat.id,"[ERR] OpenAI key yok."); return
    soru=msg.text.replace("/sor","").replace("/ask","").replace("/ai","").strip()
    if not soru: bot.send_message(msg.chat.id,"Kullanım: /sor BTC ne yapar?"); return
    bot.send_message(msg.chat.id,"[...] Düşünüyorum...")
    try:
        btc_trend,btc_price,btc_change=get_btc_data()
        history=load_gpt_history(5)
        with pos_lock: pos_bilgi=f"{len(positions)} açık pozisyon"
        messages=[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":f"Şu an:{pos_bilgi} | BTC:{btc_trend} ${btc_price:,.0f}\nSon işlemler:\n{history}\n\nSoru:{soru}"}
        ]
        yanit=call_gpt(messages,model="gpt-4o",max_tokens=400)
        bot.send_message(msg.chat.id,f"[BOT] {yanit}" if yanit else "[ERR] Cevap yok")
    except Exception as e:
        bot.send_message(msg.chat.id,f"[ERR] {e}")


@bot.message_handler(commands=["analiz"])
def cmd_analiz(msg):
    if not OPENAI_KEY: bot.send_message(msg.chat.id,"OpenAI key yok."); return
    parts = msg.text.replace("/analiz","").strip().split()
    if not parts:
        bot.send_message(msg.chat.id,"Kullanim: /analiz AVAX veya /analiz AVAX SHORT"); return
    coin_adi = parts[0].upper().replace("USDT","").replace("/","").strip()
    ek_bilgi = " ".join(parts[1:]) if len(parts) > 1 else ""
    bot.send_message(msg.chat.id,f"[...] {coin_adi} analiz ediyorum...")
    try:
        btc_trend,btc_price,btc_change = get_btc_data()
        history = load_gpt_history(8)
        with pos_lock:
            pos_bilgi = f"{len(positions)} acik pozisyon"
            pos_dolu = len(positions) >= MAX_OPEN

        symbol = f"{coin_adi}/USDT:USDT"
        data = get_coin_data(symbol)
        if not data:
            bot.send_message(msg.chat.id,f"[ERR] {coin_adi} verisi alinamadi. Sembol dogru mu?"); return

        user_msg = f"""Kullanici bu coini oneriyor: {coin_adi}
Kullanici notu: {ek_bilgi if ek_bilgi else "Yok"}
BTC: {btc_trend} ${btc_price:,.0f} ({btc_change:+.2f}%)

{coin_adi} GOSTERGELER:
Fiyat: {data['price']:.6f}
RSI: {data['rsi']:.1f}
EMA(1m): {data['ema_1m']} | EMA(5m): {data['ema_5m']} | EMA(1h): {data['ema_1h']}
MACD: {data['macd']} | BB: %{data['bb_pct']:.0f}
Hacim: {data['vol_ratio']:.1f}x
Hareket: 1dk={data['move_1']:+.2f}% 5dk={data['move_5']:+.2f}% 1s={data['move_1h']:+.2f}%
Son 5 mum: {data['candles']}

Gecmis islemlerim:
{history}

Su an {pos_bilgi}. {'MAX POZISYON DOLU.' if pos_dolu else 'Yeni islem acabilirim.'}

ONCE JSON ver, sonra aciklama yap:
{{"karar":"LONG","tp_pct":2.0,"sl_pct":1.0,"guven":80,"neden":"kisa neden"}}
veya
{{"karar":"PAS","neden":"kisa neden"}}"""

        messages = [
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":user_msg}
        ]
        yanit = call_gpt(messages, model="gpt-4o", max_tokens=250)
        if not yanit:
            bot.send_message(msg.chat.id,"GPT cevap vermedi"); return

        # JSON bul
        import re
        json_match = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
        if json_match:
            try:
                karar = json.loads(json_match.group())
                action = karar.get("karar","PAS")
                neden  = karar.get("neden","")
                guven  = int(karar.get("guven",0))

                if action in ["LONG","SHORT"] and not pos_dolu and guven >= 50:
                    t = safe_api(exchange.fetch_ticker, symbol)
                    if t:
                        price = t["last"]
                        with msg_lock:
                            pos_messages[symbol] = [
                                {"role":"system","content":SYSTEM_PROMPT},
                                {"role":"user","content":user_msg},
                                {"role":"assistant","content":yanit}
                            ]
                        open_paper(symbol, karar, price, btc_trend)
                        bot.send_message(msg.chat.id,f"[OK] {coin_adi} {action} acildi! Guven:{guven}%\n{neden[:200]}")
                    else:
                        bot.send_message(msg.chat.id,"Fiyat alinamadi")
                elif pos_dolu and action != "PAS":
                    bot.send_message(msg.chat.id,f"[BOT] {coin_adi} icin {action} sinyali var (Guven:{guven}%) ama max pozisyon dolu.\n{neden[:200]}")
                else:
                    bot.send_message(msg.chat.id,f"[BOT] {coin_adi} icin islem acilmadi.\nSebep: {neden[:300]}")
            except:
                bot.send_message(msg.chat.id,f"[BOT] {yanit[:500]}")
        else:
            bot.send_message(msg.chat.id,f"[BOT] {yanit[:500]}")

    except Exception as e:
        log.error(f"[ANALIZ] {e}")
        bot.send_message(msg.chat.id,f"Hata: {e}")

@bot.message_handler(commands=["kapat"])
def cmd_kapat(msg):
    text=msg.text.replace("/kapat","").strip().upper()
    if not text: bot.send_message(msg.chat.id,"Kullanım: /kapat SOL"); return
    symbol=f"{text}/USDT:USDT"
    with pos_lock:
        if symbol not in positions: bot.send_message(msg.chat.id,f"[ERR] {text} yok."); return
    close_paper(symbol,"MANUEL")

@bot.message_handler(commands=["hepsikapat"])
def cmd_hepsi(msg):
    with pos_lock: syms=list(positions.keys())
    for s in syms: close_paper(s,"MANUEL HEPSI")

# ─── MAIN ───
if __name__=="__main__":
    print("[BOT] SADIK GPT TRADING BOT v5 BAŞLIYOR...")
    threading.Thread(target=health_server,daemon=True).start()
    threading.Thread(target=manage_loop,  daemon=True).start()
    threading.Thread(target=scanner_loop, daemon=True).start()
    print("[OK] Health | Manage | Scanner")
    tg(
        "[BOT] SADIK GPT TRADING BOT v5\n\n"
        "[OK] 10 coini birden analiz et → en iyisini seç\n"
        "[OK] Analiz: gpt-4o | Yönetim: gpt-4o-mini\n"
        "[OK] Konuşma hafızası — geçmişi hatırlıyor\n"
        "[OK] TP max 2 kez yükseltilebilir\n"
        "[OK] Günlük -15 USDT limit\n\n"
        f"Max {MAX_OPEN} pozisyon\n\n"
        "/durum /istatistik /sor [soru] /kapat SOL /hepsikapat"
    )
    while True:
        try: bot.infinity_polling(timeout=30,long_polling_timeout=30)
        except Exception as e:
            log.error(f"[POLLING] {e}"); time.sleep(5)
