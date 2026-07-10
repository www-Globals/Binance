import os, time, threading, datetime, requests, math
from flask import Flask
import ccxt

app = Flask(__name__)

# ---------- ENV ----------
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

print(f"[DEBUG] BINANCE_API_KEY = {BINANCE_API_KEY[:4] if BINANCE_API_KEY else 'None'}...")
print(f"[DEBUG] SUPABASE_URL = {SUPABASE_URL}")

# ---------- CCXT EXCHANGE (TESTNET) ----------
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True)

try:
    exchange.load_markets()
    print("[CLIENT] ✅ Connected to Binance testnet.")
except Exception as e:
    print(f"[CLIENT] ⚠️ Initial connection failed: {e}")

# ---------- GLOBALS ----------
market_prices = {}
markets = {}
consecutive_fails = 0
last_fail_time = 0

# ---------- TRADING RULES (Safe) ----------
KES_RATE = 130
TAKER_FEE = 0.001
PROFIT_THRESHOLD = 0.001        # 0.1%
SLIPPAGE_BUFFER = 0.001
TRADE_FRACTION = 0.20           # use 20% of balance per trade
MAX_SPREAD = 0.01               # 1% max spread
MIN_PROFIT_KES = 5              # at least 5 KES profit
MIN_TRADE_USDT = 10             # minimum trade size

# ---------- VALID TRIANGLES ----------
TRIANGLES = [
    ["USDT", "BNB", "BTC"],   # BNB/USDT, BNB/BTC, BTC/USDT
    ["USDT", "SOL", "BNB"],   # SOL/USDT, SOL/BNB, BNB/USDT
]

def get_symbols_from_triangles():
    symbols = set()
    for a, b, c in TRIANGLES:
        symbols.add(f"{b}/{a}")   # BNB/USDT
        symbols.add(f"{b}/{c}")   # BNB/BTC
        symbols.add(f"{c}/{a}")   # BTC/USDT
    return list(symbols)

ALL_SYMBOLS = get_symbols_from_triangles()
print(f"[DEBUG] Target symbols: {ALL_SYMBOLS}")

def load_markets():
    global markets
    try:
        exchange.load_markets()
        matched = 0
        for sym in ALL_SYMBOLS:
            if sym in exchange.markets:
                info = exchange.markets[sym]
                markets[sym] = {
                    'step': info['precision']['amount'],
                    'minNotional': info['limits']['cost']['min']
                }
                matched += 1
        print(f"✅ Loaded markets for {matched} symbols")
        if matched < len(ALL_SYMBOLS):
            print("[WARN] Some symbols not found. Available:", list(exchange.markets.keys())[:20])
    except Exception as e:
        print(f"[FATAL] Could not load markets: {e}")

# ---------- FLASK WEB SERVER ----------
@app.route('/health')
def health():
    return {"status": "ok", "testnet": True}, 200

def run_webserver():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    while True:
        time.sleep(540)
        if RENDER_URL:
            try:
                requests.get(f"{RENDER_URL}/health", timeout=10)
            except:
                pass

# ---------- PRICE UPDATER ----------
def update_prices():
    while True:
        try:
            tickers = exchange.fetch_tickers()
            for sym, data in tickers.items():
                if sym in ALL_SYMBOLS:
                    market_prices[sym] = data['last']
        except Exception as e:
            print(f"[PRICE UPDATE ERROR] {e}")
        time.sleep(2)

# ---------- UTILITIES ----------
def telegram(msg):
    if not TELEGRAM_TOKEN or not ADMIN_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=5
        )
    except:
        pass

def log_to_supabase(data):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/trades", json=data, headers=headers, timeout=5)
        if r.status_code != 201:
            print(f"[SUPABASE] Error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[SUPABASE LOG ERROR] {e}")

def round_qty(qty, symbol):
    if symbol not in markets:
        return math.floor(qty / 0.001) * 0.001
    step = markets[symbol]['step']
    return math.floor(qty / step) * step

def get_price(symbol):
    return market_prices.get(symbol, 0.0)

def get_spread(symbol):
    try:
        orderbook = exchange.fetch_order_book(symbol, limit=5)
        best_ask = orderbook['asks'][0][0] if orderbook['asks'] else None
        best_bid = orderbook['bids'][0][0] if orderbook['bids'] else None
        if best_ask and best_bid:
            return (best_ask - best_bid) / best_bid if best_bid else 0.01
        return 0.01
    except:
        return 0.01

def get_total_usdt_balance():
    try:
        balance = exchange.fetch_balance()
        total = 0.0
        for asset, amount in balance['total'].items():
            if amount <= 0:
                continue
            if asset == 'USDT':
                total += amount
            else:
                # try both formats
                price = get_price(f"{asset}/USDT")
                if price <= 0:
                    price = get_price(f"{asset}USDT")
                if price > 0:
                    total += amount * price
        print(f"[BALANCE] Total USDT: {total:.2f}")
        return max(total, 10.0)
    except Exception as e:
        print(f"[BALANCE ERROR] {e}")
        return 50.0

def cancel_all_orders():
    try:
        exchange.cancel_all_orders()
    except:
        pass

# ---------- ARBITRAGE ----------
def calc_profit(a, b, c, amount):
    try:
        sym1 = f"{b}/{a}"   # BNB/USDT
        sym2 = f"{b}/{c}"   # BNB/BTC
        sym3 = f"{c}/{a}"   # BTC/USDT
        p_ab = get_price(sym1)
        p_bc = get_price(sym2)
        p_ca = get_price(sym3)
        if 0 in (p_ab, p_bc, p_ca):
            return 0, 0, 0
        spread_ab = get_spread(sym1)
        spread_bc = get_spread(sym2)
        spread_ca = get_spread(sym3)
        max_spread = max(spread_ab, spread_bc, spread_ca)
        dynamic_threshold = PROFIT_THRESHOLD + SLIPPAGE_BUFFER + max_spread
        b_qty = (amount / p_ab) * (1 - TAKER_FEE)
        c_qty = (b_qty * p_bc) * (1 - TAKER_FEE)  # since p_bc is price of c in terms of b, so b_qty * p_bc gives c amount? Actually, if we sell b and buy c, we get c_qty = b_qty * (bid price of c in b) / 1? The price is c/b, so if we sell b, we get c_qty = b_qty / p_bc? Let's be precise: The pair is b/c, i.e., price is how much c you get for 1 b. So if you sell b_qty of b, you get c_qty = b_qty * p_bc. Correct.
        a_final = (c_qty * p_ca) * (1 - TAKER_FEE)  # sell c for a (USDT)
        profit_pct = (a_final - amount) / amount
        return profit_pct, dynamic_threshold, max_spread
    except Exception as e:
        print(f"[CALC ERROR] {e}")
        return 0, 0, 0

def execute_trade(a, b, c, trade_amount_usd):
    global consecutive_fails, last_fail_time
    executed = []
    start_balance = get_total_usdt_balance()
    pair = f"{a}{b}{c}"

    # Safety check: ensure balance is sufficient
    if start_balance < trade_amount_usd * 1.2:
        msg = f"[SKIP] Insufficient balance: {start_balance:.2f} USDT < {trade_amount_usd:.2f} * 1.2"
        print(msg)
        return False

    try:
        cancel_all_orders()

        sym1 = f"{b}/{a}"   # buy b with a
        sym2 = f"{b}/{c}"   # sell b for c
        sym3 = f"{c}/{a}"   # sell c for a

        price = get_price(sym1)
        if price <= 0:
            raise Exception("Price unavailable")
        base_qty = trade_amount_usd / price
        base_qty = round_qty(base_qty, sym1)
        if base_qty <= 0:
            raise Exception("Quantity too small")
        o1 = exchange.create_market_buy_order(sym1, base_qty)
        qty_b = float(o1['filled'])
        if qty_b * get_price(sym1) < markets.get(sym1, {}).get('minNotional', 10):
            raise Exception("Leg1 below minNotional")
        executed.append((sym1, qty_b, 'BUY'))
        time.sleep(0.2)

        # Leg 2: sell b for c
        qty_b = round_qty(qty_b, sym2)
        o2 = exchange.create_market_sell_order(sym2, qty_b)
        qty_c = float(o2['filled'])
        if qty_c * get_price(sym2) < markets.get(sym2, {}).get('minNotional', 10):
            raise Exception("Leg2 below minNotional")
        executed.append((sym2, qty_c, 'SELL'))
        time.sleep(0.2)

        # Leg 3: sell c for a
        qty_c = round_qty(qty_c, sym3)
        o3 = exchange.create_market_sell_order(sym3, qty_c)
        executed.append((sym3, qty_c, 'SELL'))

        # WIN
        consecutive_fails = 0
        end_balance = get_total_usdt_balance()
        profit_usd = end_balance - start_balance
        profit_kes = profit_usd * KES_RATE
        msg = f"✅ <b>WIN</b> {pair}\n+{profit_kes:.0f} KES | New: {end_balance:.2f} USDT"
        print(msg)
        telegram(msg)
        log_to_supabase({"pair": pair, "profit_kes": profit_kes, "status": "WIN", "balance": end_balance})
        time.sleep(1)
        return True

    except Exception as e:
        consecutive_fails += 1
        last_fail_time = time.time()
        loss_usd = trade_amount_usd * 0.003
        loss_kes = loss_usd * KES_RATE
        msg = f"❌ <b>LOSS</b> {pair}\n-{loss_kes:.0f} KES | Err: {str(e)[:80]}"
        print(msg)
        telegram(msg)

        # Rollback
        for symbol, qty, side in reversed(executed):
            try:
                if side == 'BUY':
                    qty = round_qty(qty, symbol)
                    exchange.create_market_sell_order(symbol, qty)
                else:
                    qty = round_qty(qty, symbol)
                    exchange.create_market_buy_order(symbol, qty)
                time.sleep(0.2)
            except Exception as roll_err:
                print(f"Rollback failed for {symbol}: {roll_err}")

        log_to_supabase({"pair": pair, "profit_kes": loss_kes, "status": "LOSS", "balance": start_balance, "error": str(e)})

        # if too many fails, wait a bit
        if consecutive_fails >= 3:
            print("[BACKOFF] 3 consecutive fails – waiting 60s")
            time.sleep(60)
            consecutive_fails = 0

        return False

def scan():
    # Check if we are in backoff
    if consecutive_fails >= 3 and time.time() - last_fail_time < 60:
        return

    balance = get_total_usdt_balance()
    trade_amount = max(balance * TRADE_FRACTION, MIN_TRADE_USDT)
    print(f"[SCAN] Balance: {balance:.2f} USDT, Trade amount: {trade_amount:.2f} USDT")

    best_profit = 0
    best_tri = None
    best_threshold = 0
    best_spread = 0

    for a, b, c in TRIANGLES:
        profit_pct, threshold, spread = calc_profit(a, b, c, trade_amount)
        if spread > MAX_SPREAD:
            continue
        if profit_pct > best_profit:
            best_profit = profit_pct
            best_tri = [a, b, c]
            best_threshold = threshold
            best_spread = spread

    if best_tri and best_profit > best_threshold:
        profit_kes = (trade_amount * best_profit) * KES_RATE
        if profit_kes > MIN_PROFIT_KES:
            a, b, c = best_tri
            print(f"[BEST OPP] {a}{b}{c} {best_profit*100:.3f}% > {best_threshold*100:.3f}% Spread:{best_spread*100:.2f}% = {profit_kes:.0f} KES")
            execute_trade(a, b, c, trade_amount)

    time.sleep(1)

def main_loop():
    while True:
        try:
            scan()
        except Exception as e:
            print(f"[FATAL] {e}")
            telegram(f"💀 BOT CRASH: {e}")
            log_to_supabase({"status": "CRASH", "error": str(e)})
            time.sleep(60)

# ---------- STARTUP ----------
if __name__ == "__main__":
    cancel_all_orders()
    load_markets()
    log_to_supabase({"pair": "STARTUP", "profit_kes": 0, "status": "STARTUP", "balance": 0})

    threading.Thread(target=run_webserver, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=update_prices, daemon=True).start()

    time.sleep(5)
    telegram("🚀 <b>BOT STARTED – SAFE MODE (TESTNET)</b>")
    print("[BOT] Running on TESTNET – using 20% per trade, backoff on failures.")
    main_loop()
