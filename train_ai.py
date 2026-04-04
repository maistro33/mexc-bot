import ccxt
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib
import time

print("🚀 AI v2.1 TRAINING BAŞLADI")

# ===== EXCHANGE =====
exchange = ccxt.bitget({
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

# ===== COINS =====
SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT"
]

data = []

# ===== RSI =====
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

# ===== DATA =====
for sym in SYMBOLS:
    print(f"📡 Veri çekiliyor: {sym}")

    try:
        ohlcv = exchange.fetch_ohlcv(sym, "5m", limit=500)

        for c in ohlcv:
            t, o, h, l, close, v = c
            volatility = (h - l) / close if close else 0

            data.append({
                "symbol": sym,
                "open": o,
                "high": h,
                "low": l,
                "close": close,
                "volume": v,
                "volatility": volatility
            })

        time.sleep(0.3)

    except Exception as e:
        print("DATA ERROR:", e)

# ===== DATAFRAME =====
df = pd.DataFrame(data)

print("📊 Veri:", len(df))

# ===== FEATURES =====
df["return"] = df["close"].pct_change()
df["rsi"] = compute_rsi(df["close"])
df["momentum"] = df["close"] - df["close"].shift(3)

# 🔥 SYMBOL FIX
df["symbol_code"] = df["symbol"].astype("category").cat.codes

df["target"] = np.where(df["return"].shift(-1) > 0, 1, 0)

df = df.dropna()

print("📊 Temiz veri:", len(df))

# ===== FEATURE SET =====
features = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "volatility",
    "rsi",
    "momentum",
    "symbol_code"
]

X = df[features]
y = df["target"]

# ===== SPLIT =====
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, shuffle=False
)

# ===== MODEL =====
model = XGBClassifier(
    n_estimators=250,
    max_depth=6,
    learning_rate=0.05
)

model.fit(X_train, y_train)

# ===== TEST =====
preds = model.predict(X_test)
acc = accuracy_score(y_test, preds)

print("🎯 ACCURACY:", acc)

# ===== SAVE =====
joblib.dump(model, "ai_model.pkl")

print("✅ AI v2.1 MODEL HAZIR")
