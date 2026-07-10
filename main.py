#!/usr/bin/env python3
"""
TELEGRAM SİNYAL KOPYALAMA BOTU — GERÇEK PARA
VERSİYON: v16.12 (risk-bazli pozisyon boyutu + likidite kontrolu + guvenli
komut ayristirma + 3 sabit TP + erken genis trailing + teyit bekleme +
kademeli SL yukseltme + 3-bilesenli trend teyidi + oz tarama)

v16.12 DEGISIKLIKLERI (v16.11'e gore, guvenlik/risk odakli):
  1. KRITIK GUVENLIK DUZELTMESI - YANLIS POZITIF: Komutsuz kisa mesaj
     ayristiricisinda "ac" kelimesi v16'da opsiyoneldi. Test edildi:
     "btc long term hodl" gibi siradan sohbet cumleleri bile "coin+LONG"
     kalibina uydugu icin GERCEK pozisyon actiriyordu. "ac" YENIDEN
     ZORUNLU kilindi.
  2. RISK BAZLI POZISYON BOYUTU: Sabit $10 marj x 10x yerine, SL
     mesafesine ters orantili, gercek zamanli bakiyeden hesaplanan boyut.
  3. LIKIDITE KONTROLU TUM KAYNAKLARA GENISLETILDI (kanal/manuel/oz-tarama).

Bu kanalin gecmis performansi hakkinda hicbir veri yok - dogrulanmadi.
Bu kod hicbir kar garantisi vermez.
"""
import os, re, time, json, threading, logging
import ccxt, telebot
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SIGNAL_COPY")

TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY = os.getenv("BITGET_API", "")
API_SEC = os.getenv("BITGET_SEC", "")
PASSPHRASE = os.getenv("BITGET_PASS", "")
TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_STRING_SESSION = os.getenv("STRING_SESSION", "") or os.getenv("TG_SESSION", "")
KANAL_KULLANICI_ADI = os.getenv("KANAL_USERNAME", "FuturesKripto")

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam degiskeni ayarlanmamis.")
if not TG_API_ID or not TG_API_HASH or not TG_STRING_SESSION:
    raise RuntimeError("TG_API_ID / TG_API_HASH / STRING_SESSION eksik.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

LEV = 10
MAX_POS = int(os.getenv("MAX_POS", "2"))
MIN_POS_NOTIONAL = 30.0
MAX_GUNLUK_ZARAR = float(os.getenv("MAX_GUNLUK_ZARAR", "-10.0"))
TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/signal_copy_state.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/signal_copy_log.json")
PORT = int(os.getenv("PORT", "8080"))

bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def tg(msg):
    if not bot:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


def get_candles(sym, tf, limit=100):
    try:
        return exchange.fetch_ohlcv(sym, tf, limit=limit)
    except Exception as e:
        log.warning(f"[VERI] {sym} {tf}: {e}")
        return None


def gercek_dolus_bilgisi_al(emir, sym, tahmini_fiyat):
    fiyat = safe(emir.get("average")) or safe(emir.get("price"))
    komisyon = 0.0
    try:
        fee = emir.get("fee")
        if fee:
            komisyon = safe(fee.get("cost"))
    except Exception:
        pass
    if not fiyat:
        try:
            time.sleep(0.5)
            detay = exchange.fetch_order(emir.get("id"), sym)
            fiyat = safe(detay.get("average")) or safe(detay.get("price"))
            fee = detay.get("fee")
            if fee:
                komisyon = safe(fee.get("cost"))
        except Exception as e:
            log.warning(f"[DOLUS] {sym} emir detayi alinamadi: {e}")
    if not fiyat:
        fiyat = tahmini_fiyat
    return fiyat, komisyon

# ════════════════════════════════════════════
# KALICI DURUM
# ════════════════════════════════════════════
trade_state = {}
state_lock = threading.Lock()

def durumu_diske_yaz():
    try:
        os.makedirs(os.path.dirname(TRADE_STATE_PATH), exist_ok=True)
        with state_lock:
            veri = dict(trade_state)
        with open(TRADE_STATE_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[KALICI] Diske yazma basarisiz: {e}")
    durumu_telegrama_yedekle()


def durumu_diskten_yukle():
    global trade_state
    try:
        if os.path.exists(TRADE_STATE_PATH):
            with open(TRADE_STATE_PATH) as f:
                yuklenen = json.load(f)
            with state_lock:
                trade_state = yuklenen
            log.info(f"[KALICI] {len(yuklenen)} kayitli islem durumu yuklendi")
    except Exception as e:
        log.warning(f"[KALICI] Yukleme basarisiz: {e}")


STATE_PIN_ETIKETI = "BOT_DURUM_YEDEK (dokunma - otomatik guncellenir)"
_pin_message_id = None
_pin_lock = threading.Lock()


def durumu_telegrama_yedekle():
    global _pin_message_id
    if not bot or not CHAT_ID:
        return
    try:
        with state_lock:
            veri_state = dict(trade_state)
        try:
            with bekleyen_lock:
                veri_bekleyen = {
                    sym: {"sinyal": k["sinyal"], "gozlem_str": k["gozlem_str"],
                          "eklenme_zamani": k["eklenme_zamani"]}
                    for sym, k in bekleyen_sinyaller.items()
                }
        except NameError:
            veri_bekleyen = {}

        icerik = json.dumps({"trade_state": veri_state, "bekleyen_sinyaller": veri_bekleyen})
        metin = f"{STATE_PIN_ETIKETI}\n{icerik}"
        if len(metin) > 4000:
            log.warning("[TG_YEDEK] Durum verisi cok buyuk, Telegram'a yazilamadi")
            return

        with _pin_lock:
            if _pin_message_id:
                try:
                    bot.edit_message_text(metin, CHAT_ID, _pin_message_id)
                    return
                except Exception:
                    pass
            gonderilen = bot.send_message(CHAT_ID, metin)
            _pin_message_id = gonderilen.message_id
            try:
                bot.pin_chat_message(CHAT_ID, _pin_message_id, disable_notification=True)
            except Exception as e:
                log.warning(f"[TG_YEDEK] Sabitleme basarisiz: {e}")
    except Exception as e:
        log.warning(f"[TG_YEDEK] Telegram'a yazma basarisiz: {e}")


def durumu_telegramdan_yukle():
    global trade_state, _pin_message_id
    if not bot or not CHAT_ID:
        return
    try:
        chat = bot.get_chat(CHAT_ID)
        pinned = getattr(chat, "pinned_message", None)
        if not pinned or not pinned.text or STATE_PIN_ETIKETI not in pinned.text:
            log.info("[TG_YEDEK] Sabitlenmis durum mesaji bulunamadi")
            return
        _pin_message_id = pinned.message_id
        json_kismi = pinned.text.split("\n", 1)[1]
        veri = json.loads(json_kismi)
        yuklenen_state = veri.get("trade_state", {})
        with state_lock:
            trade_state.update(yuklenen_state)
        yuklenen_bekleyen = veri.get("bekleyen_sinyaller", {})
        with bekleyen_lock:
            for sym, kayit in yuklenen_bekleyen.items():
                bekleyen_sinyaller[sym] = kayit
        if yuklenen_state or yuklenen_bekleyen:
            tg(f"Telegram yedeginden geri yuklendi: {len(yuklenen_state)} acik islem, "
               f"{len(yuklenen_bekleyen)} bekleyen sinyal")
    except Exception as e:
        log.warning(f"[TG_YEDEK] Telegram'dan yukleme basarisiz: {e}")


trade_log = []
log_lock = threading.Lock()

def trade_log_kaydet(kayit):
    with log_lock:
        trade_log.append(kayit)
        veri = list(trade_log)
    try:
        os.makedirs(os.path.dirname(TRADE_LOG_PATH), exist_ok=True)
        with open(TRADE_LOG_PATH, "w") as f:
            json.dump(veri, f)
    except Exception as e:
        log.warning(f"[LOG] Diske yazma basarisiz: {e}")


def trade_log_yukle():
    global trade_log
    try:
        if os.path.exists(TRADE_LOG_PATH):
            with open(TRADE_LOG_PATH) as f:
                yuklenen = json.load(f)
            with log_lock:
                trade_log = yuklenen
            log.info(f"[LOG] {len(yuklenen)} gecmis islem yuklendi")
    except Exception as e:
        log.warning(f"[LOG] Yukleme basarisiz: {e}")


def acilista_pozisyonlari_dogrula():
    try:
        pozisyonlar = exchange.fetch_positions()
    except Exception as e:
        tg(f"Acilista pozisyon kontrolu basarisiz: {e}")
        return
    for p in pozisyonlar:
        qty = safe(p.get("contracts"))
        if qty <= 0:
            continue
        sym = p["symbol"]
        entry = safe(p.get("entryPrice"))
        side = p.get("side")
        with state_lock:
            kayitli = trade_state.get(sym)
        if kayitli:
            tg(f"{sym} pozisyonu kayitli durumla eslesti.")
            continue
        direction = "long" if side == "long" else "short"
        guvenlik_sl_pct = 0.03
        sl = entry * (1 - guvenlik_sl_pct) if direction == "long" else entry * (1 + guvenlik_sl_pct)
        with state_lock:
            trade_state[sym] = {"sl": sl, "tp_liste": [], "tp_index": 0,
                                 "direction": direction, "entry": entry, "kaynak": "kurtarilan"}
        durumu_diske_yaz()
        tg(f"UYARI: {sym} icin kayitli durum yoktu - gecici %3 guvenlik SL'i kondu: {sl:.8f}")


def acik_pozisyonlara_kademeli_sl_uygula():
    with state_lock:
        semboller = list(trade_state.keys())
    for sym in semboller:
        with state_lock:
            durum = trade_state.get(sym)
        if not durum:
            continue
        tp_index = durum.get("tp_index", 0)
        tp_liste = durum.get("tp_liste", [])
        entry = durum.get("entry")
        direction = durum.get("direction")
        mevcut_sl = durum.get("sl")
        if tp_index == 0 or not tp_liste or entry is None or mevcut_sl is None or direction is None:
            continue
        if tp_index == 1:
            onerilen_sl = entry * (1 - TP1_BREAKEVEN_TAMPON_PCT) if direction == "long" \
                          else entry * (1 + TP1_BREAKEVEN_TAMPON_PCT)
        else:
            hedef_index = tp_index - 2
            if hedef_index < 0 or hedef_index >= len(tp_liste):
                continue
            onerilen_sl = tp_liste[hedef_index]
        sl_iyilesir_mi = (direction == "long" and onerilen_sl > mevcut_sl) or \
                          (direction == "short" and onerilen_sl < mevcut_sl)
        if sl_iyilesir_mi:
            with state_lock:
                trade_state[sym]["sl"] = onerilen_sl
            durumu_diske_yaz()
            tg(f"{sym} - bot guncellendi, yeni kademeli SL kurali uygulandi: "
               f"{mevcut_sl:.8f} -> {onerilen_sl:.8f} (TP{tp_index} vurulmustu)")


# ════════════════════════════════════════════
# GUNLUK ZARAR TAKIBI
# ════════════════════════════════════════════
gunluk_pnl = 0.0
gunluk_lock = threading.Lock()

def gunluk_limit_asildi():
    with gunluk_lock:
        return gunluk_pnl <= MAX_GUNLUK_ZARAR

def gunluk_pnl_ekle(miktar):
    global gunluk_pnl
    with gunluk_lock:
        gunluk_pnl += miktar
        return gunluk_pnl

def gunluk_reset_loop():
    global gunluk_pnl
    import datetime
    while True:
        try:
            simdi = datetime.datetime.now(datetime.timezone.utc)
            yarin = (simdi + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
            time.sleep((yarin - simdi).total_seconds())
            with gunluk_lock:
                eski = gunluk_pnl
                gunluk_pnl = 0.0
            tg(f"Yeni gun! Dunku gerceklesen: {eski:+.2f}$")
        except Exception as e:
            log.error(f"[RESET] {e}")
            time.sleep(3600)

# ════════════════════════════════════════════
# SINYAL AYRISTIRMA
# ════════════════════════════════════════════
HIZLI_SL_PCT = 0.02
MAX_SL_PCT = 0.03
KISA_MESAJ_UST_SINIR = 30

def hizli_sinyal_ayristir(metin):
    """
    Basit format: 'MAGMA LONG AC', 'edge short ac' gibi. "ac" kelimesi
    v16.12'de komut_metni_ayikla icinde ZORUNLU kilindi (bkz. asagida).
    """
    m = re.search(r"\b([A-Za-z][A-Za-z0-9]{1,10})\b.*?\b(LONG|SHORT)\b", metin, re.IGNORECASE)
    if not m:
        return None
    sembol = m.group(1).upper()
    if sembol in ("LONG", "SHORT", "AC", "KAPAT"):
        return None
    yon = "long" if m.group(2).upper() == "LONG" else "short"
    return {"symbol": f"{sembol}/USDT:USDT", "direction": yon, "entry": None, "sl": None, "tp_liste": []}


def sinyal_ayristir(metin):
    sembol_m = re.search(r"#(\w+?)USDT", metin, re.IGNORECASE)
    yon_m = re.search(r"\b(LONG|SHORT)\b", metin, re.IGNORECASE)
    giris_m = re.search(r"Giri[şs].*?Fiyat[ıi]?\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    stop_m = re.search(r"Stop\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    tp_liste = re.findall(r"TP\d+\s*:?\s*([\d.]+)", metin, re.IGNORECASE)
    if not (sembol_m and yon_m and giris_m and stop_m):
        return None
    return {
        "symbol": f"{sembol_m.group(1).upper()}/USDT:USDT",
        "direction": "long" if yon_m.group(1).upper() == "LONG" else "short",
        "entry": float(giris_m.group(1)),
        "sl": float(stop_m.group(1)),
        "tp_liste": [float(x) for x in tp_liste],
    }


# ════════════════════════════════════════════
# v16.12 - RISK BAZLI POZISYON BOYUTU (trader mantigi)
# ════════════════════════════════════════════
RISK_YUZDESI = float(os.getenv("RISK_YUZDESI", "0.05"))  # kullanici talebiyle: %5
MAKS_KALDIRAC_CARPANI = float(os.getenv("MAKS_KALDIRAC_CARPANI", "3.0"))
MIN_SL_MESAFE_PCT = 0.003

def pozisyon_boyutu_hesapla(entry, sl, gercek_bakiye):
    """
    Doner: (amount, notional, aciklama_str) ya da (None, None, red_sebebi)
    Mantik: "hesabin RISK_YUZDESI kadarini, SADECE bu islemde, SL
    vurulursa kaybet" hedefinden, SL mesafesine TERS orantili boyut.
    MAKS_KALDIRAC_CARPANI ile ust sinir var (SL asiri dar geldiyse bile
    pozisyon cilginca buyumesin diye).
    """
    if entry <= 0 or sl is None:
        return None, None, "gecersiz giris/SL"
    if gercek_bakiye is None or gercek_bakiye <= 0:
        return None, None, "gercek bakiye alinamadi ya da sifir"

    sl_mesafe_pct = abs(entry - sl) / entry
    if sl_mesafe_pct < MIN_SL_MESAFE_PCT:
        return None, None, f"SL mesafesi cok dar (%{sl_mesafe_pct*100:.3f}) - guvenilmez, atlandi"

    risk_tutari = gercek_bakiye * RISK_YUZDESI
    notional_riskten = risk_tutari / sl_mesafe_pct
    notional_tavan = gercek_bakiye * MAKS_KALDIRAC_CARPANI
    notional = min(notional_riskten, notional_tavan)
    tavan_devrede = notional_riskten > notional_tavan

    if notional < MIN_POS_NOTIONAL:
        return None, None, (f"hesaplanan pozisyon (${notional:.2f}) borsanin asgari "
                             f"tutarinin (${MIN_POS_NOTIONAL}) altinda - atlandi")

    amount = notional / entry
    aciklama = (f"risk=${risk_tutari:.2f} (bakiyenin %{RISK_YUZDESI*100:.1f}'i), "
                f"SL mesafesi=%{sl_mesafe_pct*100:.2f} -> notional=${notional:.2f}"
                + (" [KALDIRAC TAVANINA CARPTI]" if tavan_devrede else ""))
    return amount, notional, aciklama


def gercek_bakiye_al():
    try:
        bakiye = exchange.fetch_balance()
        return safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] Alinamadi: {e}")
        return None


# ════════════════════════════════════════════
# v16.12 - LIKIDITE KONTROLU (artik TUM kaynaklara uygulaniyor)
# ════════════════════════════════════════════
MIN_HACIM_USDT_ISLEM_ACMA = float(os.getenv("MIN_HACIM_USDT_ISLEM_ACMA", "3000000"))

def likidite_yeterli_mi(sym):
    try:
        t = exchange.fetch_ticker(sym)
        hacim = safe(t.get("quoteVolume"))
        if hacim < MIN_HACIM_USDT_ISLEM_ACMA:
            return False, f"24s hacim cok dusuk (${hacim:,.0f} < ${MIN_HACIM_USDT_ISLEM_ACMA:,.0f})"
        return True, f"hacim yeterli (${hacim:,.0f})"
    except Exception as e:
        return True, f"hacim kontrol edilemedi ({e}), gecildi"


TP_OLCEK_CARPANI = 2.0
TP_DILIM_ORANLARI = [0.15, 0.15, 0.15]
TP_SAYISI_KULLANILAN = 3
TP1_BREAKEVEN_TAMPON_PCT = 0.0015
TRAILING_GERI_CEKILME_PCT = 0.035
TRAILING_BILDIRIM_ESIK_PCT = 0.01
TP1_EK_GENISLETME_CARPANI = 1.5

def tp_olcekle(entry, sl, tp_liste, direction, carpan=TP_OLCEK_CARPANI):
    risk_mesafe = abs(entry - sl)
    if risk_mesafe <= 0 or not tp_liste:
        return tp_liste
    yeni_liste = []
    for i, tp in enumerate(tp_liste):
        oran = abs(tp - entry) / risk_mesafe
        yeni_oran = oran * carpan
        if i == 0:
            yeni_oran *= TP1_EK_GENISLETME_CARPANI
        yeni_tp = entry + yeni_oran * risk_mesafe if direction == "long" else entry - yeni_oran * risk_mesafe
        yeni_liste.append(yeni_tp)
    return yeni_liste

# ════════════════════════════════════════════
# GOSTERGELER
# ════════════════════════════════════════════
def calc_macd_hist(kapanis_listesi, hizli=12, yavas=26, sinyal=9):
    import pandas as pd
    s = pd.Series(kapanis_listesi)
    ema_h = s.ewm(span=hizli, adjust=False).mean()
    ema_y = s.ewm(span=yavas, adjust=False).mean()
    macd = ema_h - ema_y
    sinyal_hatti = macd.ewm(span=sinyal, adjust=False).mean()
    return float((macd - sinyal_hatti).iloc[-1])


def calc_bollinger_yuzdeB(kapanis_listesi, period=20, std_mult=2.0):
    import pandas as pd
    s = pd.Series(kapanis_listesi)
    orta = s.rolling(period).mean()
    std = s.rolling(period).std()
    ust = orta + std_mult * std
    alt = orta - std_mult * std
    genislik = (ust - alt).replace(0, 0.0001)
    yuzdeB = (s - alt) / genislik
    return float(yuzdeB.iloc[-1]) if not pd.isna(yuzdeB.iloc[-1]) else None


def calc_sma(kapanis_listesi, period=20):
    import pandas as pd
    s = pd.Series(kapanis_listesi)
    orta = s.rolling(period).mean()
    son = orta.iloc[-1]
    return float(son) if not pd.isna(son) else None


def calc_rsi(kapanis_listesi, period=14):
    import pandas as pd
    s = pd.Series(kapanis_listesi)
    fark = s.diff()
    kazanc = fark.clip(lower=0)
    kayip = -fark.clip(upper=0)
    ort_kazanc = kazanc.rolling(period).mean()
    ort_kayip = kayip.rolling(period).mean()
    rs = ort_kazanc / ort_kayip.replace(0, 0.0001)
    rsi = 100 - (100 / (1 + rs))
    son = rsi.iloc[-1]
    return float(son) if not pd.isna(son) else None


def deneysel_gozlem_hesapla(sym):
    try:
        h4 = get_candles(sym, "4h", 30)
        h1 = get_candles(sym, "1h", 40)
        if not h4 or not h1 or len(h4) < 21 or len(h1) < 35:
            return None
        h4_kapanis = [c[4] for c in h4]
        h1_kapanis = [c[4] for c in h1]
        boll_4h = calc_bollinger_yuzdeB(h4_kapanis)
        macd_1h = calc_macd_hist(h1_kapanis)
        return {"4h_bollB": round(boll_4h, 2) if boll_4h is not None else None,
                "1h_macd_hist": round(macd_1h, 6)}
    except Exception:
        return None


def trend_teyidi_yeterli_mi(sym, direction):
    try:
        h4 = get_candles(sym, "4h", 30)
        h1 = get_candles(sym, "1h", 30)
        if not h4 or not h1 or len(h4) < 21 or len(h1) < 15:
            return True, "veri yetersiz, filtre uygulanamadi - gecildi"
        h4_kapanis = [c[4] for c in h4]
        h4_acilis = [c[1] for c in h4]
        h1_kapanis = [c[4] for c in h1]
        fiyat = h4_kapanis[-1]
        ma20 = calc_sma(h4_kapanis, period=20)
        rsi_1h = calc_rsi(h1_kapanis, period=14)
        if ma20 is None or rsi_1h is None:
            return True, "gosterge hesaplanamadi, filtre uygulanamadi - gecildi"
        son_5_acilis = h4_acilis[-5:]
        son_5_kapanis = h4_kapanis[-5:]
        yukselis_sayisi = sum(1 for a, k in zip(son_5_acilis, son_5_kapanis) if k > a)
        dusus_sayisi = sum(1 for a, k in zip(son_5_acilis, son_5_kapanis) if k < a)
        if direction == "long":
            if not (fiyat > ma20):
                return False, f"4h fiyat MA20'nin altinda ({fiyat:.8f} < {ma20:.8f})"
            if not (yukselis_sayisi >= 3):
                return False, f"son 5 mumun sadece {yukselis_sayisi}'i yukseliste (min 3)"
            if not (rsi_1h > 40):
                return False, f"1h RSI zayif ({rsi_1h:.1f} <= 40)"
        else:
            if not (fiyat < ma20):
                return False, f"4h fiyat MA20'nin ustunde ({fiyat:.8f} > {ma20:.8f})"
            if not (dusus_sayisi >= 3):
                return False, f"son 5 mumun sadece {dusus_sayisi}'i dususte (min 3)"
            if not (rsi_1h < 60):
                return False, f"1h RSI zayif ({rsi_1h:.1f} >= 60)"
        return True, (f"teyit saglandi (MA20:{ma20:.8f}, mum:{yukselis_sayisi if direction=='long' else dusus_sayisi}/5, "
                       f"1h_RSI:{rsi_1h:.1f})")
    except Exception as e:
        return True, f"kontrol hatasi ({e}), gecildi"


# ════════════════════════════════════════════
# OZ TARAMA
# ════════════════════════════════════════════
OZ_TARAMA_AKTIF = os.getenv("OZ_TARAMA_AKTIF", "true").lower() == "true"
OZ_TARAMA_ARALIK_DK = int(os.getenv("OZ_TARAMA_ARALIK_DK", "20"))
OZ_TARAMA_MIN_HACIM_USDT = float(os.getenv("OZ_TARAMA_MIN_HACIM_USDT", "5000000"))
OZ_TARAMA_WATCHLIST_BOYUTU = int(os.getenv("OZ_TARAMA_WATCHLIST_BOYUTU", "25"))

oz_tarama_gecmis = {}
oz_tarama_lock = threading.Lock()


def oz_tarama_watchlist_getir():
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[OZ_TARAMA] Ticker listesi alinamadi: {e}")
        return []
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        hacim = safe(t.get("quoteVolume"))
        if hacim >= OZ_TARAMA_MIN_HACIM_USDT:
            adaylar.append((sym, hacim))
    adaylar.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in adaylar[:OZ_TARAMA_WATCHLIST_BOYUTU]]


def oz_tarama_aday_degerlendir(sym):
    try:
        h4 = get_candles(sym, "4h", 30)
        h1 = get_candles(sym, "1h", 30)
        if not h4 or not h1 or len(h4) < 21 or len(h1) < 15:
            return None
        h4_kapanis = [c[4] for c in h4]
        h4_acilis = [c[1] for c in h4]
        h1_kapanis = [c[4] for c in h1]
        fiyat = h4_kapanis[-1]
        ma20 = calc_sma(h4_kapanis, period=20)
        rsi_1h = calc_rsi(h1_kapanis, period=14)
        if ma20 is None or rsi_1h is None:
            return None
        son_5_acilis = h4_acilis[-5:]
        son_5_kapanis = h4_kapanis[-5:]
        yukselis_sayisi = sum(1 for a, k in zip(son_5_acilis, son_5_kapanis) if k > a)
        dusus_sayisi = sum(1 for a, k in zip(son_5_acilis, son_5_kapanis) if k < a)
        if fiyat > ma20 and yukselis_sayisi >= 3 and 40 < rsi_1h < 75:
            return "long"
        if fiyat < ma20 and dusus_sayisi >= 3 and 25 < rsi_1h < 60:
            return "short"
        return None
    except Exception as e:
        log.warning(f"[OZ_TARAMA] {sym} degerlendirilemedi: {e}")
        return None


def oz_tarama_loop():
    if not OZ_TARAMA_AKTIF:
        log.info("[OZ_TARAMA] Devre disi (OZ_TARAMA_AKTIF=false)")
        return
    tg(f"Oz tarama AKTIF - her {OZ_TARAMA_ARALIK_DK} dk'da bir en likit "
       f"{OZ_TARAMA_WATCHLIST_BOYUTU} coin taranacak (min 24h hacim: "
       f"${OZ_TARAMA_MIN_HACIM_USDT:,.0f})")
    while True:
        try:
            time.sleep(OZ_TARAMA_ARALIK_DK * 60)
            if gunluk_limit_asildi():
                continue
            with state_lock:
                pozisyon_dolu = len(trade_state) >= MAX_POS
            if pozisyon_dolu:
                continue
            watchlist = oz_tarama_watchlist_getir()
            for sym in watchlist:
                with state_lock:
                    zaten_acik = sym in trade_state
                with bekleyen_lock:
                    zaten_bekliyor = sym in bekleyen_sinyaller
                if zaten_acik or zaten_bekliyor:
                    continue
                yon = oz_tarama_aday_degerlendir(sym)
                with oz_tarama_lock:
                    onceki_yon = oz_tarama_gecmis.get(sym)
                    oz_tarama_gecmis[sym] = yon
                if yon is None or yon == onceki_yon:
                    continue
                sinyal = {"symbol": sym, "direction": yon, "entry": None, "sl": None,
                          "tp_liste": [], "kaynak_etiket": "oz_tarama"}
                tg(f"[OZ TARAMA] {sym} {yon.upper()} adayi bulundu (taze teyit) - isleniyor...")
                sinyali_isle(sinyal)
                with state_lock:
                    if len(trade_state) >= MAX_POS:
                        break
        except Exception as e:
            log.error(f"[OZ_TARAMA] {e}")
            time.sleep(30)


def manuel_pozisyon_kapat(sym):
    try:
        pozisyonlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyonlar if safe(p.get("contracts")) > 0), None)
        if not gercek_pos:
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            return True, f"{sym} zaten borsada acik degilmis, kayit temizlendi."
        qty = safe(gercek_pos.get("contracts"))
        direction = "long" if gercek_pos.get("side") == "long" else "short"
        entry = safe(gercek_pos.get("entryPrice"))
        with state_lock:
            kayitli_durum = trade_state.get(sym, {})
        tp_emirlerini_iptal_et(sym, kayitli_durum.get("tp_emirleri", []), kayitli_durum.get("tp_index", 0))
        kapatma_emri = exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                       qty, params={"reduceOnly": True})
        time.sleep(1)
        guncel = exchange.fetch_positions([sym])
        kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)
        if not kapandi_mi:
            return False, f"{sym} kapatma emri gonderildi ama dogrulanamadi - tekrar dene."
        t = exchange.fetch_ticker(sym)
        tahmini_fiyat = safe(t["last"])
        price, komisyon = gercek_dolus_bilgisi_al(kapatma_emri, sym, tahmini_fiyat)
        gross = (price - entry) * qty if direction == "long" else (entry - price) * qty
        gross -= komisyon
        gunluk_pnl_ekle(gross)
        with state_lock:
            onceki_gerceklesen = trade_state.get(sym, {}).get("gerceklesen_pnl", 0)
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        trade_log_kaydet({
            "symbol": sym, "direction": direction, "entry": entry,
            "exit": price, "pnl": gross + onceki_gerceklesen, "sonuc": "MANUEL_KAPATMA",
            "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        })
        return True, f"{sym} manuel olarak kapatildi | PnL={gross:+.2f}$"
    except Exception as e:
        return False, f"{sym} kapatma sirasinda hata: {e}"


TEYIT_BEKLEME_DAKIKA = int(os.getenv("TEYIT_BEKLEME_DAKIKA", "180"))
TEYIT_KONTROL_ARALIGI_SN = 60
bekleyen_sinyaller = {}
bekleyen_lock = threading.Lock()

def sinyali_isle(sinyal):
    if gunluk_limit_asildi():
        tg("Gunluk zarar limiti asildi, bu sinyal atlandi.")
        return
    with state_lock:
        if len(trade_state) >= MAX_POS:
            tg(f"Zaten acik pozisyon var (MAX_POS={MAX_POS}), sinyal atlandi: {sinyal['symbol']}")
            return

    sym = sinyal["symbol"]
    direction = sinyal["direction"]

    # v16.12: LIKIDITE KONTROLU tum kaynaklar icin en basta yapiliyor.
    likit_ok, likit_mesaj = likidite_yeterli_mi(sym)
    if not likit_ok:
        tg(f"{sym} {direction.upper()} atlandi - {likit_mesaj}")
        return

    gozlem = deneysel_gozlem_hesapla(sym)
    gozlem_str = f" | Deneysel: {gozlem}" if gozlem else ""

    teyit_ok, teyit_mesaj = trend_teyidi_yeterli_mi(sym, direction)
    if not teyit_ok:
        with bekleyen_lock:
            zaten_bekliyor = sym in bekleyen_sinyaller
            bekleyen_sinyaller[sym] = {
                "sinyal": sinyal, "gozlem_str": gozlem_str, "eklenme_zamani": time.time(),
            }
        durumu_telegrama_yedekle()
        if zaten_bekliyor:
            tg(f"{sym} {direction.upper()} hala teyitsiz ({teyit_mesaj}) - bekleme suresi yenilendi{gozlem_str}")
        else:
            tg(f"{sym} {direction.upper()} simdilik atlandi - trend teyidi zayif ({teyit_mesaj}).\n"
               f"Arka planda en fazla {TEYIT_BEKLEME_DAKIKA} dk boyunca izlenecek{gozlem_str}")
        return

    asil_islemi_ac(sinyal, gozlem_str)


def _sinyali_guncel_fiyata_yenile(sinyal):
    sym = sinyal["symbol"]
    direction = sinyal["direction"]
    orig_entry = sinyal.get("entry")
    orig_sl = sinyal.get("sl")
    orig_tp = sinyal.get("tp_liste") or []
    if orig_entry is None or orig_sl is None:
        return dict(sinyal)
    try:
        t = exchange.fetch_ticker(sym)
        guncel_fiyat = safe(t["last"])
    except Exception as e:
        tg(f"{sym} guncel fiyat alinamadi, kuyruktan acilamadi: {e}")
        return None
    if guncel_fiyat <= 0:
        tg(f"{sym} gecersiz fiyat alindi, kuyruktan acilamadi")
        return None
    risk_pct = abs(orig_entry - orig_sl) / orig_entry
    yeni = dict(sinyal)
    yeni["entry"] = guncel_fiyat
    yeni["sl"] = guncel_fiyat * (1 - risk_pct) if direction == "long" else guncel_fiyat * (1 + risk_pct)
    if orig_tp:
        risk_mesafe_orig = abs(orig_entry - orig_sl)
        if risk_mesafe_orig > 0:
            oranlar = [abs(tp - orig_entry) / risk_mesafe_orig for tp in orig_tp]
            yeni_risk_mesafe = abs(guncel_fiyat - yeni["sl"])
            if direction == "long":
                yeni["tp_liste"] = [guncel_fiyat + o * yeni_risk_mesafe for o in oranlar]
            else:
                yeni["tp_liste"] = [guncel_fiyat - o * yeni_risk_mesafe for o in oranlar]
    return yeni


def teyit_bekleme_loop():
    while True:
        try:
            time.sleep(TEYIT_KONTROL_ARALIGI_SN)
            with bekleyen_lock:
                semboller = list(bekleyen_sinyaller.keys())
            for sym in semboller:
                with bekleyen_lock:
                    kayit = bekleyen_sinyaller.get(sym)
                if not kayit:
                    continue
                gecen_dk = (time.time() - kayit["eklenme_zamani"]) / 60
                if gecen_dk > TEYIT_BEKLEME_DAKIKA:
                    with bekleyen_lock:
                        bekleyen_sinyaller.pop(sym, None)
                    durumu_telegrama_yedekle()
                    tg(f"{sym} {kayit['sinyal']['direction'].upper()} - {TEYIT_BEKLEME_DAKIKA} dk "
                       f"icinde teyit gelmedi, sinyal tamamen dusuruldu")
                    continue
                if gunluk_limit_asildi():
                    continue
                with state_lock:
                    pozisyon_dolu = len(trade_state) >= MAX_POS
                if pozisyon_dolu:
                    continue
                direction = kayit["sinyal"]["direction"]
                teyit_ok, teyit_mesaj = trend_teyidi_yeterli_mi(sym, direction)
                if teyit_ok:
                    with bekleyen_lock:
                        bekleyen_sinyaller.pop(sym, None)
                    durumu_telegrama_yedekle()
                    guncel_sinyal = _sinyali_guncel_fiyata_yenile(kayit["sinyal"])
                    if guncel_sinyal is None:
                        continue
                    tg(f"{sym} {direction.upper()} - teyit {gecen_dk:.0f} dk sonra saglandi "
                       f"({teyit_mesaj}), GUNCEL fiyattan aciliyor")
                    asil_islemi_ac(guncel_sinyal, kayit["gozlem_str"])
        except Exception as e:
            log.error(f"[TEYIT_BEKLEME] {e}")
            time.sleep(10)


def asil_islemi_ac(sinyal, gozlem_str=""):
    sym = sinyal["symbol"]
    direction = sinyal["direction"]
    entry_hedef = sinyal["entry"]
    sl = sinyal["sl"]

    if entry_hedef is None or sl is None:
        try:
            t = exchange.fetch_ticker(sym)
            entry_hedef = safe(t["last"])
        except Exception as e:
            tg(f"{sym} anlik fiyat alinamadi: {e}")
            return
        sl = entry_hedef * (1 - HIZLI_SL_PCT) if direction == "long" else entry_hedef * (1 + HIZLI_SL_PCT)
        risk_mesafe = abs(entry_hedef - sl)
        KANAL_TP_ORANLARI = [0.1, 0.2, 0.3, 0.4, 0.5, 0.8]
        if direction == "long":
            tp_liste_otomatik = [entry_hedef + oran * risk_mesafe for oran in KANAL_TP_ORANLARI]
        else:
            tp_liste_otomatik = [entry_hedef - oran * risk_mesafe for oran in KANAL_TP_ORANLARI]
        sinyal["tp_liste"] = tp_liste_otomatik
        tg(f"{sym} basit format - giris={entry_hedef:.8f}\n"
           f"SL (%{HIZLI_SL_PCT*100:.0f}): {sl:.8f}\n"
           f"Otomatik TP (ham): {[round(x,8) for x in tp_liste_otomatik]}")

    sl_pct = abs(entry_hedef - sl) / entry_hedef
    if sl_pct > MAX_SL_PCT:
        sl_eski = sl
        sl = entry_hedef * (1 - MAX_SL_PCT) if direction == "long" else entry_hedef * (1 + MAX_SL_PCT)
        tg(f"{sym} kanalin SL'i cok genisti (%{sl_pct*100:.2f}) - kendi SL'imize "
           f"sikistirildi: {sl_eski:.8f} -> {sl:.8f} (%{MAX_SL_PCT*100:.1f})")

    if sinyal.get("tp_liste"):
        tp_ham = sinyal["tp_liste"]
        tp_olcekli_tam = tp_olcekle(entry_hedef, sl, tp_ham, direction)
        sinyal["tp_liste"] = tp_olcekli_tam[:TP_SAYISI_KULLANILAN]
        tg(f"TP'ler {TP_OLCEK_CARPANI}x olceklendi (ilk {TP_SAYISI_KULLANILAN}'u sabit hedef):\n"
           f"Ham: {[round(x,8) for x in tp_ham]}\n"
           f"Kullanilan: {[round(x,8) for x in sinyal['tp_liste']]}")

    # v16.12: RISK BAZLI POZISYON BOYUTU - gercek zamanli bakiye ile
    gercek_bakiye = gercek_bakiye_al()
    amount, notional, boyut_mesaji = pozisyon_boyutu_hesapla(entry_hedef, sl, gercek_bakiye)
    if not amount:
        tg(f"{sym} pozisyon acilmadi - {boyut_mesaji}")
        return
    tg(f"{sym} pozisyon boyutu: {boyut_mesaji}")

    gereken_marj = notional / LEV
    if gercek_bakiye is not None and gercek_bakiye < gereken_marj:
        tg(f"{sym} atlandi - gercek bakiye yetersiz (gereken marj={gereken_marj:.2f}, "
           f"bakiye={gercek_bakiye:.2f}).")
        return

    try:
        exchange.set_leverage(LEV, sym)
    except Exception as e:
        tg(f"{sym} kaldirac ayarlanamadi: {e} - islem atlandi")
        return

    try:
        t = exchange.fetch_ticker(sym)
        price = safe(t["last"])
    except Exception as e:
        tg(f"{sym} fiyat alinamadi: {e}")
        return

    try:
        qty = float(exchange.amount_to_precision(sym, amount))
    except Exception as e:
        tg(f"{sym} miktar hassasiyeti alinamadi: {e}")
        return
    if qty <= 0:
        return

    side = "buy" if direction == "long" else "sell"
    try:
        exchange.create_market_order(sym, side, qty)
    except Exception as e:
        tg(f"{sym} giris emri basarisiz: {e}")
        return

    with state_lock:
        trade_state[sym] = {
            "sl": sl, "tp_liste": sinyal["tp_liste"], "tp_index": 0,
            "direction": direction, "entry": price, "qty": qty,
            "kaynak": sinyal.get("kaynak_etiket", "kanal_kopya"),
            "orijinal_qty": qty, "tp_emirleri": [],
        }
    durumu_diske_yaz()

    tp_emirleri = tp_limit_emirlerini_koy(sym, direction, sinyal["tp_liste"], qty)
    with state_lock:
        if sym in trade_state:
            trade_state[sym]["tp_emirleri"] = tp_emirleri
    durumu_diske_yaz()

    kacan_emir_sayisi = sum(1 for e in tp_emirleri if e.get("id") is None)
    ek_uyari = (f"\n{kacan_emir_sayisi} TP seviyesi icin limit emri konulamadi") if kacan_emir_sayisi else ""

    tg(
        f"[ISLEM ACILDI] {sym} {direction.upper()}\n"
        f"Giris={price:.8f} | SL:{sl:.8f}\n"
        f"TP listesi: {sinyal['tp_liste']}\n"
        f"Notional=${notional:.2f}{gozlem_str}{ek_uyari}"
    )


def tp_limit_emirlerini_koy(sym, direction, tp_liste, orijinal_qty):
    emirler = []
    kapama_yon = "sell" if direction == "long" else "buy"
    toplam_tp = len(tp_liste)
    for i, tp_fiyat in enumerate(tp_liste):
        oran = _tp_dilim_orani(i, toplam_tp)
        miktar_ham = orijinal_qty * oran
        try:
            miktar = float(exchange.amount_to_precision(sym, miktar_ham))
            fiyat_hassas = float(exchange.price_to_precision(sym, tp_fiyat)) \
                if hasattr(exchange, "price_to_precision") else tp_fiyat
            if miktar <= 0:
                emirler.append({"id": None, "fiyat": tp_fiyat, "miktar": miktar_ham})
                continue
            emir = exchange.create_limit_order(sym, kapama_yon, miktar, fiyat_hassas,
                                                params={"reduceOnly": True})
            emirler.append({"id": emir.get("id"), "fiyat": tp_fiyat, "miktar": miktar})
        except Exception as e:
            log.warning(f"[TP_EMIR] {sym} TP{i+1} limit emri konulamadi: {e}")
            emirler.append({"id": None, "fiyat": tp_fiyat, "miktar": miktar_ham})
    return emirler


def tp_emirlerini_iptal_et(sym, tp_emirleri, tp_index):
    for i in range(tp_index, len(tp_emirleri)):
        emir_id = tp_emirleri[i].get("id")
        if emir_id:
            try:
                exchange.cancel_order(emir_id, sym)
            except Exception as e:
                log.warning(f"[TP_IPTAL] {sym} TP{i+1} emri iptal edilemedi: {e}")


def _tp_dilim_orani(tp_index, toplam_tp_sayisi):
    if toplam_tp_sayisi == len(TP_DILIM_ORANLARI):
        return TP_DILIM_ORANLARI[tp_index]
    toplam_pay = sum(TP_DILIM_ORANLARI)
    return toplam_pay / toplam_tp_sayisi

# ════════════════════════════════════════════
# POZISYON YONETIMI
# ════════════════════════════════════════════
def manage():
    while True:
        try:
            positions = exchange.fetch_positions()
            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue
                sym = p["symbol"]
                entry = safe(p["entryPrice"])
                direction = "long" if p["side"] == "long" else "short"

                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    entry_guvenlik = entry
                    guvenlik_sl_pct = 0.03
                    sl_guvenlik = entry_guvenlik * (1 - guvenlik_sl_pct) if direction == "long" else entry_guvenlik * (1 + guvenlik_sl_pct)
                    with state_lock:
                        trade_state[sym] = {"sl": sl_guvenlik, "tp_liste": [], "tp_index": 0,
                                             "direction": direction, "entry": entry_guvenlik, "kaynak": "kurtarilan_calisma_zamani"}
                    durumu_diske_yaz()
                    tg(f"UYARI: {sym} icin kayitli durum yoktu - gecici %3 guvenlik SL'i kondu")
                    continue

                t = exchange.fetch_ticker(sym)
                price = safe(t["last"])
                sl = durum["sl"]

                sl_vuruldu = (price <= sl) if direction == "long" else (price >= sl)
                if sl_vuruldu:
                    kapandi_mi = False
                    kapatma_emri = None
                    tp_emirlerini_iptal_et(sym, durum.get("tp_emirleri", []), durum.get("tp_index", 0))
                    try:
                        kapatma_emri = exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                       qty, params={"reduceOnly": True})
                        time.sleep(1)
                        guncel = exchange.fetch_positions([sym])
                        kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)
                    except Exception as e:
                        log.error(f"[STOP] {sym}: {e}")
                    if not kapandi_mi:
                        tg(f"{sym} STOP emri dogrulanamadi, tekrar denenecek")
                        continue
                    gercek_fiyat, komisyon = gercek_dolus_bilgisi_al(kapatma_emri or {}, sym, price)
                    gross = (gercek_fiyat - entry) * qty if direction == "long" else (entry - gercek_fiyat) * qty
                    gross -= komisyon
                    with state_lock:
                        onceki_gerceklesen = trade_state[sym].get("gerceklesen_pnl", 0)
                    toplam_pnl_stop = gross + onceki_gerceklesen
                    gunluk_pnl_ekle(gross)
                    fark_pct = (entry - sl) / entry if direction == "long" else (sl - entry) / entry
                    tampon_sinir = TP1_BREAKEVEN_TAMPON_PCT + 0.0015
                    if fark_pct <= 0:
                        kategori = "kar_kilitli"
                    elif fark_pct <= tampon_sinir:
                        kategori = "tampon"
                    else:
                        kategori = "zarar"
                    if kategori == "tampon" and onceki_gerceklesen > 0:
                        tg(f"STOP (TP1 tampon bolgesinde) {sym} | bu dilim={gross:+.2f}$ | "
                           f"TOPLAM islem PnL={toplam_pnl_stop:+.2f}$")
                    elif kategori == "kar_kilitli":
                        tg(f"STOP (kar kilitleme seviyesinde) {sym} | bu dilim={gross:+.2f}$ | "
                           f"TOPLAM islem PnL={toplam_pnl_stop:+.2f}$")
                    else:
                        tg(f"STOP {sym} | TOPLAM islem PnL={toplam_pnl_stop:+.2f}$")
                    with state_lock:
                        trade_state.pop(sym, None)
                    durumu_diske_yaz()
                    trade_log_kaydet({
                        "symbol": sym, "direction": direction, "entry": entry,
                        "exit": gercek_fiyat, "pnl": toplam_pnl_stop, "sonuc": "STOP",
                        "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    })
                    continue

                tp_liste = durum.get("tp_liste", [])
                tp_index = durum.get("tp_index", 0)
                tp_emirleri = durum.get("tp_emirleri", [])

                if tp_index < len(tp_liste):
                    kayitli_emir = tp_emirleri[tp_index] if tp_index < len(tp_emirleri) else {}
                    emir_id = kayitli_emir.get("id")
                    tp_vuruldu = False
                    emirle_dolmus = False
                    gercek_fiyat = price
                    komisyon = 0.0
                    kapatilacak = kayitli_emir.get("miktar")
                    emir_dogrulanabildi = False
                    if emir_id:
                        try:
                            emir_durum = exchange.fetch_order(emir_id, sym)
                            emir_dogrulanabildi = True
                            durum_str = (emir_durum.get("status") or "").lower()
                            if durum_str in ("closed", "filled"):
                                tp_vuruldu = True
                                emirle_dolmus = True
                                gercek_fiyat = safe(emir_durum.get("average")) or safe(emir_durum.get("price")) or price
                                doldurulan = safe(emir_durum.get("filled"))
                                if doldurulan > 0:
                                    kapatilacak = doldurulan
                                fee = emir_durum.get("fee")
                                if fee:
                                    komisyon = safe(fee.get("cost"))
                        except Exception as e:
                            log.warning(f"[TP_KONTROL] {sym} TP{tp_index+1} emri kontrol edilemedi: {e}")

                    if not tp_vuruldu and not (emir_id and emir_dogrulanabildi):
                        hedef = tp_liste[tp_index]
                        tp_vuruldu = (price >= hedef) if direction == "long" else (price <= hedef)

                    if tp_vuruldu:
                        son_tp = (tp_index == len(tp_liste) - 1)
                        orijinal_qty = durum.get("orijinal_qty", qty)
                        if "orijinal_qty" not in durum:
                            with state_lock:
                                trade_state[sym]["orijinal_qty"] = qty
                            orijinal_qty = qty
                        if kapatilacak is None:
                            oran = _tp_dilim_orani(tp_index, len(tp_liste))
                            kapatilacak = min(orijinal_qty * oran, qty)

                        basarili = True
                        if not emirle_dolmus:
                            basarili = False
                            kapatma_emri = None
                            try:
                                kapatma_emri = exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                               kapatilacak, params={"reduceOnly": True})
                                time.sleep(1)
                                basarili = True
                            except Exception as e:
                                log.error(f"[TP{tp_index+1}] {sym}: {e}")
                            if basarili:
                                gercek_fiyat, komisyon = gercek_dolus_bilgisi_al(kapatma_emri or {}, sym, price)

                        if basarili:
                            gross_dilim = (gercek_fiyat - entry) * kapatilacak if direction == "long" \
                                          else (entry - gercek_fiyat) * kapatilacak
                            gross_dilim -= komisyon
                            gunluk_pnl_ekle(gross_dilim)

                            if tp_index == 0:
                                yeni_sl = entry * (1 - TP1_BREAKEVEN_TAMPON_PCT) if direction == "long" \
                                          else entry * (1 + TP1_BREAKEVEN_TAMPON_PCT)
                            else:
                                yeni_sl = tp_liste[tp_index - 1]
                            mevcut_sl = trade_state[sym]["sl"]
                            sl_iyilesti = (direction == "long" and yeni_sl > mevcut_sl) or \
                                          (direction == "short" and yeni_sl < mevcut_sl)

                            with state_lock:
                                trade_state[sym]["tp_index"] = tp_index + 1
                                trade_state[sym]["gerceklesen_pnl"] = trade_state[sym].get("gerceklesen_pnl", 0) + gross_dilim
                                if sl_iyilesti:
                                    trade_state[sym]["sl"] = yeni_sl
                                if son_tp:
                                    trade_state[sym]["trailing_aktif"] = True
                                    trade_state[sym]["trailing_zirve"] = price
                                    trade_state[sym]["trailing_son_bildirim_zirve"] = price
                                kilitlenen_kar = trade_state[sym]["gerceklesen_pnl"]
                            durumu_diske_yaz()

                            mesaj = (f"TP{tp_index+1} {sym} vuruldu | dilim PnL={gross_dilim:+.2f}$ | "
                                     f"o ana kadar kilitlenen toplam={kilitlenen_kar:+.2f}$")
                            if son_tp:
                                mesaj += " | Kalan buyuk dilim TRAILING moduna gecti"
                            tg(mesaj)

                            if sl_iyilesti:
                                kalan_qty_sonrasi = max(qty - kapatilacak, 0)
                                if tp_index == 0:
                                    maks_ek_risk = abs(entry - yeni_sl) * kalan_qty_sonrasi
                                    tg(f"{sym} STOP artik giris civarinda ({yeni_sl:.8f}) - kilitlenen kar={kilitlenen_kar:+.2f}$ "
                                       f"(bu seviyede vurulursa en fazla ek={maks_ek_risk:.2f}$ kontrollu risk)")
                                else:
                                    ek_kar = (yeni_sl - entry) * kalan_qty_sonrasi if direction == "long" \
                                              else (entry - yeni_sl) * kalan_qty_sonrasi
                                    tg(f"{sym} STOP TP{tp_index} seviyesine ({yeni_sl:.8f}) yukseltildi - ek={ek_kar:+.2f}$")

                elif durum.get("trailing_aktif"):
                    zirve = durum.get("trailing_zirve", entry)
                    if direction == "long":
                        yeni_zirve = max(zirve, price)
                        geri_cekilme_tetiklendi = price <= yeni_zirve * (1 - TRAILING_GERI_CEKILME_PCT)
                    else:
                        yeni_zirve = min(zirve, price)
                        geri_cekilme_tetiklendi = price >= yeni_zirve * (1 + TRAILING_GERI_CEKILME_PCT)

                    if yeni_zirve != zirve:
                        with state_lock:
                            trade_state[sym]["trailing_zirve"] = yeni_zirve
                        durumu_diske_yaz()
                        son_bildirim_zirve = durum.get("trailing_son_bildirim_zirve", entry)
                        if direction == "long":
                            ilerleme_pct = (yeni_zirve - son_bildirim_zirve) / son_bildirim_zirve if son_bildirim_zirve else 0
                            efektif_stop = yeni_zirve * (1 - TRAILING_GERI_CEKILME_PCT)
                        else:
                            ilerleme_pct = (son_bildirim_zirve - yeni_zirve) / son_bildirim_zirve if son_bildirim_zirve else 0
                            efektif_stop = yeni_zirve * (1 + TRAILING_GERI_CEKILME_PCT)
                        if ilerleme_pct >= TRAILING_BILDIRIM_ESIK_PCT:
                            with state_lock:
                                trade_state[sym]["trailing_son_bildirim_zirve"] = yeni_zirve
                            durumu_diske_yaz()
                            tg(f"{sym} TRAILING STOP yukseldi - yeni zirve:{yeni_zirve:.8f}, efektif stop={efektif_stop:.8f}")

                    if geri_cekilme_tetiklendi:
                        kapandi_mi = False
                        kapatma_emri = None
                        tp_emirlerini_iptal_et(sym, durum.get("tp_emirleri", []), durum.get("tp_index", 0))
                        try:
                            kapatma_emri = exchange.create_market_order(sym, "sell" if direction == "long" else "buy",
                                                           qty, params={"reduceOnly": True})
                            time.sleep(1)
                            guncel = exchange.fetch_positions([sym])
                            kapandi_mi = not any(safe(pp.get("contracts")) > 0 for pp in guncel)
                        except Exception as e:
                            log.error(f"[TRAILING] {sym}: {e}")
                        if not kapandi_mi:
                            tg(f"{sym} trailing kapanisi dogrulanamadi, tekrar denenecek")
                            continue
                        gercek_fiyat, komisyon = gercek_dolus_bilgisi_al(kapatma_emri or {}, sym, price)
                        gross_dilim = (gercek_fiyat - entry) * qty if direction == "long" else (entry - gercek_fiyat) * qty
                        gross_dilim -= komisyon
                        gunluk_pnl_ekle(gross_dilim)
                        with state_lock:
                            toplam_pnl = trade_state[sym].get("gerceklesen_pnl", 0) + gross_dilim
                            trade_state.pop(sym, None)
                        durumu_diske_yaz()
                        tg(f"TRAILING kapandi {sym} | son dilim PnL={gross_dilim:+.2f}$ | TOPLAM={toplam_pnl:+.2f}$")
                        trade_log_kaydet({
                            "symbol": sym, "direction": direction, "entry": entry,
                            "exit": gercek_fiyat, "pnl": toplam_pnl, "sonuc": "TRAILING_KAPANDI",
                            "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                        })

            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)

# ════════════════════════════════════════════
# TELEGRAM KOMUTLARI (kisa/komutsuz mesajlar dahil)
# ════════════════════════════════════════════
if bot:
    @bot.message_handler(commands=["manuel"])
    def manuel_sinyal_komutu(msg):
        metin = msg.text.replace("/manuel", "", 1).strip()
        if not metin:
            bot.send_message(msg.chat.id, "Kullanim: /manuel MAGMA LONG")
            return
        sinyal = sinyal_ayristir(metin)
        if not sinyal:
            sinyal = hizli_sinyal_ayristir(metin)
        if not sinyal:
            bot.send_message(msg.chat.id, "Metin hicbir formatta ayristirilamadi.")
            return
        bot.send_message(msg.chat.id, f"Ayristirildi: {sinyal}\nIsleniyor...")
        sinyal["kaynak_etiket"] = "manuel"
        sinyali_isle(sinyal)

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        with state_lock:
            if not trade_state:
                bot.send_message(msg.chat.id, "Acik pozisyon yok.")
                return
            satirlar = ["ACIK POZISYONLAR\n"]
            for sym, d in trade_state.items():
                satirlar.append(f"{sym} [{d['direction'].upper()}] giris:{d['entry']:.8f} "
                                 f"SL:{d['sl']:.8f} TP_index:{d.get('tp_index',0)}/{len(d.get('tp_liste',[]))}")
            bot.send_message(msg.chat.id, "\n".join(satirlar))

    @bot.message_handler(commands=["bakiye"])
    def bakiye_komutu(msg):
        b = gercek_bakiye_al()
        if b is None:
            bot.send_message(msg.chat.id, "Bakiye alinamadi.")
            return
        risk_tutari = b * RISK_YUZDESI
        bot.send_message(msg.chat.id, f"Serbest bakiye: ${b:.2f}\n"
                                       f"Islem basi hedef risk (%{RISK_YUZDESI*100:.0f}): ${risk_tutari:.2f}")

    @bot.message_handler(commands=["ac"])
    def ac_komutu(msg):
        metin = msg.text.replace("/ac", "", 1).strip()
        if not metin:
            bot.send_message(msg.chat.id, "Kullanim: /ac MAGMA LONG")
            return
        sinyal = sinyal_ayristir(metin) or hizli_sinyal_ayristir(metin)
        if not sinyal:
            bot.send_message(msg.chat.id, "Anlasilamadi. Ornek: /ac MAGMA LONG")
            return
        bot.send_message(msg.chat.id, f"Aciliyor: {sinyal['symbol']} {sinyal['direction'].upper()}")
        sinyal["kaynak_etiket"] = "manuel"
        sinyali_isle(sinyal)

    @bot.message_handler(commands=["kapat"])
    def kapat_komutu(msg):
        parca = msg.text.replace("/kapat", "", 1).strip().upper()
        basari, mesaj = _pozisyon_kapat_yardimci(msg.chat.id, parca)
        bot.send_message(msg.chat.id, mesaj)

    def _pozisyon_kapat_yardimci(chat_id, parca):
        with state_lock:
            acik_semboller = list(trade_state.keys())
        if not acik_semboller:
            return False, "Acik pozisyon yok, kapatilacak bir sey bulunamadi."
        hedef_sym = None
        if parca:
            for sym in acik_semboller:
                if parca in sym.upper():
                    hedef_sym = sym
                    break
            if not hedef_sym:
                return False, (f"'{parca}' ile eslesen acik pozisyon bulunamadi. "
                                f"Acik olanlar: {acik_semboller}")
        else:
            if len(acik_semboller) > 1:
                return False, (f"Birden fazla acik pozisyon var, hangisini kastettigini belirt: "
                                f"{acik_semboller}\nOrn: /kapat {acik_semboller[0].split('/')[0]}")
            hedef_sym = acik_semboller[0]
        bot.send_message(chat_id, f"{hedef_sym} kapatiliyor...")
        return manuel_pozisyon_kapat(hedef_sym)

    def komut_metni_ayikla(metin):
        """
        v16.12 GUVENLIK DUZELTMESI: "ac" kelimesi YENIDEN ZORUNLU.
        v16'da bu kelime opsiyonel yapilmisti - ama test edildi ve
        dogrulandi: "btc long term hodl" gibi TAMAMEN SIRADAN sohbet
        cumleleri de "coin+LONG" kalibina uydugu icin GERCEK 10x
        kaldiracli pozisyon ACTIRIYORDU. "ac" zorunlu kilininca, sadece
        net bir acma niyeti tasiyan mesajlar ("btc long ac") isleme
        girer. "kapat" davranisi degismedi - o zaten net bir niyet.
        """
        temiz = metin.strip()
        if not temiz or len(temiz) > KISA_MESAJ_UST_SINIR:
            return None, None
        if re.search(r"\bkapat\b", temiz, re.IGNORECASE):
            sembol_parca = re.sub(r"\bkapat\b", "", temiz, flags=re.IGNORECASE)
            sembol_parca = re.sub(r"\bet\b", "", sembol_parca, flags=re.IGNORECASE).strip().upper()
            return "kapat", sembol_parca
        if not re.search(r"\bac\b", temiz, re.IGNORECASE):
            return None, None
        sinyal = hizli_sinyal_ayristir(temiz)
        if sinyal:
            return "ac", sinyal
        return None, None

    @bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
    def komutsuz_hizli_giris(msg):
        """
        "edge long ac"  -> EDGE LONG acar ("ac" ZORUNLU - v16.12)
        "edge kapat"    -> EDGE pozisyonunu kapatir
        "kapat"         -> tek acik pozisyon varsa onu kapatir
        """
        tur, veri = komut_metni_ayikla(msg.text)
        if tur == "kapat":
            basari, mesaj = _pozisyon_kapat_yardimci(msg.chat.id, veri)
            bot.send_message(msg.chat.id, mesaj)
            return
        if tur == "ac":
            sinyal = veri
            bot.send_message(msg.chat.id, f"Hizli giris algilandi: {sinyal['symbol']} {sinyal['direction'].upper()}")
            sinyal["kaynak_etiket"] = "manuel"
            sinyali_isle(sinyal)
            return


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
            time.sleep(5)


# ════════════════════════════════════════════
# TELEGRAM KANAL DINLEME (Telethon)
# ════════════════════════════════════════════
telethon_client = TelegramClient(StringSession(TG_STRING_SESSION), TG_API_ID, TG_API_HASH)


@telethon_client.on(events.NewMessage(chats=KANAL_KULLANICI_ADI))
async def yeni_mesaj_geldi(event):
    metin = event.raw_text
    log.info(f"[KANAL] Yeni mesaj alindi: {metin[:80]}...")
    sinyal = sinyal_ayristir(metin)
    if not sinyal:
        log.info("[KANAL] Mesaj sinyal olarak ayristirilamadi, atlandi")
        return
    tg(f"Kanal sinyali algilandi: {sinyal['symbol']} {sinyal['direction'].upper()}")
    sinyali_isle(sinyal)


def telethon_baslat():
    telethon_client.start()
    log.info("[TELETHON] Kanal dinleme basladi")
    telethon_client.run_until_disconnected()


# ════════════════════════════════════════════
# WEB PANEL
# ════════════════════════════════════════════
def panel_html_olustur():
    with log_lock:
        gecmis = list(trade_log)
    toplam = len(gecmis)
    if toplam == 0:
        icerik_ozet = "<p style='color:#888'>Henuz kapanan islem yok.</p>"
        grafik_svg = ""
        liste_html = ""
    else:
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        kaybeden = [t for t in gecmis if t["pnl"] <= 0]
        net_toplam = sum(t["pnl"] for t in gecmis)
        kazanma_orani = len(kazanan) / toplam * 100
        ort_kazanan = sum(t["pnl"] for t in kazanan) / len(kazanan) if kazanan else 0
        ort_kaybeden = sum(t["pnl"] for t in kaybeden) / len(kaybeden) if kaybeden else 0
        basabas_oran = abs(ort_kaybeden) / (abs(ort_kaybeden) + ort_kazanan) * 100 if (ort_kazanan + abs(ort_kaybeden)) > 0 else 0
        renk_net = "#00e08a" if net_toplam >= 0 else "#ff4d6d"
        icerik_ozet = f"""
        <div class="grid">
          <div class="kart"><div class="etiket">NET TOPLAM</div>
            <div class="deger" style="color:{renk_net}">{net_toplam:+.2f}$</div></div>
          <div class="kart"><div class="etiket">KAZANMA ORANI</div>
            <div class="deger">%{kazanma_orani:.1f}</div></div>
          <div class="kart"><div class="etiket">KAZANAN ({len(kazanan)})</div>
            <div class="deger" style="color:#00e08a">ort {ort_kazanan:+.2f}$</div></div>
          <div class="kart"><div class="etiket">KAYBEDEN ({len(kaybeden)})</div>
            <div class="deger" style="color:#ff4d6d">ort {ort_kaybeden:+.2f}$</div></div>
        </div>
        <div class="kart" style="margin-top:12px">
          <span class="etiket">Basa bas icin gereken kazanma orani</span>
          <span class="deger" style="float:right;color:#ff4d6d">%{basabas_oran:.1f}</span>
        </div>
        """
        kumulatif = []
        toplam_su_an = 0
        for t in gecmis:
            toplam_su_an += t["pnl"]
            kumulatif.append(toplam_su_an)
        genislik, yukseklik = 700, 200
        if len(kumulatif) > 1:
            min_v, max_v = min(kumulatif), max(kumulatif)
            aralik = (max_v - min_v) or 1
            noktalar = []
            for i, v in enumerate(kumulatif):
                x = i / (len(kumulatif) - 1) * genislik
                y = yukseklik - ((v - min_v) / aralik * yukseklik)
                noktalar.append(f"{x:.1f},{y:.1f}")
            svg_puan = " ".join(noktalar)
            grafik_svg = f"""
            <div class="kart" style="margin-top:12px">
              <div class="etiket">KUMULATIF NET PNL</div>
              <svg viewBox="0 0 {genislik} {yukseklik}" style="width:100%;height:180px">
                <polyline fill="none" stroke="#4da3ff" stroke-width="2" points="{svg_puan}" />
              </svg>
            </div>
            """
        else:
            grafik_svg = ""
        satirlar = []
        for t in reversed(gecmis[-100:]):
            renk = "#00e08a" if t["pnl"] > 0 else "#ff4d6d"
            satirlar.append(f"""
            <div class="islem-satir">
              <div><b>{t['symbol'].split('/')[0]}</b>
                <span class="rozet">{t['direction'].upper()}</span>
                <span class="rozet" style="background:#333">{t.get('sonuc','?')}</span></div>
              <div style="color:{renk}">{t['pnl']:+.2f}$</div>
            </div>
            <div style="color:#888;font-size:12px">{t.get('zaman','')}</div>
            """)
        liste_html = "".join(satirlar)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sinyal Kopya Botu - Panel</title>
<style>
body {{ background:#0d0d12; color:#eee; font-family:-apple-system,sans-serif; padding:16px; margin:0; }}
.baslik {{ color:#888; font-size:13px; letter-spacing:2px; text-transform:uppercase; }}
h1 {{ margin:4px 0 16px 0; font-size:28px; }}
.rozet-mod {{ background:#3a2a00; color:#ffb300; padding:8px 14px; border-radius:8px; display:inline-block; margin-bottom:16px; font-weight:600; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.kart {{ background:#16161f; border-radius:12px; padding:16px; }}
.etiket {{ color:#888; font-size:12px; letter-spacing:1px; text-transform:uppercase; }}
.deger {{ font-size:28px; font-weight:700; margin-top:6px; }}
.islem-satir {{ display:flex; justify-content:space-between; padding:10px 0 2px 0; border-top:1px solid #222; font-size:15px; }}
.rozet {{ background:#222; padding:2px 8px; border-radius:6px; font-size:11px; margin-left:6px; }}
</style></head>
<body>
  <div class="baslik">SINYAL KOPYA BOTU</div>
  <h1>Performans Paneli</h1>
  <div class="rozet-mod">GERCEK PARA - @{KANAL_KULLANICI_ADI} kanalindan kopyalaniyor</div>
  <p style="color:#888">{len(trade_log)} kapanan islem</p>
  {icerik_ozet}
  {grafik_svg}
  <h3 style="margin-top:24px;color:#888">ISLEM GECMISI (yeniden eskiye, son 100)</h3>
  {liste_html}
</body></html>"""


def panel_sunucu_baslat():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/panel", "/panel/"):
                icerik = panel_html_olustur().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(icerik)
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
        def log_message(self, *args):
            pass
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


# ════════════════════════════════════════════
# BASLANGIC
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("TELEGRAM SINYAL KOPYALAMA BOTU (v16.12) BASLIYOR...")
    durumu_diskten_yukle()
    trade_log_yukle()
    durumu_telegramdan_yukle()
    acilista_pozisyonlari_dogrula()
    acik_pozisyonlara_kademeli_sl_uygula()

    threading.Thread(target=manage, daemon=True).start()
    threading.Thread(target=gunluk_reset_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    threading.Thread(target=panel_sunucu_baslat, daemon=True).start()
    threading.Thread(target=teyit_bekleme_loop, daemon=True).start()
    threading.Thread(target=oz_tarama_loop, daemon=True).start()

    baslangic_bakiye = gercek_bakiye_al()
    bakiye_str = f"${baslangic_bakiye:.2f}" if baslangic_bakiye is not None else "alinamadi"

    tg(
        "TELEGRAM SINYAL KOPYALAMA BOTU\n"
        "VERSIYON: v16.12 (risk-bazli pozisyon + likidite kontrolu + guvenli komut ayristirma)\n\n"
        f"Gercek bakiye: {bakiye_str} | Kaldirac: {LEV}x\n"
        f"Islem basi risk: bakiyenin %{RISK_YUZDESI*100:.0f}'i (tavan: bakiyenin {MAKS_KALDIRAC_CARPANI}x'i notional)\n"
        f"Asgari 24s hacim (islem acma sarti): ${MIN_HACIM_USDT_ISLEM_ACMA:,.0f}\n"
        f"Dinlenen kanal: @{KANAL_KULLANICI_ADI}\n"
        f"Oz tarama: {'AKTIF' if OZ_TARAMA_AKTIF else 'KAPALI'} "
        f"(her {OZ_TARAMA_ARALIK_DK} dk, en likit {OZ_TARAMA_WATCHLIST_BOYUTU} coin, "
        f"ayni MAX_POS={MAX_POS} havuzunu paylasir)\n"
        f"Gunluk zarar limiti: ${MAX_GUNLUK_ZARAR}\n"
        f"Teyit bekleme suresi: {TEYIT_BEKLEME_DAKIKA} dk\n\n"
        "Bu kanalin gecmis performansi dogrulanmadi. Bu kod kar garantisi vermez.\n"
        "Hizli komutlar: 'edge long ac', 'edge short ac', 'edge kapat' ('ac' kelimesi artik ZORUNLU)"
    )

    telethon_baslat()
