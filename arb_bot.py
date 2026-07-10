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

# ---------- INITIALISE CCXT EXCHANGE (TESTNET) ----------
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET,
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True)   # forces testnet

print(f"[CLIENT] Using testnet: {exchange.urls['api']['public']}")

if not exchange:
    raise RuntimeError("CCXT exchange not initialised.")

# ---------- GLOBALS ----------
market_prices = {}        # symbol -> float (last price)
markets = {}              # symbol -> market info
ws_prices = {}            # kept for compatibility

# ---------- PRODUCTION RULES (LOWERED FOR TESTING) ----------
KES_RATE = 130
TAKER_FEE = 0.001
PROFIT_THRESHOLD = 0.0005   # 0.05% – much lower to force trades
SLIPPAGE_BUFFER = 0.0005    # smaller buffer
COMPOUND_RATE = 0.85
MAX_CONSECUTIVE_FAILS = 2
PAUSE_AFTER_2_FAILS_SEC = 900
MAX_DAILY_LOSS_KES = 300
PAUSE_AFTER_300KES_LOSS_SEC = 86400
MAX_LOSS_PER_TRADE_KES = 15
MIN_TRADE_USDT = 15
MAX_SPREAD = 0.01           # allow wider spreads on testnet
MIN_PROFIT_KES = 1          # any profit is fine

TRIANGLES = [
    ["USDT", "BTC", "ETH"], ["USDT", "BNB", "BTC"], ["USDT", "SOL", "BNB"],
    ["USDT", "XRP", "SOL"], ["USDT", "DOGE", "XRP"], ["USDT", "TRX", "DOGE"],
    ["USDT", "ADA", "TRX"], ["USDT", "DOT", "ADA"], ["USDT", "MATIC", "DOT"],
    ["USDT", "LTC", "MATIC"], ["USDT", "AVAX", "LTC"], ["USDT", "ATOM", "AVAX"],
    ["USDT", "LINK", "ATOM"], ["USDT", "UNI", "LINK"], ["USDT", "BCH", "UNI"],
]

def get_symbols_from_triangles():
    symbols = set()
    for a, b, c in TRIANGLES:
        symbols.add(f"{b}{a}")
        symbols.add(f"{b}{c}")
        symbols.add(f"{c}{a}")
    return list(symbols)

ALL_SYMBOLS = get_symbols_from_triangles()

# STATE
daily_loss_kes = 0.0
consecutive_fails = 0
daily_reset_time = datetime.datetime.utcnow().date()
pause_until = 0
trades_today = 0
last_win_time = 0
first_scan_done = False   # to force a test trade

# ---------- FLASK WEB SERVER ----------
@app.route('/health')
def health():
    return {"status": "ok", "daily_loss": daily_loss_kes, "testnet": True}, 200

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

# ---------- PRICE UPDATER (using ccxt ticker) ----------
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
        return
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/trades", json=data, headers=headers, timeout=5)
    except Exception as e:
        print(f"[SUPABASE LOG ERROR] {e}")

def load_markets():
    global markets
    try:
        exchange.load_markets()
        for sym in ALL_SYMBOLS:
            if sym in exchange.markets:
                info = exchange.markets[sym]
                lot_step = info['precision']['amount']
                min_notional = info['limits']['cost']['min']
                markets[sym] = {'step': lot_step, 'minNotional': min_notional}
        print(f"✅ Loaded markets for {len(markets)} symbols")
    except Exception as e:
        print(f"[FATAL] Could not load markets: {e}")

def round_qty(qty, symbol):
    step = markets.get(symbol, {}).get('step', 0.001)
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
                price = get_price(asset + 'USDT')
                if price > 0:
                    total += amount * price
        print(f"[BALANCE] Total USDT: {total:.2f}")
        return max(total, 10.0)
    except Exception as e:
        print(f"[BALANCE ERROR] {e}")
        return 50.0

def reset_daily():
    global daily_loss_kes, consecutive_fails, daily_reset_time, trades_today
    now = datetime.datetime.utcnow().date()
    if now != daily_reset_time:
        daily_loss_kes = 0.0
        consecutive_fails = 0
        trades_today = 0
        daily_reset_time = now

def is_paused():
    return time.time() < pause_until

def set_pause(seconds, reason):
    global pause_until
    pause_until = time.time() + seconds
    msg = f"⛔ <b>BOT PAUSED</b> for {seconds//60:.0f}min\nReason: {reason}"
    print(msg)
    telegram(msg)
    log_to_supabase({"status": "PAUSE", "reason": reason})

def cancel_all_orders():
    try:
        exchange.cancel_all_orders()
    except:
        pass

# ---------- ARBITRAGE LOGIC ----------
def calc_profit(a, b, c, amount):
    try:
        sym1 = f"{b}{a}"
        sym2 = f"{b}{c}"
        sym3 = f"{c}{a}"

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
        c_qty = (b_qty / p_bc) * (1 - TAKER_FEE)
        a_final = (c_qty * p_ca) * (1 - TAKER_FEE)
        profit_pct = (a_final - amount) / amount
        return profit_pct, dynamic_threshold, max_spread
    except:
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

        # LEG 1: Buy b with a (USDT)
        sym1 = f"{b}{a}"
        price = get_price(sym1)
        if price <= 0:
            raise Exception("Price unavailable")
        base_qty = trade_amount_usd / price
        base_qty = round_qty(base_qty, sym1)
        if base_qty <= 0:
            raise Exception("Quantity too small")
        o1 = exchange.create_market_buy_order(sym1, base_qty)
        qty_b = float(o1['filled'])
        if qty_b * get_price(sym1) < markets[sym1]['minNotional']:
            raise Exception("Leg1 below minNotional")
        executed.append((sym1, qty_b, 'BUY'))
        time.sleep(0.2)

        # LEG 2: Sell b for c
        sym2 = f"{b}{c}"
        qty_b = round_qty(qty_b, sym2)
        o2 = exchange.create_market_sell_order(sym2, qty_b)
        qty_c = float(o2['filled'])
        if qty_c * get_price(sym2) < markets[sym2]['minNotional']:
            raise Exception("Leg2 below minNotional")
        executed.append((sym2, qty_c, 'SELL'))
        time.sleep(0.2)

        # LEG 3: Sell c for a (USDT)
        sym3 = f"{c}{a}"
        qty_c = round_qty(qty_c, sym3)
        o3 = exchange.create_market_sell_order(sym3, qty_c)
        executed.append((sym3, qty_c, 'SELL'))

        # WIN
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
        time.sleep(15)
        return True

    except Exception as e:
        consecutive_fails += 1
        loss_usd = trade_amount_usd * 0.003
        loss_kes = loss_usd * KES_RATE
        daily_loss_kes += loss_kes
        trades_today += 1
        msg = f"❌ <b>LOSS</b> {pair}\n-{loss_kes:.0f} KES | Daily: {daily_loss_kes:.0f} KES\nErr: {str(e)[:80]}"
        print(msg)
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
                print(f"Rollback failed for {symbol}: {roll_err}")

        log_to_supabase({"pair": pair, "loss_kes": loss_kes, "status": "LOSS", "error": str(e)})

        if loss_kes > MAX_LOSS_PER_TRADE_KES:
            set_pause(3600, f"Single trade loss > {MAX_LOSS_PER_TRADE_KES} KES")
        if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
            set_pause(PAUSE_AFTER_2_FAILS_SEC, "2 consecutive fails")
            consecutive_fails = 0
        if daily_loss_kes >= MAX_DAILY_LOSS_KES:
            set_pause(PAUSE_AFTER_300KES_LOSS_SEC, "Daily loss > 300 KES")
        return False

def scan():
    global first_scan_done
    reset_daily()
    if is_paused():
        return
    if time.time() - last_win_time < 15:
        return

    balance = get_total_usdt_balance()
    trade_amount = max(balance * COMPOUND_RATE, MIN_TRADE_USDT)

    # ---------- FORCE A TEST TRADE ON FIRST SCAN ----------
    if not first_scan_done and trades_today == 0:
        print("[FORCE] Executing a test trade on USDT-BTC-ETH")
        # Use a small amount to avoid too much risk
        test_amount = min(trade_amount, 20.0)
        execute_trade('USDT', 'BTC', 'ETH', test_amount)
        first_scan_done = True
        return   # skip normal scan for this cycle

    # ---------- NORMAL SCAN ----------
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

    time.sleep(3)

def main_loop():
    while True:
        try:
            scan()
        except Exception as e:
            print(f"[FATAL] {e}")
            telegram(f"💀 BOT CRASH: {e}")
            time.sleep(60)

# ---------- STARTUP ----------
if __name__ == "__main__":
    cancel_all_orders()
    load_markets()

    threading.Thread(target=run_webserver, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=update_prices, daemon=True).start()

    time.sleep(5)
    telegram("🚀 <b>BOT STARTED (TESTNET – CCXT)</b>")
    print("[BOT] Running on TESTNET using ccxt – all trades are paper.")

    main_loop()
