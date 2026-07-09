import os, time, threading, datetime, requests, math
from flask import Flask
from binance.client import Client
from binance.websocket.spot.websocket_client import SpotWebsocketClient
from binance.exceptions import BinanceAPIException

app = Flask(__name__)

# ---------- ENV ----------
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
USE_TESTNET = os.getenv("USE_TESTNET", "false").lower() == "true"

if USE_TESTNET:
    client = Client(BINANCE_API_KEY, BINANCE_SECRET, testnet=True)
    client.API_URL = 'https://testnet.binance.vision/api'
else:
    client = Client(BINANCE_API_KEY, BINANCE_SECRET) if BINANCE_API_KEY else None

if not client:
    raise RuntimeError("Binance client not initialised. Check API keys and testnet flag.")

ws_prices = {}       # symbol -> {'bid': float, 'ask': float}
symbol_info = {}

# ---------- PRODUCTION RULES V3.4 PARANOID ----------
KES_RATE = 130
TAKER_FEE = 0.001
PROFIT_THRESHOLD = 0.0030
SLIPPAGE_BUFFER = 0.003
COMPOUND_RATE = 0.85
MAX_CONSECUTIVE_FAILS = 2
PAUSE_AFTER_2_FAILS_SEC = 900
MAX_DAILY_LOSS_KES = 300
PAUSE_AFTER_300KES_LOSS_SEC = 86400
MAX_LOSS_PER_TRADE_KES = 15
MIN_TRADE_USDT = 15
MAX_SPREAD = 0.002
MIN_PROFIT_KES = 40

TRIANGLES = [
    ["USDT", "BTC", "ETH"], ["USDT", "BNB", "BTC"], ["USDT", "SOL", "BNB"],
    ["USDT", "XRP", "SOL"], ["USDT", "DOGE", "XRP"], ["USDT", "TRX", "DOGE"],
    ["USDT", "ADA", "TRX"], ["USDT", "DOT", "ADA"], ["USDT", "MATIC", "DOT"],
    ["USDT", "LTC", "MATIC"], ["USDT", "AVAX", "LTC"], ["USDT", "ATOM", "AVAX"],
    ["USDT", "LINK", "ATOM"], ["USDT", "UNI", "LINK"], ["USDT", "BCH", "UNI"],
]

# STATE
daily_loss_kes = 0.0
consecutive_fails = 0
daily_reset_time = datetime.datetime.utcnow().date()
pause_until = 0
trades_today = 0
last_win_time = 0

# ---------- HEALTH + PING ----------
@app.route('/health')
def health():
    return {"status": "ok", "daily_loss": daily_loss_kes, "testnet": USE_TESTNET}, 200

def run_webserver():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

def keep_alive():
    while True:
        time.sleep(540)
        try:
            if RENDER_URL: requests.get(f"{RENDER_URL}/health", timeout=10)
        except: pass

# ---------- WEBSOCKET ----------
def handle_ws_message(msg):
    global ws_prices
    if msg.get('e') == 'bookTicker':
        ws_prices[msg['s']] = {
            'bid': float(msg['b']),
            'ask': float(msg['a'])
        }

def get_symbols_from_triangles():
    symbols = set()
    for a, b, c in TRIANGLES:
        symbols.add(f"{b}{a}")   # BTCUSDT
        symbols.add(f"{b}{c}")   # BTCETH
        symbols.add(f"{c}{a}")   # ETHUSDT
    return list(symbols)

def start_websocket():
    ws_client = SpotWebsocketClient()
    symbols = get_symbols_from_triangles()
    ws_client.book_ticker(symbol=symbols, callback=handle_ws_message)
    ws_client.start()

# ---------- UTILS ----------
def telegram(msg):
    if not TELEGRAM_TOKEN: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": ADMIN_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except: pass

def log(data):
    if not SUPABASE_URL: return
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/trades", json=data, headers=headers, timeout=5)
    except: pass

def load_filters():
    try:
        info = client.get_exchange_info()
        for s in info['symbols']:
            step, minN = 0.001, 10.0
            for f in s['filters']:
                if f['filterType'] == 'LOT_SIZE': step = float(f['stepSize'])
                if f['filterType'] == 'MIN_NOTIONAL': minN = float(f['minNotional'])
            symbol_info[s['symbol']] = {'step': step, 'minNotional': minN}
        print(f" Loaded {len(symbol_info)} symbol filters")
    except Exception as e:
        print(f"[FATAL] Could not load filters: {e}")

def round_qty(qty, symbol):
    step = symbol_info.get(symbol, {}).get('step', 0.001)
    return math.floor(qty / step) * step

def get_price(symbol, side='bid'):
    if symbol in ws_prices:
        return ws_prices[symbol].get(side, 0.0)
    # fallback to REST
    try:
        return float(client.get_symbol_ticker(symbol=symbol)['price'])
    except:
        return 0.0

def get_spread(symbol):
    try:
        ticker = client.get_order_book(symbol=symbol, limit=5)
        best_ask = float(ticker['asks'][0][0])
        best_bid = float(ticker['bids'][0][0])
        return (best_ask - best_bid) / best_bid if best_bid else 0.01
    except:
        return 0.01

def get_total_usdt_balance():
    try:
        account = client.get_account()
        total = 0.0
        for asset in account['balances']:
            free = float(asset['free'])
            if free <= 0: continue
            if asset['asset'] == 'USDT':
                total += free
            else:
                price = get_price(asset['asset'] + 'USDT', 'bid')
                if price > 0: total += free * price
        return max(total, 10.0)
    except:
        return 50.0

def reset_daily():
    global daily_loss_kes, consecutive_fails, daily_reset_time, trades_today
    if datetime.datetime.utcnow().date() != daily_reset_time:
        daily_loss_kes = 0.0
        consecutive_fails = 0
        trades_today = 0
        daily_reset_time = datetime.datetime.utcnow().date()

def is_paused(): return time.time() < pause_until

def set_pause(seconds, reason):
    global pause_until
    pause_until = time.time() + seconds
    msg = f"⛔ <b>BOT PAUSED</b> for {seconds/60:.0f}min\nReason: {reason}"
    print(msg); telegram(msg); log({"status": "PAUSE", "reason": reason})

def cancel_all():
    try:
        client.cancel_open_orders(symbol="")
    except BinanceAPIException:
        pass

# ---------- CORE LOGIC ----------
def calc_profit(a,b,c,amount):
    try:
        sym1 = f"{b}{a}"   # buy BTC with USDT
        sym2 = f"{b}{c}"   # sell BTC for ETH
        sym3 = f"{c}{a}"   # sell ETH for USDT

        p_ab = get_price(sym1, 'ask')   # use ask for buying
        p_bc = get_price(sym2, 'bid')   # use bid for selling
        p_ca = get_price(sym3, 'bid')   # use bid for selling

        if 0 in [p_ab, p_bc, p_ca]:
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

# ---------- ATOMIC EXECUTION WITH ROLLBACK ----------
def execute_trade(a, b, c, trade_amount_usd):
    global daily_loss_kes, consecutive_fails, trades_today, last_win_time
    executed = []
    start_balance = get_total_usdt_balance()
    pair = f"{a}{b}{c}"

    try:
        if start_balance < trade_amount_usd + 1:
            raise Exception("Low balance")

        cancel_all()

        # LEG 1: buy b with a (USDT)
        sym1 = f"{b}{a}"
        o1 = client.order_market_buy(symbol=sym1, quoteOrderQty=trade_amount_usd)
        qty_b = round_qty(float(o1['executedQty']), sym1)
        if qty_b * get_price(sym1, 'bid') < symbol_info[sym1]['minNotional']:
            raise Exception("Leg1 below minNotional")
        executed.append((sym1, qty_b, 'BUY'))
        time.sleep(0.2)

        # LEG 2: sell b for c
        sym2 = f"{b}{c}"
        qty_b = round_qty(qty_b, sym2)
        o2 = client.order_market_sell(symbol=sym2, quantity=qty_b)
        qty_c = round_qty(float(o2['executedQty']), sym2)
        if qty_c * get_price(sym2, 'bid') < symbol_info[sym2]['minNotional']:
            raise Exception("Leg2 below minNotional")
        executed.append((sym2, qty_c, 'SELL'))
        time.sleep(0.2)

        # LEG 3: sell c for a (USDT)
        sym3 = f"{c}{a}"
        qty_c = round_qty(qty_c, sym3)
        o3 = client.order_market_sell(symbol=sym3, quantity=qty_c)
        executed.append((sym3, qty_c, 'SELL'))

        # WIN
        consecutive_fails = 0
        trades_today += 1
        last_win_time = time.time()
        end_balance = get_total_usdt_balance()
        profit_usd = end_balance - start_balance
        profit_kes = profit_usd * KES_RATE
        msg = f"✅ <b>WIN</b> {pair}\n+{profit_kes:.0f} KES | New: {end_balance:.2f} USDT"
        print(msg); telegram(msg)
        log({"pair": pair, "profit_kes": profit_kes, "status": "WIN", "balance": end_balance})
        time.sleep(15)
        return True

    except Exception as e:
        consecutive_fails += 1
        loss_usd = trade_amount_usd * 0.003
        loss_kes = loss_usd * KES_RATE
        daily_loss_kes += loss_kes
        trades_today += 1
        msg = f"❌ <b>LOSS</b> {pair}\n-{loss_kes:.0f} KES | Daily: {daily_loss_kes:.0f} KES\nErr: {str(e)[:80]}"
        print(msg); telegram(msg)

        # ROLLBACK
        for symbol, qty, side in reversed(executed):
            try:
                if side == 'BUY':
                    qty = round_qty(qty, symbol)
                    client.order_market_sell(symbol=symbol, quantity=qty)
                    time.sleep(0.2)
                else:  # SELL
                    qty = round_qty(qty, symbol)
                    client.order_market_buy(symbol=symbol, quantity=qty)
                    time.sleep(0.2)
            except:
                print(f"Rollback failed {symbol}")

        log({"pair": pair, "loss_kes": loss_kes, "status": "LOSS", "error": str(e)})

        if loss_kes > MAX_LOSS_PER_TRADE_KES:
            set_pause(3600, f"Single trade loss > {MAX_LOSS_PER_TRADE_KES} KES")
        if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
            set_pause(PAUSE_AFTER_2_FAILS_SEC, "2 consecutive fails")
            consecutive_fails = 0
        if daily_loss_kes >= MAX_DAILY_LOSS_KES:
            set_pause(PAUSE_AFTER_300KES_LOSS_SEC, "Daily loss > 300 KES")
        return False

def scan():
    reset_daily()
    if is_paused():
        return
    if time.time() - last_win_time < 15:
        return

    balance = get_total_usdt_balance()
    trade_amount = max(balance * COMPOUND_RATE, MIN_TRADE_USDT)

    best_profit = 0
    best_tri = None
    best_threshold = 0
    best_spread = 0

    for a,b,c in TRIANGLES:
        profit_pct, threshold, spread = calc_profit(a,b,c,trade_amount)
        if spread > MAX_SPREAD:
            continue
        if profit_pct > best_profit:
            best_profit = profit_pct
            best_tri = [a,b,c]
            best_threshold = threshold
            best_spread = spread

    if best_tri and best_profit > best_threshold:
        profit_kes = (trade_amount * best_profit) * KES_RATE
        if profit_kes > MIN_PROFIT_KES:
            a,b,c = best_tri
            print(f"[BEST OPP] {a}{b}{c} {best_profit*100:.3f}% > {best_threshold*100:.3f}% Spread:{best_spread*100:.2f}% = {profit_kes:.0f} KES")
            execute_trade(a,b,c,trade_amount)

    time.sleep(3)

def main():
    while True:
        try:
            scan()
        except Exception as e:
            print(f"[FATAL] {e}")
            telegram(f"💀 BOT CRASH: {e}")
            time.sleep(60)

if __name__ == "__main__":
    cancel_all()
    load_filters()
    threading.Thread(target=run_webserver, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=start_websocket, daemon=True).start()
    time.sleep(5)
    mode = "TESTNET" if USE_TESTNET else "LIVE"
    telegram(f"🚀 <b>BOT V3.4 PARANOID</b>\n85% Compound | 0.30%+Spread+0.3% Buffer | 300KES Daily Stop")
    print(f"[BOT] V3.4 LIVE. Mode: {mode}. Max Profit / Min Loss Mode")
    main()
