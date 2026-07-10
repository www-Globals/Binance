import os, time, threading, datetime, requests, math, json
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

print(f"[INIT] BINANCE_API_KEY = {BINANCE_API_KEY[:4] if BINANCE_API_KEY else 'None'}...")
print(f"[INIT] SUPABASE_URL = {SUPABASE_URL}")

# ---------- CCXT EXCHANGE (TESTNET) ----------
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True)   # always testnet for now

try:
    exchange.load_markets()
    print("[CLIENT] ✅ Connected to Binance testnet.")
except Exception as e:
    print(f"[CLIENT] ❌ Connection failed: {e}")

# ---------- GLOBALS ----------
prices = {}                # symbol -> last price
markets = {}
blacklist = {}             # triangle -> expiry timestamp
daily_loss_kes = 0.0
daily_start_balance = 0.0
daily_reset_time = datetime.datetime.utcnow().date()
last_price_update = 0      # timestamp of last price fetch
consecutive_fails = 0
last_fail_time = 0

# ---------- CONSTANTS (tuned per your recommendations) ----------
KES_RATE = 130
TAKER_FEE = 0.001
PROFIT_THRESHOLD = 0.0035        # 0.35% (was 0.30)
SLIPPAGE_BUFFER = 0.004          # 0.4% (was 0.3)
TRADE_FRACTION = 0.80            # 80% of balance
MAX_TRADE_USD = 100              # safety cap for testnet
MIN_TRADE_USDT = 10
MIN_PROFIT_KES = 50              # was 40
MAX_SPREAD = 0.002               # 0.2% – blacklist if exceeded
DAILY_LOSS_LIMIT_PCT = 0.05      # 5%

# ---------- 15 PRE‑LOADED TRIANGLES (from the prompt) ----------
# We keep the list, but only those with available pairs on testnet will be used.
TRIANGLES = [
    ("USDT", "SOL", "DOGE"),   # 1
    ("USDT", "PEPE", "SHIB"),  # 2
    ("USDT", "WIF", "BONK"),   # 3
    ("USDT", "DOGE", "PE"),    # 4
    ("USDT", "RNDR", "TAO"),   # 5
    ("USDT", "FET", "AGIX"),   # 6
    ("USDT", "RNDR", "SOL"),   # 7
    ("USDT", "OP", "ARB"),     # 8
    ("USDT", "IMX", "GALA"),   # 9
    ("USDT", "MATIC", "OP"),   # 10
    ("USDT", "XRP", "ADA"),    # 11
    ("USDT", "LTC", "XRP"),    # 12
    ("USDT", "TRX", "BTC"),    # 13
    ("USDT", "SOL", "PEPE"),   # 14
    ("USDT", "TAO", "FET"),    # 15
]

def get_symbols_from_triangles():
    syms = set()
    for a, b, c in TRIANGLES:
        syms.add(f"{b}/{a}")   # buy b with a (e.g., SOL/USDT)
        syms.add(f"{b}/{c}")   # sell b for c (e.g., SOL/DOGE)
        syms.add(f"{c}/{a}")   # sell c for a (e.g., DOGE/USDT)
    return list(syms)

ALL_SYMBOLS = get_symbols_from_triangles()
print(f"[INIT] Target symbols: {ALL_SYMBOLS}")

# ---------- LOAD MARKETS & FILTER AVAILABLE SYMBOLS ----------
def load_markets():
    global markets
    try:
        exchange.load_markets()
        available = []
        for sym in ALL_SYMBOLS:
            if sym in exchange.markets:
                info = exchange.markets[sym]
                markets[sym] = {
                    'step': info['precision']['amount'],
                    'minNotional': info['limits']['cost']['min']
                }
                available.append(sym)
        print(f"[MARKETS] Loaded {len(available)}/{len(ALL_SYMBOLS)} symbols")
        if len(available) < len(ALL_SYMBOLS):
            print("[WARN] Some symbols missing – will skip those triangles.")
    except Exception as e:
        print(f"[FATAL] Could not load markets: {e}")

# ---------- FLASK WEB SERVER (with WS‑age monitoring) ----------
@app.route('/health')
def health():
    ws_age = time.time() - last_price_update
    return {
        "status": "ok",
        "daily_loss_kes": daily_loss_kes,
        "daily_start_balance": daily_start_balance,
        "testnet": True,
        "ws_age_sec": round(ws_age, 1),
        "pairs_tracked": len(prices)
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

# ---------- PRICE UPDATER (REST with timestamp, WebSocket‑like freshness) ----------
def update_prices():
    global prices, last_price_update
    while True:
        try:
            tickers = exchange.fetch_tickers()
            now = time.time()
            for sym, data in tickers.items():
                if sym in ALL_SYMBOLS:
                    prices[sym] = data['last']
            last_price_update = now
        except Exception as e:
            print(f"[PRICE ERROR] {e}")
        time.sleep(2)   # refresh every 2s

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
        print(f"[SUPABASE] {e}")

def get_price(symbol):
    """Return latest price, with stale‑data protection."""
    if time.time() - last_price_update > 3:
        # fallback to direct REST call
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
    step = markets.get(symbol, {}).get('step', 0.001)
    return math.floor(qty / step) * step

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
        print(f"[BALANCE] {total:.2f} USDT")
        return total
    except Exception as e:
        print(f"[BALANCE ERROR] {e}")
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
        print(f"[DAILY RESET] New balance: {daily_start_balance:.2f} USDT")

def is_blacklisted(triangle):
    return triangle in blacklist and blacklist[triangle] > time.time()

# ---------- ARBITRAGE CORE ----------
def calc_profit(a, b, c, amount):
    """Return profit_percent, max_spread, and leg prices (or None)."""
    try:
        # Correct symbol order: 
        # Leg1: buy b with a  -> pair b/a (e.g., SOL/USDT)
        # Leg2: sell b for c -> pair b/c (e.g., SOL/DOGE)
        # Leg3: sell c for a -> pair c/a (e.g., DOGE/USDT)
        sym1 = f"{b}/{a}"
        sym2 = f"{b}/{c}"
        sym3 = f"{c}/{a}"

        p_ab = get_price(sym1)
        p_bc = get_price(sym2)
        p_ca = get_price(sym3)
        if 0 in (p_ab, p_bc, p_ca):
            return 0, 0, None

        # Compute spreads
        sp1 = get_spread(sym1)
        sp2 = get_spread(sym2)
        sp3 = get_spread(sym3)
        max_spread = max(sp1, sp2, sp3)

        # Simulate trade (market order, taker fees)
        b_qty = (amount / p_ab) * (1 - TAKER_FEE)
        c_qty = (b_qty * p_bc) * (1 - TAKER_FEE)
        a_final = (c_qty * p_ca) * (1 - TAKER_FEE)
        profit_pct = (a_final - amount) / amount * 100   # percent

        return profit_pct, max_spread, (sym1, sym2, sym3, p_ab, p_bc, p_ca)
    except Exception as e:
        print(f"[CALC ERROR] {e}")
        return 0, 0, None

def execute_trade(a, b, c, trade_amount_usd, gross_spread, legs):
    global daily_loss_kes, consecutive_fails, last_fail_time
    sym1, sym2, sym3, p_ab, p_bc, p_ca = legs
    pair = f"{a}{b}{c}"
    executed = []
    start_balance = get_total_usdt_balance()
    start_time = time.time()

    try:
        # Check balance before trading
        if start_balance < trade_amount_usd * 1.1:
            raise Exception("Insufficient balance")

        cancel_all_orders()

        # ----- LEG 1: Market buy b with a (USDT) -----
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

        # ----- LEG 2: Market sell b for c -----
        qty_b = round_qty(qty_b, sym2)
        o2 = exchange.create_market_sell_order(sym2, qty_b)
        qty_c = float(o2['filled'])
        if qty_c * get_price(sym2) < markets.get(sym2, {}).get('minNotional', 10):
            raise Exception("Leg2 below minNotional")
        executed.append((sym2, qty_c, 'SELL'))
        time.sleep(0.2)

        # ----- LEG 3: Market sell c for a (USDT) -----
        qty_c = round_qty(qty_c, sym3)
        o3 = exchange.create_market_sell_order(sym3, qty_c)
        executed.append((sym3, qty_c, 'SELL'))

        # WIN
        consecutive_fails = 0
        end_balance = get_total_usdt_balance()
        profit_usd = end_balance - start_balance
        profit_kes = profit_usd * KES_RATE
        latency_ms = int((time.time() - start_time) * 1000)
        msg = f"✅ WIN {pair} +{profit_kes:.0f} KES | New: {end_balance:.2f} USDT"
        print(msg)
        telegram(msg)
        log_to_supabase({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "current_balance": end_balance,
            "trade_size_80pct": trade_amount_usd,
            "triangle": pair,
            "gross_spread": gross_spread,
            "net_profit_kes": profit_kes,
            "execution_mode": "MARKET",
            "latency_ms": latency_ms,
            "action": "WIN",
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
                print(f"Rollback failed {symbol}: {roll_err}")

        log_to_supabase({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "current_balance": start_balance,
            "trade_size_80pct": trade_amount_usd,
            "triangle": pair,
            "gross_spread": gross_spread,
            "net_profit_kes": loss_kes,
            "execution_mode": "MARKET",
            "latency_ms": int((time.time() - start_time) * 1000),
            "action": "LOSS",
            "reason": str(e)
        })

        # Blacklist if slippage > 0.2%
        if gross_spread > 0.002:
            blacklist[pair] = time.time() + 3600
            print(f"[BLACKLIST] {pair} blacklisted 1h (spread {gross_spread:.3%})")

        # Backoff on consecutive fails
        if consecutive_fails >= 3:
            print("[BACKOFF] 3 fails – waiting 60s")
            time.sleep(60)
            consecutive_fails = 0

        return False

# ---------- MAIN SCAN ----------
def scan():
    global daily_loss_kes, last_price_update
    reset_daily()

    # Check daily loss limit (5%)
    if daily_loss_kes > daily_start_balance * DAILY_LOSS_LIMIT_PCT:
        msg = f"[DAILY LOSS] Hit 5% limit. Pausing 1 hour."
        print(msg)
        telegram(f"⛔ {msg}")
        time.sleep(3600)
        return

    # Compute trade amount: 80% of balance, but cap at $100 for testnet safety
    balance = get_total_usdt_balance()
    raw_trade = balance * TRADE_FRACTION
    trade_amount = min(raw_trade, MAX_TRADE_USD)
    trade_amount = max(trade_amount, MIN_TRADE_USDT)

    # Scan all triangles
    best_profit = 0
    best_tri = None
    best_spread = 0
    best_legs = None

    for a, b, c in TRIANGLES:
        pair_key = f"{a}{b}{c}"
        if is_blacklisted(pair_key):
            continue
        profit_pct, spread, legs = calc_profit(a, b, c, trade_amount)
        if profit_pct > best_profit:
            best_profit = profit_pct
            best_tri = (a, b, c)
            best_spread = spread
            best_legs = legs

    if best_tri and best_profit >= PROFIT_THRESHOLD:
        a, b, c = best_tri
        pair_key = f"{a}{b}{c}"
        profit_kes = (trade_amount * best_profit / 100) * KES_RATE
        if profit_kes >= MIN_PROFIT_KES:
            print(f"[OPPORTUNITY] {pair_key} {best_profit:.2f}% > {PROFIT_THRESHOLD:.2f}% spread {best_spread:.3%}")
            execute_trade(a, b, c, trade_amount, best_spread, best_legs)
    else:
        print(f"[SCAN] No profitable opportunity (best {best_profit:.2f}%)")

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
    load_markets()
    log_to_supabase({"pair": "STARTUP", "profit_kes": 0, "status": "STARTUP", "balance": 0})
    daily_start_balance = get_total_usdt_balance()

    threading.Thread(target=run_webserver, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=update_prices, daemon=True).start()

    time.sleep(5)
    telegram("🚀 BOT STARTED – ULTRASOUND V3.0 (TESTNET)")
    print("[BOT] Running – 80% balance, 0.35% threshold, 5% daily stop, $100 cap.")
    main_loop()
