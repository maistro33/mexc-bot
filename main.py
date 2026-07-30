#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
SCALP BOT v3.1 — 30 Temmuz 2026
5m/15m/1h çoklu zaman dilimi, SADECE LONG, o an pump yapan coinleri
DİNAMİK olarak bulur (sabit coin listesi YOK — her taramada borsanın
TAMAMI taranır, RWA/tokenize hisse ve durgun majörler hariç).
════════════════════════════════════════════════════════
⚠️ ÖNEMLİ DÜRÜSTLÜK NOTU: HİÇBİR TP/SL AYARI KÂRI GARANTİ ETMEZ.
Aşağıdaki ayarlar geçmiş veride (60 likit coin, 15 gün, 5m mumlar,
gerçek Bitget verisi, komisyon dahil, bar-by-bar simülasyon) pozitif
edge gösterdi, ama örneklem küçük (131 işlem) ve gelecekte aynı
performansı vermesi garanti değildir:
  - SL = 2.0×ATR(5m,14)
  - TP kademeli: %30 pozisyon @1R, %30 @2R, %40 @3R
  - İlk TP (1R) vurunca kalan pozisyonun SL'i BAŞABAŞA (girişe) çekilir
    - bu "garanti kâr" değildir, ama o andan sonra en kötü ihtimalle
    sıfır zararla kapanmayı sağlar (borsa kayması/gap riski hariç)
  - Backtest: 131 işlem, %58.0 kazanma, +25.78R toplam, +0.197R/işlem
    ortalama, İKİ ZAMAN YARISINDA DA pozitif (11.1R / 14.7R)
  - Karşılaştırma: tek TP (RR=1.0) aynı veri setinde sadece +0.063R/işlem
    verdi - kademeli TP burada AÇIKÇA daha iyi (1h'deki ana pullback
    botunun aksine - orada kademeli TP kaybediyordu, stratejiye göre
    değişiyor, kör kör kopyalanmadı)

DİNAMİK COİN TARAMA MANTIĞI:
Sabit bir coin listesi YOK. Her tarama turunda:
  1) exchange.fetch_tickers() ile TÜM USDT-M perpetual coinlerin 24s
     hacim/değişim bilgisi TEK istekte alınır (hızlı, ~700+ coin)
  2) RWA (isRwa=YES, tokenize hisse/emtia) ve durgun majörler
     (BTC/ETH/XRP/ADA/DOGE/BNB/TRX/LINK/LTC/BCH) elenir
  3) Kalanlardan hacim/hareket bazlı ön eleme ile en "canlı" ~80 aday
     seçilir (700+ coinin hepsinin 5m mumuna bakmak çok yavaş/rate-limit
     riskli olurdu)
  4) Sadece bu adayların 5m mumlarına bakılıp GERÇEK pump sinyali
     (hacim spike + kısa vadeli fiyat sıçraması) doğrulanır

COOLDOWN: Bir coin kapandıktan sonra (kâr/zarar fark etmeksizin) 1 SAAT
boyunca tekrar açılmaz - kullanıcı talebiyle eklendi, "kârı aldı hemen
tekrar açma" sorununu önlemek için.
"""

import os
import time
import json
import logging
import threading
import ccxt
import telebot
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("SCALP_BOT")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY = os.getenv("BITGET_API", "")
API_SEC = os.getenv("BITGET_SEC", "")
PASSPHRASE = os.getenv("BITGET_PASS", "")

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni eksik.")
if not CHAT_ID:
    raise RuntimeError("MY_CHAT_ID ortam değişkeni eksik - yetki kontrolü için ZORUNLU.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None


def tg(msg):
    if not bot or not CHAT_ID:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


def yetkili_mi(msg_or_call):
    try:
        chat_id = msg_or_call.message.chat.id if hasattr(msg_or_call, "message") else msg_or_call.chat.id
    except Exception:
        return False
    if chat_id != CHAT_ID:
        log.warning(f"[YETKISIZ ERISIM] chat_id={chat_id}")
        return False
    return True


# ── DURGUN/SLUGGISH MAJÖRLER — dinamik taramada bilerek elenir ──
SLUGGISH_BASE = {"BTC", "ETH", "XRP", "ADA", "DOGE", "BNB", "TRX", "LINK", "LTC", "BCH"}

# ── SİNYAL PARAMETRELERİ (backtest doğrulamalı, bkz. üstteki not) ──
VOL_SPIKE_MULT = 4.0        # 5m hacim, 20-bar ortalamasının kaç katı olmalı
RET_WINDOW_BARS = 3         # kaç 5m bar'lık getiriye bakılıyor (3x5dk=15dk)
RET_THRESHOLD = 0.025       # %2.5 hareket eşiği
ADX_ESIK_15M = 15
COOLDOWN_SAAT = float(os.getenv("COOLDOWN_SAAT", "1"))   # v1.0: kullanıcı talebiyle 1 saat
MAX_HOLD_SAAT = 3.0         # bu süreden uzun açık kalan pozisyon piyasa fiyatından kapatılır

# v1.1 YENİ: SÜRDÜRÜLEBİLİR TIRMANIŞ sinyali (VANRY örneği üzerine eklendi).
# Ani-patlama sinyali (yukarıdaki VOL_SPIKE_MULT vb.) sadece TEK bir 5m mumda
# hacim+fiyat sıçraması arıyor - VANRY gibi saatler süren, kademeli, tek mumda
# patlamayan ama toplamda güçlü tırmanışları KAÇIRIYORDU. Bu ikinci sinyal 15m
# bazlı: son 1.5 saatte %4+ hareket VE hafifçe yükselmiş (1.2x) sürekli hacim
# arıyor - tek büyük spike değil, süreklilik. Backtest (60 coin, 15 gün, 15m
# bar): 144 işlem, %57.7 kazanma, +30.7R, ort +0.206R/işlem, iki yarıda da
# dengeli pozitif (15.0R/14.7R). ⚠️ DÜRÜSTLÜK NOTU: bu parametre noktası
# komşularına göre HASSAS (ör. eşik %4 yerine %3.5 veya %4.5 yapılınca sonuç
# belirgin kötüleşiyor) - hafif overfitting riski var, bu yüzden ANİ-PATLAMA
# sinyalinin YERİNE değil YANINA eklendi, riski tek sinyale bağlamamak için.
SUSTAINED_RET_WINDOW_BARS = 6   # 15m x 6 = 1.5 saat
SUSTAINED_RET_THRESHOLD = 0.04  # %4 hareket
SUSTAINED_VOL_RATIO_THRESH = 1.2
SUSTAINED_ADX_ESIK = 15
SUSTAINED_ZIRVE_MESAFE_MIN = float(os.getenv("SUSTAINED_ZIRVE_MESAFE_MIN", "0.03"))
# v2.1: ESP örneği - fiyat son 2 saatin zirvesine bu orandan daha yakınsa
# sürdürülebilir tırmanış sinyali ARANMAZ (dönüş riski yüksek). Backtest:
# %3 eşiği ile kazanma %59->%71, ort R/işlem +0.206->+0.388 (komşu eşiklerde
# de tutarlı iyileşme görüldü, tek noktaya özgü değil).

ATR_CARPANI_SL = 2.0        # backtest: en dengeli SL çarpanı bu çıktı
# v1.3 YENİ: SL/TP TAVANI. COTI örneğinde görüldü - bir coin dev tek mumla
# pump yapınca, o mum 14 periyotluk ATR penceresine girip ATR'yi geçici
# olarak şişiriyor (tek anomali barı "normal volatilite" sanılıyor). Bu da
# SL mesafesini (ve orantılı olarak TÜM TP hedeflerini) gerçekçi olmayan
# şekilde genişletiyor - COTI'de SL %10.6, TP3 günün zirvesinin %17.7
# ÜSTÜNDEYDİ (neredeyse imkansız bir hedef). Dolar risk sistem tarafından
# zaten sabit tutuluyordu (pozisyon küçültülerek), ama TP'lere ulaşma
# olasılığı düşüyordu. Bu tavan, ATR ne kadar şişerse şişsin SL mesafesini
# (ve TP'leri) fiyatın belirli bir yüzdesiyle sınırlıyor.
MAX_SL_PCT = float(os.getenv("MAX_SL_PCT", "0.06"))  # SL mesafesi fiyatın en fazla %6'sı olabilir
MIN_SL_PCT = float(os.getenv("MIN_SL_PCT", "0.02"))
# v3.1 YENİ: GIGGLE örneği - aşırı ince likiditeli/volatil bir coinde ATR
# gerçek volatiliteyi yakalayamadı, SL sadece %1.42 çıktı ve 25 SANİYEDE
# whipsaw ile vuruldu. Backtest (60 coin, 15 gün): SL mesafesine %2.0 minimum
# taban eklenince ort R/işlem +0.141 -> +0.190 (iki zaman yarısında da güçlü
# tutarlı iyileşme, 14.8R/27.0R). ATR ne kadar dar hesaplarsa hesaplasın,
# SL artık en az fiyatın %2'si kadar mesafede olacak.
# v2.7 DÜZELTME: çoklu-aşama TP sistemi (v2.5) KALDIRILDI. Kullanıcı geri
# bildirimi: "kasa büyütme" adına sıkıştırılan TP'ler (0.5R/1R/2R) backtest'te
# zaten ZAYIF çıkmıştı (ort +0.05R/işlem), oysa aşağıdaki tek yapı (1R/2R/3R)
# +0.197R/işlem veriyordu - kasa büyütmenin matematiği "sık kazan" değil
# "toplam R'yi maksimize et". Çoklu aşama sistemi de kafa karıştırıcıydı.
# Artık TEK, backtest doğrulamalı TP yapısı kullanılıyor.
TIERED_TP = [(0.30, 1.0), (0.30, 2.0), (0.40, 3.0)]  # backtest: 131 işlem/15gün,
# %58 kazanma, ort +0.197R/işlem, iki zaman yarısında da pozitif ve tutarlı.

ADAY_HAVUZU_BUYUKLUGU = int(os.getenv("ADAY_HAVUZU_BUYUKLUGU", "40"))
# v1.5 DÜZELTME: 80 iken tam tarama ~60sn sürüyordu (ölçüldü) - bu da
# KONTROL_ARALIGI_SN (60sn) ile neredeyse eşit, yani "hemen aç" tam tersi
# oluyordu: erken bulunan sinyal, tarama bitene kadar bekliyordu. 40'a
# düşürülüp AŞAĞIDAKİ "bulunca hemen aç" mantığıyla birleştirildi.
GOSTERGE_MUM_5M = 60
GOSTERGE_MUM_15M = 40

# ── RİSK/GÜVENLİK AYARLARI ──
LEV_HAM_DEGER = os.getenv("LEV")
LEV = int(LEV_HAM_DEGER) if LEV_HAM_DEGER else 10
RISK_PCT_BAKIYE = float(os.getenv("RISK_PCT_BAKIYE", "0.10"))
# v2.9: kullanıcı talebiyle %5'ten %10'a çıkarıldı - daha büyük marj/pozisyon
# ve dolayısıyla TP'lerde daha büyük $ kazanç için. SL mesafesine göre otomatik
# ölçeklendiği için risk oranı yine de tutarlı kalıyor (sabit $ marjdan farklı
# olarak) - sadece o oran büyüdü.
MAX_POS = int(os.getenv("MAX_POS", "2"))
GUNLUK_ZARAR_LIMIT_PCT = 0.15
HAFTALIK_ZARAR_LIMIT_PCT = float(os.getenv("HAFTALIK_ZARAR_LIMIT_PCT", "0.25"))
KONTROL_ARALIGI_SN = 60     # scalp - 5m mumları yakalamak için sık tarama

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/scalp_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/scalp_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/scalp_log.json")
GUNLUK_PATH = os.getenv("GUNLUK_PATH", "/data/scalp_gunluk.json")

trade_state = {}
state_lock = threading.Lock()
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()

gunluk_pnl = 0.0
gunluk_baslangic_bakiye = None
gunluk_gun_damgasi = None
haftalik_pnl = 0.0
haftalik_baslangic_bakiye = None
haftalik_hafta_damgasi = None
gunluk_lock = threading.Lock()

# v3.0 YENİ: ANİ PATLAMA sinyali için GİRİŞ TEYİDİ. Kullanıcı gözlemi (COTI,
# VELVET, UB, EUL) - sinyal anında piyasa emriyle HEMEN girmek, çoğu zaman
# spike mumunun TEPESİNE yakın bir fiyattan giriyordu, hemen ardından geri
# çekilme geliyordu. Backtest (60 coin, 15 gün, 5m): sinyalden 1 bar (5dk)
# sonra, EĞER fiyat o sürede sinyal anındaki seviyenin %1'inden fazla geri
# çekilmediyse gir, çekildiyse sinyali İPTAL ET - ort +0.146R/işlem'den
# +0.179R/işlem'e çıktı (iki zaman yarısında da tutarlı, 12.1R/14.2R).
# Sürdürülebilir tırmanış sinyaline uygulanmadı (farklı bir mantığı var,
# zaten kendi zirve-mesafe filtresi mevcut).
CONFIRM_BEKLEME_SN = 300
CONFIRM_MAX_RETRACE_PCT = 0.01
bekleyen_sinyaller = {}  # sym -> {sinyal_fiyat, atr, skor, tur, zaman}


# ════════════════════════════════════════════
# ATOMİK DOSYA YAZMA
# ════════════════════════════════════════════
def atomik_yaz(path, veri):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(veri, f)
        os.replace(tmp, path)
    except Exception as e:
        log.warning(f"[ATOMIK_YAZ] {path}: {e}")


def guvenli_oku(path, varsayilan):
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"[OKU] {path}: {e}")
    return varsayilan


def durumu_diske_yaz():
    with state_lock:
        veri = dict(trade_state)
    atomik_yaz(TRADE_STATE_PATH, veri)


def durumu_diskten_yukle():
    global trade_state
    trade_state = guvenli_oku(TRADE_STATE_PATH, {})


def cooldown_diske_yaz():
    with cooldown_lock:
        veri = dict(son_kapanis_zamani)
    atomik_yaz(COOLDOWN_PATH, veri)


def cooldown_diskten_yukle():
    global son_kapanis_zamani
    son_kapanis_zamani = guvenli_oku(COOLDOWN_PATH, {})


def trade_log_kaydet(kayit):
    with log_lock:
        trade_log.append(kayit)
        veri = list(trade_log)
    atomik_yaz(TRADE_LOG_PATH, veri)


def trade_log_yukle():
    global trade_log
    trade_log = guvenli_oku(TRADE_LOG_PATH, [])


def gunluk_haftalik_diske_yaz():
    with gunluk_lock:
        veri = {
            "gunluk_pnl": gunluk_pnl, "gunluk_baslangic_bakiye": gunluk_baslangic_bakiye,
            "gunluk_gun_damgasi": gunluk_gun_damgasi,
            "haftalik_pnl": haftalik_pnl, "haftalik_baslangic_bakiye": haftalik_baslangic_bakiye,
            "haftalik_hafta_damgasi": haftalik_hafta_damgasi,
        }
    atomik_yaz(GUNLUK_PATH, veri)


def gunluk_haftalik_diskten_yukle():
    global gunluk_pnl, gunluk_baslangic_bakiye, gunluk_gun_damgasi
    global haftalik_pnl, haftalik_baslangic_bakiye, haftalik_hafta_damgasi
    veri = guvenli_oku(GUNLUK_PATH, {})
    gunluk_pnl = veri.get("gunluk_pnl", 0.0)
    gunluk_baslangic_bakiye = veri.get("gunluk_baslangic_bakiye")
    gunluk_gun_damgasi = veri.get("gunluk_gun_damgasi")
    haftalik_pnl = veri.get("haftalik_pnl", 0.0)
    haftalik_baslangic_bakiye = veri.get("haftalik_baslangic_bakiye")
    haftalik_hafta_damgasi = veri.get("haftalik_hafta_damgasi")


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_ = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr_.replace(0, 1e-9)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr_.replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return dx.rolling(period).mean()


def get_df(sym, tf, limit=60):
    """Son (kapanmamış) mumu atar - sadece kapanmış mumlarla çalışır."""
    for deneme in range(3):
        try:
            candles = exchange.fetch_ohlcv(sym, tf, limit=limit + 1)
            if not candles or len(candles) < 2:
                return None
            candles = candles[:-1]
            df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
            time.sleep(0.08)
            return df
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                time.sleep(1.5 * (deneme + 1))
                continue
            log.warning(f"[VERI] {sym} {tf}: {e}")
            return None
    return None


# ════════════════════════════════════════════
# AJAN 1: PİYASA İZLEYİCİ — dinamik coin havuzu + sinyal tespiti
# ════════════════════════════════════════════
_market_cache = {"markets": None, "ts": 0}


def market_bilgisi_al():
    """isRwa bayrağını okumak için market listesini önbelleğe alır (1 saatte bir yeniler)."""
    if _market_cache["markets"] is None or (time.time() - _market_cache["ts"]) > 3600:
        try:
            _market_cache["markets"] = exchange.load_markets()
            _market_cache["ts"] = time.time()
        except Exception as e:
            log.warning(f"[MARKET_BILGI] {e}")
    return _market_cache["markets"] or {}


def sembol_max_kaldirac(sym, istenen_lev):
    """v1.2 YENİ: her coin için Bitget'in izin verdiği MAX kaldıraç farklı
    olabilir (özellikle küçük/yeni coinlerde 5x, 3x hatta 1x'e kadar düşebilir -
    BTW örneğinde görüldüğü gibi 'Exceeded the maximum settable leverage'
    hatası). Körü körüne istenen kaldıracı göndermek yerine, önce borsanın
    o sembol için verdiği limiti okuyup istenenle kıyaslıyoruz, düşük olanı
    kullanıyoruz. Bu sayede hem hata mesajı önleniyor hem de gerçek kullanılan
    kaldıraç, pozisyon büyüklüğü hesabıyla tutarlı kalıyor."""
    markets = market_bilgisi_al()
    m = markets.get(sym)
    if not m:
        return istenen_lev
    max_lev = (m.get("limits", {}) or {}).get("leverage", {}).get("max")
    if max_lev is None:
        return istenen_lev
    return min(istenen_lev, int(max_lev))


def piyasa_izleyici_aday_havuzu():
    """AJAN 1 - ADIM A: borsanın TAMAMINI tek istekte tarar, RWA/durgun majörleri
    eler, hacim+hareket bazlı en 'canlı' ADAY_HAVUZU_BUYUKLUGU coini döner.
    Sabit coin listesi YOK - bu fonksiyon her turda güncel piyasayı okur."""
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
        return []

    markets = market_bilgisi_al()
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE:
            continue
        m = markets.get(sym)
        if m and m.get("info", {}).get("isRwa") == "YES":
            continue
        vol = t.get("quoteVolume") or 0
        if vol < 300000:  # asgari likidite (slippage riskini sınırlamak için)
            continue
        chg = t.get("percentage")
        if chg is None:
            continue
        # "canlılık" skoru: mutlak 24s değişim x hacmin log'u (çok küçük coinlerin
        # sadece hacminden dolayı öne çıkmasını, çok büyük coinlerin de sadece
        # hacminden dolayı domine etmesini dengelemek için)
        skor = abs(chg) * np.log10(max(vol, 10))
        adaylar.append((sym, skor))

    adaylar.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in adaylar[:ADAY_HAVUZU_BUYUKLUGU]]


def piyasa_izleyici_sinyal_kontrol(sym, btc_bullish):
    """AJAN 1 - ADIM B: bir adayın 5m+15m verisine bakıp gerçek pump sinyali
    olup olmadığını doğrular. Sinyal varsa AJAN 2'ye (islem_acici) iletilecek
    bir sözlük döner."""
    df5 = get_df(sym, "5m", GOSTERGE_MUM_5M)
    if df5 is None or len(df5) < 25:
        return None

    df5["vol_ma20"] = df5["volume"].rolling(20).mean()
    df5["vol_ratio"] = df5["volume"] / df5["vol_ma20"].replace(0, np.nan)
    df5["ret_win"] = df5["close"].pct_change(RET_WINDOW_BARS)
    df5["atr"] = atr(df5, 14)

    row = df5.iloc[-1]
    if pd.isna(row["vol_ratio"]) or pd.isna(row["ret_win"]) or pd.isna(row["atr"]) or row["atr"] <= 0:
        return None

    is_pump = row["vol_ratio"] >= VOL_SPIKE_MULT and row["ret_win"] >= RET_THRESHOLD
    if not is_pump:
        return None

    # 15m trend teyidi
    df15 = get_df(sym, "15m", GOSTERGE_MUM_15M)
    if df15 is None or len(df15) < 25:
        return None
    df15["ma20"] = df15["close"].rolling(20).mean()
    df15["adx"] = adx(df15, 14)
    row15 = df15.iloc[-1]
    if pd.isna(row15["ma20"]) or pd.isna(row15["adx"]):
        return None
    if not (row15["close"] > row15["ma20"] and row15["adx"] >= ADX_ESIK_15M):
        return None

    if not btc_bullish:
        return None

    fiyat = row["close"]
    atr_val = row["atr"]
    skor = row["ret_win"] * row["vol_ratio"]
    return {"symbol": sym, "entry": fiyat, "atr": atr_val, "skor": skor, "tur": "spike"}


def piyasa_izleyici_sustained_sinyal_kontrol(sym, btc_bullish):
    """AJAN 1 - v1.1 YENİ: 'yavaş yanan' sürdürülebilir tırmanışları yakalar
    (VANRY örneği). Ani-patlama sinyalinden (yukarıdaki fonksiyon) BAĞIMSIZ
    çalışır, aynı aday havuzunda taranır. Sinyal tipi 'sustained' olarak
    etiketlenir ki Telegram mesajlarında hangi mantıkla açıldığı belli olsun.

    v2.1 DÜZELTME: ESP örneğinde görüldü - bu sinyal geriye bakan göstergelere
    (MA20, ADX, 1.5 saatlik getiri) dayandığı için, fiyat TAM TEPE YAPIP
    DÖNMEYE BAŞLADIKTAN sonra bile birkaç mum boyunca 'hâlâ güçlü tırmanış'
    gibi görünebiliyor - göstergeler geçmişe bakıyor, henüz dönüşü fark
    etmiyor. Backtest (60 coin, 15 gün, 15m bar) bunu doğruladı: sinyal
    fiyatının son 2 saatin (8x15dk) zirvesine YAKIN olduğu durumlar filtrelenip
    çıkarılınca performans belirgin iyileşti:
      - Filtresiz: 144 işlem, %59.0 kazanma, ort +0.206R/işlem
      - Zirveye >%3 uzak şartı: 76 işlem, %71.1 kazanma, ort +0.388R/işlem
        (komşu eşiklerde de - %2.5→+0.354, %3.5→+0.324 - tutarlı, tek
        noktaya özgü bir tesadüf değil)
    Yani artık: sinyal anındaki fiyat, son 2 saatin zirvesinin en az %3
    ALTINDA olmalı - tam tepeye yakın girişler (ESP'deki gibi) elenir."""
    df15 = get_df(sym, "15m", GOSTERGE_MUM_15M)
    if df15 is None or len(df15) < 30:
        return None

    df15["ma20"] = df15["close"].rolling(20).mean()
    df15["adx"] = adx(df15, 14)
    df15["atr"] = atr(df15, 14)
    df15["vol_ma20"] = df15["volume"].rolling(20).mean()
    df15["vol_ma6"] = df15["volume"].rolling(6).mean()
    df15["vol_ratio_sustained"] = df15["vol_ma6"] / df15["vol_ma20"].replace(0, np.nan)
    df15["ret_6bar"] = df15["close"].pct_change(SUSTAINED_RET_WINDOW_BARS)
    df15["zirve_2sa"] = df15["high"].rolling(8).max()

    row = df15.iloc[-1]
    if pd.isna(row["ma20"]) or pd.isna(row["adx"]) or pd.isna(row["atr"]) or row["atr"] <= 0:
        return None
    if pd.isna(row["ret_6bar"]) or pd.isna(row["vol_ratio_sustained"]):
        return None

    trend_ok = row["close"] > row["ma20"] and row["adx"] >= SUSTAINED_ADX_ESIK
    momentum_ok = row["ret_6bar"] >= SUSTAINED_RET_THRESHOLD
    volume_ok = row["vol_ratio_sustained"] >= SUSTAINED_VOL_RATIO_THRESH
    if not (trend_ok and momentum_ok and volume_ok):
        return None

    if pd.isna(row["zirve_2sa"]) or row["zirve_2sa"] <= 0:
        return None
    zirve_mesafe = (row["zirve_2sa"] - row["close"]) / row["zirve_2sa"]
    if zirve_mesafe < SUSTAINED_ZIRVE_MESAFE_MIN:
        return None  # fiyat zirveye cok yakin - dönüş riski yüksek, girme

    if not btc_bullish:
        return None

    return {"symbol": sym, "entry": row["close"], "atr": row["atr"],
            "skor": row["ret_6bar"], "tur": "sustained"}


def btc_1h_bullish():
    df = get_df("BTC/USDT:USDT", "1h", 40)
    if df is None or len(df) < 25:
        return None
    ma20 = df["close"].rolling(20).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma20):
        return None
    return fiyat > ma20


# ════════════════════════════════════════════
# HESAP / RİSK YARDIMCI FONKSİYONLAR
# ════════════════════════════════════════════
def gercek_bakiye_al():
    try:
        bakiye = exchange.fetch_balance()
        return safe(bakiye.get("USDT", {}).get("free", 0))
    except Exception as e:
        log.warning(f"[BAKIYE] {e}")
        return None


def gun_damgasi():
    return time.strftime("%Y-%m-%d", time.gmtime())


def hafta_damgasi():
    t = time.gmtime()
    return f"{t.tm_year}-W{time.strftime('%W', t)}"


def gunluk_haftalik_reset_kontrol():
    global gunluk_pnl, gunluk_baslangic_bakiye, gunluk_gun_damgasi
    global haftalik_pnl, haftalik_baslangic_bakiye, haftalik_hafta_damgasi
    bugun = gun_damgasi()
    bu_hafta = hafta_damgasi()
    degisti = False
    with gunluk_lock:
        if gunluk_gun_damgasi != bugun:
            bakiye = gercek_bakiye_al()
            if bakiye is not None:
                gunluk_pnl = 0.0; gunluk_baslangic_bakiye = bakiye; gunluk_gun_damgasi = bugun
                degisti = True
                tg(f"🔄 Yeni gün, günlük zarar limiti sıfırlandı (bakiye: {bakiye:.2f}$)")
        if haftalik_hafta_damgasi != bu_hafta:
            bakiye = gercek_bakiye_al()
            if bakiye is not None:
                haftalik_pnl = 0.0; haftalik_baslangic_bakiye = bakiye; haftalik_hafta_damgasi = bu_hafta
                degisti = True
                tg(f"🔄 Yeni hafta, haftalık zarar limiti sıfırlandı (bakiye: {bakiye:.2f}$)")
    if degisti:
        gunluk_haftalik_diske_yaz()


def gunluk_limit_kontrolu():
    with gunluk_lock:
        if gunluk_baslangic_bakiye is None:
            return False
        return gunluk_pnl <= -(gunluk_baslangic_bakiye * GUNLUK_ZARAR_LIMIT_PCT)


def haftalik_limit_kontrolu():
    with gunluk_lock:
        if haftalik_baslangic_bakiye is None:
            return False
        return haftalik_pnl <= -(haftalik_baslangic_bakiye * HAFTALIK_ZARAR_LIMIT_PCT)


def cooldown_da_mi(sym):
    with cooldown_lock:
        son = son_kapanis_zamani.get(sym)
    if son is None:
        return False
    return (time.time() - son) < COOLDOWN_SAAT * 3600


# ════════════════════════════════════════════
# AJAN 2: İŞLEM AÇICI — pozisyon açma, kademeli TP, breakeven kilit
# ════════════════════════════════════════════
def acilis_basarisiz_cooldown_uygula(sym):
    """v2.0 YENİ: BTW örneğinde görüldü - açılış meşru bir sebeple (kaldıraç/
    minimum tutar kısıtı gibi) başarısız olursa, cooldown UYGULANMIYORDU -
    bu da her tarama turunda (dakikada bir) aynı coin için aynı başarısız
    denemenin tekrarlanmasına, gereksiz Telegram mesajı kirliliğine yol
    açıyordu. Artık başarısız açılışlar da normal bir kapanış gibi 1 saatlik
    cooldown'a giriyor."""
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()


def islem_acici_pozisyon_ac(sinyal):
    """AJAN 2: Ajan 1'den gelen sinyali alır, risk bazlı boyutlandırıp
    SL + 3 kademeli TP emirlerini borsaya yerleştirir."""
    sym = sinyal["symbol"]
    entry = sinyal["entry"]
    atr_val = sinyal["atr"]
    tur = sinyal.get("tur", "bilinmiyor")

    bakiye = gercek_bakiye_al()
    if bakiye is None or bakiye <= 0:
        tg(f"⚠️ {sym} atlandı — bakiye alınamadı")
        return

    sl = entry - ATR_CARPANI_SL * atr_val
    # v1.3: ATR anomali yüzünden şişmişse SL/TP mesafesini tavana çek
    if (entry - sl) / entry > MAX_SL_PCT:
        sl = entry * (1 - MAX_SL_PCT)
    # v3.1: ATR gerçek volatiliteyi yakalayamayıp SL çok darsa (GIGGLE örneği)
    # tabana çek
    if (entry - sl) / entry < MIN_SL_PCT:
        sl = entry * (1 - MIN_SL_PCT)
    sl_mesafe_pct = (entry - sl) / entry
    if sl_mesafe_pct <= 0:
        acilis_basarisiz_cooldown_uygula(sym)
        return

    # v2.9: pozisyon büyüklüğü RISK_PCT_BAKIYE ile ölçekleniyor (marj sabit
    # $ değil - SL mesafesine göre otomatik ayarlanıyor ki her işlemde gerçek
    # $ risk tutarlı kalsın). Daha büyük marj/kâr isteniyorsa RISK_PCT_BAKIYE
    # büyütülür (varsayılan %5 -> %10) - bu, sabit $ marjdan daha güvenli,
    # çünkü SL dar/geniş olduğuna göre riski dengede tutuyor.
    risk_dolar = bakiye * RISK_PCT_BAKIYE
    notional = risk_dolar / sl_mesafe_pct

    # v1.2: gerçek kullanılabilir kaldıraç önceden belirlenir (bkz.
    # sembol_max_kaldirac notu) - marj hesabı da BUNA göre yapılır.
    LEV_KULLANILAN = sembol_max_kaldirac(sym, LEV)

    # v1.9 DÜZELTME: v1.8'de sadece set_leverage() çağrısı yeniden deneniyordu,
    # ama BTW'de hata GİRİŞ EMRİNİN KENDİSİNDE (create_market_order) tekrar
    # oluştu - yani set_leverage muhtemelen "başarılı" görünmüştü ama borsa
    # tarafında değişikliğin oturması (propagation) zaman almış olabilir, ya da
    # emrin kendisi ayrı bir kontrolden geçiyor. Artık kaldıraç ayarlama VE
    # giriş emri TEK bir döngüde birlikte deneniyor - hangisi başarısız olursa
    # olsun kaldıraç düşürülüp ikisi baştan deneniyor. Ayrıca set_leverage
    # sonrası kısa bir bekleme eklendi (borsa tarafında oturması için).
    qty = None
    for deneme in range(5):
        gereken_marj = notional / LEV_KULLANILAN
        MAX_MARJ_PCT = 0.25 if MAX_POS <= 1 else 0.15
        notional_bu_deneme = notional
        if gereken_marj > bakiye * MAX_MARJ_PCT:
            notional_bu_deneme = bakiye * MAX_MARJ_PCT * LEV_KULLANILAN
        amount = notional_bu_deneme / entry
        try:
            qty = float(exchange.amount_to_precision(sym, amount))
        except Exception as e:
            tg(f"⚠️ {sym} miktar hesaplanamadı: {e}")
            acilis_basarisiz_cooldown_uygula(sym)
            return
        if qty <= 0:
            acilis_basarisiz_cooldown_uygula(sym)
            return

        try:
            exchange.set_leverage(LEV_KULLANILAN, sym)
            time.sleep(0.3)  # borsada kaldıraç değişikliğinin oturması için
        except Exception as e:
            log.warning(f"[KALDIRAC] {sym}: set_leverage {LEV_KULLANILAN}x hata: {e}")

        try:
            exchange.create_market_order(sym, "buy", qty)
            notional = notional_bu_deneme
            break
        except Exception as e:
            hata_metni = str(e)
            leverage_hatasi = "40797" in hata_metni or "maximum settable leverage" in hata_metni.lower() or "leverage" in hata_metni.lower()
            if leverage_hatasi and LEV_KULLANILAN > 1 and deneme < 4:
                LEV_KULLANILAN = max(1, LEV_KULLANILAN // 2)
                log.warning(f"[GIRIS] {sym}: kaldıraç kaynaklı hata, {LEV_KULLANILAN}x ile tekrar deneniyor: {e}")
                continue
            tg(f"⚠️ {sym} giriş emri başarısız (denenen kaldıraç: {LEV_KULLANILAN}x): {e}")
            acilis_basarisiz_cooldown_uygula(sym)
            return
    else:
        tg(f"⚠️ {sym} atlandı — 5 denemede de giriş emri açılamadı")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    time.sleep(0.8)
    # not: LEV_KULLANILAN zaten yukarıda sembol_max_kaldirac() ile doğru
    # ayarlanmıştı - burada sadece borsanın GERÇEKTE uyguladığı değeri
    # teyit ediyoruz, varsayılan olarak LEV (istenen ham değer) değil,
    # zaten hesapladığımız kırpılmış değeri koruyoruz.
    try:
        pozisyon_bilgisi = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyon_bilgisi if safe(p.get("contracts")) > 0), None)
        if gercek_pos and gercek_pos.get("leverage"):
            LEV_KULLANILAN = int(float(gercek_pos["leverage"]))
    except Exception as e:
        gercek_pos = None
        log.warning(f"[KALDIRAC_DOGRULA] {sym}: {e}")

    # v3.2 KRİTİK DÜZELTME: EPIC örneğinde görüldü - SL fiyatı, borsadan
    # GERÇEK dolum fiyatı gelmeden ÖNCE, sinyal anındaki TAHMİNİ fiyata göre
    # sabitleniyordu. Sürdürülebilir tırmanış gibi hızlı hareket eden
    # sinyallerde gerçek dolum fiyatı tahminden belirgin kayabiliyor (EPIC'te
    # %1.34 kaydı) - SL fiyatı sabit kaldığı için gerçek risk mesafesi
    # planlanandan (%6 tavan) daha GENİŞ hale geliyordu (%7.16 çıktı). Artık
    # SL/TP, borsadan gelen GERÇEK ortalama dolum fiyatına göre yeniden
    # hesaplanıyor - aynı yüzde mesafesi korunuyor, ama doğru referans
    # noktasından.
    if gercek_pos and safe(gercek_pos.get("entryPrice")) > 0:
        gercek_giris = safe(gercek_pos.get("entryPrice"))
        if abs(gercek_giris - entry) / entry > 0.001:  # %0.1'den fazla kaymışsa yeniden hesapla
            log.info(f"[GIRIS_KAYMASI] {sym}: sinyal={entry:.6f} gercek={gercek_giris:.6f} "
                     f"(%{(gercek_giris-entry)/entry*100:+.2f})")
        entry = gercek_giris
        sl = entry * (1 - sl_mesafe_pct)  # ayni yuzde mesafesi, dogru referans noktasindan

    notional = qty * entry
    r_risk = entry - sl

    # v2.2 KRİTİK GÜVENLİK DÜZELTMESİ: UB örneğinde SL emri borsaya
    # YERLEŞEMEDİ ama kod bunu SADECE Railway logunda sessizce kaydediyordu -
    # Telegram'a hiç haber gitmiyordu, pozisyon TAMAMEN KORUMASIZ kaldı ve
    # gerçek para kaybı oldu. Artık: (1) SL yerleştirme 3 kez denenir ve
    # GERÇEKTEN oluştuğu doğrulanır, (2) hâlâ başarısız olursa pozisyon
    # SL'siz AÇIK BIRAKILMAZ - hemen piyasa fiyatından kapatılır ve sana
    # ACİL bir uyarı gider - "sessiz başarısızlık" artık mümkün değil.
    sl_emir_id = None
    sl_fiyat = float(exchange.price_to_precision(sym, sl))
    for sl_deneme in range(3):
        try:
            sl_emri = exchange.create_order(sym, "market", "sell", qty, None,
                                             {"reduceOnly": True, "stopLossPrice": sl_fiyat})
            sl_emir_id = sl_emri.get("id")
            if sl_emir_id:
                break
        except Exception as e:
            log.warning(f"[HARD_STOP] {sym} deneme {sl_deneme+1}/3: {e}")
        time.sleep(0.5)

    if not sl_emir_id:
        # 3 denemede de SL yerleştirilemedi - pozisyonu KORUMASIZ BIRAKMA,
        # hemen kapat ve acil uyar.
        tg(f"🚨 ACİL: {sym} için SL emri 3 denemede de yerleştirilemedi! "
           f"Pozisyon KORUMASIZ kalmasın diye HEMEN piyasa fiyatından kapatılıyor.")
        try:
            exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})
            tg(f"✅ {sym} güvenlik amaçlı kapatıldı (SL yerleştirilemediği için).")
        except Exception as e:
            tg(f"🚨🚨 KRİTİK: {sym} SL YERLEŞTİRİLEMEDİ VE GÜVENLİK KAPATMASI DA BAŞARISIZ OLDU: {e}\n"
               f"LÜTFEN HEMEN BORSAYA GİRİP MANUEL KONTROL ET.")
        acilis_basarisiz_cooldown_uygula(sym)
        return

    # 3 kademeli TP emri
    tp_emirleri = []
    kalan_qty = qty
    for i, (oran, rr) in enumerate(TIERED_TP):
        tp_fiyat_ham = entry + r_risk * rr
        tp_qty = float(exchange.amount_to_precision(sym, qty * oran))
        if i == len(TIERED_TP) - 1:
            tp_qty = kalan_qty  # yuvarlama artığını son kademeye ekle
        if tp_qty <= 0:
            continue
        try:
            tp_fiyat = float(exchange.price_to_precision(sym, tp_fiyat_ham))
            emir = exchange.create_limit_order(sym, "sell", tp_qty, tp_fiyat, params={"reduceOnly": True})
            tp_emirleri.append({"id": emir.get("id"), "fiyat": tp_fiyat, "qty": tp_qty, "rr": rr, "dolu": False})
            kalan_qty = round(kalan_qty - tp_qty, 8)
        except Exception as e:
            log.warning(f"[TP_EMIR {i}] {sym}: {e}")

    with state_lock:
        trade_state[sym] = {
            "entry": entry, "sl_orijinal": sl, "sl_guncel": sl, "sl_emir_id": sl_emir_id,
            "qty_orijinal": qty, "r_risk": r_risk, "tp_emirleri": tp_emirleri,
            "acilis_zamani": time.time(), "breakeven_cekildi": False, "tur": tur,
        }
    durumu_diske_yaz()

    tur_etiket = "ani patlama" if tur == "spike" else ("sürdürülebilir tırmanış" if tur == "sustained" else tur)
    tp_ozet = " | ".join(f"TP{i+1}:{t['fiyat']:.6f}({t['rr']}R)" for i, t in enumerate(tp_emirleri))
    tg(f"📈 SCALP POZİSYON: {sym} LONG [{tur_etiket}]\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} (2×ATR)\n"
       f"{tp_ozet}\n"
       f"Notional≈${notional:.2f} ({LEV_KULLANILAN}x) | Risk≈${risk_dolar:.2f} (bakiyenin ~%{RISK_PCT_BAKIYE*100:.0f}'i)")


def pozisyonu_tamamen_kapat(sym, sebep="manuel"):
    try:
        pozisyonlar = exchange.fetch_positions([sym])
        gercek_pos = next((p for p in pozisyonlar if safe(p.get("contracts")) > 0), None)
        with state_lock:
            durum = trade_state.get(sym)
        if not gercek_pos:
            with state_lock:
                trade_state.pop(sym, None)
            durumu_diske_yaz()
            # v2.8 DÜZELTME: DIA örneğinde görüldü - pozisyon çağrıldığı anda
            # borsada ZATEN kapanmışsa (örn. borsanın kendi SL'i az önce
            # tetiklenmiş, biz henüz haberdar olmadan), bu erken çıkış
            # cooldown UYGULAMIYORDU - coin hemen tekrar açılabiliyordu.
            with cooldown_lock:
                son_kapanis_zamani[sym] = time.time()
            cooldown_diske_yaz()
            return True, f"ℹ️ {sym} zaten borsada açık değilmiş, kayıt temizlendi (cooldown uygulandı)."

        qty = safe(gercek_pos.get("contracts"))
        entry_fiyat = safe(gercek_pos.get("entryPrice"))
        exchange.create_market_order(sym, "sell", qty, params={"reduceOnly": True})

        if durum:
            for t in durum.get("tp_emirleri", []):
                if not t.get("dolu") and t.get("id"):
                    try:
                        exchange.cancel_order(t["id"], sym)
                    except Exception:
                        pass
            if durum.get("sl_emir_id"):
                try:
                    exchange.cancel_order(durum["sl_emir_id"], sym)
                except Exception:
                    pass

        time.sleep(1)
        try:
            t = exchange.fetch_ticker(sym)
            cikis_fiyat = safe(t["last"])
        except Exception:
            cikis_fiyat = entry_fiyat
        pnl = (cikis_fiyat - entry_fiyat) * qty
        trade_log_kaydet({"symbol": sym, "entry": entry_fiyat, "exit": cikis_fiyat, "pnl": pnl,
                           "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), "not": sebep,
                           "tur": (durum or {}).get("tur", "bilinmiyor")})
        with state_lock:
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        with cooldown_lock:
            son_kapanis_zamani[sym] = time.time()
        cooldown_diske_yaz()
        return True, f"✅ {sym} tamamen kapatıldı | PnL≈{pnl:+.2f}$"
    except Exception as e:
        return False, f"⚠️ {sym} kapatma sırasında hata: {e}"


def sembol_bul(acik_semboller, parca):
    parca = parca.upper()
    for sym in acik_semboller:
        if sym.split("/")[0] == parca:
            return sym
    eslesen = [sym for sym in acik_semboller if parca in sym.upper()]
    return eslesen[0] if len(eslesen) == 1 else None


# ════════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════════
if bot:
    @bot.message_handler(commands=["kapat"])
    def kapat_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            acik_semboller = list(trade_state.keys())
        if not acik_semboller:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        parca = msg.text.replace("/kapat", "", 1).strip().upper()
        if parca:
            hedef = sembol_bul(acik_semboller, parca)
            if not hedef:
                bot.send_message(msg.chat.id, f"'{parca}' ile eşleşen tek pozisyon bulunamadı: {acik_semboller}")
                return
        else:
            if len(acik_semboller) > 1:
                bot.send_message(msg.chat.id, f"Birden fazla açık pozisyon var: {acik_semboller}")
                return
            hedef = acik_semboller[0]
        bot.send_message(msg.chat.id, f"⏳ {hedef} kapatılıyor...")
        basari, mesaj = pozisyonu_tamamen_kapat(hedef)
        bot.send_message(msg.chat.id, mesaj)

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        if not yetkili_mi(msg):
            return
        with state_lock:
            durumlar = dict(trade_state)
        if not durumlar:
            bot.send_message(msg.chat.id, "Açık pozisyon yok.")
            return
        satirlar = ["📋 AÇIK POZİSYON(LAR)\n"]
        for sym, d in durumlar.items():
            try:
                t = exchange.fetch_ticker(sym)
                guncel = safe(t["last"])
                pnl_pct = (guncel - d["entry"]) / d["entry"] * 100
                dolu_tp = sum(1 for x in d["tp_emirleri"] if x.get("dolu"))
                be_durum = " | 🔒 SL başabaşta" if d.get("breakeven_cekildi") else ""
                satirlar.append(f"🟢 {sym} LONG\n"
                                 f"   Giriş:{d['entry']:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                                 f"   SL:{d['sl_guncel']:.6f} | TP kademesi: {dolu_tp}/{len(d['tp_emirleri'])} dolu{be_durum}")
            except Exception:
                satirlar.append(f"{sym} (fiyat alınamadı)")
        bot.send_message(msg.chat.id, "\n".join(satirlar))

    def panel_ozet_metni():
        with log_lock:
            gecmis = list(trade_log)
        satirlar = ["📊 SCALP BOT ÖZET\n"]
        try:
            bakiye_bilgi = exchange.fetch_balance()
            usdt = bakiye_bilgi.get("USDT", {})
            toplam_bakiye = safe(usdt.get("total", 0)) or safe(usdt.get("free", 0))
            satirlar.append(f"💰 Bakiye: {toplam_bakiye:.2f}$")
        except Exception:
            pass
        if gecmis:
            toplam = len(gecmis)
            kazanan = [t for t in gecmis if t["pnl"] > 0]
            net = sum(t["pnl"] for t in gecmis)
            satirlar.append(f"Toplam kapanan işlem: {toplam} | Kazanma: %{len(kazanan)/toplam*100:.1f}")
            satirlar.append(f"Net PnL: {net:+.2f}$")
            satirlar.append("\n📋 Son 5 kapanan işlem:")
            for t in list(reversed(gecmis))[:5]:
                emoji = "🟢" if t["pnl"] >= 0 else "🔴"
                sebep = t.get("not", "")
                satirlar.append(f"  {emoji} {t['symbol'].split('/')[0]} {t['pnl']:+.2f}$ ({sebep})")
        else:
            satirlar.append("Henüz kapanan işlem yok.")
        with gunluk_lock:
            satirlar.append(f"\n📅 Bugün: {gunluk_pnl:+.2f}$ | 📆 Bu hafta: {haftalik_pnl:+.2f}$")
        with state_lock:
            satirlar.append(f"\n📈 Açık pozisyon: {len(trade_state)}/{MAX_POS}")
        return "\n".join(satirlar)

    def panel_ayarlar_metni():
        return ("⚙️ SCALP BOT AYARLARI\n\n"
                f"Sürüm: v3.1 (SL minimum %2 taban - GIGGLE whipsaw örneği)\n"
                f"Kaldıraç: {LEV}x | MAX_POS: {MAX_POS}\n"
                f"İşlem başına risk: bakiyenin %{RISK_PCT_BAKIYE*100:.0f}'i\n"
                f"SL: {ATR_CARPANI_SL}x ATR(5m,14)\n"
                f"TP kademeleri: " + ", ".join(f"%{int(o*100)}@{r}R" for o, r in TIERED_TP) + "\n"
                f"İlk TP'de SL başabaşa çekilir\n"
                f"Coin cooldown: {COOLDOWN_SAAT} saat\n"
                f"Aday havuzu: her turda en canlı {ADAY_HAVUZU_BUYUKLUGU} coin taranır\n"
                f"Günlük zarar limiti: %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f} | Haftalık: %{HAFTALIK_ZARAR_LIMIT_PCT*100:.0f}\n"
                f"Tarama aralığı: {KONTROL_ARALIGI_SN}sn")

    def panel_gecmis_metni():
        with log_lock:
            gecmis = list(trade_log)
        if not gecmis:
            return "📜 Henüz kapanan işlem yok."
        satirlar = ["📜 SON 15 İŞLEM\n"]
        for t in list(reversed(gecmis))[:15]:
            tur = t.get("tur", "?")
            tur_kisa = "patlama" if tur == "spike" else ("sürdürülebilir" if tur == "sustained" else tur)
            sebep = t.get("not", "")
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} {t['pnl']:+.2f}$ "
                             f"[{tur_kisa}] ({sebep}) — {t['zaman']}")
        return "\n".join(satirlar)

    def panel_analiz_metni():
        with log_lock:
            gecmis = list(trade_log)
        if not gecmis:
            return "🔬 SCALP ANALİZ\n\nHenüz kapanan işlem yok."
        satirlar = ["🔬 SCALP ANALİZ\n"]
        satirlar.append("📊 Sinyal tipi bazında:")
        for tur in ["spike", "sustained"]:
            alt = [t for t in gecmis if t.get("tur") == tur]
            if not alt:
                continue
            kazanan = [t for t in alt if t["pnl"] > 0]
            net = sum(t["pnl"] for t in alt)
            tur_ad = "Ani patlama" if tur == "spike" else "Sürdürülebilir tırmanış"
            satirlar.append(f"  {tur_ad}: {len(alt)} işlem, %{len(kazanan)/len(alt)*100:.0f} kazanma, net {net:+.2f}$")
        satirlar.append("\n🚪 Kapanış sebebi bazında:")
        for sebep in ["tum_tp_tamamlandi", "SL_basabasta_TP1_sonrasi", "SL_ilk_TPden_once", "max_hold_timeout", "manuel"]:
            alt = [t for t in gecmis if t.get("not") == sebep]
            if not alt:
                continue
            net = sum(t["pnl"] for t in alt)
            satirlar.append(f"  {sebep}: {len(alt)} işlem, net {net:+.2f}$")
        coin_pnl = {}
        for t in gecmis:
            sym = t["symbol"].split("/")[0]
            coin_pnl[sym] = coin_pnl.get(sym, 0) + t["pnl"]
        siralanmis = sorted(coin_pnl.items(), key=lambda x: x[1], reverse=True)
        if siralanmis:
            satirlar.append("\n🏆 En kazandıran coinler:")
            for sym, pnl in siralanmis[:3]:
                satirlar.append(f"  {sym}: {pnl:+.2f}$")
            satirlar.append("💀 En kaybettiren coinler:")
            for sym, pnl in siralanmis[-3:][::-1]:
                satirlar.append(f"  {sym}: {pnl:+.2f}$")
        return "\n".join(satirlar)

    def panel_risk_metni():
        """v2.6 YENİ: pullback botunda (v8.2) vardı, scalp botuna eklenmemişti -
        günlük/haftalık zarar limiti durumu ve cooldown'daki coinler burada."""
        satirlar = ["📉 RİSK DURUMU\n"]
        with gunluk_lock:
            gp = gunluk_pnl; hp = haftalik_pnl
            gb = gunluk_baslangic_bakiye; hb = haftalik_baslangic_bakiye
        if gb:
            limit_dolar = gb * GUNLUK_ZARAR_LIMIT_PCT
            kalan = limit_dolar + gp
            satirlar.append(f"Günlük zarar limiti: -{limit_dolar:.2f}$ (bakiyenin %{GUNLUK_ZARAR_LIMIT_PCT*100:.0f}'i)")
            satirlar.append(f"Bugünkü PnL: {gp:+.2f}$ | Limite kalan pay: {kalan:.2f}$")
            satirlar.append("⛔ GÜNLÜK LİMİT AŞILDI - tarama duruyor" if gunluk_limit_kontrolu() else "✅ Günlük limit aşılmadı")
        else:
            satirlar.append("Günlük başlangıç bakiyesi henüz kaydedilmedi.")
        if hb:
            limit_dolar_h = hb * HAFTALIK_ZARAR_LIMIT_PCT
            kalan_h = limit_dolar_h + hp
            satirlar.append(f"\nHaftalık zarar limiti: -{limit_dolar_h:.2f}$ (bakiyenin %{HAFTALIK_ZARAR_LIMIT_PCT*100:.0f}'i)")
            satirlar.append(f"Bu haftaki PnL: {hp:+.2f}$ | Limite kalan pay: {kalan_h:.2f}$")
            satirlar.append("⛔ HAFTALIK LİMİT AŞILDI - tarama duruyor" if haftalik_limit_kontrolu() else "✅ Haftalık limit aşılmadı")
        else:
            satirlar.append("\nHaftalık başlangıç bakiyesi henüz kaydedilmedi.")

        try:
            btc_bull = btc_1h_bullish()
            if btc_bull is None:
                satirlar.append("\n₿ BTC 1h rejimi alınamadı")
            elif btc_bull:
                satirlar.append("\n₿ BTC 1h rejimi: 🟢 YÜKSELİŞTE - tarama aktif")
            else:
                satirlar.append("\n₿ BTC 1h rejimi: 🔴 DÜŞÜŞTE/YATAY - tarama DURUYOR (LONG sinyali aranmıyor)")
        except Exception:
            pass

        with cooldown_lock:
            cd = dict(son_kapanis_zamani)
        aktif_cooldown = [(s, t) for s, t in cd.items() if (time.time()-t) < COOLDOWN_SAAT*3600]
        if aktif_cooldown:
            satirlar.append(f"\n🕐 Cooldown'da olan coinler ({COOLDOWN_SAAT}sa):")
            for s, t in sorted(aktif_cooldown, key=lambda x: x[1], reverse=True)[:10]:
                kalan_dk = (COOLDOWN_SAAT*3600 - (time.time()-t)) / 60
                satirlar.append(f"  {s.split('/')[0]}: {kalan_dk:.0f} dk kaldı")
        return "\n".join(satirlar)

    def ana_menu_klavye():
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("📊 Özet", callback_data="panel_ozet"),
            telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="panel_ayarlar"),
        )
        markup.row(
            telebot.types.InlineKeyboardButton("📜 Geçmiş İşlemler", callback_data="panel_gecmis"),
            telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="panel_analiz"),
        )
        markup.row(telebot.types.InlineKeyboardButton("📉 Risk Durumu", callback_data="panel_risk"))
        markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="panel_ana"))
        return markup

    def geri_butonu():
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
        return markup

    @bot.message_handler(commands=["panel"])
    def panel_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        veri = call.data
        try:
            if veri == "panel_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye())
            elif veri == "panel_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_ayarlar":
                bot.edit_message_text(panel_ayarlar_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_gecmis":
                bot.edit_message_text(panel_gecmis_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_analiz":
                bot.edit_message_text(panel_analiz_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_risk":
                bot.edit_message_text(panel_risk_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            bot.answer_callback_query(call.id)
        except Exception as e:
            if "message is not modified" not in str(e):
                log.warning(f"[PANEL_BUTON] {e}")
            try: bot.answer_callback_query(call.id, "Tamam")
            except Exception: pass


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
            time.sleep(5)


def baslangic_uzlastirma():
    try:
        gercek_pozlar = exchange.fetch_positions()
        gercek_semboller = {p["symbol"] for p in gercek_pozlar if safe(p.get("contracts")) > 0}
    except Exception as e:
        log.warning(f"[UZLASTIRMA] {e}")
        return
    with state_lock:
        state_semboller = set(trade_state.keys())
    sadece_diskte = state_semboller - gercek_semboller
    if sadece_diskte:
        with state_lock:
            for sym in sadece_diskte:
                trade_state.pop(sym, None)
        durumu_diske_yaz()
        tg(f"ℹ️ Uzlaştırma: {len(sadece_diskte)} eski kayıt temizlendi: {sorted(sadece_diskte)}")
    sadece_borsada = gercek_semboller - state_semboller
    if sadece_borsada:
        tg(f"⚠️ UYARI: borsada açık ama state'te olmayan pozisyonlar var: {sorted(sadece_borsada)}")


def tarama_loop():
    tg(f"🚀 SCALP BOT v3.1 başladı (MAX_POS={MAX_POS})\n"
       f"Strateji: dinamik pump taraması — 2 sinyal tipi (ani patlama 5m + sürdürülebilir tırmanış 15m), SADECE LONG\n"
       f"SL={ATR_CARPANI_SL}x ATR | TP kademeleri: " + ", ".join(f"%{int(o*100)}@{r}R" for o, r in TIERED_TP) + "\n"
       f"Backtest: 131 işlem/15gün, %58 kazanma, +0.197R/işlem ort. (iki yarıda da pozitif)\n"
       f"🔧 v2.7: çoklu-aşama TP sistemi kaldırıldı (kafa karıştırıcıydı, backtest'te de zayıf çıkmıştı) - "
       f"tek, kanıtlanmış TP yapısına sabitlendi. Ayrıca TP1/başabaş kontrolü artık SL güvenlik ağından ÖNCE çalışıyor (RAVE bugı düzeltildi).\n"
       f"Coin cooldown: {COOLDOWN_SAAT} saat\n"
       f"⚠️ Küçük örneklemli backtest - gerçek performans garantisi yoktur.")

    baslangic_uzlastirma()
    gunluk_haftalik_reset_kontrol()

    while True:
        try:
            gunluk_haftalik_reset_kontrol()

            if gunluk_limit_kontrolu() or haftalik_limit_kontrolu():
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            with state_lock:
                bos_slot = MAX_POS - len(trade_state)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            btc_bullish = btc_1h_bullish()
            if not btc_bullish:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            # AJAN 1: piyasayı izle, aday havuzunu bul
            # v1.5 DÜZELTME: eskiden TÜM havuz taranıp sonra en iyi sinyaller
            # seçilirdi - bu da taramanın başında bulunan bir sinyalin, tarama
            # bitene kadar (ölçüldü: ~60sn) BEKLEMESİ anlamına geliyordu, tam
            # da "hemen aç" hedefinin tersiydi. Artık aday havuzu zaten 24s
            # değişim/hacme göre en güçlüden zayıfa SIRALI geliyor
            # (piyasa_izleyici_aday_havuzu içinde skor sıralı) - bu sırayla
            # taranır, bir coin için sinyal (patlama VEYA sürdürülebilir)
            # bulunur bulunmaz AJAN 2'ye HEMEN iletilir, slot dolunca tarama
            # o an durur - kalan adaylar bir sonraki turda taranır.
            adaylar_havuzu = piyasa_izleyici_aday_havuzu()
            acilan_sayisi = 0

            # v3.0: önce bekleyen (teyit aşamasındaki) sinyalleri kontrol et
            for sym in list(bekleyen_sinyaller.keys()):
                if acilan_sayisi >= bos_slot:
                    break
                p = bekleyen_sinyaller[sym]
                try:
                    t = exchange.fetch_ticker(sym)
                    guncel_fiyat = safe(t["last"])
                except Exception:
                    continue
                if guncel_fiyat <= 0:
                    continue
                retrace = (p["sinyal_fiyat"] - guncel_fiyat) / p["sinyal_fiyat"]
                if retrace > CONFIRM_MAX_RETRACE_PCT:
                    del bekleyen_sinyaller[sym]  # tepe yakalama şüphesi, iptal
                    continue
                if (time.time() - p["zaman"]) >= CONFIRM_BEKLEME_SN:
                    del bekleyen_sinyaller[sym]
                    with state_lock:
                        if sym in trade_state:
                            continue
                    if cooldown_da_mi(sym):
                        continue
                    tg(f"✅ AJAN 1: {sym} teyit edildi (fiyat tuttu) — AJAN 2'ye 'şimdi aç' komutu veriliyor")
                    islem_acici_pozisyon_ac({"symbol": sym, "entry": guncel_fiyat, "atr": p["atr"],
                                              "skor": p["skor"], "tur": p["tur"]})
                    acilan_sayisi += 1

            for sym in adaylar_havuzu:
                if acilan_sayisi >= bos_slot:
                    break
                with state_lock:
                    if sym in trade_state:
                        continue
                if cooldown_da_mi(sym) or sym in bekleyen_sinyaller:
                    continue

                sinyal = piyasa_izleyici_sinyal_kontrol(sym, btc_bullish)
                if sinyal:
                    # ani patlama - hemen açmak yerine teyit bekleme sırasına al
                    bekleyen_sinyaller[sym] = {"sinyal_fiyat": sinyal["entry"], "atr": sinyal["atr"],
                                                "skor": sinyal["skor"], "tur": sinyal["tur"], "zaman": time.time()}
                    tg(f"⏳ AJAN 1: {sym} ani patlama sinyali bulundu, {CONFIRM_BEKLEME_SN//60} dakika "
                       f"'tutuyor mu' diye izleniyor (tepe yakalamayı önlemek için)")
                    continue

                sinyal = piyasa_izleyici_sustained_sinyal_kontrol(sym, btc_bullish)
                if not sinyal:
                    continue

                tg(f"🔍 AJAN 1: {sym} güçlü LONG sinyali [sürdürülebilir tırmanış] bulundu — AJAN 2'ye 'hemen aç' komutu veriliyor")
                islem_acici_pozisyon_ac(sinyal)
                acilan_sayisi += 1

            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


def manage_loop():
    """Açık pozisyonları izler: kademeli TP dolumlarını tespit eder, ilk TP'de
    SL'i başabaşa çeker, max hold süresini aşanları kapatır, kapanmışları loglar."""
    global gunluk_pnl, haftalik_pnl
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            if not semboller:
                time.sleep(10)
                continue

            for sym in semboller:
                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue

                # max hold kontrolü
                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    tg(f"⏱️ {sym} — max tutma süresi ({MAX_HOLD_SAAT}sa) aşıldı, piyasa fiyatından kapatılıyor")
                    pozisyonu_tamamen_kapat(sym, sebep="max_hold_timeout")
                    continue

                # v2.7 KRİTİK SIRA DÜZELTMESİ: RAVE örneğinde görüldü - TP1 dolmuş
                # ve SL başabaşa çekilmesi gerekirken, YAZILIM SL GÜVENLİK AĞI bunu
                # fark etmeden ÖNCE eski (dar) SL'e göre pozisyonu kapatıyordu.
                # Artık TP dolum/başabaş kontrolü ÖNCE yapılıyor, güvenlik ağı
                # SONRA (güncellenmiş SL ile) çalışıyor.
                try:
                    pozlar_erken = exchange.fetch_positions([sym])
                    gercek_pos_erken = next((p for p in pozlar_erken if safe(p.get("contracts")) > 0), None)
                except Exception:
                    gercek_pos_erken = None

                if gercek_pos_erken:
                    guncel_qty_erken = safe(gercek_pos_erken.get("contracts"))
                    degisti_erken = False
                    for t in durum["tp_emirleri"]:
                        if t.get("dolu"):
                            continue
                        try:
                            emir_durumu = exchange.fetch_order(t["id"], sym)
                            if emir_durumu.get("status") in ("closed", "filled"):
                                t["dolu"] = True
                                degisti_erken = True
                        except Exception:
                            pass
                    if degisti_erken and not durum.get("breakeven_cekildi"):
                        try:
                            if durum.get("sl_emir_id"):
                                exchange.cancel_order(durum["sl_emir_id"], sym)
                        except Exception:
                            pass
                        try:
                            yeni_sl_fiyat = float(exchange.price_to_precision(sym, durum["entry"]))
                            yeni_sl_emri = exchange.create_order(sym, "market", "sell", guncel_qty_erken, None,
                                                                  {"reduceOnly": True, "stopLossPrice": yeni_sl_fiyat})
                            with state_lock:
                                durum["sl_emir_id"] = yeni_sl_emri.get("id")
                                durum["sl_guncel"] = yeni_sl_fiyat
                                durum["breakeven_cekildi"] = True
                            durumu_diske_yaz()
                            tg(f"🔒 {sym} — ilk TP vuruldu, SL başabaşa ({yeni_sl_fiyat:.6f}) çekildi. "
                               f"Bu andan sonra pozisyon en kötü ihtimalle sıfır zararla kapanır.")
                        except Exception as e:
                            log.warning(f"[BREAKEVEN_ERKEN] {sym}: {e}")
                    elif degisti_erken:
                        durumu_diske_yaz()

                # v2.2 YENİ - YAZILIM TARAFI SL GÜVENLİK AĞI: UB örneğinde borsa
                # SL emri hiç yerleşmemişti (bkz. islem_acici_pozisyon_ac'taki
                # düzeltme, bunu artık açılışta yakalayıp engelliyor). Ama yine
                # de - emir sonradan iptal olursa, borsa tarafında bir aksaklık
                # olursa, ya da başka bir sebeple borsadaki SL çalışmazsa diye -
                # bot burada BAĞIMSIZ OLARAK, borsadaki emre hiç güvenmeden,
                # güncel fiyatı kendi kayıtlı SL seviyesiyle karşılaştırıyor.
                # Fiyat SL'i geçmişse ve pozisyon hâlâ açıksa, borsa ne derse
                # desin BOT KENDİSİ hemen piyasa fiyatından kapatıyor. Bu,
                # borsadaki emirle YEDEKLİ çalışan ikinci bir güvenlik katmanı.
                try:
                    t = exchange.fetch_ticker(sym)
                    guncel_fiyat = safe(t["last"])
                    if guncel_fiyat > 0 and guncel_fiyat <= durum["sl_guncel"]:
                        tg(f"🛡️ YAZILIM SL GÜVENLİK AĞI: {sym} fiyatı ({guncel_fiyat:.6f}) "
                           f"SL seviyesini ({durum['sl_guncel']:.6f}) geçti — borsadaki emir ne "
                           f"durumda olursa olsun bot kendisi HEMEN kapatıyor.")
                        pozisyonu_tamamen_kapat(sym, sebep="yazilim_sl_guvenlik_agi")
                        continue
                except Exception as e:
                    log.warning(f"[SL_GUVENLIK_AGI] {sym}: fiyat kontrol edilemedi: {e}")

                # borsadaki gerçek pozisyon hâlâ açık mı?
                try:
                    pozlar = exchange.fetch_positions([sym])
                    gercek_pos = next((p for p in pozlar if safe(p.get("contracts")) > 0), None)
                except Exception as e:
                    log.warning(f"[MANAGE] {sym} pozisyon sorgu hatası: {e}")
                    continue

                if not gercek_pos:
                    # tamamen kapanmış (SL ya da son TP kademesi vurmuş)
                    with state_lock:
                        durum2 = trade_state.pop(sym, None)
                    durumu_diske_yaz()
                    # v1.7 DÜZELTME: ZIL örneğinde görüldü - TP2 ve TP3 hızlıca art
                    # arda dolduğunda, bir önceki döngüde henüz 'dolu' işaretlenmemiş
                    # kademeler burada KONTROL EDİLMEDEN direkt "iptal edilmeye
                    # çalışılıyordu" (zaten dolmuş oldukları için iptal sessizce
                    # başarısız oluyordu ama 'dolu' bayrağı hiç True olmuyordu) -
                    # bu da PnL'i eksik saydırıyor ve "tum_tp_tamamlandi" yerine
                    # yanlışlıkla "SL_basabasta_TP1_sonrasi" etiketi koyuyordu.
                    # Artık iptal etmeden ÖNCE gerçekten dolup dolmadığı kontrol
                    # ediliyor.
                    for t in (durum2 or {}).get("tp_emirleri", []):
                        if t.get("dolu") or not t.get("id"):
                            continue
                        try:
                            emir_durumu = exchange.fetch_order(t["id"], sym)
                            if emir_durumu.get("status") in ("closed", "filled"):
                                t["dolu"] = True
                                continue
                        except Exception:
                            pass
                        try:
                            exchange.cancel_order(t["id"], sym)
                        except Exception:
                            pass
                    if durum2 and durum2.get("sl_emir_id"):
                        try:
                            exchange.cancel_order(durum2["sl_emir_id"], sym)
                        except Exception:
                            pass
                    with cooldown_lock:
                        son_kapanis_zamani[sym] = time.time()
                    cooldown_diske_yaz()
                    if durum2:
                        try:
                            t = exchange.fetch_ticker(sym)
                            cikis_fiyat = safe(t["last"])
                        except Exception:
                            cikis_fiyat = durum2["sl_guncel"]
                        entry = durum2["entry"]
                        # v1.6 DÜZELTME: eskiden (çıkış-giriş)×orijinal_miktar×0.3 gibi kaba
                        # bir tahmin kullanılıyordu - BEAT örneğinde gerçek sonuç +$0.09 iken
                        # bu formül -$0.11 gösterdi (YÖNÜ BİLE TERSTİ). Artık her dolan TP
                        # kademesinin GERÇEK fiyatı ve miktarıyla, kalan miktarın da gerçek
                        # kapanış fiyatıyla ayrı ayrı hesaplanıp toplanıyor - kademeli
                        # pozisyonun gerçek PnL'ine çok daha yakın bir tahmin.
                        tp_emirleri = durum2.get("tp_emirleri", [])
                        dolu_qty_toplam = sum(t.get("qty", 0) for t in tp_emirleri if t.get("dolu"))
                        pnl_kademeler = sum((t["fiyat"] - entry) * t.get("qty", 0) for t in tp_emirleri if t.get("dolu"))
                        kalan_qty = max(durum2["qty_orijinal"] - dolu_qty_toplam, 0)
                        pnl_kalan = (cikis_fiyat - entry) * kalan_qty
                        pnl_tahmini = pnl_kademeler + pnl_kalan
                        with gunluk_lock:
                            gunluk_pnl += pnl_tahmini
                            haftalik_pnl += pnl_tahmini
                        gunluk_haftalik_diske_yaz()
                        tum_tp_dolu = all(t.get("dolu") for t in tp_emirleri) and len(tp_emirleri) > 0
                        if tum_tp_dolu:
                            sebep_etiket = "tum_tp_tamamlandi"
                        elif durum2.get("breakeven_cekildi"):
                            sebep_etiket = "SL_basabasta_TP1_sonrasi"
                        else:
                            sebep_etiket = "SL_ilk_TPden_once"
                        trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat,
                                           "pnl": pnl_tahmini, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                                           "not": sebep_etiket, "tur": durum2.get("tur", "bilinmiyor")})
                        tg(f"✅ {sym} pozisyonu tamamen kapandı [{sebep_etiket}] (tahmini PnL≈{pnl_tahmini:+.2f}$ — "
                           f"komisyon dahil değil, kesin tutar borsa Pozisyon Geçmişi'nden teyit edilmeli)")
                    continue

                # hâlâ açık - miktar azaldı mı (bir TP kademesi dolmuş mu)?
                guncel_qty = safe(gercek_pos.get("contracts"))
                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue

                degisti = False
                for t in durum["tp_emirleri"]:
                    if t.get("dolu"):
                        continue
                    try:
                        emir_durumu = exchange.fetch_order(t["id"], sym)
                        if emir_durumu.get("status") in ("closed", "filled"):
                            t["dolu"] = True
                            degisti = True
                    except Exception:
                        pass

                if degisti and not durum.get("breakeven_cekildi"):
                    # ilk TP dolmuş - SL'i başabaşa çek
                    try:
                        if durum.get("sl_emir_id"):
                            exchange.cancel_order(durum["sl_emir_id"], sym)
                    except Exception:
                        pass
                    try:
                        yeni_sl_fiyat = float(exchange.price_to_precision(sym, durum["entry"]))
                        yeni_sl_emri = exchange.create_order(sym, "market", "sell", guncel_qty, None,
                                                              {"reduceOnly": True, "stopLossPrice": yeni_sl_fiyat})
                        with state_lock:
                            durum["sl_emir_id"] = yeni_sl_emri.get("id")
                            durum["sl_guncel"] = yeni_sl_fiyat
                            durum["breakeven_cekildi"] = True
                        durumu_diske_yaz()
                        tg(f"🔒 {sym} — ilk TP vuruldu, SL başabaşa ({yeni_sl_fiyat:.6f}) çekildi. "
                           f"Bu andan sonra pozisyon en kötü ihtimalle sıfır zararla kapanır.")
                    except Exception as e:
                        log.warning(f"[BREAKEVEN] {sym}: {e}")
                elif degisti:
                    durumu_diske_yaz()

            time.sleep(10)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(10)


if __name__ == "__main__":
    print("SCALP BOT v3.1 BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    trade_log_yukle()
    gunluk_haftalik_diskten_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
