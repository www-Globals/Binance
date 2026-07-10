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
    all_keys = list(exchange.markets.keys())
    print(f"[DEBUG] Total symbols: {len(all_keys)}")
    print(f"[DEBUG] Sample symbols: {all_keys[:10]}")
except Exception as e:
    print(f"[CLIENT] ⚠️ Initial connection failed: {e}")

# ---------- GLOBALS ----------
market_prices = {}
markets = {}
ws_prices = {}

# ---------- TRADING RULES (Risk-controlled, no pauses) ----------
KES_RATE = 130
TAKER_FEE = 0.001
PROFIT_THRESHOLD = 0.0005        # 0.05% – low but safe
SLIPPAGE_BUFFER = 0.0005
COMPOUND_RATE = 0.85             # use 85% of balance
MAX_LOSS_PER_TRADE_KES = 15      # max loss before logging but not pausing
MIN_TRADE_USDT = 5
MAX_SPREAD = 0.02                # 2% max spread
MIN_PROFIT_KES = 1               # trade even for 1 KES profit

# ---------- AVAILABLE TRIANGLES (based on testnet symbols) ----------
TRIANGLES = [
    ["USDT", "BTC", "BNB"],   # BTC/USDT, BNB/BTC, BNB/USDT
    ["USDT", "SOL", "BNB"],   # SOL/USDT, SOL/BNB, BNB/USDT
    ["USDT", "BNB", "BTC"],   # BNB/USDT, BNB/BTC, BTC/USDT
]

def get_symbols_from_triangles():
    candidates = set()
    for a, b, c in TRIANGLES:
        candidates.add(f"{b}/{a}")
        candidates.add(f"{b}/{c}")
        candidates.add(f"{c}/{a}")
        candidates.add(f"{b}{a}")
        candidates.add(f"{b}{c}")
        candidates.add(f"{c}{a}")
    return list(candidates)

ALL_SYMBOLS = get_symbols_from_triangles()
print(f"[DEBUG] Candidate symbols: {ALL_SYMBOLS}")

def filter_existing_symbols(candidates):
    if not exchange.markets:
        return candidates
    existing = [s for s in candidates if s in exchange.markets]
    if not existing:
        print("[WARN] None of the candidate symbols exist.")
        print("[WARN] Available sample:", list(exchange.markets.keys())[:20])
    return existing

ALL_SYMBOLS = filter_existing_symbols(ALL_SYMBOLS)
print(f"[DEBUG] Matched symbols: {ALL_SYMBOLS}")

# STATE – no daily resets, no pausing
daily_loss_kes = 0.0
consecutive_fails = 0
daily_reset_time = datetime.datetime.utcnow().date()
pause_until = 0          # will never be set
trades_today = 0
last_win_time = 0
first_scan_done = False

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
            global ws_prices
            ws_prices = market_prices
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
        print("[SUPABASE] Missing URL or key, cannot log.")
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
        else:
            print(f"[SUPABASE] Logged: {data}")
    except Exception as e:
        print(f"[SUPABASE LOG ERROR] {e}")

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
        if matched == 0:
            print("[WARN] No symbols matched – check available symbols.")
    except Exception as e:
        print(f"[FATAL] Could not load markets: {e}")

def round_qty(qty, symbol):
    if symbol not in markets:
        alt = symbol.replace('/', '') if '/' in symbol else f"{symbol[:3]}/{symbol[3:]}"
        if alt in markets:
            symbol = alt
    step = markets.get(symbol, {}).get('step', 0.001)
    return math.floor(qty / step) * step

def get_price(symbol):
    if symbol in market_prices:
        return market_prices[symbol]
    alt = symbol.replace('/', '') if '/' in symbol else f"{symbol[:3]}/{symbol[3:]}"
    if alt in market_prices:
        return market_prices[alt]
    return 0.0

def get_spread(symbol):
    try:
        orderbook = exchange.fetch_order_book(symbol, limit=5)
    except:
        alt = symbol.replace('/', '') if '/' in symbol else f"{symbol[:3]}/{symbol[3:]}"
        try:
            orderbook = exchange.fetch_order_book(alt, limit=5)
        except:
            return 0.01
    best_ask = orderbook['asks'][0][0] if orderbook['asks'] else None
    best_bid = orderbook['bids'][0][0] if orderbook['bids'] else None
    if best_ask and best_bid:
        return (best_ask - best_bid) / best_bid if best_bid else 0.01
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

# No daily reset or pausing – we keep functions but they are effectively no-ops
def reset_daily():
    # We don't reset anything – just keep state
    pass

def is_paused():
    return False   # never pause

def set_pause(seconds, reason):
    # Never pause – just log
    print(f"[PAUSE IGNORED] {reason}")
    telegram(f"⚠️ {reason} (ignored, bot continues)")

def cancel_all_orders():
    try:
        exchange.cancel_all_orders()
    except:
        pass

# ---------- ARBITRAGE ----------
def calc_profit(a, b, c, amount):
    try:
        sym1 = f"{b}/{a}"
        sym2 = f"{b}/{c}"
        sym3 = f"{c}/{a}"
        p_ab = get_price(sym1)
        p_bc = get_price(sym2)
        p_ca = get_price(sym3)
        if 0 in (p_ab, p_bc, p_ca):
            sym1_n = f"{b}{a}"
            sym2_n = f"{b}{c}"
            sym3_n = f"{c}{a}"
            p_ab = get_price(sym1_n)
            p_bc = get_price(sym2_n)
            p_ca = get_price(sym3_n)
            if 0 in (p_ab, p_bc, p_ca):
                return 0, 0, 0
            sym1, sym2, sym3 = sym1_n, sym2_n, sym3_n
        spread_ab = get_spread(sym1)
        spread_bc = get_spread(sym2)
        spread_ca = get_spread(sym3)
        max_spread = max(spread_ab, spread_bc, spread_ca)
        dynamic_threshold = PROFIT_THRESHOLD + SLIPPAGE_BUFFER + max_spread
        b_qty = (amount / p_ab) * (1 - TAKER_FEE)
        c_qty = (b_qty / p_bc) * (1 - TAKER_FEE)
        a_final = (c_qty * p_ca) * (1 - TAKER_FEE)
        profit_pct = (a_final - amount) / amount
        return profit_pct, dynamic_threshold, max_spread
    except Exception as e:
        print(f"[CALC ERROR] {e}")
        return 0, 0, 0

def execute_trade(a, b, c, trade_amount_usd):
    global daily_loss_kes, consecutive_fails, trades_today, last_win_time
    executed = []
    start_balance = get_total_usdt_balance()
    pair = f"{a}{b}{c}"

    try:
        if start_balance < trade_amount_usd + 1:
            raise Exception("Low balance")
        cancel_all_orders()

        sym1 = f"{b}/{a}"
        if get_price(sym1) <= 0:
            sym1 = f"{b}{a}"
        sym2 = f"{b}/{c}"
        if get_price(sym2) <= 0:
            sym2 = f"{b}{c}"
        sym3 = f"{c}/{a}"
        if get_price(sym3) <= 0:
            sym3 = f"{c}{a}"

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

        qty_b = round_qty(qty_b, sym2)
        o2 = exchange.create_market_sell_order(sym2, qty_b)
        qty_c = float(o2['filled'])
        if qty_c * get_price(sym2) < markets.get(sym2, {}).get('minNotional', 10):
            raise Exception("Leg2 below minNotional")
        executed.append((sym2, qty_c, 'SELL'))
        time.sleep(0.2)

        qty_c = round_qty(qty_c, sym3)
        o3 = exchange.create_market_sell_order(sym3, qty_c)
        executed.append((sym3, qty_c, 'SELL'))

        consecutive_fails = 0
        trades_today += 1
        last_win_time = time.time()
        end_balance = get_total_usdt_balance()
        profit_usd = end_balance - start_balance
        profit_kes = profit_usd * KES_RATE
        msg = f"✅ <b>WIN</b> {pair}\n+{profit_kes:.0f} KES | New: {end_balance:.2f} USDT"
        print(msg)
        telegram(msg)
        log_to_supabase({"pair": pair, "profit_kes": profit_kes, "status": "WIN", "balance": end_balance})
        time.sleep(1)   # brief cooldown
        return True

    except Exception as e:
        consecutive_fails += 1
        loss_usd = trade_amount_usd * 0.003
        loss_kes = loss_usd * KES_RATE
        daily_loss_kes += loss_kes
        trades_today += 1
        msg = f"❌ <b>LOSS</b> {pair}\n-{loss_kes:.0f} KES | Total loss: {daily_loss_kes:.0f} KES\nErr: {str(e)[:80]}"
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

        # No pause – just continue
        return False

def scan():
    global first_scan_done
    # reset_daily() is no-op
    # is_paused() always False
    if time.time() - last_win_time < 1:   # small cooldown
        return

    balance = get_total_usdt_balance()
    trade_amount = max(balance * COMPOUND_RATE, MIN_TRADE_USDT)

    if not first_scan_done and trades_today == 0:
        print("[FORCE] Executing a test trade on USDT-BTC-BNB")
        test_amount = min(trade_amount, 10.0)
        execute_trade('USDT', 'BTC', 'BNB', test_amount)
        first_scan_done = True
        return

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

    time.sleep(0.5)   # small pause between scans

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
    telegram("🚀 <b>BOT STARTED – TRADING FOREVER (TESTNET)</b>")
    print("[BOT] Running on TESTNET – no daily limits, no pauses.")
    main_loop()
