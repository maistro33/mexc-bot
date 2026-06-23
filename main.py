#!/usr/bin/env python3
"""
SADIK TRADER BOT
- GPT her islemden ders cikarir ve ogrenır
- Piyasa rejimi analizi
- Risk/odul dengesi
- Trailing stop + SL
- Konusma hafizasi
- Sen onaylarsın, GPT yönetir
"""

import os, time, threading, logging, json, re
import ccxt
import pandas as pd
import numpy as np
import requests as req
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK")

# CONFIG
TELE_TOKEN  = os.getenv("TELE_TOKEN","")
CHAT_ID     = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API  = os.getenv("BITGET_API","")
BITGET_SEC  = os.getenv("BITGET_SEC","")
BITGET_PASS = os.getenv("BITGET_PASS","")
SUPA_URL    = os.getenv("SUPABASE_URL","")
SUPA_KEY    = os.getenv("SUPABASE_KEY","")
OPENAI_KEY  = os.getenv("OPENAI_API_KEY","")

LEVERAGE       = 5
MARGIN         = 10.0
MAX_OPEN       = 4
MIN_VOL        = 1_000_000
MAX_PRICE      = 30
COMMISSION     = 0.0006
MAX_DAILY_LOSS = -15.0
ONERI_INTERVAL = 120  # Her 2 dakikada tara

# STATE
positions     = {}
pos_lock      = threading.Lock()
pos_messages  = {}
msg_lock      = threading.Lock()
daily_pnl       = 0.0
gpt_calls       = 0
recently_closed = {}   # Kapanan coinler - 30dk tekrar acma
closed_lock     = threading.Lock()
# bekleyen kaldirild - tamamen otomatik mod

# EXCHANGE
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})
LAST_API  = 0
api_lock  = threading.Lock()

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER",
    "ABNB","SHOP","SQ","PLTR","RKLB","SMCI","ARQQ",
}

# TELEGRAM
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: log.warning(f"[TG] {e}")

# SUPABASE
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

def save_lesson(symbol, signal, pnl, ders, btc_trend, piyasa):
    """GPT dersini ayri tabloya kaydet"""
    if not supa: return
    try:
        sonuc = "KAZANC" if pnl > 0 else "KAYIP"
        supa.table("gpt_lessons").insert({
            "symbol": symbol, "signal": signal,
            "pnl": round(pnl, 4), "sonuc": sonuc,
            "ders": ders[:500], "piyasa": piyasa,
            "btc_trend": btc_trend,
        }).execute()
        log.info(f"[DERS] Kaydedildi: {symbol.split('/')[0]} {sonuc}")
    except Exception as e:
        log.error(f"[DERS SAVE] {e}")

def load_lessons(limit=8):
    """Gecmis islemler + dersler"""
    if not supa: return "Gecmis yok."
    try:
        # Dersler
        lessons_r = supa.table("gpt_lessons").select(
            "symbol,signal,pnl,sonuc,ders,btc_trend"
        ).order("created_at", desc=True).limit(6).execute()
        
        # Islemler
        trades_r = supa.table("gpt_trades").select(
            "symbol,signal,pnl,neden,reason,sure_dk,btc_trend"
        ).order("created_at", desc=True).limit(limit).execute()

        lines = ["=== GECMIS ISLEMLER ==="]
        data = trades_r.data or []
        if data:
            kazanc = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            lines.append(f"Son {len(data)}: {kazanc} kazanc, {len(data)-kazanc} kayip")
            for d in data:
                pnl = float(d.get("pnl") or 0)
                icon = "+" if pnl > 0 else "-"
                lines.append(f"[{icon}] {d.get('symbol','').split('/')[0]} {d.get('signal','')} {pnl:+.2f}$ | {d.get('sure_dk',0)}dk | {d.get('reason','')[:30]}")

        lessons = lessons_r.data or []
        if lessons:
            lines.append("\n=== OGRENILENLER ===")
            for l in lessons:
                icon = "+" if float(l.get("pnl") or 0) > 0 else "-"
                lines.append(f"[{icon}] {l.get('symbol','').split('/')[0]}: {l.get('ders','')[:80]}")

        return "\n".join(lines)
    except Exception as e:
        return f"Gecmis yuklenemedi: {e}"


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
            log.warning(f"[API] {e}")
            time.sleep(2)
    return None

# BTC + PIYASA REJİMİ
def get_market():
    try:
        raw1h = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=48)
        raw4h = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "4h", limit=24)
        if not raw1h: return "NEUTRAL", 0, 0, "BELIRSIZ"
        
        df1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"])
        price = float(df1h["c"].iloc[-1])
        e20 = float(df1h["c"].ewm(span=20).mean().iloc[-1])
        e50 = float(df1h["c"].ewm(span=50).mean().iloc[-1])
        chg24 = (price - float(df1h["c"].iloc[-24])) / float(df1h["c"].iloc[-24]) * 100
        
        # 4h trend
        regime = "YATAY"
        if raw4h:
            df4h = pd.DataFrame(raw4h, columns=["t","o","h","l","c","v"])
            e20_4h = float(df4h["c"].ewm(span=20).mean().iloc[-1])
            price_4h = float(df4h["c"].iloc[-1])
            chg_4h = (price_4h - float(df4h["c"].iloc[-12])) / float(df4h["c"].iloc[-12]) * 100
            
            if price_4h > e20_4h * 1.02 and chg_4h > 3: regime = "BOGASI"
            elif price_4h < e20_4h * 0.98 and chg_4h < -3: regime = "AYISI"
            else: regime = "YATAY"

        if price > e20 * 1.001 and price > e50: trend = "UP"
        elif price < e20 * 0.999 and price < e50: trend = "DOWN"
        elif price > e20 * 1.001: trend = "UP"
        elif price < e20 * 0.999: trend = "DOWN"
        else: trend = "NEUTRAL"
        
        return trend, price, chg24, regime
    except:
        return "NEUTRAL", 0, 0, "BELIRSIZ"

# COIN VERİSİ - KAPSAMLI
def get_coin(symbol):
    try:
        raw1  = safe_api(exchange.fetch_ohlcv, symbol, "1m",  limit=50)
        raw5  = safe_api(exchange.fetch_ohlcv, symbol, "5m",  limit=30)
        raw15 = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=20)
        raw1h = safe_api(exchange.fetch_ohlcv, symbol, "1h",  limit=24)
        if not raw1 or not raw5: return None

        df1  = pd.DataFrame(raw1,  columns=["t","o","h","l","c","v"])
        df5  = pd.DataFrame(raw5,  columns=["t","o","h","l","c","v"])
        df1h = pd.DataFrame(raw1h, columns=["t","o","h","l","c","v"]) if raw1h else df5

        c1 = df1["c"]; v1 = df1["v"]
        price = float(c1.iloc[-1])

        # RSI
        d = c1.diff()
        g = d.clip(lower=0).rolling(14).mean()
        l = (-d.clip(upper=0)).rolling(14).mean()
        rsi = float((100 - 100/(1+g/l.replace(0,0.001))).iloc[-1])

        # EMA'lar
        ema9   = float(c1.ewm(span=9).mean().iloc[-1])
        ema20  = float(c1.ewm(span=20).mean().iloc[-1])
        ema50  = float(c1.ewm(span=50).mean().iloc[-1]) if len(c1) >= 50 else ema20
        ema9_5 = float(df5["c"].ewm(span=9).mean().iloc[-1])
        ema20_5= float(df5["c"].ewm(span=20).mean().iloc[-1])
        ema20_1h = float(df1h["c"].ewm(span=20).mean().iloc[-1])

        # MACD
        macd_line   = c1.ewm(span=12).mean() - c1.ewm(span=26).mean()
        signal_line = macd_line.ewm(span=9).mean()
        macd_hist   = float((macd_line - signal_line).iloc[-1])
        macd_trend  = "YUKARI" if macd_hist > 0 else "ASAGI"
        macd_guc    = "GUCLU" if abs(macd_hist) > abs(float((macd_line - signal_line).iloc[-2])) else "ZAYIF"

        # Bollinger
        bb_ma    = float(c1.rolling(20).mean().iloc[-1])
        bb_std   = float(c1.rolling(20).std().iloc[-1])
        bb_upper = bb_ma + 2*bb_std
        bb_lower = bb_ma - 2*bb_std
        bb_pct   = (price-bb_lower)/(bb_upper-bb_lower)*100 if bb_upper != bb_lower else 50
        bb_pos   = "UST" if bb_pct > 80 else "ALT" if bb_pct < 20 else "ORTA"

        # Hacim analizi
        vol_avg   = float(v1.rolling(20).mean().iloc[-1])
        vol_son   = float(v1.iloc[-1])
        vol_ratio = vol_son / max(vol_avg, 0.001)
        vol_trend = "ARTIYOR" if float(v1.iloc[-1]) > float(v1.iloc[-3]) else "AZALIYOR"

        # Fiyat hareketleri
        move_1m  = (price - float(c1.iloc[-2])) / float(c1.iloc[-2]) * 100
        move_5m  = (price - float(c1.iloc[-6])) / float(c1.iloc[-6]) * 100
        move_15m = (price - float(c1.iloc[-16])) / float(c1.iloc[-16]) * 100
        move_1h  = (price - float(df1h["c"].iloc[-2])) / float(df1h["c"].iloc[-2]) * 100 if raw1h else 0

        # 15m mum analizi
        chart_str = ""
        destek = price; direnc = price
        if raw15:
            df15 = pd.DataFrame(raw15, columns=["t","o","h","l","c","v"])
            highs  = df15["h"].values
            lows   = df15["l"].values
            closes = df15["c"].values
            opens  = df15["o"].values

            destek  = float(min(lows[-8:]))
            direnc  = float(max(highs[-8:]))
            up_cnt  = sum(1 for i in range(-8,0) if closes[i] > opens[i])
            
            mum_ozet = ""
            for i in range(-6, 0):
                o=float(opens[i]); c=float(closes[i])
                h=float(highs[i]); l=float(lows[i])
                yon = "+" if c > o else "-"
                deg = (c-o)/o*100
                mum_ozet += f"{yon}{deg:+.1f}% "

            chart_str = (
                f"15m Mumlar: {mum_ozet}\n"
                f"Yukari:{up_cnt}/8 | Asagi:{8-up_cnt}/8\n"
                f"Destek:{destek:.6f} | Direnc:{direnc:.6f}\n"
                f"Destek Uzakligi: %{(price-destek)/price*100:.2f} | "
                f"Direnc Uzakligi: %{(direnc-price)/price*100:.2f}"
            )

        # Momentum skoru (0-100)
        momentum = 0
        if ema9 > ema20: momentum += 20
        if ema9_5 > ema20_5: momentum += 20
        if price > ema20_1h: momentum += 20
        if macd_hist > 0: momentum += 20
        if vol_ratio > 1.5: momentum += 20
        if move_5m > 0: momentum = momentum
        else: momentum = max(0, momentum - 10)

        return {
            "symbol": symbol, "price": price,
            "rsi": rsi, "bb_pos": bb_pos, "bb_pct": bb_pct,
            "ema_1m": "YUKARI" if ema9>ema20 else "ASAGI",
            "ema_5m": "YUKARI" if ema9_5>ema20_5 else "ASAGI",
            "ema_1h": "USTUNDE" if price>ema20_1h else "ALTINDA",
            "ema50":  "USTUNDE" if price>ema50 else "ALTINDA",
            "macd": macd_trend, "macd_guc": macd_guc,
            "vol_ratio": vol_ratio, "vol_trend": vol_trend,
            "move_1m": move_1m, "move_5m": move_5m,
            "move_15m": move_15m, "move_1h": move_1h,
            "momentum": momentum,
            "destek": destek, "direnc": direnc,
            "chart_str": chart_str,
        }
    except Exception as e:
        log.warning(f"[COIN] {symbol}: {e}")
        return None

# GPT - TIMEOUT ILE
def gpt(messages, model="gpt-4o", max_tokens=500):
    global gpt_calls
    if not OPENAI_KEY: return None
    gpt_calls += 1
    if gpt_calls > 600: return None

    result = [None]
    def call():
        try:
            r = req.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                json={"model": model, "max_tokens": max_tokens, "temperature": 0.2, "messages": messages},
                timeout=12)
            if r.status_code == 200:
                result[0] = r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning(f"[GPT] {e}")

    t = threading.Thread(target=call, daemon=True)
    t.start(); t.join(timeout=15)
    if t.is_alive():
        log.warning("[GPT] Timeout")
        return None
    return result[0]

# SISTEM PROMPT - TRADER RUHU
SYSTEM = """Sen SADIK, deneyimli bir kripto futures trader'isin.
Yillar once cok kayip yasamis, simdi disiplinli ve sabırlı bir trader olmusun.

TRADER KIMLIGIN:
- Her islemden once risk/odul hesaplarsin
- Gecmis hatalarindan ogrenmissin
- Trend ile gidersin, trende karsi gitmezsin
- Kotu bir islemde kucuk kayipla cikmayi bilirsin
- Iyi bir islemde karı buyutursun

KESIN KURALLAR:
- Komisyon %0.12 | Kaldirac 5x | Margin 10$ | Pozisyon 50$
- BTC UP → sadece LONG | BTC DOWN → sadece SHORT | NEUTRAL → bekliyorsun
- %30+ yukselmus coinlere SHORT ACMA — momentum cok guclu
- Dusuk hacim (turnover < 1M) → RİSKLİ, kac
- SL %2 otomatik — bunun disinda zarar buyutme
- Min %1.2 kar olmadan kapatma — komisyon yiyor
- 15 dakika dolmadan kapanmiyorsun — pozisyonun oturmasini bekle

POZISYON YONETIMI:
- Kar %2+ ve trend zayifliyorsa → kapat, kar al
- Kar %3+ → mutlaka kapat
- Trailing: kar %2 olunca SL'i maliyete cek
- Zarar var ama trend devam ediyorsa → bekle, SL korur
- Trend NET aleyhine donduyse → erken cik, kucuk zarar

OGRENMEK:
- Her kapanan islemi analiz et
- "Neden kazandim/kaybettim?" sorusunu sor
- Ayni hatay tekrarlama
- Basarili pattern'leri tekrarla"""

# COİN BUL - TAM KELIME
def find_coin(text):
    words = re.findall(r'[A-Z0-9]+', text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        for word in words:
            if len(word) < 2: continue
            symbol = f"{word}/USDT:USDT"
            if symbol in tickers and word not in BLACKLIST:
                return symbol
        best = None; best_len = 0
        for symbol in tickers.keys():
            if not symbol.endswith("/USDT:USDT"): continue
            sym = symbol.split("/")[0].upper()
            if sym in BLACKLIST: continue
            if sym in words and len(sym) > best_len:
                best = symbol; best_len = len(sym)
        return best
    except: return None

# ISLEM AC
def open_pos(symbol, yon, neden, btc_trend):
    # Once fiyati al
    t = safe_api(exchange.fetch_ticker, symbol)
    if not t: return False
    price = t["last"]
    sl_price = price * (1 - 0.02) if yon == "LONG" else price * (1 + 0.02)

    with pos_lock:
        # Ayni coin varsa acma (hem pozisyon hem recently_closed)
        sym_base = symbol.split("/")[0].upper()
        for existing in positions.keys():
            if existing.split("/")[0].upper() == sym_base:
                log.info(f"[SKIP] {sym_base} zaten acik")
                return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 1800:
                    log.info(f"[SKIP] {sym_base} 30dk bekleme")
                    return False
        if len(positions) >= MAX_OPEN:
            tg(f"Max {MAX_OPEN} pozisyon."); return False
        # Gunluk limit kontrolu
        if daily_pnl <= MAX_DAILY_LOSS:
            tg(f"\u26d4 Gunluk limit asimi, islem acilmiyor.")
            return False
        # Pozisyonu kaydet
        positions[symbol] = {
            "signal": yon, "entry": price,
            "sl_price": sl_price,
            "max_pnl": 0.0, "trailing_aktif": False,
            "neden": neden, "btc_trend": btc_trend,
            "open_time": time.time(),
        }

    # Pozisyon acildiktan SONRA mesaj at
    sym = symbol.split("/")[0]
    icon = "\U0001f4c8" if yon == "LONG" else "\U0001f4c9"
    tg(
        f"\U0001f4cb {icon} {sym} {yon}\n"
        f"Giris: {price:.6f}\n"
        f"SL: {sl_price:.6f} (-%2.0)\n"
        f"BTC: {btc_trend}\n"
        f"\U0001f4ac {neden}"
    )
    return True

# ISLEM KAPAT + DERS CİKAR
def close_pos(symbol, reason, exit_price=None):
    global daily_pnl
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return
    with msg_lock:
        pos_messages.pop(symbol, None)

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    sig = pos["signal"]; entry = pos["entry"]
    pos_size = MARGIN * LEVERAGE
    if sig == "LONG":
        pnl = (exit_price-entry)/entry*pos_size - pos_size*COMMISSION
    else:
        pnl = (entry-exit_price)/entry*pos_size - pos_size*COMMISSION

    sure = int((time.time()-pos["open_time"])/60)
    daily_pnl += pnl

    if daily_pnl <= MAX_DAILY_LOSS:
        tg(f"\u26d4 GUNLUK LİMİT! {daily_pnl:+.2f}$ — Bot durduruldu.")
        # Tum acik pozisyonlari kapat
        with pos_lock: syms = list(positions.keys())
        for s in syms:
            close_pos(s, "Gunluk limit asimi", None)

    # GPT ders cikariyor
    def ders_cikar():
        try:
            ders_prompt = (
                f"Bir islem kapandi. Analiz et ve ders cikar:\n\n"
                f"Coin: {symbol.split('/')[0]} {sig}\n"
                f"Giris: {entry:.6f} | Cikis: {exit_price:.6f}\n"
                f"PnL: {pnl:+.2f}$ | Sure: {sure}dk\n"
                f"Kapanma sebebi: {reason}\n"
                f"BTC trendi: {pos.get('btc_trend','')}\n"
                f"Neden acilmisti: {pos.get('neden','')}\n\n"
                f"Kisa analiz yaz (max 2 cumle): Ne yapildi dogru/yanlis? "
                f"Bir dahaki benzer durumda ne yapilmali?"
            )
            msgs = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": ders_prompt}
            ]
            ders = gpt(msgs, model="gpt-4o-mini", max_tokens=150)
            if ders:
                save_lesson(symbol, sig, pnl, ders, pos.get("btc_trend",""), "")
            else:
                # GPT cevap vermediyse kural bazli fallback ders
                if pnl > 0:
                    fallback = f"Kazanc: {pos.get('neden','')[:100]} - {reason} ile kapandi"
                else:
                    fallback = f"Kayip: {reason} - Sebep: {pos.get('neden','')[:100]}"
                save_lesson(symbol, sig, pnl, fallback, pos.get("btc_trend",""), "fallback")
        except Exception as e:
            log.warning(f"[DERS] {e}")
            save_trade({
                "symbol": symbol, "signal": sig, "pnl": round(pnl,4),
                "tp_pct": 0, "sl_pct": 2.0, "guven": 0,
                "btc_trend": pos.get("btc_trend",""),
                "sure_dk": sure, "reason": reason, "neden": pos.get("neden",""),
            })

    # Trade kaydet - bagimsiz, hata toleransli
    try:
        save_trade({
            "symbol": symbol, "signal": sig, "pnl": round(pnl,4),
            "tp_pct": pos.get("max_pnl",0), "sl_pct": 2.0, "guven": 0,
            "btc_trend": pos.get("btc_trend",""),
            "sure_dk": sure, "reason": reason, "neden": pos.get("neden",""),
        })
    except Exception as e:
        log.error(f"[SAVE_TRADE] {e}")

    # Lesson kaydet - bagimsiz, hata toleransli
    threading.Thread(target=ders_cikar, daemon=True).start()

    # 30 dakika tekrar acma - coin adina gore sakla
    sym_base = symbol.split("/")[0].upper()
    with closed_lock:
        recently_closed[sym_base] = time.time()

    icon = "\U0001f7e2" if pnl >= 0 else "\U0001f534"
    tg(f"{icon} {symbol.split('/')[0]} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ | {sure}dk\nGunluk: {daily_pnl:+.2f}$")

# YÖNETİCİ
def manage_loop():
    while True:
        time.sleep(60)
        try:
            with pos_lock: syms = list(positions.keys())
            if syms:
                log.info(f"[MANAGE] {len(syms)} pozisyon kontrol ediliyor")
            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price = t["last"]
                sig   = pos["signal"]; entry = pos["entry"]
                sure  = int((time.time()-pos["open_time"])/60)
                pos_size = MARGIN * LEVERAGE
                sym = symbol.split("/")[0]

                if sig == "LONG":
                    pnl_pct = (price-entry)/entry*100
                    pnl     = (price-entry)/entry*pos_size - pos_size*COMMISSION
                else:
                    pnl_pct = (entry-price)/entry*100
                    pnl     = (entry-price)/entry*pos_size - pos_size*COMMISSION

                # MAX KAR GUNCELLE
                with pos_lock:
                    if symbol in positions:
                        if pnl_pct > positions[symbol]["max_pnl"]:
                            positions[symbol]["max_pnl"] = pnl_pct
                max_pnl = pos["max_pnl"]

                # ZAMAN ASIMI
                if sure > 120:
                    close_pos(symbol, "Zaman asimi 2 saat", price)
                    continue

                # SABIT SL %2
                if pnl_pct <= -2.0:
                    close_pos(symbol, "Stop Loss -%2.0", price)
                    continue

                # TRAILING STOP - Kar %2 olunca aktif
                if max_pnl >= 2.0:
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["trailing_aktif"] = True
                    # Zirveden %1 dustuyse kapat
                    if pnl_pct < max_pnl - 1.0:
                        close_pos(symbol, f"Trailing Stop (zirve:%{max_pnl:.1f})", price)
                        continue

                # ILK 15 DAKİKA - sadece SL kontrol et
                if sure < 15:
                    continue

                # GPT YÖNETİM
                with msg_lock:
                    msgs = list(pos_messages.get(symbol, []))
                if not msgs:
                    msgs = [{"role": "system", "content": SYSTEM}]

                # Guncel coin verisi - her 3 dakikada bir cek (maliyet azalt)
                coin_ozet = ""
                if sure % 3 == 0:  # 3 dakikada bir guncelle
                    coin_d = get_coin(symbol)
                    if coin_d:
                        coin_ozet = (
                            f"RSI:{coin_d['rsi']:.0f} | "
                            f"EMA1m:{coin_d['ema_1m']} | EMA5m:{coin_d['ema_5m']} | "
                            f"MACD:{coin_d['macd']}({coin_d['macd_guc']}) | "
                            f"Hacim:{coin_d['vol_ratio']:.1f}x({coin_d['vol_trend']}) | "
                            f"Momentum:{coin_d['momentum']}/100"
                        )

                update = (
                    f"{sym} {sig} — {sure}. dakika\n"
                    f"Giris:{entry:.6f} | Simdi:{price:.6f}\n"
                    f"PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%)\n"
                    f"En yuksek kar: %{max_pnl:.2f}\n"
                    f"Trailing: {'Aktif' if pos.get('trailing_aktif') else 'Bekliyor'}\n"
                    f"{coin_ozet}\n"
                    f"Karar: DEVAM mi KAPAT mi?\n"
                    f"JSON: {{\"devam\": true}} veya {{\"kapat\": true, \"mesaj\": \"neden\"}}"
                )

                new_msgs = msgs + [{"role": "user", "content": update}]
                yanit = gpt(new_msgs, model="gpt-4o-mini", max_tokens=150)
                if not yanit: continue

                try:
                    j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
                    if j:
                        karar = json.loads(j.group())
                        if karar.get("kapat"):
                            if sure < 15: continue
                            if 0 < pnl_pct < 1.2: continue  # Min kar yok
                            if -1.5 < pnl_pct < 0: continue  # Kucuk zarar, SL bekle
                            mesaj = karar.get("mesaj", "GPT kapat")
                            close_pos(symbol, mesaj, price)
                        else:
                            # Her 15 dakikada kullaniciya bilgi
                            if sure % 15 == 0 and sure > 0:
                                temiz = re.sub(r'\{[^{}]+\}','',yanit).strip()
                                if temiz:
                                    icon = "\U0001f7e2" if pnl>=0 else "\U0001f534"
                                    tg(f"{icon} {sym} | {pnl:+.2f}$ ({pnl_pct:+.2f}%) | {sure}dk\n\U0001f916 {temiz[:150]}")
                            new_msgs.append({"role": "assistant", "content": yanit})
                            if len(new_msgs) > 20:
                                new_msgs = [new_msgs[0]] + new_msgs[-10:]
                            with msg_lock:
                                pos_messages[symbol] = new_msgs
                except Exception as e:
                    log.warning(f"[YON] {e}")

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ÖNERİ LOOP
def oneri_loop():
    time.sleep(90)
    while True:
        try:
            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(ONERI_INTERVAL); continue

            btc_trend, btc_price, btc_chg, regime = get_market()
            log.info(f"[SCAN] BTC:{btc_trend} ${btc_price:,.0f} | Rejim:{regime}")

            # BTC NEUTRAL'da da tara ama daha dikkatli ol
            # Sadece cok guclu sinyallerde ac

            # Sadece gerekli alanlari cek - daha hizli
            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(ONERI_INTERVAL); continue

            with pos_lock: open_syms = set(positions.keys())

            # PUMP DEDEKTORU - Ani hacim ve fiyat hareketi
            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                sym = symbol.split("/")[0]
                if sym in BLACKLIST: continue
                if symbol in open_syms: continue
                qv = ticker.get("quoteVolume") or 0
                if qv < MIN_VOL: continue
                price = ticker.get("last") or 0
                if not price or price > MAX_PRICE: continue
                pct = ticker.get("percentage") or 0
                # BTC ile uyumlu
                if btc_trend == "UP" and pct < 0: continue
                if btc_trend == "DOWN" and pct > 0: continue
                if abs(pct) < 0.5: continue
                
                # Pump skoru hesapla
                pump_score = 0
                if abs(pct) > 5: pump_score += 40   # Guclu hareket
                elif abs(pct) > 2: pump_score += 20
                elif abs(pct) > 1: pump_score += 10
                if qv > 5_000_000: pump_score += 30  # Yuksek hacim
                elif qv > 2_000_000: pump_score += 15
                elif qv > 1_000_000: pump_score += 5
                
                candidates.append({
                    "symbol": symbol, "volume": qv, 
                    "pct": abs(pct), "pump_score": pump_score
                })

            # Pump skoruna gore sirala - en iyi firsatlar once
            candidates.sort(key=lambda x: x["pump_score"], reverse=True)
            candidates = candidates[:8]

            if not candidates:
                time.sleep(ONERI_INTERVAL); continue

            # Veri topla
            coins_data = []
            for c in candidates[:5]:
                d = get_coin(c["symbol"])
                if d: coins_data.append(d)
                time.sleep(0.3)

            if not coins_data:
                time.sleep(ONERI_INTERVAL); continue

            # DERSLER
            lessons = load_lessons(8)

            # GPT BATCH ANALİZ
            summary = ""
            for d in coins_data:
                s = d["symbol"].split("/")[0]
                summary += (
                    f"\n{s}: Fiyat:{d['price']:.6f} | RSI:{d['rsi']:.0f} | "
                    f"Momentum:{d['momentum']}/100 | "
                    f"EMA1m:{d['ema_1m']} EMA5m:{d['ema_5m']} EMA1h:{d['ema_1h']} | "
                    f"MACD:{d['macd']}({d['macd_guc']}) | "
                    f"Hacim:{d['vol_ratio']:.1f}x({d['vol_trend']}) | "
                    f"5dk:{d['move_5m']:+.2f}%\n"
                    f"{d.get('chart_str','')}\n"
                )

            msgs = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": (
                    f"PIYASA DURUMU:\n"
                    f"BTC: {btc_trend} ${btc_price:,.0f} ({btc_chg:+.2f}%) | Rejim: {regime}\n"
                    f"Acik pozisyon: {len(positions)}/{MAX_OPEN}\n\n"
                    f"{lessons}\n\n"
                    f"ANALIZ EDILECEK COİNLER:\n{summary}\n\n"
                    f"Deneyimli trader olarak en iyi 1 firsat sec.\n"
                    f"PUMP yakalama odakli dusun:\n"
                    f"- Ani hacim artisi olan coinler\n"
                    f"- Guclu yukselis momentumu\n"
                    f"- EMA yukari, MACD pozitif\n"
                    f"- BTC NEUTRAL olsa bile guclu sinyal varsa AC\n"
                    f"- Az islem acmak yerine PUMP firsatlarini kacirma\n"
                    f"Varsa: JSON {{\"oneri\": true, \"symbol\": \"X/USDT:USDT\", "
                    f"\"yon\": \"LONG\", \"mesaj\": \"neden iyi\"}}\n"
                    f"Sadece gercekten hic yoksa pas gec: {{\"oneri\": false}}"
                )}
            ]

            yanit = gpt(msgs, model="gpt-4o", max_tokens=350)
            if not yanit:
                time.sleep(ONERI_INTERVAL); continue

            try:
                j = re.search(r'\{[^{}]+\}', yanit, re.DOTALL)
                if j:
                    karar = json.loads(j.group())
                    if karar.get("oneri") and karar.get("symbol"):
                        symbol = karar["symbol"]
                        yon    = karar.get("yon", "LONG")
                        mesaj  = karar.get("mesaj", "")
                        sym    = symbol.split("/")[0]
                        # Direkt ac - onay bekleme
                        with msg_lock:
                            pos_messages[symbol] = [{"role": "system", "content": SYSTEM}]
                        acildi = open_pos(symbol, yon, mesaj, btc_trend)
                        if not acildi:
                            log.info(f"[ONERI] {sym} acilamadi")
                    elif not karar.get("oneri"):
                        mesaj = karar.get("mesaj","")
                        if mesaj:
                            log.info(f"[ONERI] Pas: {mesaj[:100]}")
            except Exception as e:
                log.warning(f"[ONERI JSON] {e}")

            time.sleep(ONERI_INTERVAL)

        except Exception as e:
            log.error(f"[ONERI] {e}")
            time.sleep(30)

# HEALTH
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(f"OK|pos:{len(positions)}|pnl:{daily_pnl:+.2f}|gpt:{gpt_calls}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0",8080),H).serve_forever()

# MESAJ HANDLER
@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    if not msg.text: return
    text = msg.text.strip()
    text_lower = text.lower()

    # ONCELIK 1: Komutlar (/ ile baslayanlar)
    if "/durum" in text_lower or "/status" in text_lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "\U0001f4cb Acik pozisyon yok."); return
            lines = ["\U0001f4cb POZİSYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if t:
                    price = t["last"]; entry = pos["entry"]; signal = pos["signal"]
                    pnl = (price-entry)/entry*MARGIN*LEVERAGE if signal=="LONG" else (entry-price)/entry*MARGIN*LEVERAGE
                    pnl_pct = (price-entry)/entry*100 if signal=="LONG" else (entry-price)/entry*100
                    sure = int((time.time()-pos["open_time"])/60)
                    icon = "\U0001f7e2" if pnl>=0 else "\U0001f534"
                    sig_icon = "\U0001f4c8" if signal=="LONG" else "\U0001f4c9"
                    trailing = " | Trailing aktif" if pos.get("trailing_aktif") else ""
                    lines.append(
                        f"{icon} {sig_icon} {sym.split('/')[0]} {signal}\n"
                        f"   {entry:.6f} \u2192 {price:.6f}\n"
                        f"   PnL: {pnl:+.2f}$ ({pnl_pct:+.2f}%) | {sure}dk{trailing}\n"
                        f"   Max kar: %{pos.get('max_pnl',0):.2f}\n"
                    )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    # /istatistik
    if "/istatistik" in text_lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r = supa.table("gpt_trades").select("pnl,signal,sure_dk").execute()
            data = r.data or []
            if not data:
                bot.send_message(msg.chat.id, "Kayit yok."); return
            toplam = len(data)
            kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net    = sum(float(d.get("pnl") or 0) for d in data)
            avg_sure = sum(int(d.get("sure_dk") or 0) for d in data) / max(toplam,1)
            bot.send_message(msg.chat.id,
                f"\U0001f4ca İSTATİSTİK\n\n"
                f"Toplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net PnL: {net:+.2f}$\n"
                f"Gunluk: {daily_pnl:+.2f}$\n"
                f"Ort sure: {avg_sure:.0f}dk\n"
                f"GPT cagri: {gpt_calls}"
            )
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    # KAPAT - anlık
    if "kapat" in text_lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Acik pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            sym_name = symbol.split("/")[0].upper()
            if sym_name in text.upper() or "hepsi" in text_lower or "hepsini" in text_lower:
                close_pos(symbol, "Kullanici kapatma istedı")
                kapatildi = True
        if not kapatildi:
            isimler = [s.split("/")[0] for s in syms]
            bot.send_message(msg.chat.id, f"Hangisini kapatayim? {', '.join(isimler)}")
        return

    # EVET - onay
    if text_lower.startswith("evet") or text_lower == "evet":
        parts = text.split()
        coin_adi = parts[1].upper() if len(parts) > 1 else ""
        if not coin_adi and len(bekleyen) == 1:
            coin_adi = list(bekleyen.keys())[0]
        if coin_adi in bekleyen:
            oneri = bekleyen.pop(coin_adi)
            if time.time() - oneri["zaman"] > 600:
                bot.send_message(msg.chat.id, "Oneri suresi gecti."); return
            with msg_lock:
                pos_messages[oneri["symbol"]] = [{"role": "system", "content": SYSTEM}]
            open_pos(oneri["symbol"], oneri["yon"], oneri["neden"], oneri["btc_trend"])
        elif bekleyen:
            bot.send_message(msg.chat.id, f"Hangi oneri? Bekleyen: {', '.join(bekleyen.keys())}")
        else:
            bot.send_message(msg.chat.id, "Bekleyen oneri yok.")
        return

    # PAS
    if text_lower.startswith("pas") or text_lower == "pas":
        parts = text.split()
        coin_adi = parts[1].upper() if len(parts) > 1 else ""
        if not coin_adi:
            bekleyen.clear()
            bot.send_message(msg.chat.id, "\U0001f44d Tum oneriler pas gecildi.")
        elif coin_adi in bekleyen:
            bekleyen.pop(coin_adi)
            bot.send_message(msg.chat.id, f"\U0001f44d {coin_adi} pas.")
        return

    # DIREKT AC
    ac_keys = ["long ac", "short ac", "long aç", "short aç"]
    if any(k in text_lower for k in ac_keys):
        coin_symbol = find_coin(text)
        if coin_symbol:
            yon = "LONG" if "long" in text_lower else "SHORT"
            btc_trend, _, _, _ = get_market()
            with msg_lock:
                pos_messages[coin_symbol] = [{"role": "system", "content": SYSTEM}]
            open_pos(coin_symbol, yon, "Kullanici istegi", btc_trend)
        else:
            bot.send_message(msg.chat.id, "Coin bulunamadi. Ornek: 'AVAX long ac'")
        return

    # DOGAL DIL - GPT
    bot.send_message(msg.chat.id, "\U0001f914 Bakiyorum...")
    try:
        btc_trend, btc_price, btc_chg, regime = get_market()
        lessons = load_lessons(4)
        current = ""
        with pos_lock:
            if positions:
                for sym, pos in positions.items():
                    t = safe_api(exchange.fetch_ticker, sym)
                    if t:
                        price = t["last"]; entry = pos["entry"]; signal = pos["signal"]
                        pnl = (price-entry)/entry*MARGIN*LEVERAGE if signal=="LONG" else (entry-price)/entry*MARGIN*LEVERAGE
                        sure = int((time.time()-pos["open_time"])/60)
                        current += f"{sym.split('/')[0]} {signal} {pnl:+.2f}$ {sure}dk\n"
            else:
                current = "Acik pozisyon yok"

        coin_str = ""
        coin_symbol = find_coin(text)
        if coin_symbol:
            data = get_coin(coin_symbol)
            if data:
                s = coin_symbol.split("/")[0]
                coin_str = (
                    f"\n{s} VERILER:\n"
                    f"Fiyat:{data['price']:.6f} | RSI:{data['rsi']:.0f} | Momentum:{data['momentum']}/100\n"
                    f"EMA1m:{data['ema_1m']} | EMA5m:{data['ema_5m']} | EMA1h:{data['ema_1h']}\n"
                    f"MACD:{data['macd']}({data['macd_guc']}) | Hacim:{data['vol_ratio']:.1f}x({data['vol_trend']})\n"
                    f"Hareket: 1m={data['move_1m']:+.2f}% 5m={data['move_5m']:+.2f}% 1s={data['move_1h']:+.2f}%\n"
                    f"{data.get('chart_str','')}"
                )

        user_content = (
            f"BTC:{btc_trend} ${btc_price:,.0f} ({btc_chg:+.2f}%) | Rejim:{regime}\n"
            f"Pozisyonlar: {current}\n"
            f"{lessons}\n"
            f"{coin_str}\n\n"
            f"Kullanici: {text}"
        )

        msgs = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content}
        ]

        yanit = gpt(msgs, model="gpt-4o", max_tokens=400)
        if not yanit:
            bot.send_message(msg.chat.id, "GPT cevap vermedi."); return

        bot.send_message(msg.chat.id, f"\U0001f916 {yanit[:800]}")

    except Exception as e:
        log.error(f"[HANDLE] {e}")
        bot.send_message(msg.chat.id, f"\u274c {type(e).__name__}")

# MAIN
import signal as sig_mod, sys

def shutdown(signum, frame):
    log.info("[SHUTDOWN] Kapanıyor...")
    with pos_lock: syms = list(positions.keys())
    for symbol in syms:
        try:
            t = safe_api(exchange.fetch_ticker, symbol)
            close_pos(symbol, "Bot restart", t["last"] if t else None)
        except: pass
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT, shutdown)

if __name__ == "__main__":
    print("SADIK TRADER BASLIYOR...")
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=oneri_loop,    daemon=True).start()
    tg(
        "\U0001f916 SADIK TRADER\n\n"
        "Deneyimli trader gibi davranıyorum!\n"
        "Her islemden ders cikariyorum.\n\n"
        "\u2705 SL %2 otomatik\n"
        "\u2705 Trailing stop (kar %2+)\n"
        "\u2705 Her islemden GPT ders cikariyor\n"
        "\u2705 Gecmis hatalardan ogreniyor\n"
        "\u2705 Piyasa rejimi analizi\n\n"
        "Komutlar:\n"
        "- 'AVAX analiz et'\n"
        "- 'evet' veya 'evet AVAX'\n"
        "- 'pas'\n"
        "- 'AVAX long ac'\n"
        "- 'AVAX kapat' / 'hepsini kapat'\n"
        "- /durum /istatistik"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[POLLING] {e}"); time.sleep(5)
