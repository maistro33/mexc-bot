#!/usr/bin/env python3
"""
VOLATİLİTE SIKIŞMASI (SQUEEZE) KIRILIM STRATEJİSİ — BACKTEST
🔖 VERSİYON: v1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bu strateji, önceki scalp denemelerimizden (v8-v10) BİLİNÇLİ olarak farklı
bir mantık kullanıyor. Önceki denemeler "ani hareketi gördüm, hemen (veya
kısa bekleyip) gir" mantığındaydı — bu, hareketin ORTASINDA/SONUNDA giriş
yapıp sürekli kötü fiyattan yakalanmamıza sebep oluyordu (canlı veride
%13-20 kazanma oranıyla kanıtlandı).

BU STRATEJİ TERSİNİ YAPAR: Piyasa SIKIŞIP sessizleştiğinde (oynaklık
tarihsel olarak düşükken) bekler, sonra o sıkışmadan hacimle teyitli
şekilde çıkan İLK kırılımı yakalar — hareketin BAŞLANGICINI, ortasını
değil. Bu, teknik analizde "volatilite daralması sonrası genişleme"
olarak bilinen, iyi belgelenmiş bir kavramdır (Bollinger Bands sıkışması,
NR7 gibi düşük-menzil paternleri).

BİLEŞENLER:
  1. 1 saatlik EMA50 trend filtresi — sadece üst trend yönünde kırılıma girilir
  2. 15 dakikalık ATR sıkışması — ATR, son 100 mumun en düşük %20'lik
     diliminde ise "sıkışma" kabul edilir
  3. Donchian kanal kırılımı (son 20 mum) + hacim teyidi (ortalamanın 1.5x'i)
  4. ATR bazlı SL + R-katı kademeli TP (1R/2R/3R, %40/%30/%30 bölünme) +
     TP1 sonrası başa baş kaydırma

ÖNEMLİ: Gerçek para KULLANMAZ, hiçbir emir açmaz. Sadece geçmiş veriyle
"olsaydı ne olurdu" simülasyonu yapar. Bakış-öne (look-ahead) hatası
olmaması için: her karar SADECE o ana kadarki kapanmış mumlarla verilir,
işlem yönetimi de sinyal mumundan SONRAKİ mumdan başlar.

ÇALIŞTIRMA: pip install ccxt pandas --break-system-packages
            python3 scalp_squeeze_backtest.py
"""

import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta, timezone

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
GECMIS_GUN        = 180     # kaç gün geriye gidilecek
TOP_COINS         = 60
MIN_VOLUME        = 5_000_000
MAX_POS_BACKTEST  = 5        # aynı anda kaç işleme izin verilir

EMA_PERIOD        = 50       # 1h trend filtresi
ATR_PERIOD        = 14       # 15m ATR (sıkışma ölçümü + SL mesafesi)
SQUEEZE_LOOKBACK  = 100      # ATR'nin percentile'ını hesaplarken kaç mum geriye bakılır
SQUEEZE_PERCENTILE = 20      # bu percentile'ın altındaysa "sıkışma" kabul edilir
DONCHIAN_PERIOD   = 20       # kırılım kanalı periyodu
VOLUME_MULT       = 1.5      # kırılım mumunun hacmi, ortalamanın kaç katı olmalı
ATR_SL_MULT       = 1.5      # SL mesafesi = bu × ATR

R_KADEMELERI      = [1.0, 2.0, 3.0]
TP_SPLIT          = [0.4, 0.3, 0.3]

exchange = ccxt.bitget({"options": {"defaultType": "swap"}, "enableRateLimit": True})


# ════════════════════════════════════════════
# VERİ ÇEKME (FVG backtest'iyle aynı, kanıtlanmış)
# ════════════════════════════════════════════
def gecmis_veri_cek(symbol, timeframe, gun_sayisi):
    ms_baslangic = int((datetime.now(timezone.utc) - timedelta(days=gun_sayisi)).timestamp() * 1000)
    tum_mumlar = []
    since = ms_baslangic
    while True:
        try:
            mumlar = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except Exception as e:
            print(f"  [HATA] {symbol} {timeframe}: {e}")
            break
        if not mumlar:
            break
        tum_mumlar.extend(mumlar)
        if len(mumlar) < 2:
            break
        yeni_since = mumlar[-1][0] + 1
        if yeni_since <= since:
            break
        since = yeni_since
        if mumlar[-1][0] >= int(datetime.now(timezone.utc).timestamp() * 1000) - 60_000:
            break
        time.sleep(exchange.rateLimit / 1000)
    if not tum_mumlar:
        return None
    df = pd.DataFrame(tum_mumlar, columns=["t", "o", "h", "l", "c", "v"])
    df = df.drop_duplicates(subset="t").sort_values("t").reset_index(drop=True)
    return df


def sembol_listesi_al(top_n, min_hacim):
    tickers = exchange.fetch_tickers()
    filtreli = []
    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue
        vol = data.get("quoteVolume") or 0
        if vol >= min_hacim:
            filtreli.append((sym, vol))
    filtreli.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtreli[:top_n]]


# ════════════════════════════════════════════
# İNDİKATÖRLER
# ════════════════════════════════════════════
def calc_atr_series(df, period=14):
    """Tüm seri boyunca ATR hesaplar (tek bir son değer değil — percentile
    karşılaştırması için geçmiş ATR dizisine ihtiyacımız var)."""
    high, low, close = df["h"], df["l"], df["c"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


# ════════════════════════════════════════════
# SİNYAL MANTIĞI
# ════════════════════════════════════════════
def trend_filtresi(h1_df, simdiki_zaman, yon):
    gecerli = h1_df[h1_df["t"] <= simdiki_zaman]
    if len(gecerli) < EMA_PERIOD + 5:
        return False
    ema = gecerli["c"].ewm(span=EMA_PERIOD, adjust=False).mean().iloc[-1]
    son_kapanis = gecerli["c"].iloc[-1]
    if yon == "long":
        return son_kapanis > ema
    else:
        return son_kapanis < ema


def squeeze_kirilim_sinyali(m15_df, atr_series, i):
    """
    i: şu anki (dahil) kapanmış mumun index'i. Sadece i ve öncesi kullanılır.
    Döner: "long" / "short" / None
    """
    if i < SQUEEZE_LOOKBACK + DONCHIAN_PERIOD + 5:
        return None

    # ── Sıkışma kontrolü: kırılım mumundan HEMEN ÖNCEKİ ATR, geçmiş
    # SQUEEZE_LOOKBACK mumun en düşük %SQUEEZE_PERCENTILE dilimindeyse ──
    atr_onceki = atr_series.iloc[i - 1]
    atr_gecmis_pencere = atr_series.iloc[i - 1 - SQUEEZE_LOOKBACK: i - 1]
    if atr_gecmis_pencere.isna().any() or len(atr_gecmis_pencere) < SQUEEZE_LOOKBACK * 0.8:
        return None
    percentile_rank = (atr_gecmis_pencere < atr_onceki).mean() * 100
    if percentile_rank > SQUEEZE_PERCENTILE:
        return None  # sıkışma yok, piyasa zaten hareketliydi

    # ── Donchian kırılımı: son DONCHIAN_PERIOD mumun (şu anki mum HARİÇ)
    # en yükseği/en düşüğü kırılıyor mu? ──
    onceki_high = m15_df["h"].iloc[i - DONCHIAN_PERIOD:i].max()
    onceki_low = m15_df["l"].iloc[i - DONCHIAN_PERIOD:i].min()
    kapanis = m15_df["c"].iloc[i]

    # ── Hacim teyidi ──
    hacim_simdi = m15_df["v"].iloc[i]
    hacim_ort = m15_df["v"].iloc[i - DONCHIAN_PERIOD:i].mean()
    if hacim_ort <= 0 or hacim_simdi < hacim_ort * VOLUME_MULT:
        return None

    if kapanis > onceki_high:
        return "long"
    if kapanis < onceki_low:
        return "short"
    return None


# ════════════════════════════════════════════
# İŞLEM SİMÜLASYONU (FVG backtest'iyle birebir aynı mantık — kanıtlanmış)
# ════════════════════════════════════════════
def islemi_simule_et(m15_df, giris_idx, direction, entry, sl):
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    tp1 = entry + risk if direction == "long" else entry - risk
    tp2 = entry + 2 * risk if direction == "long" else entry - 2 * risk
    tp3 = entry + 3 * risk if direction == "long" else entry - 3 * risk

    kalan = 1.0
    r_toplam = 0.0
    aktif_sl = sl
    tp1_oldu = tp2_oldu = False

    for i in range(giris_idx, len(m15_df)):
        h = m15_df["h"].iloc[i]; l = m15_df["l"].iloc[i]

        sl_vuruldu = (l <= aktif_sl) if direction == "long" else (h >= aktif_sl)
        if sl_vuruldu:
            r_bu_parca = (aktif_sl - entry) / risk if direction == "long" else (entry - aktif_sl) / risk
            r_toplam += r_bu_parca * kalan
            return {"r": r_toplam, "sure_mum": i - giris_idx, "sonuc": "SL/BE", "cikis_i": i}

        if not tp1_oldu:
            tp1_vuruldu = (h >= tp1) if direction == "long" else (l <= tp1)
            if tp1_vuruldu:
                r_toplam += 1.0 * TP_SPLIT[0]
                kalan -= TP_SPLIT[0]
                tp1_oldu = True
                aktif_sl = entry

        if tp1_oldu and not tp2_oldu:
            tp2_vuruldu = (h >= tp2) if direction == "long" else (l <= tp2)
            if tp2_vuruldu:
                r_toplam += 2.0 * TP_SPLIT[1]
                kalan -= TP_SPLIT[1]
                tp2_oldu = True

        if tp2_oldu:
            tp3_vuruldu = (h >= tp3) if direction == "long" else (l <= tp3)
            if tp3_vuruldu:
                r_toplam += 3.0 * TP_SPLIT[2]
                return {"r": r_toplam, "sure_mum": i - giris_idx, "sonuc": "TP3", "cikis_i": i}

    return {"r": r_toplam, "sure_mum": len(m15_df) - giris_idx, "sonuc": "AÇIK_KALDI(veri bitti)", "cikis_i": len(m15_df) - 1}


# ════════════════════════════════════════════
# ADIM 1: HER COIN İÇİN ADAY SİNYALLERİ BUL
# ════════════════════════════════════════════
def coin_sinyalleri_bul(symbol):
    print(f"[{symbol}] veri indiriliyor...")
    h1_df  = gecmis_veri_cek(symbol, "1h", GECMIS_GUN + 5)
    m15_df = gecmis_veri_cek(symbol, "15m", GECMIS_GUN + 5)

    if any(df is None or len(df) < 200 for df in [h1_df, m15_df]):
        print(f"[{symbol}] yetersiz veri, atlandı")
        return None, []

    atr_series = calc_atr_series(m15_df, ATR_PERIOD)

    sinyaller = []
    for i in range(SQUEEZE_LOOKBACK + DONCHIAN_PERIOD + 5, len(m15_df)):
        yon = squeeze_kirilim_sinyali(m15_df, atr_series, i)
        if not yon:
            continue

        simdiki_zaman = m15_df["t"].iloc[i]
        if not trend_filtresi(h1_df, simdiki_zaman, yon):
            continue

        entry = m15_df["c"].iloc[i]
        atr_simdi = atr_series.iloc[i]
        risk_mesafe = ATR_SL_MULT * atr_simdi
        if risk_mesafe <= 0:
            continue
        sl = entry - risk_mesafe if yon == "long" else entry + risk_mesafe

        sinyaller.append({
            "symbol": symbol, "i": i + 1, "t": simdiki_zaman,  # yönetim i+1'den başlar (bakış-öne hatası olmasın)
            "direction": yon, "entry": entry, "sl": sl,
        })

    print(f"[{symbol}] {len(sinyaller)} aday sinyal bulundu")
    return m15_df, sinyaller


# ════════════════════════════════════════════
# ADIM 2: PORTFÖY SİMÜLASYONU (MAX_POS kısıtı)
# ════════════════════════════════════════════
def portfoy_simulasyonu(tum_m15, tum_sinyaller, max_pos=1):
    tum_sinyaller.sort(key=lambda s: s["t"])
    islemler = []
    acik_pozisyonlar = []

    for sig in tum_sinyaller:
        acik_pozisyonlar = [bitis for bitis in acik_pozisyonlar if bitis > sig["t"]]
        if len(acik_pozisyonlar) >= max_pos:
            continue

        m15_df = tum_m15[sig["symbol"]]
        sonuc = islemi_simule_et(m15_df, sig["i"], sig["direction"], sig["entry"], sig["sl"])
        if not sonuc:
            continue

        cikis_i = sonuc["cikis_i"]
        cikis_zaman = m15_df["t"].iloc[min(cikis_i, len(m15_df) - 1)]

        sonuc["symbol"] = sig["symbol"]
        sonuc["direction"] = sig["direction"]
        sonuc["zaman"] = datetime.fromtimestamp(sig["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        islemler.append(sonuc)
        acik_pozisyonlar.append(cikis_zaman)

    return islemler


# ════════════════════════════════════════════
# ANA
# ════════════════════════════════════════════
def main():
    print("🔖 VERSİYON: v1\n")
    print(f"═══ SQUEEZE KIRILIM BACKTEST — son {GECMIS_GUN} gün, en yüksek hacimli {TOP_COINS} coin, MAX_POS={MAX_POS_BACKTEST} ═══\n")
    semboller = sembol_listesi_al(TOP_COINS, MIN_VOLUME)
    print(f"{len(semboller)} coin bulundu: {', '.join(s.split('/')[0] for s in semboller[:10])}...\n")

    tum_m15 = {}
    tum_sinyaller = []
    for sym in semboller:
        try:
            m15_df, sinyaller = coin_sinyalleri_bul(sym)
            if m15_df is not None:
                tum_m15[sym] = m15_df
                tum_sinyaller.extend(sinyaller)
        except Exception as e:
            print(f"[{sym}] HATA: {e}")

    print(f"\nToplam aday sinyal (tüm coinlerde): {len(tum_sinyaller)}")
    print(f"Portföy genelinde MAX_POS={MAX_POS_BACKTEST} kısıtı uygulanıyor...\n")

    tum_islemler = portfoy_simulasyonu(tum_m15, tum_sinyaller, max_pos=MAX_POS_BACKTEST)

    if not tum_islemler:
        print("\nHİÇ İŞLEM BULUNAMADI — filtre çok sıkı olabilir veya veri çekilemedi.")
        return

    df = pd.DataFrame(tum_islemler)
    kazanan = df[df["r"] > 0]
    kaybeden = df[df["r"] <= 0]

    print("\n" + "═" * 50)
    print(f"TOPLAM İŞLEM: {len(df)} (aday sinyal: {len(tum_sinyaller)}, MAX_POS={MAX_POS_BACKTEST} nedeniyle {len(tum_sinyaller)-len(df)} kaçırıldı)")
    print(f"Kazanan: {len(kazanan)} ({len(kazanan)/len(df)*100:.1f}%)")
    print(f"Kaybeden: {len(kaybeden)} ({len(kaybeden)/len(df)*100:.1f}%)")
    print(f"Toplam R: {df['r'].sum():+.2f}")
    print(f"Ortalama R/işlem: {df['r'].mean():+.3f}")
    print(f"Ortalama kazanan R: {kazanan['r'].mean():+.3f}" if len(kazanan) else "Kazanan yok")
    print(f"Ortalama kaybeden R: {kaybeden['r'].mean():+.3f}" if len(kaybeden) else "Kaybeden yok")
    print(f"Ortalama işlem süresi: {df['sure_mum'].mean()*15:.0f} dakika")
    print(f"Günde ortalama işlem: {len(df)/GECMIS_GUN:.2f}")
    print("═" * 50)

    df.to_csv("squeeze_backtest_sonuclar.csv", index=False)
    print("\nDetaylı sonuçlar 'squeeze_backtest_sonuclar.csv' dosyasına kaydedildi.")


if __name__ == "__main__":
    main()
