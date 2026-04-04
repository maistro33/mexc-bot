import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib

print("🚀 AI TRAINING BAŞLADI")

df = pd.read_csv("ai_live_data.csv")

print("📊 Veri:", len(df))

df["return"] = df["close"].pct_change()
df["target"] = np.where(df["return"].shift(-1) > 0, 1, 0)

df = df.dropna()

features = ["open","high","low","close","volume","volatility"]

X = df[features]
y = df["target"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, shuffle=False
)

model = XGBClassifier(n_estimators=120, max_depth=5)

model.fit(X_train, y_train)

preds = model.predict(X_test)
acc = accuracy_score(y_test, preds)

print("🎯 ACC:", acc)

joblib.dump(model, "ai_model.pkl")

print("✅ MODEL HAZIR")
