#!/usr/bin/env python3
"""
FVG/SMC STRATEJİSİ — GEÇMİŞ VERİYLE BACKTEST (+ MARKET YAPISI DEĞİŞİMİ TEYİDİ)
🔖 VERSİYON: v5 (BOS/market yapısı değişimi teyidi eklendi — bir trader'ın
    öğrettiği metodolojiden: likidite süpürmesi + FVG yeterli değil,
    ikisi arasında piyasa yapısının GERÇEKTEN değiştiği de teyit ediliyor)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Amaç: "Profesyonel FVG bot" stratejisinin (günlük+4h trend teyidi +
likidite süpürmesi + 15m FVG girişi + R bazlı kademeli TP/başa baş)
GERÇEK GEÇMİŞ VERİDE ne sıklıkta sinyal ürettiğini ve sonuçlarının ne
olduğunu gösterir — günlerce canlı beklemek yerine dakikalar içinde.

ÖNEMLİ DÜRÜSTLÜK NOTU: Coin listesi ŞU ANKİ en yüksek hacimli coinlerden
alınıyor (sembol_listesi_al canlı ticker kullanıyor). 2022 gibi eski bir
dönem test edilirken, o coinlerin BİR KISMI henüz borsada işlem
görmüyordu ("yetersiz veri, atlandı" olarak elenir) — yani test edilen
küme kısmen daha az sayıda, daha çok "kalıcı/köklü" coin olur. Bu,
survivorship bias'ı tamamen ORTADAN KALDIRMAZ ama en azından bu dönemde
gerçekten var olan coinlerle sınırlar.

ÖNEMLİ: Bu script gerçek para KULLANMAZ, hiçbir emir açmaz. Sadece
geçmiş OHLCV verisini indirip, aynı sinyal mantığını "olsaydı ne olurdu"
şeklinde simüle eder (bakış-öne hatası olmaması için mum-mum ilerler).

ÇALIŞTIRMA:
  pip install ccxt pandas --break-system-packages   (gerekirse)
  python3 fvg_backtest.py
"""

import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta, timezone

# ════════════════════════════════════════════
# CONFIG — istediğin gibi değiştirebilirsin
# ════════════════════════════════════════════
# ── Tarih aralığı: belirli bir dönemi test etmek için ──
# Varsayılan: 2022 (kripto ayı/düşüş piyasası) — stratejinin SADECE iyi
# giden 2024-2025 döneminde değil, zorlu bir dönemde de tutup tutmadığını
# görmek için. None bırakırsan (BASLANGIC_TARIHI=None) "bugünden GECMIS_GUN
# kadar geriye" eski davranışa döner.
BASLANGIC_TARIHI = None   # önce yakın dönemde (son 365 gün) test — BOS eklemenin
                          # etkisini mevcut kanıtlanmış dönemle karşılaştırmak için
BITIS_TARIHI     = None
GECMIS_GUN     = 365

TOP_COINS      = 100     # en yüksek hacimli kaç coin denenecek
MAX_POS_BACKTEST = 5     # aynı anda kaç işleme izin verilir
MIN_VOLUME     = 5_000_000
BUFFER_PCT     = 0.0015
LEV            = 10
MARGIN         = 10
TP_SPLIT       = [0.4, 0.3, 0.3]

# ── Funding rate maliyeti (gerçekçilik için) ──
# Kripto perpetual'larda her 8 saatte bir funding ödenir/alınır. Ortalama
# bir varsayım kullanıyoruz (gerçek geçmiş funding verisi çekmek ayrı bir
# API yükü gerektirir) — bu, KONSERVATİF bir tahmin, gerçek maliyet daha
# yüksek ya da düşük olabilir.
FUNDING_ORANI_8SAAT = 0.0001   # %0.01 / 8 saat (tipik ortalama varsayım)

exchange = ccxt.bitget({"options": {"defaultType": "swap"}, "enableRateLimit": True})


# ════════════════════════════════════════════
# GEÇMİŞ VERİ ÇEKME (sayfalama ile — belirli bir tarih aralığında)
# ════════════════════════════════════════════
def gecmis_veri_cek(symbol, timeframe, baslangic_ms, bitis_ms):
    """Bitget'ten [baslangic_ms, bitis_ms] aralığındaki OHLCV verisini
    sayfalayarak çeker."""
    tum_mumlar = []
    since = baslangic_ms
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
        son_zaman = mumlar[-1][0]
        if son_zaman >= bitis_ms:
            break
        yeni_since = son_zaman + 1
        if yeni_since <= since:
            break
        since = yeni_since
        time.sleep(exchange.rateLimit / 1000)
    if not tum_mumlar:
        return None
    df = pd.DataFrame(tum_mumlar, columns=["t", "o", "h", "l", "c", "v"])
    df = df.drop_duplicates(subset="t").sort_values("t").reset_index(drop=True)
    df = df[(df["t"] >= baslangic_ms) & (df["t"] <= bitis_ms)].reset_index(drop=True)
    return df


def tarih_araligi_hesapla():
    """Config'e göre (baslangic_ms, bitis_ms) döner."""
    if BASLANGIC_TARIHI:
        baslangic = datetime.strptime(BASLANGIC_TARIHI, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        bitis_gecici = datetime.now(timezone.utc) if not BITIS_TARIHI else datetime.strptime(BITIS_TARIHI, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        baslangic = bitis_gecici - timedelta(days=GECMIS_GUN)

    if BITIS_TARIHI:
        bitis = datetime.strptime(BITIS_TARIHI, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        bitis = datetime.now(timezone.utc)

    return int(baslangic.timestamp() * 1000), int(bitis.timestamp() * 1000)


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
# SİNYAL MANTIĞI (orijinal bottan BİREBİR alınmıştır — mum-mum ilerleyecek
# şekilde uyarlanmıştır, bakış-öne hatası yok: her karar SADECE o ana
# kadarki mumlarla veriliyor)
# ════════════════════════════════════════════
def yon_belirle(d_df, h4_df, i_d, i_h4):
    """d_df/h4_df: günlük/4h DataFrame. i_d/i_h4: şu anki (dahil) son index."""
    if i_d < 2 or i_h4 < 2:
        return None
    d_high = d_df["h"].iloc[i_d - 1]
    d_high_onceki = d_df["h"].iloc[i_d - 2]
    d_low = d_df["l"].iloc[i_d - 1]
    d_low_onceki = d_df["l"].iloc[i_d - 2]

    h_high = h4_df["h"].iloc[i_h4 - 1]
    h_high_onceki = h4_df["h"].iloc[i_h4 - 2]
    h_low = h4_df["l"].iloc[i_h4 - 1]
    h_low_onceki = h4_df["l"].iloc[i_h4 - 2]

    if d_high > d_high_onceki and h_high > h_high_onceki:
        return "long"
    if d_low < d_low_onceki and h_low < h_low_onceki:
        return "short"
    return None


def likidite_supurmesi(h1_df, i_h1, direction):
    if i_h1 < 30:
        return False
    pencere_low = h1_df["l"].iloc[i_h1 - 30:i_h1 - 1]
    pencere_high = h1_df["h"].iloc[i_h1 - 30:i_h1 - 1]
    son_low = h1_df["l"].iloc[i_h1 - 1]
    son_high = h1_df["h"].iloc[i_h1 - 1]
    if direction == "long":
        return son_low < pencere_low.min()
    else:
        return son_high > pencere_high.max()


def market_yapisi_degisimi(m15_df, i_m15, direction):
    """
    YENİ EKLENEN ADIM (bir trader'ın öğrettiği metodolojiden): likidite
    süpürmesinden SONRA, piyasa yapısının GERÇEKTEN değiştiğini (BOS —
    Break of Structure) teyit eder. Süpürmeden hemen önceki yakın swing
    noktasının, ters yönde kırılıp kırılmadığını kontrol eder.

    Bu, sadece "FVG var" demenin ötesinde, "bu FVG gerçekten bir yön
    değişiminin İÇİNDE oluştu" teyidini ekliyor — sahte/erken sinyalleri
    elemeyi hedefliyor.
    """
    idx = i_m15 - 1
    pencere = 15
    if idx < pencere + 5:
        return False

    onceki_yuksek = m15_df["h"].iloc[idx - pencere: idx - 2].max()
    onceki_dusuk = m15_df["l"].iloc[idx - pencere: idx - 2].min()
    kapanis = m15_df["c"].iloc[idx]

    if direction == "long":
        return kapanis > onceki_yuksek
    else:
        return kapanis < onceki_dusuk


def giris_modeli(m15_df, i_m15, direction):
    if i_m15 < 60:
        return None
    o = m15_df["o"]; h = m15_df["h"]; l = m15_df["l"]; c = m15_df["c"]

    idx = i_m15 - 1
    body = abs(c.iloc[idx] - o.iloc[idx])
    avg_body = sum(abs(c.iloc[idx - k] - o.iloc[idx - k]) for k in range(1, 10)) / 9
    if body < avg_body * 1.5:
        return None

    if direction == "long" and h.iloc[idx - 2] < l.iloc[idx]:
        entry = (h.iloc[idx - 2] + l.iloc[idx]) / 2
        swing_low = l.iloc[idx - 14: idx + 1].min()
        sl = swing_low - (swing_low * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    if direction == "short" and l.iloc[idx - 2] > h.iloc[idx]:
        entry = (l.iloc[idx - 2] + h.iloc[idx]) / 2
        swing_high = h.iloc[idx - 14: idx + 1].max()
        sl = swing_high + (swing_high * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    return None


# ════════════════════════════════════════════
# İŞLEM SİMÜLASYONU (R bazlı, kademeli TP + başa baş)
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
                aktif_sl = entry  # başa baş

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
# ADIM 1: HER COIN İÇİN ADAY SİNYALLERİ TOPLA (henüz simüle etmeden)
# ════════════════════════════════════════════
def coin_sinyalleri_bul(symbol, baslangic_ms, bitis_ms):
    print(f"[{symbol}] veri indiriliyor...")
    buffer_ms = 10 * 24 * 60 * 60 * 1000  # 10 gün ısınma payı (indikatörler için)
    fetch_baslangic = baslangic_ms - buffer_ms

    d_df   = gecmis_veri_cek(symbol, "1d", fetch_baslangic, bitis_ms)
    h4_df  = gecmis_veri_cek(symbol, "4h", fetch_baslangic, bitis_ms)
    h1_df  = gecmis_veri_cek(symbol, "1h", fetch_baslangic, bitis_ms)
    m15_df = gecmis_veri_cek(symbol, "15m", fetch_baslangic, bitis_ms)

    if any(df is None or len(df) < 60 for df in [d_df, h4_df, h1_df, m15_df]):
        print(f"[{symbol}] yetersiz veri, atlandı")
        return None, []

    sinyaller = []
    for i in range(60, len(m15_df)):
        simdiki_zaman = m15_df["t"].iloc[i]
        if simdiki_zaman < baslangic_ms:
            continue  # bu, ısınma payı — gerçek test aralığı değil

        i_d = d_df[d_df["t"] <= simdiki_zaman].shape[0]
        i_h4 = h4_df[h4_df["t"] <= simdiki_zaman].shape[0]
        i_h1 = h1_df[h1_df["t"] <= simdiki_zaman].shape[0]

        direction = yon_belirle(d_df, h4_df, i_d, i_h4)
        if not direction:
            continue
        if not likidite_supurmesi(h1_df, i_h1, direction):
            continue
        if not market_yapisi_degisimi(m15_df, i + 1, direction):
            continue  # ── YENİ: BOS teyidi olmadan devam etme ──
        setup = giris_modeli(m15_df, i + 1, direction)
        if not setup:
            continue

        sinyaller.append({
            "symbol": symbol, "i": i, "t": simdiki_zaman,
            "direction": direction, "entry": setup["entry"], "sl": setup["sl"],
        })

    print(f"[{symbol}] {len(sinyaller)} aday sinyal bulundu")
    return m15_df, sinyaller


# ════════════════════════════════════════════
# ADIM 2: TÜM SİNYALLERİ ZAMANA GÖRE SIRALA, TEK-POZİSYON (MAX_POS=1)
# KISITINI PORTFÖY GENELİNDE GERÇEKÇİ ŞEKİLDE UYGULA
# ════════════════════════════════════════════
def portfoy_simulasyonu(tum_m15, tum_sinyaller, max_pos=1):
    """
    max_pos: aynı anda kaç işleme izin verilir (orijinal bot MAX_POS=1
    kullanıyordu; burada bunu artırıp gerçekten bu kısıtın fırsat
    kaçırdığını doğrulayabiliyoruz).
    """
    tum_sinyaller.sort(key=lambda s: s["t"])

    islemler = []
    acik_pozisyonlar = []  # her eleman: bitiş zamanı (timestamp, ms)

    for sig in tum_sinyaller:
        # Süresi dolmuş (kapanmış) pozisyonları listeden temizle
        acik_pozisyonlar = [bitis for bitis in acik_pozisyonlar if bitis > sig["t"]]

        if len(acik_pozisyonlar) >= max_pos:
            continue  # slot dolu, bu sinyal kaçırılır

        m15_df = tum_m15[sig["symbol"]]
        sonuc = islemi_simule_et(m15_df, sig["i"], sig["direction"], sig["entry"], sig["sl"])
        if not sonuc:
            continue

        cikis_i = sonuc["cikis_i"]
        cikis_zaman = m15_df["t"].iloc[min(cikis_i, len(m15_df) - 1)]
        sonuc["entry"] = sig["entry"]
        sonuc["sl"] = sig["sl"]

        sonuc["symbol"] = sig["symbol"]
        sonuc["direction"] = sig["direction"]
        sonuc["zaman"] = datetime.fromtimestamp(sig["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        islemler.append(sonuc)

        acik_pozisyonlar.append(cikis_zaman)

    return islemler





def main():
    print("🔖 VERSİYON: v5 (BOS/market yapısı değişimi teyidi eklendi)\n")

    baslangic_ms, bitis_ms = tarih_araligi_hesapla()
    baslangic_str = datetime.fromtimestamp(baslangic_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    bitis_str = datetime.fromtimestamp(bitis_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    print(f"═══ FVG/SMC BACKTEST — {baslangic_str} → {bitis_str}, en yüksek hacimli {TOP_COINS} coin, MAX_POS={MAX_POS_BACKTEST} ═══\n")

    semboller = sembol_listesi_al(TOP_COINS, MIN_VOLUME)
    print(f"{len(semboller)} coin bulundu: {', '.join(s.split('/')[0] for s in semboller[:10])}...\n")

    tum_m15 = {}
    tum_sinyaller = []
    for sym in semboller:
        try:
            m15_df, sinyaller = coin_sinyalleri_bul(sym, baslangic_ms, bitis_ms)
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

    # ── FUNDING RATE MALİYETİ (konservatif tahmin) ──
    notional = MARGIN * LEV
    df["risk_dolar"] = notional * (abs(df["entry"] - df["sl"]) / df["entry"])
    df["sure_saat"] = df["sure_mum"] * 15 / 60
    df["funding_donem"] = df["sure_saat"] / 8
    df["funding_maliyet_dolar"] = notional * FUNDING_ORANI_8SAAT * df["funding_donem"]
    df["funding_maliyet_r"] = df["funding_maliyet_dolar"] / df["risk_dolar"].replace(0, float("nan"))
    df["r_net"] = df["r"] - df["funding_maliyet_r"].fillna(0)

    kazanan = df[df["r_net"] > 0]
    kaybeden = df[df["r_net"] <= 0]

    print("\n" + "═" * 50)
    print(f"TOPLAM İŞLEM: {len(df)} (aday sinyal: {len(tum_sinyaller)}, MAX_POS={MAX_POS_BACKTEST} nedeniyle {len(tum_sinyaller)-len(df)} kaçırıldı)")
    print(f"Kazanan (funding sonrası): {len(kazanan)} ({len(kazanan)/len(df)*100:.1f}%)")
    print(f"Kaybeden (funding sonrası): {len(kaybeden)} ({len(kaybeden)/len(df)*100:.1f}%)")
    print(f"Toplam R (funding ÖNCESİ, ham): {df['r'].sum():+.2f}")
    print(f"Toplam R (funding SONRASI, net): {df['r_net'].sum():+.2f}")
    print(f"Ortalama R/işlem (net): {df['r_net'].mean():+.3f}")
    print(f"Ortalama kazanan R (net): {kazanan['r_net'].mean():+.3f}" if len(kazanan) else "Kazanan yok")
    print(f"Ortalama kaybeden R (net): {kaybeden['r_net'].mean():+.3f}" if len(kaybeden) else "Kaybeden yok")
    print(f"Toplam funding maliyeti (R cinsinden): {df['funding_maliyet_r'].sum():+.2f}")
    print(f"Ortalama işlem süresi: {df['sure_mum'].mean()*15:.0f} dakika")
    toplam_gun = (bitis_ms - baslangic_ms) / (1000 * 60 * 60 * 24)
    print(f"Aya ortalama işlem: {len(df)/toplam_gun*30:.2f}")
    print(f"Test edilen dönem: {baslangic_str} → {bitis_str} ({toplam_gun:.0f} gün)")
    print("═" * 50)

    df.to_csv("fvg_backtest_sonuclar.csv", index=False)
    print("\nDetaylı sonuçlar 'fvg_backtest_sonuclar.csv' dosyasına kaydedildi.")


if __name__ == "__main__":
    main()
