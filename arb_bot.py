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

print("[INIT] Starting bot...", flush=True)
print(f"[INIT] BINANCE_API_KEY = {BINANCE_API_KEY[:4] if BINANCE_API_KEY else 'None'}...", flush=True)
print(f"[INIT] SUPABASE_URL = {SUPABASE_URL}", flush=True)

# ---------- CCXT EXCHANGE (TESTNET) ----------
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True)

try:
    exchange.load_markets()
    print("[CLIENT] ✅ Connected to Binance testnet.", flush=True)
except Exception as e:
    print(f"[CLIENT] ❌ Connection failed: {e}", flush=True)

# ---------- GLOBALS ----------
prices = {}
markets = {}
blacklist = {}
daily_loss_kes = 0.0
daily_start_balance = 0.0
daily_reset_time = datetime.datetime.utcnow().date()
last_price_update = 0
consecutive_fails = 0
last_fail_time = 0
scan_count = 0

# ---------- CONSTANTS (ultra-low for testnet) ----------
KES_RATE = 130
TAKER_FEE = 0.001

PROFIT_THRESHOLD = 0.0001        # 0.01%
SLIPPAGE_BUFFER = 0.0001
MIN_PROFIT_KES = 1
MAX_SPREAD = 0.02                # 2%

TRADE_FRACTION = 0.05
MAX_TRADE_USD = 5000
MIN_TRADE_USDT = 5
DAILY_LOSS_LIMIT_PCT = 0.05

# ---------- TESTNET TRIANGLES ----------
TRIANGLES = [
    ("USDT", "BTC", "ETH"),
    ("USDT", "BTC", "BNB"),
    ("USDT", "ETH", "BNB"),
    ("USDT", "BTC", "FDUSD"),
    ("USDT", "ETH", "FDUSD"),
    ("USDT", "BNB", "FDUSD"),
]

def get_all_symbols():
    syms = set()
    for a, b, c in TRIANGLES:
        syms.add(f"{b}/{a}")
        syms.add(f"{b}/{c}")
        syms.add(f"{c}/{a}")
    return list(syms)

ALL_SYMBOLS = get_all_symbols()
print(f"[INIT] Target symbols: {ALL_SYMBOLS}", flush=True)

# ---------- LOAD MARKETS ----------
VALID_TRIANGLES = []

def load_markets():
    global markets, VALID_TRIANGLES
    try:
        exchange.load_markets()
        available = set(exchange.markets.keys())
        for a, b, c in TRIANGLES:
            sym1 = f"{b}/{a}"
            sym2 = f"{b}/{c}"
            sym3 = f"{c}/{a}"
            if sym1 in available and sym2 in available and sym3 in available:
                VALID_TRIANGLES.append((a, b, c))
                for sym in (sym1, sym2, sym3):
                    info = exchange.markets[sym]
                    markets[sym] = {
                        'step': info['precision']['amount'],
                        'minNotional': info['limits']['cost']['min']
                    }
        print(f"[MARKETS] Loaded {len(VALID_TRIANGLES)} valid triangles", flush=True)
        for tri in VALID_TRIANGLES:
            print(f"  ✅ {tri[0]}-{tri[1]}-{tri[2]}", flush=True)
    except Exception as e:
        print(f"[FATAL] Could not load markets: {e}", flush=True)

# ---------- FLASK WEB SERVER ----------
@app.route('/health')
def health():
    ws_age = time.time() - last_price_update
    return {
        "status": "ok",
        "daily_loss_kes": daily_loss_kes,
        "testnet": True,
        "ws_age_sec": round(ws_age, 1),
        "pairs_tracked": len(prices),
        "valid_triangles": len(VALID_TRIANGLES)
    }, 200

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
    global prices, last_price_update
    while True:
        try:
            tickers = exchange.fetch_tickers()
            now = time.time()
            for sym, data in tickers.items():
                if sym in markets:
                    prices[sym] = data['last']
            last_price_update = now
        except Exception as e:
            print(f"[PRICE ERROR] {e}", flush=True)
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
            print(f"[SUPABASE] Error {r.status_code}: {r.text}", flush=True)
    except Exception as e:
        print(f"[SUPABASE] {e}", flush=True)

def get_price(symbol):
    if time.time() - last_price_update > 3:
        try:
            ticker = exchange.fetch_ticker(symbol)
            prices[symbol] = ticker['last']
            return ticker['last']
        except:
            return 0.0
    return prices.get(symbol, 0.0)

def get_spread(symbol):
    try:
        ob = exchange.fetch_order_book(symbol, limit=5)
        best_ask = ob['asks'][0][0] if ob['asks'] else None
        best_bid = ob['bids'][0][0] if ob['bids'] else None
        if best_ask and best_bid:
            return (best_ask - best_bid) / best_bid
        return 0.01
    except:
        return 0.01

def round_qty(qty, symbol):
    if symbol not in markets:
        return max(math.floor(qty / 0.001) * 0.001, 0.001)
    step = markets[symbol]['step']
    minN = markets[symbol]['minNotional']
    price = get_price(symbol)
    if price <= 0:
        return step
    min_qty = minN / price
    rounded = math.floor(qty / step) * step
    if rounded < min_qty:
        rounded = math.ceil(min_qty / step) * step
    if rounded <= 0:
        rounded = step
    return rounded

def get_total_usdt_balance():
    try:
        bal = exchange.fetch_balance()
        total = 0.0
        for asset, amount in bal['total'].items():
            if amount <= 0: continue
            if asset == 'USDT':
                total += amount
            else:
                price = get_price(f"{asset}/USDT")
                if price <= 0:
                    price = get_price(f"{asset}USDT")
                if price > 0:
                    total += amount * price
        print(f"[BALANCE] {total:.2f} USDT", flush=True)
        return total
    except Exception as e:
        print(f"[BALANCE ERROR] {e}", flush=True)
        return 50.0

def cancel_all_orders():
    try:
        exchange.cancel_all_orders()
    except:
        pass

def reset_daily():
    global daily_loss_kes, daily_start_balance, daily_reset_time
    now = datetime.datetime.utcnow().date()
    if now != daily_reset_time:
        daily_loss_kes = 0.0
        daily_start_balance = get_total_usdt_balance()
        daily_reset_time = now
        print(f"[DAILY RESET] New balance: {daily_start_balance:.2f} USDT", flush=True)

def is_blacklisted(triangle):
    return triangle in blacklist and blacklist[triangle] > time.time()

# ---------- ARBITRAGE CORE ----------
def calc_profit(a, b, c, amount):
    try:
        sym1 = f"{b}/{a}"
        sym2 = f"{b}/{c}"
        sym3 = f"{c}/{a}"
        p_ab = get_price(sym1)
        p_bc = get_price(sym2)
        p_ca = get_price(sym3)
        if 0 in (p_ab, p_bc, p_ca):
            return 0, 0, None
        sp1 = get_spread(sym1)
        sp2 = get_spread(sym2)
        sp3 = get_spread(sym3)
        max_spread = max(sp1, sp2, sp3)
        b_qty = (amount / p_ab) * (1 - TAKER_FEE)
        c_qty = (b_qty * p_bc) * (1 - TAKER_FEE)
        a_final = (c_qty * p_ca) * (1 - TAKER_FEE)
        profit_pct = (a_final - amount) / amount * 100
        return profit_pct, max_spread, (sym1, sym2, sym3, p_ab, p_bc, p_ca)
    except Exception as e:
        print(f"[CALC ERROR] {e}", flush=True)
        return 0, 0, None

def execute_trade(a, b, c, trade_amount_usd, gross_spread, legs):
    global daily_loss_kes, consecutive_fails, last_fail_time
    sym1, sym2, sym3, p_ab, p_bc, p_ca = legs
    pair = f"{a}{b}{c}"
    executed = []
    start_balance = get_total_usdt_balance()
    start_time = time.time()

    try:
        if start_balance < trade_amount_usd * 1.1:
            raise Exception("Insufficient balance")
        cancel_all_orders()

        price = p_ab
        if price <= 0:
            raise Exception("Price1 unavailable")
        base_qty = trade_amount_usd / price
        base_qty = round_qty(base_qty, sym1)
        if base_qty <= 0:
            raise Exception("Qty1 too small")
        o1 = exchange.create_market_buy_order(sym1, base_qty)
        qty_b = float(o1['filled'])
        if qty_b * get_price(sym1) < markets.get(sym1, {}).get('minNotional', 10):
            raise Exception("Leg1 below minNotional")
        executed.append((sym1, qty_b, 'BUY'))
        time.sleep(0.2)

        qty_b = round_qty(qty_b, sym2)
        if qty_b <= 0:
            raise Exception("Qty2 too small")
        o2 = exchange.create_market_sell_order(sym2, qty_b)
        qty_c = float(o2['filled'])
        if qty_c * get_price(sym2) < markets.get(sym2, {}).get('minNotional', 10):
            raise Exception("Leg2 below minNotional")
        executed.append((sym2, qty_c, 'SELL'))
        time.sleep(0.2)

        qty_c = round_qty(qty_c, sym3)
        if qty_c <= 0:
            raise Exception("Qty3 too small")
        o3 = exchange.create_market_sell_order(sym3, qty_c)
        executed.append((sym3, qty_c, 'SELL'))

        consecutive_fails = 0
        end_balance = get_total_usdt_balance()
        profit_usd = end_balance - start_balance
        profit_kes = profit_usd * KES_RATE
        latency_ms = int((time.time() - start_time) * 1000)
        status = "WIN" if profit_kes > 0 else "LOSS"

        msg = f"✅ {status} {pair} {profit_kes:+.0f} KES | New: {end_balance:.2f} USDT"
        print(msg, flush=True)
        telegram(msg)

        log_to_supabase({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "balance": end_balance,
            "pair": pair,
            "profit_kes": profit_kes,
            "status": status,
            "trade_size_80pct": trade_amount_usd,
            "gross_spread": gross_spread,
            "execution_mode": "MARKET",
            "latency_ms": latency_ms,
            "reason": ""
        })
        time.sleep(1)
        return True

    except Exception as e:
        consecutive_fails += 1
        last_fail_time = time.time()
        loss_usd = trade_amount_usd * 0.003
        loss_kes = loss_usd * KES_RATE
        daily_loss_kes += loss_kes
        msg = f"❌ LOSS {pair} -{loss_kes:.0f} KES | Err: {str(e)[:80]}"
        print(msg, flush=True)
        telegram(msg)

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
                print(f"Rollback failed {symbol}: {roll_err}", flush=True)

        log_to_supabase({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "balance": start_balance,
            "pair": pair,
            "profit_kes": loss_kes,
            "status": "LOSS",
            "trade_size_80pct": trade_amount_usd,
            "gross_spread": gross_spread,
            "execution_mode": "MARKET",
            "latency_ms": int((time.time() - start_time) * 1000),
            "reason": str(e)
        })

        if gross_spread > 0.002:
            blacklist[pair] = time.time() + 3600
            print(f"[BLACKLIST] {pair} blacklisted 1h", flush=True)

        if consecutive_fails >= 3:
            print("[BACKOFF] 3 fails – waiting 60s", flush=True)
            time.sleep(60)
            consecutive_fails = 0

        return False

def scan():
    global daily_loss_kes, scan_count
    print(f"[SCAN] Running scan #{scan_count+1}", flush=True)
    reset_daily()

    if daily_loss_kes > daily_start_balance * DAILY_LOSS_LIMIT_PCT:
        print(f"[DAILY LOSS] Hit 5% limit. Pausing 1h.", flush=True)
        telegram(f"⛔ Daily loss limit hit. Pausing 1h.")
        time.sleep(3600)
        return

    balance = get_total_usdt_balance()
    raw_trade = balance * TRADE_FRACTION
    trade_amount = min(raw_trade, MAX_TRADE_USD)
    trade_amount = max(trade_amount, MIN_TRADE_USDT)

    best_profit = 0
    best_tri = None
    best_spread = 0
    best_legs = None

    for a, b, c in VALID_TRIANGLES:
        pair_key = f"{a}{b}{c}"
        if is_blacklisted(pair_key):
            continue
        profit_pct, spread, legs = calc_profit(a, b, c, trade_amount)
        if profit_pct > best_profit:
            best_profit = profit_pct
            best_tri = (a, b, c)
            best_spread = spread
            best_legs = legs

    scan_count += 1

    # ---- Print best profit every scan (for visibility) ----
    if best_tri is not None:
        print(f"[SCAN #{scan_count}] Best: {best_profit:.4f}% from {best_tri[0]}{best_tri[1]}{best_tri[2]}, spread {best_spread:.3%}", flush=True)
    else:
        print(f"[SCAN #{scan_count}] No valid triangle (best profit {best_profit:.4f}%)", flush=True)

    # ---- Trade if opportunity ----
    if best_tri is not None and best_profit >= PROFIT_THRESHOLD:
        a, b, c = best_tri
        pair_key = f"{a}{b}{c}"
        profit_kes = (trade_amount * best_profit / 100) * KES_RATE
        if profit_kes >= MIN_PROFIT_KES:
            print(f"[OPPORTUNITY] {pair_key} {best_profit:.2f}% > {PROFIT_THRESHOLD:.2f}% spread {best_spread:.3%}", flush=True)
            execute_trade(a, b, c, trade_amount, best_spread, best_legs)

    time.sleep(1)

def main_loop():
    print("[MAIN] Entering main loop", flush=True)
    while True:
        try:
            scan()
        except Exception as e:
            print(f"[FATAL] {e}", flush=True)
            telegram(f"💀 BOT CRASH: {e}")
            log_to_supabase({"status": "CRASH", "error": str(e)})
            time.sleep(60)

# ---------- STARTUP ----------
if __name__ == "__main__":
    load_markets()
    if VALID_TRIANGLES:
        daily_start_balance = get_total_usdt_balance()
        print(f"[BOT] Starting balance: {daily_start_balance:.2f} USDT", flush=True)

        threading.Thread(target=run_webserver, daemon=True).start()
        threading.Thread(target=keep_alive, daemon=True).start()
        threading.Thread(target=update_prices, daemon=True).start()

        time.sleep(5)
        telegram(f"🚀 BOT STARTED – {len(VALID_TRIANGLES)} triangles (testnet)")
        print(f"[BOT] {len(VALID_TRIANGLES)} triangles active. Trade cap: ${MAX_TRADE_USD}", flush=True)
        main_loop()
    else:
        print("[FATAL] No valid triangles found on testnet. Exiting.", flush=True)
        telegram("❌ No valid triangles on testnet – check symbols.")
