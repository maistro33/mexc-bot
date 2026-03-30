import ccxt from "ccxt";
import axios from "axios";

// ===== API =====
const exchange = new ccxt.bitget({
  apiKey: process.env.API_KEY,
  secret: process.env.API_SECRET,
  password: process.env.API_PASS,
  options: { defaultType: "swap" },
  enableRateLimit: true,
});

// ===== TELEGRAM =====
const TELEGRAM_TOKEN = process.env.TG_TOKEN;
const CHAT_ID = process.env.TG_CHAT;

// ===== SETTINGS =====
const SYMBOL = "BTC/USDT:USDT";
const LEVERAGE = 5;

const GRID_SIZE = 6;
const GRID_SPREAD = 0.012;     // %1.2 aralık
const RESET_THRESHOLD = 0.018; // %1.8 reset

let lastCenterPrice = null;
let lastResetTime = 0;

// ===== TELEGRAM =====
async function send(msg) {
  try {
    await axios.post(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
      chat_id: CHAT_ID,
      text: msg,
    });
  } catch {}
}

// ===== LEVERAGE =====
async function setLeverage() {
  try {
    await exchange.setLeverage(LEVERAGE, SYMBOL);
  } catch {}
}

// ===== LOT HESAP =====
function calcQty(balance, price) {
  if (!price || price <= 0) return 0;

  const usable = balance * 0.9;
  let qty = usable / GRID_SIZE / price;

  return parseFloat(qty.toFixed(4)); // BTC precision
}

// ===== EMİRLERİ TEMİZLE =====
async function cancelAll() {
  try {
    const orders = await exchange.fetchOpenOrders(SYMBOL);
    for (let o of orders) {
      await exchange.cancelOrder(o.id, SYMBOL);
    }
  } catch {}
}

// ===== GRID KUR =====
async function placeGrid(price) {
  try {
    const balance = await exchange.fetchBalance();
    const usdt = balance.USDT.free;

    if (!usdt || usdt < 5) {
      await send("❌ Bakiye düşük");
      return;
    }

    const qty = calcQty(usdt, price);
    if (qty <= 0) return;

    for (let i = 1; i <= GRID_SIZE; i++) {
      const buyPrice = price * (1 - GRID_SPREAD * i);
      const sellPrice = price * (1 + GRID_SPREAD * i);

      try {
        await exchange.createLimitBuyOrder(SYMBOL, qty, buyPrice);
        await send(`📉 BUY ${buyPrice.toFixed(1)}`);
      } catch {}

      try {
        await exchange.createLimitSellOrder(SYMBOL, qty, sellPrice);
        await send(`📈 SELL ${sellPrice.toFixed(1)}`);
      } catch {}
    }

    await send("📊 GRID KURULDU");
  } catch (e) {
    console.log("GRID ERROR:", e.message);
  }
}

// ===== RESET =====
async function resetGrid(price) {
  const now = Date.now();

  // spam koruma (15 sn)
  if (now - lastResetTime < 15000) return;

  await send("♻️ RESET");

  await cancelAll();
  await placeGrid(price);

  lastCenterPrice = price;
  lastResetTime = now;
}

// ===== ANA KONTROL =====
async function monitor() {
  try {
    const ticker = await exchange.fetchTicker(SYMBOL);
    const price = ticker.last;

    if (!price || price <= 0) return;

    // ilk kurulum
    if (!lastCenterPrice) {
      await placeGrid(price);
      lastCenterPrice = price;
      return;
    }

    const diff = Math.abs(price - lastCenterPrice) / lastCenterPrice;

    // reset kontrol
    if (diff > RESET_THRESHOLD) {
      await resetGrid(price);
    }

  } catch (e) {
    console.log("MONITOR ERROR:", e.message);
  }
}

// ===== START =====
async function run() {
  await setLeverage();
  await send("🤖 FINAL GRID BOT AKTİF");

  while (true) {
    await monitor();
    await new Promise(r => setTimeout(r, 5000));
  }
}

run();
