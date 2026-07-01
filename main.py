#!/usr/bin/env python3
"""
SADIK SCALP v3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sinyal Kaynakları:
  1. CoinSonar V2 — Telegram kanalı (Telethon ile dinlenir)
  2. FuturesKripto — Telegram kanalı (Telethon ile dinlenir)
  3. Manuel — Sen bota yazarsın

Giriş Filtresi (CoinSonar sinyali için):
  ✅ MA(5) > MA(10) > MA(20) — 15m grafik
  ✅ Hacim MA(5) > MA(10)    — 15m grafik
  ✅ RSI(14) 30-55 arası     — 15m grafik

FuturesKripto sinyali:
  → Direkt giriş fiyatı + SL + TP1-6 kullanılır, filtre yok

TP/SL:
  - CoinSonar/Manuel: 6 TP (sabit yüzde), SL ATR bazlı
  - FuturesKripto: Sinyaldeki değerler birebir
"""

import os, time, threading, logging, re, asyncio
import ccxt
import pandas as pd
import telebot
from supabase import create_client
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SCALP_V3")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN    = os.getenv("TELE_TOKEN", "")
CHAT_ID       = int(os.getenv("MY_CHAT_ID", "0"))
BITGET_API    = os.getenv("BITGET_API", "")
BITGET_SEC    = os.getenv("BITGET_SEC", "")
BITGET_PASS   = os.getenv("BITGET_PASS", "")
SUPA_URL      = os.getenv("SUPABASE_URL", "")
SUPA_KEY      = os.getenv("SUPABASE_KEY", "")
TG_API_ID     = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH   = os.getenv("TG_API_HASH", "")
TG_SESSION    = os.getenv("TG_SESSION", "")  # Telethon session string

# Dinlenecek kanallar
COINSONAR_KANAL     = "CoinSonarV2"
FUTURESKRIPTO_KANAL = "FuturesKripto"

# İşlem parametreleri
LEVERAGE        = 5
MARGIN          = 15.0
POS_SIZE        = MARGIN * LEVERAGE   # 75$
COMMISSION      = 0.0006
MAX_OPEN_AUTO   = 2
MAX_OPEN_MANUEL = 3
MAX_DAILY_LOSS  = -15.0
MAX_SURE        = 240   # Max 4 saat

# Manuel/CoinSonar TP/SL (sabit yüzde, 75$ pozisyon)
TP_PCTS = [2.1, 3.5, 4.1, 5.1, 6.1, 7.1]
SL_PCT  = 1.5    # -%1.5 varsayılan SL
TRAILING_PCT = 1.0  # TP6 sonrası trailing

# 15m Filtre eşikleri
RSI_MIN = 30
RSI_MAX = 55
MIN_PRICE    = 0.0001
MAX_PRICE    = 100.0
MIN_TURNOVER = 200_000   # Min 200K USDT 24h turnover

# ════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════
positions       = {}
pos_lock        = threading.Lock()
daily_pnl       = 0.0
daily_pnl_lock  = threading.Lock()

# ════════════════════════════════════════════
# TELEGRAM BOT
# ════════════════════════════════════════════
bot = telebot.TeleBot(TELE_TOKEN)

def tg(msg):
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")

# ════════════════════════════════════════════
# SUPABASE
# ════════════════════════════════════════════
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        log.info("[SUPA] Bağlandı")
    except Exception as e:
        log.error(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try:
        supa.table("gpt_trades").insert(data).execute()
    except Exception as e:
        log.error(f"[SAVE] {e}")

# ════════════════════════════════════════════
# EXCHANGE
# ════════════════════════════════════════════
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})

_last_api = 0
_api_lock = threading.Lock()

def safe_api(func, *args, **kwargs):
    global _last_api
    for attempt in range(4):
        try:
            with _api_lock:
                wait = 0.5 - (time.time() - _last_api)
                if wait > 0: time.sleep(wait)
                _last_api = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except ccxt.NetworkError as e:
            log.warning(f"[API] Network: {e}"); time.sleep(3)
        except Exception as e:
            log.warning(f"[API] {attempt+1}: {e}"); time.sleep(2)
    return None

# ════════════════════════════════════════════
# PNL
# ════════════════════════════════════════════
def günlük_limit_asıldı():
    with daily_pnl_lock:
        return daily_pnl <= MAX_DAILY_LOSS

def pnl_ekle(miktar):
    global daily_pnl
    with daily_pnl_lock:
        daily_pnl += miktar
        return daily_pnl

def hesap_pnl(pos, price):
    entry  = pos["entry"]
    amount = pos.get("amount", POS_SIZE / max(entry, 0.000001))
    pnl    = (price - entry) * amount - POS_SIZE * COMMISSION
    pct    = (price - entry) / entry * 100
    return pnl, pct

# ════════════════════════════════════════════
# İNDİKATÖRLER
# ════════════════════════════════════════════
def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, 0.001)
    return float((100 - 100 / (1 + rs)).iloc[-1])

def calc_atr(df, period=14):
    h, l, c = df["h"], df["l"], df["c"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

# ════════════════════════════════════════════
# 15M FİLTRE (MA + Hacim + RSI)
# ════════════════════════════════════════════
def filtre_15m(symbol):
    """
    15 dakikalık grafik kontrolü:
    1. MA(5) > MA(10) > MA(20) — fiyat trendi
    2. Hacim MA(5) > MA(10)    — hacim artıyor
    3. RSI(14) 30-55 arası     — aşırı alım/satımda değil
    Döner: (gecti: bool, detay: dict)
    """
    try:
        r = safe_api(exchange.fetch_ohlcv, symbol, "15m", limit=25)
        if not r or len(r) < 20:
            return False, {"red": "Veri yetersiz"}

        df = pd.DataFrame(r, columns=["t","o","h","l","c","v"])

        ma5  = float(df["c"].rolling(5).mean().iloc[-1])
        ma10 = float(df["c"].rolling(10).mean().iloc[-1])
        ma20 = float(df["c"].rolling(20).mean().iloc[-1])

        vol_ma5  = float(df["v"].rolling(5).mean().iloc[-1])
        vol_ma10 = float(df["v"].rolling(10).mean().iloc[-1])

        rsi = calc_rsi(df["c"])

        ma_ok  = ma5 > ma10 > ma20
        vol_ok = vol_ma5 > vol_ma10
        rsi_ok = RSI_MIN <= rsi <= RSI_MAX

        gecti = ma_ok and vol_ok and rsi_ok

        detay = {
            "ma5":      round(ma5, 8),
            "ma10":     round(ma10, 8),
            "ma20":     round(ma20, 8),
            "vol_ma5":  round(vol_ma5, 0),
            "vol_ma10": round(vol_ma10, 0),
            "rsi":      round(rsi, 1),
            "ma_ok":    ma_ok,
            "vol_ok":   vol_ok,
            "rsi_ok":   rsi_ok,
        }
        return gecti, detay

    except Exception as e:
        log.warning(f"[FİLTRE] {symbol}: {e}")
        return False, {"red": str(e)}

# ════════════════════════════════════════════
# BORSA YARDIMCILARI
# ════════════════════════════════════════════
def borsa_hazirla(symbol):
    try: exchange.set_margin_mode("isolated", symbol, params={"marginCoin": "USDT"})
    except: pass
    try: exchange.set_leverage(LEVERAGE, symbol, params={"marginCoin": "USDT"})
    except: pass

def limit_emir_ac(symbol, fiyat, amount, bekle_sn=300):
    try:
        fiyat_p = float(exchange.price_to_precision(symbol, fiyat))
        order = safe_api(
            exchange.create_order, symbol, "limit", "buy", amount, fiyat_p,
            {"marginMode": "isolated", "marginCoin": "USDT", "timeInForce": "GTC"}
        )
        if not order: return None

        order_id = order.get("id")
        for _ in range(bekle_sn // 3):
            time.sleep(3)
            durum = safe_api(exchange.fetch_order, order_id, symbol)
            if durum and durum.get("status") == "closed":
                return float(durum.get("average") or fiyat_p)

        try: safe_api(exchange.cancel_order, order_id, symbol)
        except: pass
        return None

    except Exception as e:
        log.error(f"[LİMİT] {symbol}: {e}")
        return None

def pozisyon_slot_al(symbol, entry, sl, tps, kaynak, mod="auto"):
    sym_base = symbol.split("/")[0].upper()
    max_open = MAX_OPEN_AUTO if mod == "auto" else MAX_OPEN_MANUEL

    with pos_lock:
        if symbol in positions: return False
        for ex in positions:
            if ex.split("/")[0].upper() == sym_base: return False
        if len(positions) >= max_open: return False
        if günlük_limit_asıldı(): return False

        positions[symbol] = {
            "entry":     entry,
            "sl":        sl,
            "tps":       tps,
            "tp_idx":    0,
            "max_price": entry,
            "open_time": time.time(),
            "amount":    0,
            "kaynak":    kaynak,
            "mod":       mod,
            "pending":   True,
        }
        return True

# ════════════════════════════════════════════
# İŞLEM AÇ — CoinSonar / Manuel
# ════════════════════════════════════════════
def open_pos_auto(symbol, kaynak="coinsonar", bekle_sn=180):
    """CoinSonar sinyali veya 'long aç' komutu için."""
    sym = symbol.split("/")[0]

    t0 = safe_api(exchange.fetch_ticker, symbol)
    if not t0: return False, "Fiyat alınamadı"
    price = float(t0["last"])

    try:
        r1h = safe_api(exchange.fetch_ohlcv, symbol, "1h", limit=15)
        df1h = pd.DataFrame(r1h, columns=["t","o","h","l","c","v"])
        atr = calc_atr(df1h)
        sl_pct = max(1.0, min(atr / price * 100 * 1.2, 3.0))
    except:
        sl_pct = SL_PCT

    sl  = round(price * (1 - sl_pct / 100), 8)
    tps = [round(price * (1 + pct / 100), 8) for pct in TP_PCTS]

    if not pozisyon_slot_al(symbol, price, sl, tps, kaynak, "auto"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / price, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            tg(f"📡 {sym} [{kaynak}] limit emir açılıyor @ {price:.8f}\n{bekle_sn}sn bekleniyor...")

            limit_p = round(price * (1 - 0.1 / 100), 8)
            gercek  = limit_emir_ac(symbol, limit_p, amount, bekle_sn)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı, iptal.")
                return

            sl_g  = round(gercek * (1 - sl_pct / 100), 8)
            tps_g = [round(gercek * (1 + pct / 100), 8) for pct in TP_PCTS]

            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({
                        "entry":   gercek,
                        "sl":      sl_g,
                        "tps":     tps_g,
                        "amount":  amount,
                        "pending": False,
                    })

            tp_str = "\n".join([f"TP{i+1}: {tp:.8f} (+%{TP_PCTS[i]})" for i, tp in enumerate(tps_g)])
            tg(
                f"⚡ #{sym}USDT.P LONG\n"
                f"📡 Kaynak: {kaynak.upper()}\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_g:.8f} (-%{sl_pct:.1f})\n\n"
                f"{tp_str}\n\n"
                f"💰 Pozisyon: {POS_SIZE}$ | Kaldıraç: {LEVERAGE}x"
            )
            log.info(f"[AÇIK] {sym} @ {gercek:.8f} [{kaynak}]")

        except Exception as e:
            log.error(f"[OPEN_AUTO] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM AÇ — FuturesKripto Sinyali
# ════════════════════════════════════════════
def open_pos_futureskripto(symbol, giris, sl, tps):
    """FuturesKripto sinyalindeki fiyatları birebir kullanır."""
    sym = symbol.split("/")[0]

    if not pozisyon_slot_al(symbol, giris, sl, tps, "futureskripto", "manuel"):
        return False, "Slot alınamadı"

    def _ac():
        try:
            borsa_hazirla(symbol)
            amount = float(exchange.amount_to_precision(symbol, round(POS_SIZE / giris, 4)))
            if amount <= 0:
                with pos_lock: positions.pop(symbol, None)
                return

            tg(f"📡 {sym} [FuturesKripto] limit emir @ {giris:.8f}\n5 dakika bekleniyor...")

            gercek = limit_emir_ac(symbol, giris, amount, bekle_sn=300)

            if not gercek:
                with pos_lock: positions.pop(symbol, None)
                tg(f"⏰ {sym} limit dolmadı (5dk), iptal.")
                return

            if sl > 0 and sl < gercek * 0.990:
                sl_gercek = sl
            else:
                sl_gercek = round(gercek * (1 - SL_PCT / 100), 8)

            if tps:
                tp_oran  = [(tp - giris) / giris for tp in tps]
                tps_gercek = [round(gercek * (1 + r), 8) for r in tp_oran]
            else:
                tps_gercek = [round(gercek * (1 + pct / 100), 8) for pct in TP_PCTS]

            with pos_lock:
                if symbol in positions:
                    positions[symbol].update({
                        "entry":   gercek,
                        "sl":      sl_gercek,
                        "tps":     tps_gercek,
                        "amount":  amount,
                        "pending": False,
                    })

            sl_pct = (gercek - sl_gercek) / gercek * 100
            tp_str = "\n".join([f"TP{i+1}: {tp:.8f} ──" for i, tp in enumerate(tps_gercek)])
            tg(
                f"✅ #{sym}USDT.P LONG\n"
                f"📡 Kaynak: FUTURESKRIPTO\n"
                f"🏁 Giriş: {gercek:.8f}\n"
                f"🚫 SL: {sl_gercek:.8f} (-%{sl_pct:.1f})\n\n"
                f"{tp_str}\n\n"
                f"💰 Pozisyon: {POS_SIZE}$ | Kaldıraç: {LEVERAGE}x"
            )
            log.info(f"[AÇIK] {sym} @ {gercek:.8f} [futureskripto]")

        except Exception as e:
            log.error(f"[FK_OPEN] {sym}: {e}")
            with pos_lock: positions.pop(symbol, None)

    threading.Thread(target=_ac, daemon=True).start()
    return True, "OK"

# ════════════════════════════════════════════
# İŞLEM KAPAT
# ════════════════════════════════════════════
def close_pos(symbol, reason, exit_price=None):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    sym    = symbol.split("/")[0]
    amount = pos.get("amount", 0)
    if not amount or amount <= 0:
        amount = round(POS_SIZE / pos["entry"], 4)

    try:
        pos_list = safe_api(exchange.fetch_positions, [symbol])
        if pos_list:
            for p in pos_list:
                c = float(p.get("contracts") or 0)
                if c > 0 and p.get("side") == "long":
                    amount = c; break
    except: pass

    try:
        safe_api(
            exchange.create_order, symbol, "market", "sell", amount, None,
            {"reduceOnly": True, "marginCoin": "USDT"}
        )
    except Exception as e:
        if "22002" not in str(e) and "No position" not in str(e):
            log.error(f"[KAPAT] {sym}: {e}")

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = float(t["last"]) if t else pos["entry"]

    pnl, pct = hesap_pnl(pos, exit_price)
    sure      = int((time.time() - pos["open_time"]) / 60)
    toplam    = pnl_ekle(pnl)
    kaynak    = pos.get("kaynak", "?")

    try:
        save_trade({
            "symbol": symbol, "signal": "LONG",
            "pnl": round(pnl, 4), "sure_dk": sure,
            "reason": reason, "kaynak": kaynak,
        })
    except: pass

    if toplam <= MAX_DAILY_LOSS:
        tg(f"⛔ GÜNLÜK LİMİT! {toplam:+.2f}$")

    icon = "🟢" if pnl >= 0 else "🔴"
    tg(
        f"{icon} {sym.upper()} KAPANDI\n"
        f"{reason}\n"
        f"PnL: {pnl:+.2f}$ ({pct:+.1f}%) | {sure}dk\n"
        f"📡 {kaynak.upper()} | Günlük: {toplam:+.2f}$"
    )

# ════════════════════════════════════════════
# YÖNETİM DÖNGÜSÜ
# ════════════════════════════════════════════
def manage_loop():
    while True:
        time.sleep(3)
        try:
            with pos_lock:
                syms = list(positions.keys())
            if not syms: continue

            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos or pos.get("pending"): continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue

                price        = float(t["last"])
                pnl, pct     = hesap_pnl(pos, price)
                sure         = int((time.time() - pos["open_time"]) / 60)
                entry        = pos["entry"]
                sl           = pos["sl"]
                tps          = pos["tps"]
                tp_idx       = pos.get("tp_idx", 0)
                max_price    = pos.get("max_price", entry)
                mod          = pos.get("mod", "auto")

                if price > max_price:
                    with pos_lock:
                        if symbol in positions:
                            positions[symbol]["max_price"] = price
                    max_price = price

                if price <= sl:
                    close_pos(symbol, f"🚫 SL ({sl:.8f})", price)
                    continue

                if sure >= MAX_SURE:
                    close_pos(symbol, f"⏰ Süre doldu ({MAX_SURE}dk)", price)
                    continue

                if günlük_limit_asıldı():
                    close_pos(symbol, "Günlük limit", price)
                    continue

                if tp_idx < len(tps) and price >= tps[tp_idx]:
                    sym = symbol.split("/")[0]

                    if mod == "auto" and tp_idx == 0:
                        close_pos(symbol, f"🎯 TP1 +{pct:.1f}%", price)
                        continue
                    else:
                        # Her TP sonrası SL → başabaş (giriş fiyatının %0.2 üstü)
                        # (önceki TP'ye çekme yerine, daha geniş nefes payı bırakır)
                        try:
                            pos_list = safe_api(exchange.fetch_positions, [symbol])
                            gercek_giris = entry
                            if pos_list:
                                for p in pos_list:
                                    if float(p.get("contracts") or 0) > 0 and p.get("side") == "long":
                                        gercek_giris = float(p.get("entryPrice") or entry)
                                        break
                        except:
                            gercek_giris = entry
                        yeni_sl = round(gercek_giris * 1.002, 8)

                        with pos_lock:
                            if symbol in positions:
                                positions[symbol]["tp_idx"] = tp_idx + 1
                                positions[symbol]["sl"]     = yeni_sl

                        sonraki = f"{tps[tp_idx+1]:.8f}" if tp_idx + 1 < len(tps) else "∞"
                        tg(
                            f"🎯 {sym} TP{tp_idx+1}! +{pct:.1f}%\n"
                            f"SL → {yeni_sl:.8f}\n"
                            f"Sonraki: {sonraki}"
                        )
                        tp_idx += 1

                if tp_idx >= len(tps):
                    geri = (max_price - price) / max_price * 100
                    if geri >= TRAILING_PCT:
                        close_pos(symbol, f"Trailing -%{geri:.1f}", price)
                        continue

        except Exception as e:
            log.error(f"[MANAGE] {e}")

# ════════════════════════════════════════════
# SİNYAL PARSE
# ════════════════════════════════════════════
def sinyal_parse(text):
    """Metinden coin, giriş, SL ve TP'leri çıkar."""
    text_up = text.upper()

    match = re.search(r'#([A-Z0-9]+)USDT', text_up)
    if not match: match = re.search(r'\$([A-Z0-9]+)\s*\|', text_up)
    if not match: match = re.search(r'\b([A-Z]{2,10})USDT\b', text_up)
    if not match: return None

    coin_adi = match.group(1)

    giris = None
    for pattern in [
        r'Giri[şs]\s*Fiyat[ıi]\s*[:\s]+([0-9.]+)',
        r'LONG\s*\|\s*([0-9.]+)',
        r'Price[:\s]+([0-9.]+)',
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m: giris = float(m.group(1)); break

    sl = None
    m = re.search(r'Stop[:\s]+([0-9.]+)', text, re.IGNORECASE)
    if m: sl = float(m.group(1))

    tps = [float(x) for x in re.findall(r'TP\d+[:\s]+([0-9.]+)', text)]

    return coin_adi, giris, sl, tps

# ════════════════════════════════════════════
# COINSONAR SİNYALİ İŞLE
# ════════════════════════════════════════════
def coinsonar_isle(text):
    """
    CoinSonar mesajı: "$XXX | #XXXUSDT | TradingView"
    Coin adını çek, 15m filtreden geç, uygunsa aç.
    """
    text_up = text.upper()

    match = re.search(r'#([A-Z0-9]+)USDT', text_up)
    if not match: match = re.search(r'\$([A-Z0-9]+)\s*\|', text_up)
    if not match: return

    coin_adi = match.group(1)
    symbol   = f"{coin_adi}/USDT:USDT"

    try:
        tickers = safe_api(exchange.fetch_tickers)
        if tickers and symbol not in tickers:
            log.info(f"[COINSONAR] {coin_adi} Bitget'te yok")
            return
    except: pass

    if günlük_limit_asıldı(): return

    with pos_lock:
        if len(positions) >= MAX_OPEN_AUTO: return
        if symbol in positions: return

    log.info(f"[COINSONAR] {coin_adi} analiz ediliyor...")

    gecti, detay = filtre_15m(symbol)

    if gecti:
        log.info(f"[COINSONAR] {coin_adi} ✅ GİRİYOR")
        tg(
            f"📡 CoinSonar Sinyali: {coin_adi}\n"
            f"MA5:{detay['ma5']:.6f} > MA10:{detay['ma10']:.6f} > MA20:{detay['ma20']:.6f} ✅\n"
            f"Hacim MA5:{detay['vol_ma5']:.0f} > MA10:{detay['vol_ma10']:.0f} ✅\n"
            f"RSI: {detay['rsi']:.1f} ✅\n"
            f"Limit emir açılıyor..."
        )
        open_pos_auto(symbol, "coinsonar")
    else:
        reason = []
        if not detay.get("ma_ok"): reason.append(f"MA ters ({detay.get('ma5',0):.6f}<{detay.get('ma10',0):.6f})")
        if not detay.get("vol_ok"): reason.append(f"Hacim düşük")
        if not detay.get("rsi_ok"): reason.append(f"RSI:{detay.get('rsi',0):.1f}")
        log.info(f"[COINSONAR] {coin_adi} ❌ PAS — {', '.join(reason)}")

# ════════════════════════════════════════════
# TELETHON — KANAL DİNLEYİCİ
# ════════════════════════════════════════════
async def telethon_loop():
    """CoinSonar ve FuturesKripto kanallarını dinler."""
    try:
        if TG_SESSION:
            client = TelegramClient(StringSession(TG_SESSION), TG_API_ID, TG_API_HASH)
        else:
            client = TelegramClient("sadik_session", TG_API_ID, TG_API_HASH)

        await client.start()
        log.info("[TELETHON] Bağlandı!")
        tg("📡 Telethon aktif — CoinSonar + FuturesKripto dinleniyor")

        @client.on(events.NewMessage(chats=[COINSONAR_KANAL, FUTURESKRIPTO_KANAL]))
        async def handler(event):
            text   = event.message.text or ""
            chat   = await event.get_chat()
            kanal  = getattr(chat, "username", "") or ""

            log.info(f"[TELETHON] Mesaj: {kanal} — {text[:50]}")

            if COINSONAR_KANAL.lower() in kanal.lower():
                threading.Thread(target=coinsonar_isle, args=(text,), daemon=True).start()

            elif FUTURESKRIPTO_KANAL.lower() in kanal.lower():
                sonuc = sinyal_parse(text)
                if sonuc:
                    coin_adi, giris, sl, tps = sonuc
                    if not giris or not sl or not tps:
                        return
                    symbol = f"{coin_adi}/USDT:USDT"
                    try:
                        tickers = safe_api(exchange.fetch_tickers)
                        if tickers and symbol not in tickers:
                            log.info(f"[FK] {coin_adi} Bitget'te yok")
                            return
                    except: pass
                    if not günlük_limit_asıldı():
                        tg(f"📊 FuturesKripto Sinyali: {coin_adi}\nGiriş: {giris} | SL: {sl}\nTP sayısı: {len(tps)}")
                        threading.Thread(
                            target=open_pos_futureskripto,
                            args=(symbol, giris, sl, tps),
                            daemon=True
                        ).start()

        await client.run_until_disconnected()

    except Exception as e:
        log.error(f"[TELETHON] {e}")
        tg(f"⚠️ Telethon bağlantı hatası: {e}")

def telethon_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telethon_loop())

# ════════════════════════════════════════════
# AÇILIŞTA POZİSYON YÜKLE
# ════════════════════════════════════════════
def load_open_positions():
    try:
        raw = safe_api(exchange.fetch_positions)
        if not raw: return
        yuklenen = 0
        lines = ["♻️ Pozisyonlar yüklendi:\n"]
        for p in raw:
            try:
                contracts = float(p.get("contracts") or 0)
                symbol    = p.get("symbol", "")
                side      = p.get("side", "")
                entry     = float(p.get("entryPrice") or 0)
                if contracts == 0 or not symbol or side != "long" or entry == 0: continue
                sl  = round(entry * (1 - SL_PCT / 100), 8)
                tps = [round(entry * (1 + pct / 100), 8) for pct in TP_PCTS]
                with pos_lock:
                    if symbol not in positions:
                        positions[symbol] = {
                            "entry": entry, "sl": sl, "tps": tps,
                            "tp_idx": 0, "max_price": entry,
                            "open_time": time.time(), "amount": contracts,
                            "kaynak": "yukle", "mod": "manuel", "pending": False,
                        }
                        yuklenen += 1
                        t  = safe_api(exchange.fetch_ticker, symbol)
                        now = float(t["last"]) if t else entry
                        pnl = (now - entry) * contracts
                        lines.append(f"{'🟢' if pnl>=0 else '🔴'} {symbol.split('/')[0]} @ {entry:.8f} | {pnl:+.2f}$")
            except Exception as e:
                log.warning(f"[YUKLE] {e}")
        if yuklenen > 0:
            tg("\n".join(lines))
        else:
            log.info("[YUKLE] Açık pozisyon yok")
    except Exception as e:
        log.error(f"[YUKLE] {e}")

# ════════════════════════════════════════════
# GÜNLÜK SIFIRLAMA
# ════════════════════════════════════════════
def gunluk_reset_loop():
    global daily_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now()
            yarin = (simdi + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            with daily_pnl_lock:
                eski = daily_pnl; daily_pnl = 0.0
            tg(f"🔄 Yeni gün! Dün: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}"); time.sleep(3600)

# ════════════════════════════════════════════
# HEALTH SERVER
# ════════════════════════════════════════════
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers()
            with pos_lock: ps = ",".join(s.split("/")[0] for s in positions)
            with daily_pnl_lock: pnl = daily_pnl
            self.wfile.write(f"OK|pos:{len(positions)}({ps})|pnl:{pnl:+.2f}".encode())
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ════════════════════════════════════════════
# TELEGRAM HANDLER
# ════════════════════════════════════════════
def find_coin(text):
    words = re.findall(r"\b[A-Z]{2,10}\b", text.upper())
    try:
        tickers = safe_api(exchange.fetch_tickers)
        if not tickers: return None
        for w in words:
            sym = f"{w}/USDT:USDT"
            if sym in tickers: return sym
    except: pass
    return None

@bot.message_handler(func=lambda msg: True)
def handle(msg):
    if not msg.text: return
    threading.Thread(target=handle_async, args=(msg,), daemon=True).start()

def handle_async(msg):
    text  = msg.text.strip()
    lower = text.lower()

    sinyal_var = (
        "🏁 long" in lower or "long - giri" in lower or
        "tradingview" in lower or
        (("#" in text or "$" in text) and "usdt" in text.upper())
    )

    if sinyal_var:
        sonuc = sinyal_parse(text)
        if sonuc:
            coin_adi, giris, sl, tps = sonuc
            symbol = f"{coin_adi}/USDT:USDT"

            try:
                tickers = safe_api(exchange.fetch_tickers)
                if tickers and symbol not in tickers:
                    bot.send_message(msg.chat.id, f"❌ {coin_adi} Bitget'te bulunamadı.")
                    return
            except: pass

            if günlük_limit_asıldı():
                bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı.")
                return

            with pos_lock:
                if len(positions) >= MAX_OPEN_MANUEL:
                    bot.send_message(msg.chat.id, f"❌ Max pozisyon ({MAX_OPEN_MANUEL}) dolu.")
                    return

            is_futureskripto = "🏁 long" in lower or "long - giri" in lower

            if is_futureskripto:
                if not giris or not sl or not tps:
                    bot.send_message(msg.chat.id, f"❌ Sinyal eksik.")
                    return
                bot.send_message(msg.chat.id, f"📡 {coin_adi} FuturesKripto sinyali alındı\nLimit emir açılıyor...")
                open_pos_futureskripto(symbol, giris, sl, tps)
            else:
                gecti, detay = filtre_15m(symbol)
                if not giris:
                    t0 = safe_api(exchange.fetch_ticker, symbol)
                    if t0: giris = float(t0["last"])

                durum = "✅ GİRİLİR" if gecti else "❌ PAS"
                bot.send_message(
                    msg.chat.id,
                    f"📊 {coin_adi} analiz:\n"
                    f"MA: {'✅' if detay.get('ma_ok') else '❌'} "
                    f"Hacim: {'✅' if detay.get('vol_ok') else '❌'} "
                    f"RSI: {detay.get('rsi',0):.1f} {'✅' if detay.get('rsi_ok') else '❌'}\n"
                    f"{durum}"
                )
                if gecti:
                    open_pos_auto(symbol, "tradingview")
            return

    if "long ac" in lower or "long aç" in lower:
        coin = find_coin(text)
        if not coin:
            bot.send_message(msg.chat.id, "❌ Coin bulunamadı.")
            return

        coin_adi = coin.split("/")[0]

        if günlük_limit_asıldı():
            bot.send_message(msg.chat.id, "❌ Günlük limit aşıldı.")
            return

        with pos_lock:
            if len(positions) >= MAX_OPEN_MANUEL:
                bot.send_message(msg.chat.id, f"❌ Max pozisyon dolu.")
                return
            if coin in positions:
                bot.send_message(msg.chat.id, f"❌ {coin_adi} zaten açık.")
                return

        bot.send_message(msg.chat.id, f"⚡ {coin_adi} açılıyor, 3 dakika bekleniyor...")
        open_pos_auto(coin, "manuel", bekle_sn=180)
        return

    if "/durum" in lower:
        with pos_lock:
            if not positions:
                bot.send_message(msg.chat.id, "📋 Açık pozisyon yok."); return
            lines = ["📋 POZİSYONLAR\n"]
            for sym, pos in positions.items():
                t = safe_api(exchange.fetch_ticker, sym)
                if not t: continue
                price = float(t["last"])
                pnl, pct = hesap_pnl(pos, price)
                sure = int((time.time() - pos["open_time"]) / 60)
                lines.append(
                    f"{'🟢' if pnl>=0 else '🔴'} {sym.split('/')[0]} [{pos.get('kaynak','?')}]\n"
                    f"   {pos['entry']:.8f}→{price:.8f}\n"
                    f"   PnL:{pnl:+.2f}$ ({pct:+.1f}%) | {sure}dk\n"
                    f"   SL:{pos['sl']:.8f} TP{pos.get('tp_idx',0)}/{len(pos.get('tps',[]))}\n"
                )
            bot.send_message(msg.chat.id, "\n".join(lines))
        return

    if "/istatistik" in lower:
        if not supa:
            bot.send_message(msg.chat.id, "Supabase yok."); return
        try:
            r    = supa.table("gpt_trades").select("pnl,kaynak").execute()
            data = r.data or []
            if not data:
                bot.send_message(msg.chat.id, "Kayıt yok."); return
            toplam = len(data)
            kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
            net    = sum(float(d.get("pnl") or 0) for d in data)
            with daily_pnl_lock: gunluk = daily_pnl
            bot.send_message(msg.chat.id,
                f"📊 İSTATİSTİK\n"
                f"Toplam: {toplam} | Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
                f"Net: {net:+.2f}$ | Günlük: {gunluk:+.2f}$"
            )
        except Exception as e:
            bot.send_message(msg.chat.id, f"Hata: {e}")
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

    coin = find_coin(text)
    if coin:
        sym = coin.split("/")[0]
        bot.send_message(msg.chat.id, f"🔍 {sym} 15m analiz...")
        gecti, detay = filtre_15m(coin)
        bot.send_message(msg.chat.id,
            f"📊 {sym} 15m ANALİZ\n"
            f"MA5: {detay.get('ma5',0):.8f}\n"
            f"MA10: {detay.get('ma10',0):.8f}\n"
            f"MA20: {detay.get('ma20',0):.8f}\n"
            f"MA Sırası: {'✅' if detay.get('ma_ok') else '❌'}\n"
            f"Hacim: {'✅' if detay.get('vol_ok') else '❌'}\n"
            f"RSI(14): {detay.get('rsi',0):.1f} {'✅' if detay.get('rsi_ok') else '❌'}\n\n"
            f"{'✅ GİRİLİR' if gecti else '❌ PAS'}"
        )
        return

    bot.send_message(msg.chat.id,
        "Komutlar:\n"
        "/durum — Açık pozisyonlar\n"
        "/istatistik — Geçmiş işlemler\n"
        "COIN long aç — Manuel giriş\n"
        "COIN kapat / hepsi kapat\n"
        "COIN adı yaz — Analiz"
    )

# ════════════════════════════════════════════
# SHUTDOWN
# ════════════════════════════════════════════
import signal as sig_mod, sys

def shutdown(signum, frame):
    with pos_lock: syms = list(positions.keys())
    if syms: tg(f"⏸ Yeniden başlıyor...\n{len(syms)} pozisyon açık.")
    sys.exit(0)

sig_mod.signal(sig_mod.SIGTERM, shutdown)
sig_mod.signal(sig_mod.SIGINT, shutdown)

# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("SADIK SCALP v3 BAŞLIYOR...")
    load_open_positions()
    threading.Thread(target=health_server,     daemon=True).start()
    threading.Thread(target=manage_loop,       daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=telethon_thread,   daemon=True).start()

    tg(
        "🚀 SADIK SCALP v3\n\n"
        "📡 Sinyal Kaynakları:\n"
        "  • CoinSonar V2 (otomatik)\n"
        "  • FuturesKripto (otomatik)\n"
        "  • Manuel (sen yazarsın)\n\n"
        "🔍 15m Filtre (CoinSonar için):\n"
        f"  • MA(5) > MA(10) > MA(20)\n"
        f"  • Hacim MA(5) > MA(10)\n"
        f"  • RSI(14) {RSI_MIN}-{RSI_MAX} arası\n\n"
        "⚡ TP/SL:\n"
        f"  • 6 TP: +{TP_PCTS[0]}% → +{TP_PCTS[-1]}%\n"
        f"  • SL: -%{SL_PCT}\n"
        f"  • Max: {MAX_SURE}dk\n\n"
        "Komutlar:\n"
        "/durum | /istatistik\n"
        "COIN long aç | COIN kapat"
    )

    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[BOT] {e}"); time.sleep(5)
