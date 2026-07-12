# v16.42-bugfix Changelog

## 🔴 KRITIK HATALAR DÜZELTILDI

### 1. **Race Condition - Açılış Sırasında Manage Müdahalesi**
**Problem:** 
- `asil_islemi_ac()` market emri gönderip `trade_state`'e yazmadan ÖNCE
- `manage()` döngüsü (ayrı thread) pozisyonu "kayıtsız" sanıp kurtarma SL koymaya çalışıyor
- TP limit emirleri başarısız oluyor ("reduceOnly miktar yetersiz" hatası)

**Çözüm:**
- `islem_aciliyor` seti artık emri gönderirken değil, **HEMEN BAŞINDAN** set ediliyor
- `manage()` tamamen bitene kadar manage() döngüsü bu sembolü atlar
- Timeout kontrolü (30sn) eklendi - sonsuz beklemeyi önler

**Kod:**
```python
# ÖNCESİ (YANLIŞ):
acilis_emri = exchange.create_market_order(...)  # emri gönder
with state_lock:
    trade_state[sym] = {...}  # sonra kaydet

# SONRASİ (DOĞRU):
with islem_aciliyor_lock:
    islem_aciliyor[sym] = time.time()  # HEMEN başında
try:
    acilis_emri = exchange.create_market_order(...)
    # ... tüm TP/SL işlemleri ...
    # ... trade_state yazma ...
finally:
    with islem_aciliyor_lock:
        islem_aciliyor.pop(sym, None)  # açılış tamamen bitince çık
```

---

### 2. **Hard Stop Emri Başarısızlığı - Sessiz Geçme**
**Problem:**
- Hard stop emri konamadı → None döner
- Log yazılır ama işlem yine de açılır
- Ani çöküşlerde koruma yok

**Çözüm:**
- Hard stop konamazsa işlemi tamamen DURDUR
- Kullanıcıya hata mesajı gönder
- Tekrar dene mekanizması ekle

**Kod:**
```python
hard_stop_id = hard_stop_yerlestir(sym, direction, sl, qty)
if hard_stop_id is None and MAX_SL_PCT > 0:
    # v16.42: Hard stop ZORUNLU - başarısızsa işlem açılmaz
    tg(f"⛔ KRİTİK: {sym} borsada stop emri konalamadı - işlem açılmıyor. "
       f"Borsa durumunu kontrol et.")
    with islem_aciliyor_lock:
        islem_aciliyor.pop(sym, None)
    return
```

---

### 3. **TP Dilim Miktarı Hesaplama Hatası**
**Problem:**
- `kalan_qty` hesaplanırken canlı `qty` kullanılıyor (TP'ler nedeniyle küçülmüş)
- SL güncellemesinde yanlış miktar hard stop emrine gidiyor
- Örnek: TP1'de 30% kapandı, geriye 70% kaldı ama hard stop için full qty kullanılıyor

**Çözüm:**
- `orijinal_qty` korunuyor (açılış anındaki tam miktar)
- TP dilimler `orijinal_qty` × oran'dan hesaplanıyor
- Hard stop güncellemesinde kalan gerçek miktar kullanılıyor

**Kod:**
```python
# ÖNCESİ (YANLIŞ):
kalan_qty_sonrasi = max(qty - kapatilacak, 0)
hard_stop_guncelle(sym, direction, yeni_sl, kalan_qty_sonrasi)

# SONRASİ (DOĞRU):
orijinal_qty = durum.get("orijinal_qty", qty)
oran = _tp_dilim_orani(tp_index, len(tp_liste))
kapatilacak = min(orijinal_qty * oran, qty)  # limitli
kalan_qty_sonrasi = max(qty - kapatilacak, 0)  # gerçek kalan
hard_stop_guncelle(sym, direction, yeni_sl, kalan_qty_sonrasi)
```

---

### 4. **Volatilite Ölçümü - Scalp vs Manuel Ayrımı**
**Problem:**
- Manuel işlemler 3m volatilite kullanıyordu (WLDUSDT: %0.27 → SL %0.4 → anında stop)
- Scalp işlemler ayrı hesaplama yapıyor ama inconsistent

**Çözüm:**
- `manuel_volatilite_hesapla()` açıkça 1H kullanıyor (makul)
- `oz_tarama_volatilite_hesapla()` 3m'de tutuluyor (scalp için uygun)
- Minimum SL tabanı artırıldı: %0.4 → %0.6 (gürültü toleransı)

**Kod:**
```python
def asil_islemi_ac(sinyal, gozlem_str=""):
    if entry_hedef is None or sl is None:
        # v16.42: Manuel işlemler için HARP 1H volatilite
        volatilite_pct = manuel_volatilite_hesapla(sym, tf="1h", mum_sayisi=20)
        if volatilite_pct is not None:
            sl_pct_hesap = max(0.006, min(volatilite_pct / 100 * 2.0, MAX_SL_PCT))
        else:
            sl_pct_hesap = HIZLI_SL_PCT
```

---

### 5. **Telegram Yedek Boyut Kontrolü**
**Problem:**
- 10+ açık pozisyon varsa state > 4000 karakter
- Telegram'a yazılamıyor, sessizce başarısız oluyor

**Çözüm:**
- Yedek verisi sıkıştırılıyor (sadece kritik alanlar)
- Büyükse parçaya ayrılıyor veya log yazılıyor

**Kod:**
```python
# v16.42: State'i sıkıştır
veri_bekleyen = {
    sym: {
        "direction": k["sinyal"]["direction"],
        "entry": k["sinyal"].get("entry"),
        "eklenme_zamani": k["eklenme_zamani"]
    }
    for sym, k in bekleyen_sinyaller.items()
}
```

---

### 6. **Emir Doğrulama Logic'i - Çift Kapanma Önleme**
**Problem:**
- API gecikme varsa limit emrin durumu "open" görünüyor
- Code fiyat hedefini geçtiyse kendi market emri gönderip çift kapanma oluyor

**Çözüm:**
- Limit emir durumu başarıyla doğrulandıysa (durum_str in ("closed", "filled"))
  → fiyat karşılaştırmasına HIÇBIR şekilde girilmiyor
- Fallback SADECE: emir_id yok VEYA durumu ÖĞRENİLEMEDİ

**Kod:**
```python
if emir_dogrulanabildi and durum_str in ("closed", "filled"):
    # v16.42: Emir başarıyla doğrulandı - fiyat kontrol EDİLMEZ
    tp_vuruldu = True
    emirle_dolmus = True
elif not tp_vuruldu and not (emir_id and emir_dogrulanabildi):
    # v16.42: Fallback SADECE: emir yok veya kontrol başarısız
    hedef = tp_liste[tp_index]
    tp_vuruldu = (price >= hedef) if direction == "long" else (price <= hedef)
```

---

## 📊 ÖZET TABLO

| Hata | Etki | Çözüm | Statü |
|------|------|-------|-------|
| Race Condition | TP emirleri başarısız | islem_aciliyor seti + finally | ✅ |
| Hard Stop Hatası | Ani çöküşe karşı çaresiz | Konamazsa işlem durdur | ✅ |
| TP Dilim Qty | Yanlış SL miktarı | orijinal_qty korunuyor | ✅ |
| Volatilite (scalp) | Çok dar SL | Min %0.6'ya yükseltildi | ✅ |
| Telegram Backup | State yazılamıyor | Sıkıştırma + parçalama | ✅ |
| Çift Kapanma | Aynı TP iki kez | Emir doğrulama kesinleştirme | ✅ |

---

## 🚀 NASIL DEPLOY EDILECEK

1. `v16.42-bugfix` branch'ini test et (paper trading)
2. Sorun yoksa main'e merge et
3. Railway'de redeploy et

---

**Versiyon:** v16.42-bugfix  
**Tarih:** 2026-07-12  
**Yazar:** Copilot Bugfix Team
