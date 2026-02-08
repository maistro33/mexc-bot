# --- TEST KODU: ÇALIŞTIĞI AN MARKET EMİR GÖNDERİR ---

def test_run():
    symbol = 'SOL/USDT:USDT' # Test için seçilen koin
    test_amount_usdt = 1.1    # Minimum limitlere takılmamak için 1.1 USDT
    test_leverage = 10        # 10x kaldıraç
    
    try:
        print(f"🚀 Test başlatılıyor: {symbol} için market emri gönderiliyor...")
        
        # 1. Kaldıraç Ayarla
        ex.set_leverage(test_leverage, symbol)
        
        # 2. Fiyatı Al ve Miktarı Hesapla
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        amount = (test_amount_usdt * test_leverage) / price
        
        # 3. DOĞRUDAN MARKET ALIM (LONG)
        order = ex.create_market_order(symbol, 'buy', amount)
        
        print(f"✅ BAŞARILI! İşlem açıldı. ID: {order['id']}")
        bot.send_message(MY_CHAT_ID, f"⚡ TEST: {symbol} işlemi başarıyla açıldı!")
        
    except Exception as e:
        print(f"❌ Test Hatası: {e}")
        bot.send_message(MY_CHAT_ID, f"❌ Test başarısız: {str(e)}")

# Ana döngü yerine sadece bunu çağırarak dene:
if __name__ == "__main__":
    test_run()
