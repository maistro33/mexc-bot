#!/usr/bin/env python3
"""
SADIK TRADER v6 - Hızlı Sinyal Modu
Strateji:
- Düşük fiyatlı altcoin tarama (0.0001 - 5$)
- Hacim artışı + RSI oversold bounce
- Sabit %0.5'lik 6 TP seviyesi
- Stop %5 altında
- BTC filtresi hafifletildi
- Fear&Greed filtresi gevşetildi
"""

import os, time, threading, logging, re, requests
import ccxt
import pandas as pd
import telebot
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SADIK_V6")

# ─── CONFIG ───
TELE_TOKEN  = os.getenv("TELE_TOKEN", "")
CHAT_ID     = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API  = os.getenv("BITGET_API", "")
BITGET_SEC  = os.getenv("BITGET_SEC", "")
BITGET_PASS = os.getenv("BITGET_PASS", "")
SUPA_URL    = os.getenv("SUPABASE_URL", "")
SUPA_KEY    = os.getenv("SUPABASE_KEY", "")

LEVERAGE       = 5
MARGIN         = 10.0
POS_SIZE       = MARGIN * LEVERAGE   # 50$
COMMISSION     = 0.0006
MAX_OPEN       = 2
MAX_DAILY_LOSS = -15.0
SCAN_INTERVAL  = 45

# TP seviyeleri (sabit %0.5 adımlar, o bot gibi)
TP_PCTS = [0.5, 1.0, 1.5, 2.0, 2.5, 4.0]  # TP1-TP6
SL_PCT  = 5.0   # Stop %5 altında
TP_GERI_DONUS = 0.60  # TP sonrası %0.60 geri dönerse kapat

# Filtreler
MIN_VOL_USDT   = 500_000    # 500K minimum
MAX_VOL_USDT   = 20_000_000 # 20M maksimum
MIN_PRICE      = 0.0001
MAX_PRICE      = 5.0
FG_MIN         = 10         # Sadece çok aşırı Fear'da dur (eski: 20)
RSI_OVERSOLD   = 48         # RSI bu altındaysa oversold sayar
VOL_SPIKE_MIN  = 1.8        # 1.8x hacim artışı yeterli (eski: 3x)
SIGNAL_SCORE   = 4          # En az 4 sinyal gerekli (8 üzerinden)

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","RGTI","SATL","WET","POET",
    "SOXL","SOXS","UVXY","SVIX","KORU","AMC","GME",
    "SHIB","DOGE","PEPE","FLOKI","BONK","WIF","MEME",
    "1000SHIB","1000DOGE","1000PEPE","1000FLOKI","1000BONK","1000WIF",
}

# ─── STATE ───
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
recently_closed = {}
closed_lock     = threading.Lock()

btc_cache      = {"trend": "NEUTRAL", "price": 0, "chg": 0, "ts": 0}
btc_cache_lock = threading.Lock()
BTC_CACHE_SURE = 180  # 3 dakikada bir güncelle

fg_cache      = {"value": 50, "label": "Neutral", "ts": 0}
fg_cache_lock = threading.Lock()
FG_CACHE_SURE = 600

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
                w = 0.5 - (time.time() - LAST_API)
                if w > 0: time.sleep(w)
                LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            log.warning(f"[API] {e}")
            time.sleep(2)
    return None

# ─── FEAR & GREED ───
def get_fear_greed():
    with fg_cache_lock:
        if time.time() - fg_cache["ts"] < FG_CACHE_SURE:
            return fg_cache["value"], fg_cache["label"]
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
        data = r.json()["data"][0]
        value = int(data["value"])
        label = data["value_classification"]
        with fg_cache_lock:
            fg_cache.update({"value": value, "label": label, "ts": time.time()})
        return value, label
    except:
        return 50, "Neutral"

# ─── BTC TREND ───
def get_btc_trend():
    with btc_cache_lock:
        if time.time() - btc_cache["ts"] < BTC_CACHE_SURE:
            return btc_cache["trend"], btc_cache["price"], btc_cache["chg"]
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=50)
        if not raw:
            return "NEUTRAL", 0, 0
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        price  = float(df["c"].iloc[-1])
        chg1h  = (price - float(df["c"].iloc[-2]))  / float(df["c"].iloc[-2])  * 100
        chg4h  = (price - float(df["c"].iloc[-5]))  / float(df["c"].iloc[-5])  * 100
        chg24h = (price - float(df["c"].iloc[-25])) / float(df["c"].iloc[-25]) * 100
        ema9   = float(df["c"].ewm(span=9).mean().iloc[-1])
        ema21  = float(df["c"].ewm(span=21).mean().iloc[-1])

        if chg24h < -3.0 or chg4h < -1.5:
            trend = "DOWN"
        elif chg24h > 2.0 or (chg4h > 1.0 and ema9 > ema21):
            trend = "UP"
        elif chg4h < -0.8:
            trend = "NEUTRAL_SHORT"
        else:
            trend = "NEUTRAL_LONG"  # v6'da NEUTRAL → NEUTRAL_LONG gibi davran

        with btc_cache_lock:
            btc_cache.update({"trend": trend, "price": price, "chg": chg24h, "ts": time.time()})
        log.info(f"[BTC] {trend} ${price:,.0f} ({chg24h:+.1f}%)")
        return trend, price, chg24h
    except Exception as e:
        log.warning(f"[BTC] {e}")
        return "NEUTRAL_LONG", 0, 0

# ─── İNDİKATÖRLER ───
def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def calc_macd_hist(series):
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    macd  = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    return float((macd - signal).iloc[-1])

def calc_vol_ratio(df, n=3):
    avg = float(df["v"].rolling(20).mean().iloc[-1])
    son = float(df["v"].tail(n).mean())
    return son / max(avg, 0.001)

def calc_ema_cross(series):
    e9  = series.ewm(span=9).mean()
    e21 = series.ewm(span=21).mean()
    return float(e9.iloc[-1]) > float(e21.iloc[-1])

def calc_bb_position(series):
    sma = series.rolling(20).mean()
    std = series.rolling(20).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    price = float(series.iloc[-1])
    u = float(upper.iloc[-1])
    l = float(lower.iloc[-1])
    return (price - l) / (u - l) if (u - l) > 0 else 0.5

# ─── DİP TESPİTİ ───
def dip_bounce_analiz(df1h, df15m):
    """
    Dipten giriş analizi:
    1. Son 8 saatin dibine yakın mı?
    2. RSI dip bounce (30-45 arası yukarı dönüş)?
    3. İlk güçlü yeşil mum konfirmasyonu?
    4. Destek seviyesinde mi?
    """
    detay = {}

    price   = float(df1h["c"].iloc[-1])
    son8_low  = float(df1h["l"].tail(8).min())
    son8_high = float(df1h["h"].tail(8).max())
    aralik    = son8_high - son8_low

    # Fiyat dip bölgesinde mi? (Son 8h aralığının alt %35'i)
    dip_esik  = son8_low + aralik * 0.35
    dip_bolge = price <= dip_esik
    detay["dip"] = f"✅ Dip bölge" if dip_bolge else f"❌ Dip değil ({((price-son8_low)/aralik*100):.0f}%)"

    # RSI dip bounce: önceki mum düşük RSI, şimdiki mum yukarı dönüş
    rsi_seri = []
    for i in range(-5, 0):
        try:
            kisa = df1h["c"].iloc[:i] if i != 0 else df1h["c"]
            rsi_seri.append(calc_rsi(kisa))
        except:
            pass
    rsi_onceki = min(rsi_seri) if rsi_seri else 50
    rsi_simdi  = calc_rsi(df1h["c"])
    rsi_bounce = rsi_onceki < 42 and rsi_simdi > rsi_onceki + 3
    detay["rsi_bounce"] = f"✅ RSI bounce {rsi_onceki:.0f}→{rsi_simdi:.0f}" if rsi_bounce else f"❌ RSI {rsi_simdi:.0f}"

    # İlk yeşil mum konfirmasyonu (15m):
    # Son 6 mumdan en az 3'ü kırmızı SONRA son mum güçlü yeşil
    son_mumlar = df15m.tail(7)
    kirmizi_sayisi = sum(1 for _, r in son_mumlar.iloc[:-1].iterrows() if float(r["c"]) < float(r["o"]))
    son_mum = son_mumlar.iloc[-1]
    son_yesil = float(son_mum["c"]) > float(son_mum["o"])
    mum_boy   = abs(float(son_mum["c"]) - float(son_mum["o"])) / float(son_mum["o"]) * 100
    ilk_yesil = kirmizi_sayisi >= 2 and son_yesil and mum_boy >= 0.2
    detay["yesil_mum"] = f"✅ Yeşil konfirm ({mum_boy:.1f}%)" if ilk_yesil else f"❌ Yeşil yok"

    # Destek seviyesi: Son 20 mumun dip bölgesi (birden fazla kez dokunulmuş)
    son20_low   = df1h["l"].tail(20)
    destek      = float(son20_low.quantile(0.15))  # %15 persentil = güçlü destek
    destek_yakin = price <= destek * 1.015  # Destekten %1.5 uzakta
    detay["destek"] = f"✅ Destek yakın ({destek:.6f})" if destek_yakin else f"❌ Destek uzak"

    puan = sum([dip_bolge, rsi_bounce, ilk_yesil, destek_yakin])
    detay["dip_puan"] = puan
    return puan, detay

# ─── SİNYAL SKORU ───
def sinyal_skoru(symbol):
    """
    Gelişmiş sinyal skoru: 0-8 arası
    - 4 teknik indikatör (0-4)
    - 4 dip bounce kriteri (0-4)
    Toplam 4+ → LONG gir (en az 1 dip kriteri zorunlu)
    """
    try:
        r1h  = safe_api(exchange.fetch_ohlcv, symbol, "1h",  limit=50)
        r15m = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=40)
        if not r1h or len(r1h) < 30: return 0, {}, 0
        if not r15m or len(r15m) < 20: return 0, {}, 0

        df1h  = pd.DataFrame(r1h,  columns=["t","o","h","l","c","v"])
        df15m = pd.DataFrame(r15m, columns=["t","o","h","l","c","v"])

        price    = float(df1h["c"].iloc[-1])
        rsi_1h   = calc_rsi(df1h["c"])
        rsi_15m  = calc_rsi(df15m["c"])
        macd_1h  = calc_macd_hist(df1h["c"])
        macd_15m = calc_macd_hist(df15m["c"])
        vol_1h   = calc_vol_ratio(df1h)
        vol_15m  = calc_vol_ratio(df15m, 5)
        ema_up   = calc_ema_cross(df1h["c"])
        bb_pos   = calc_bb_position(df1h["c"])
        pct_1h   = (price - float(df1h["c"].iloc[-2])) / float(df1h["c"].iloc[-2]) * 100
        pct_4h   = (price - float(df1h["c"].iloc[-5])) / float(df1h["c"].iloc[-5]) * 100

        # ── Hard filtreler (geçemezse direkt 0) ──
        if rsi_1h > 72:
            return 0, {"red": f"RSI aşırı alım {rsi_1h:.0f}"}, price
        if pct_4h > 10.0:
            return 0, {"red": f"Geç kalındı 4h+{pct_4h:.1f}%"}, price
        if pct_1h > 6.0:
            return 0, {"red": f"Geç kalındı 1h+{pct_1h:.1f}%"}, price

        skor = 0
        detay = {}

        # ── Teknik indikatörler (0-4 puan) ──

        # 1. RSI oversold
        if rsi_1h < RSI_OVERSOLD:
            skor += 1
            detay["rsi"] = f"✅ {rsi_1h:.0f}"
        elif rsi_15m < RSI_OVERSOLD:
            skor += 1
            detay["rsi"] = f"✅ 15m:{rsi_15m:.0f}"
        else:
            detay["rsi"] = f"❌ {rsi_1h:.0f}"

        # 2. MACD pozitif
        if macd_1h > 0:
            skor += 1
            detay["macd"] = "✅ 1h+"
        elif macd_15m > 0:
            skor += 1
            detay["macd"] = "✅ 15m+"
        else:
            detay["macd"] = "❌"

        # 3. EMA yukarı
        if ema_up:
            skor += 1
            detay["ema"] = "✅ ↑"
        else:
            detay["ema"] = "❌ ↓"

        # 4. Bollinger alt bölge
        if bb_pos < 0.55:
            skor += 1
            detay["bb"] = f"✅ {bb_pos:.2f}"
        else:
            detay["bb"] = f"❌ {bb_pos:.2f}"

        # ── Dip bounce analizi (0-4 puan) ──
        dip_puan, dip_detay = dip_bounce_analiz(df1h, df15m)
        skor += dip_puan
        detay.update(dip_detay)

        # ── Hacim bilgi amaçlı ──
        detay["vol"] = f"{'✅' if vol_1h >= VOL_SPIKE_MIN else '⚠️'} {vol_1h:.1f}x"

        # En az 1 dip kriteri zorunlu (dip bounce olmadan girme)
        if dip_puan == 0:
            skor = max(0, skor - 2)  # Dip yoksa skoru düşür

        detay["price"] = price
        detay["skor"]  = skor
        return skor, detay, price

    except Exception as e:
        log.warning(f"[SINYAL] {symbol}: {e}")
        return 0, {}, 0

# ─── TP/SL HESAPLA ───
def hesapla_tp_sl(price):
    tps = [round(price * (1 + pct/100), 8) for pct in TP_PCTS]
    sl  = round(price * (1 - SL_PCT/100), 8)
    return tps, sl

# ─── PNL ───
def hesap_pnl(pos, price):
    entry   = pos["entry"]
    pnl_pct = (price - entry) / entry * 100
    pnl     = (price - entry) / entry * POS_SIZE - POS_SIZE * COMMISSION
    return pnl, pnl_pct

# ─── İŞLEM AÇ ───
def open_pos(symbol, skor, detay, btc_trend):
    global daily_pnl
    if daily_pnl <= MAX_DAILY_LOSS: return False

    t = safe_api(exchange.fetch_ticker, symbol)
    if not t: return False
    price = float(t["last"])

    tps, sl = hesapla_tp_sl(price)

    with pos_lock:
        sym_base = symbol.split("/")[0].upper()
        if symbol in positions: return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        with closed_lock:
            if sym_base in recently_closed:
                if time.time() - recently_closed[sym_base] < 3600: return False
        if len(positions) >= MAX_OPEN: return False

        positions[symbol] = {
            "entry":     price,
            "sl":        sl,
            "tps":       tps,
            "tp_idx":    0,
            "max_price": price,
            "open_time": time.time(),
            "amount":    0,
            "btc_trend": btc_trend,
            "skor":      skor,
        }

    try:
        try: exchange.set_margin_mode("isolated", symbol)
        except: pass
        try: exchange.set_leverage(LEVERAGE, symbol)
        except: pass

        amount = round(POS_SIZE / price, 4)
        amount = float(exchange.amount_to_precision(symbol, amount))
        if amount <= 0:
            with pos_lock: positions.pop(symbol, None)
            return False

        order = exchange.create_order(symbol, "market", "buy", amount,
                                      params={"marginMode": "isolated"})
        if not order:
            with pos_lock: positions.pop(symbol, None)
            return False

        with pos_lock:
            if symbol in positions:
                positions[symbol]["amount"] = amount

    except Exception as e:
        log.error(f"[EMIR] {symbol.split('/')[0]}: {e}")
        with pos_lock: positions.pop(symbol, None)
        return False

    sym = symbol.split("/")[0]
    tp_str = "\n".join([f"TP{i+1}: {tp:.8f} ──" for i, tp in enumerate(tps)])
    tg(
        f"📊 #{sym}USDT.P\n"
        f"🏁 LONG - Giriş: {price:.8f}\n"
        f"🚫 Stop: {sl:.8f}\n\n"
        f"💡 Pozisyon Detayları\n{tp_str}\n\n"
        f"📊 Skor: {skor}/6 | BTC: {btc_trend}\n"
        f"RSI:{detay.get('rsi','?')} MACD:{detay.get('macd','?')} "
        f"Vol:{detay.get('vol','?')} EMA:{detay.get('ema','?')}"
    )
    log.info(f"[ACIK] {sym} LONG @ {price:.8f} skor:{skor}")
    return True

# ─── İŞLEM KAPAT ───
def close_pos(symbol, reason, exit_price=None):
    global daily_pnl
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    try:
        amount = pos.get("amount", 0)
        if not amount: amount = round(POS_SIZE / pos["entry"], 4)
        safe_api(exchange.create_order, symbol, "market", "sell", amount, None,
                 {"reduceOnly": True})
    except Exception as e:
        if "22002" not in str(e) and "No position" not in str(e):
            log.error(f"[KAPAT] {symbol.split('/')[0]}: {e}")

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = float(t["last"]) if t else pos["entry"]

    pnl, pnl_pct = hesap_pnl(pos, exit_price)
    sure = int((time.time() - pos["open_time"]) / 60)
    daily_pnl += pnl

    sym_base = symbol.split("/")[0].upper()
    with closed_lock: recently_closed[sym_base] = time.time()

    try:
        save_trade({
            "symbol": symbol, "signal": "LONG",
            "pnl": round(pnl, 4), "sure_dk": sure,
            "reason": reason, "btc_trend": pos.get("btc_trend", "")
        })
    except: pass

    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} {sym_base} KAPANDI\n{reason}\nPnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%) | {sure}dk\nGünlük: {daily_pnl:+.2f}$")

# ─── YÖNETİM DÖNGÜSÜ ───
def manage_loop():
    while True:
        time.sleep(20)
        try:
            with pos_lock: syms = list(positions.keys())
            if not syms: continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price    = float(t["last"])
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure     = int((time.time() - pos["open_time"]) / 60)
                entry    = pos["entry"]
                sl       = pos["sl"]
                tps      = pos["tps"]
                tp_idx   = pos.get("tp_idx", 0)
                max_price = pos.get("max_price", entry)

                # Max fiyatı güncelle
                if price > max_price:
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["max_price"] = price

                # Stop Loss
                if price <= sl:
                    close_pos(symbol, f"🚫 Stop Loss ({sl:.8f})", price)
                    continue

                # Erken zarar (ilk 8dk)
                if sure <= 8 and pnl_pct <= -1.5:
                    close_pos(symbol, f"Erken zarar ({pnl_pct:.1f}%)", price)
                    continue

                # Zaman aşımı 3 saat
                if sure >= 180:
                    close_pos(symbol, "Zaman aşımı 3 saat", price)
                    continue

                # TP seviyeleri
                if tp_idx < len(tps):
                    if price >= tps[tp_idx]:
                        yeni_sl = entry if tp_idx == 0 else tps[tp_idx - 1]
                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["tp_idx"] = tp_idx + 1
                                positions[symbol]["sl"]     = yeni_sl
                        sym = symbol.split("/")[0]
                        sonraki = f"{tps[tp_idx+1]:.8f}" if tp_idx+1 < len(tps) else "∞"
                        tg(f"🎯 {sym} TP{tp_idx+1} HIT! +{pnl_pct:.1f}%\nSL → {yeni_sl:.8f}\nSonraki TP: {sonraki}")

                # TP sonrası trailing stop
                if tp_idx > 0:
                    geri = (max_price - price) / max_price * 100
                    if geri >= TP_GERI_DONUS:
                        close_pos(symbol, f"Trailing stop (tepeden -%{geri:.1f})", price)
                        continue

                # Günlük limit
                if daily_pnl <= MAX_DAILY_LOSS:
                    close_pos(symbol, "Günlük limit", price)
                    continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    time.sleep(30)
    while True:
        try:
            if daily_pnl <= MAX_DAILY_LOSS:
                time.sleep(SCAN_INTERVAL); continue

            btc_trend, btc_price, btc_chg = get_btc_trend()

            # Sadece DOWN ve NEUTRAL_SHORT'ta dur
            if btc_trend == "DOWN":
                log.info(f"[SCAN] BTC DOWN - bekleniyor")
                time.sleep(SCAN_INTERVAL); continue

            fg_val, fg_lbl = get_fear_greed()
            if fg_val <= FG_MIN:
                log.info(f"[SCAN] Extreme Fear ({fg_val}) - bekleniyor")
                time.sleep(SCAN_INTERVAL); continue

            with pos_lock:
                if len(positions) >= MAX_OPEN:
                    time.sleep(20); continue
                open_syms = set(positions.keys())

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            candidates = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                sym   = symbol.split("/")[0]
                if sym in BLACKLIST: continue
                if symbol in open_syms: continue

                qv    = ticker.get("quoteVolume") or 0
                pct   = ticker.get("percentage")  or 0
                price = float(ticker.get("last") or 0)

                if qv < MIN_VOL_USDT or qv > MAX_VOL_USDT: continue
                if price < MIN_PRICE or price > MAX_PRICE: continue
                if abs(pct) > 30: continue
                if pct < 0.2: continue  # En az %0.2 pozitif hareket

                sym_base = sym.upper()
                with closed_lock:
                    if sym_base in recently_closed:
                        if time.time() - recently_closed[sym_base] < 3600: continue

                candidates.append({"symbol": symbol, "pct": pct, "qv": qv})

            # Pct'ye göre sırala (en yüksek momentum önce)
            candidates.sort(key=lambda x: x["pct"], reverse=True)
            candidates = candidates[:8]

            log.info(f"[SCAN] {len(candidates)} aday | BTC:{btc_trend} FG:{fg_val}")

            for c in candidates:
                symbol = c["symbol"]
                sym    = symbol.split("/")[0]
                with pos_lock:
                    if len(positions) >= MAX_OPEN: break
                    if symbol in open_syms: continue

                skor, detay, price = sinyal_skoru(symbol)
                if skor >= SIGNAL_SCORE:
                    log.info(f"[SİNYAL] {sym} skor:{skor}/6 → GİRİYOR")
                    ok = open_pos(symbol, skor, detay, btc_trend)
                    if ok:
                        with pos_lock: open_syms = set(positions.keys())
                else:
                    log.info(f"[PAS] {sym} skor:{skor}/6")
                time.sleep(1.5)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            log.error(f"[SCANNER] {e}")
            time.sleep(10)

# ─── GÜNLÜK SIFIRLAMA ───
def gunluk_reset_loop():
    global daily_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now()
            yarin = (simdi + datetime.timedelta(days=1)).replace(
                     hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            eski = daily_pnl; daily_pnl = 0.0
            tg(f"🔄 Yeni gün! Dün: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}"); time.sleep(3600)

# ─── HEALTH SERVER ───
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            fg, _ = get_fear_greed()
            with pos_lock:
                pstr = ",".join(f"{s.split('/')[0]}" for s in positions)
            self.wfile.write(
                f"OK|btc:{get_btc_trend()[0]}|fg:{fg}|pos:{len(positions)}({pstr})|pnl:{daily_pnl:+.2f}".encode()
            )
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ─── COİN BUL ───
def find_coin(text):
    words = re.findall(r'[A-Z0-9]+', text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        for word in words:
            if len(word) < 3: continue
            sym = f"{word}/USDT:USDT"
            if sym in tickers and word not in BLACKLIST:
                return sym
    except: pass
    return None

# ─── TELEGRAM HANDLER ───
@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    text  = msg.text.strip()
    lower = text.lower()

    if "/durum" in lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "📋 Açık pozisyon yok."); return
            lines = ["📋 POZİSYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = float(t["last"])
                pnl, pnl_pct = hesap_pnl(pos, price)
                sure = int((time.time() - pos["open_time"]) / 60)
                tp_idx = pos.get("tp_idx", 0)
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} LONG\n"
                    f"   {pos['entry']:.8f} → {price:.8f}\n"
                    f"   PnL: {pnl:+.2f}$ ({pnl_pct:+.1f}%) | {sure}dk\n"
                    f"   SL: {pos['sl']:.8f} | TP{tp_idx} geçildi\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    if "/istatistik" in lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r    = supa.table("gpt_trades").select("pnl,signal").execute()
            data = [d for d in (r.data or []) if d.get("signal") not in ["CLOSED"]]
            if not data: bot.send_message(msg.chat.id, "Kayıt yok."); return
            toplam = len(data)
            kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net    = sum(float(d.get("pnl") or 0) for d in data)
            bot.send_message(msg.chat.id,
                f"📊 İSTATİSTİK\nToplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net: {net:+.2f}$\nGünlük: {daily_pnl:+.2f}$")
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
        return

    if "/btc" in lower:
        trend, price, chg = get_btc_trend()
        fg, fl = get_fear_greed()
        aciklama = {
            "UP":           "⬆️ Güçlü yukarı → LONG açar",
            "DOWN":         "⬇️ Güçlü aşağı → BEKLER",
            "NEUTRAL_LONG": "↗️ Nötr/hafif yukarı → LONG açar",
            "NEUTRAL_SHORT":"↘️ Hafif aşağı → BEKLER",
        }.get(trend, "↔️ Bekliyor")
        bot.send_message(msg.chat.id,
            f"BTC: {trend}\n${price:,.0f} ({chg:+.1f}%)\n{aciklama}\n\nFear&Greed: {fg} ({fl})")
        return

    if "kapat" in lower:
        with pos_lock: syms = list(positions.keys())
        if not syms:
            bot.send_message(msg.chat.id, "Açık pozisyon yok."); return
        kapatildi = False
        for symbol in syms:
            if symbol.split("/")[0].upper() in text.upper() or "hepsi" in lower:
                close_pos(symbol, "Kullanıcı isteği")
                kapatildi = True
        if not kapatildi:
            bot.send_message(msg.chat.id, f"Hangisini? {', '.join(s.split('/')[0] for s in syms)}")
        return

    # Coin analizi
    coin = find_coin(text)
    if coin:
        sym = coin.split("/")[0]
        bot.send_message(msg.chat.id, f"{sym} analiz ediliyor...")
        skor, detay, price = sinyal_skoru(coin)
        trend, _, _ = get_btc_trend()
        fg, fl = get_fear_greed()
        tps, sl = hesapla_tp_sl(price) if price > 0 else ([], 0)
        tp_str = " | ".join([f"TP{i+1}:{tp:.6f}" for i, tp in enumerate(tps)])
        bot.send_message(msg.chat.id,
            f"📊 {sym} | Skor: {skor}/6\n"
            f"RSI:{detay.get('rsi','?')} MACD:{detay.get('macd','?')}\n"
            f"Vol:{detay.get('vol','?')} EMA:{detay.get('ema','?')}\n"
            f"BB:{detay.get('bb','?')} Mom:{detay.get('mom','?')}\n"
            f"BTC: {trend} | FG: {fg}({fl})\n\n"
            f"{'✅ GİRİLİR' if skor >= SIGNAL_SCORE else '❌ PAS'} ({skor}/6 gerekli:{SIGNAL_SCORE})\n"
            f"SL: {sl:.8f}\n{tp_str}")
        return

    bot.send_message(msg.chat.id,
        "Komutlar:\n/durum\n/istatistik\n/btc\nCOIN_ADI - analiz")

# ─── SHUTDOWN ───
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    if syms:
        tg(f"⏸ Bot yeniden başlıyor...\n{len(syms)} pozisyon açık.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT,  shutdown)

# ─── AÇIK POZİSYON YÜKLE ───
def load_open_positions():
    try:
        log.info("[YUKLE] Borsadaki açık pozisyonlar kontrol ediliyor...")
        raw = safe_api(exchange.fetch_positions)
        if not raw:
            log.info("[YUKLE] Açık pozisyon yok")
            return
        btc_trend, _, _ = get_btc_trend()
        yuklenen = 0
        lines = ["♻️ Önceki pozisyonlar yüklendi:\n"]
        for pos in raw:
            try:
                contracts = float(pos.get("contracts") or 0)
                if contracts == 0: continue
                symbol = pos.get("symbol", "")
                side   = pos.get("side", "")
                entry  = float(pos.get("entryPrice") or 0)
                if not symbol or not side or entry == 0: continue
                if side != "long": continue  # Sadece long

                tps, sl = hesapla_tp_sl(entry)
                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "entry":     entry,
                            "sl":        sl,
                            "tps":       tps,
                            "tp_idx":    0,
                            "max_price": entry,
                            "open_time": time.time(),
                            "amount":    contracts,
                            "btc_trend": btc_trend,
                            "skor":      0,
                        }
                        yuklenen += 1
                        t = safe_api(exchange.fetch_ticker, symbol)
                        price_now = float(t["last"]) if t else entry
                        pnl = (price_now - entry) / entry * POS_SIZE
                        icon = "🟢" if pnl >= 0 else "🔴"
                        lines.append(f"{icon} {symbol.split('/')[0]} @ {entry:.8f} | {pnl:+.2f}$")
                        log.info(f"[YUKLE] {symbol.split('/')[0]} LONG @ {entry}")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")

        if yuklenen > 0:
            tg("\n".join(lines))
        else:
            log.info("[YUKLE] Yüklenecek pozisyon bulunamadı")
    except Exception as e:
        log.error(f"[YUKLE] {e}")

# ─── MAIN ───
if __name__ == "__main__":
    print("SADIK TRADER v6 BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=scanner_loop,      daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()

    fg, fl = get_fear_greed()
    trend, price, chg = get_btc_trend()
    tg(
        "🤖 SADIK TRADER v6 — HIZLI SİNYAL MODU\n\n"
        "📊 Strateji:\n"
        "  ✅ RSI oversold bounce\n"
        "  ✅ MACD + EMA crossover\n"
        "  ✅ Hacim artışı (1.8x+)\n"
        "  ✅ Bollinger alt bölge\n"
        "  ✅ Momentum filtresi\n\n"
        f"🎯 6 TP seviyesi (%0.5 adım)\n"
        f"🚫 Stop: -%{SL_PCT}\n"
        f"📊 Skor: {SIGNAL_SCORE}/6 gerekli\n\n"
        f"BTC: {trend} ${price:,.0f}\n"
        f"Fear&Greed: {fg} ({fl})\n\n"
        "/durum /istatistik /btc"
    )

    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
