import os
import time
import json
import logging
from datetime import datetime, timedelta
from threading import Thread
import telebot
import requests
from telebot import types
from flask import Flask, jsonify

# ============================================
# LOGGING SETUP
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION
# ============================================
TELEGRAM_BOT_TOKEN = os.environ.get('8446938916:AAGlQFTVFwcbsQe2__T5729imMb4-83G3T4')
PORT = int(os.environ.get('PORT', 10000))

# Data file paths
USERS_FILE = 'data/users.json'

# ============================================
# TOP 10 FOREX PAIRS
# ============================================
FOREX_PAIRS = {
    'EUR/USD': {'base': 'EUR', 'quote': 'USD', 'name': 'Euro / US Dollar'},
    'GBP/USD': {'base': 'GBP', 'quote': 'USD', 'name': 'British Pound / US Dollar'},
    'USD/JPY': {'base': 'USD', 'quote': 'JPY', 'name': 'US Dollar / Japanese Yen'},
    'USD/CHF': {'base': 'USD', 'quote': 'CHF', 'name': 'US Dollar / Swiss Franc'},
    'AUD/USD': {'base': 'AUD', 'quote': 'USD', 'name': 'Australian Dollar / US Dollar'},
    'USD/CAD': {'base': 'USD', 'quote': 'CAD', 'name': 'US Dollar / Canadian Dollar'},
    'NZD/USD': {'base': 'NZD', 'quote': 'USD', 'name': 'New Zealand Dollar / US Dollar'},
    'EUR/GBP': {'base': 'EUR', 'quote': 'GBP', 'name': 'Euro / British Pound'},
    'EUR/JPY': {'base': 'EUR', 'quote': 'JPY', 'name': 'Euro / Japanese Yen'},
    'GBP/JPY': {'base': 'GBP', 'quote': 'JPY', 'name': 'British Pound / Japanese Yen'}
}

# ============================================
# FLASK WEB SERVER (for Render health checks)
# ============================================
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        'status': 'running',
        'bot': 'Forex Trading Bot',
        'timestamp': datetime.now().isoformat(),
        'subscribers': len(subscribers)
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/stats')
def stats():
    return jsonify({
        'total_subscribers': len(subscribers),
        'active_pairs': len([s for s in subscribers.values() if s['pairs']]),
        'last_update': max([m.last_update.isoformat() if m.last_update else None 
                           for m in market_data.values()], default=None)
    })

# ============================================
# DATA PERSISTENCE
# ============================================
def load_subscribers():
    """Load subscribers from JSON file"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                data = json.load(f)
                logger.info(f"✅ Loaded {len(data)} subscribers from file")
                return data
        else:
            logger.info("📝 Creating new users file")
            return {}
    except Exception as e:
        logger.error(f"❌ Error loading subscribers: {e}")
        return {}

def save_subscribers():
    """Save subscribers to JSON file"""
    try:
        os.makedirs('data', exist_ok=True)
        with open(USERS_FILE, 'w') as f:
            json.dump(subscribers, f, indent=2)
        logger.info(f"💾 Saved {len(subscribers)} subscribers")
    except Exception as e:
        logger.error(f"❌ Error saving subscribers: {e}")

# ============================================
# Initialize Bot
# ============================================
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
subscribers = load_subscribers()

# Store price history for each pair
price_history = {pair: [] for pair in FOREX_PAIRS.keys()}

# Store market data for each pair
class MarketData:
    def __init__(self):
        self.current_price = 0
        self.pivot = 0
        self.tc = 0
        self.bc = 0
        self.r1 = 0
        self.r2 = 0
        self.r3 = 0
        self.s1 = 0
        self.s2 = 0
        self.s3 = 0
        self.prev_high = 0
        self.prev_low = 0
        self.prev_close = 0
        self.ema_8 = 0
        self.ema_20 = 0
        self.last_update = None
        self.last_alert_time = {}

# Market data for each pair
market_data = {pair: MarketData() for pair in FOREX_PAIRS.keys()}

# ============================================
# DATA FETCHING
# ============================================
def get_forex_price(base, quote):
    """Get current forex price"""
    try:
        if base == 'USD':
            url = f"https://api.exchangerate-api.com/v4/latest/{base}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return float(data['rates'][quote])
        else:
            url = f"https://api.exchangerate-api.com/v4/latest/{base}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return float(data['rates'][quote])
        return None
    except Exception as e:
        logger.error(f"❌ Error fetching {base}/{quote}: {e}")
        return None

def get_historical_data(pair):
    """Get historical data for a pair"""
    try:
        pair_info = FOREX_PAIRS[pair]
        base = pair_info['base']
        quote = pair_info['quote']
        
        current = get_forex_price(base, quote)
        if not current:
            return None
        
        yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        if base == 'USD':
            url_hist = f"https://api.frankfurter.app/{yesterday}?from={base}&to={quote}"
        else:
            url_hist = f"https://api.frankfurter.app/{yesterday}?from={base}&to={quote}"
        
        response = requests.get(url_hist, timeout=10)
        
        if response.status_code == 200:
            hist_data = response.json()
            if 'rates' in hist_data and quote in hist_data['rates']:
                prev_close = float(hist_data['rates'][quote])
            else:
                prev_close = current * 0.999
        else:
            prev_close = current * 0.999
        
        if 'JPY' in pair:
            prev_high = prev_close * 1.005
            prev_low = prev_close * 0.995
        else:
            prev_high = prev_close * 1.002
            prev_low = prev_close * 0.998
        
        return {
            'current': current,
            'prev_high': prev_high,
            'prev_low': prev_low,
            'prev_close': prev_close
        }
    except Exception as e:
        logger.error(f"❌ Error getting historical data for {pair}: {e}")
        return None

# ============================================
# EMA CALCULATIONS
# ============================================
def calculate_ema(prices, period):
    """Calculate EMA"""
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price * k) + (ema * (1 - k))
    return ema

def update_ema_values(pair):
    """Update EMAs for a pair"""
    global price_history
    
    if len(price_history[pair]) > 30:
        price_history[pair] = price_history[pair][-30:]
    
    market = market_data[pair]
    
    if len(price_history[pair]) >= 8:
        market.ema_8 = calculate_ema(price_history[pair], 8)
    
    if len(price_history[pair]) >= 20:
        market.ema_20 = calculate_ema(price_history[pair], 20)

# ============================================
# CPR CALCULATIONS
# ============================================
def calculate_cpr(high, low, close):
    """Calculate CPR levels"""
    pivot = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = pivot - bc + pivot
    
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)
    
    return {
        'pivot': pivot, 'tc': tc, 'bc': bc,
        'r1': r1, 'r2': r2, 'r3': r3,
        's1': s1, 's2': s2, 's3': s3
    }

def get_trading_signal(pair):
    """Generate trading signal for a pair"""
    market = market_data[pair]
    price = market.current_price
    
    if price == 0 or market.pivot == 0:
        return "WAIT", "⏳ Calculating levels..."
    
    if 'JPY' in pair:
        distance = (price - market.pivot) * 100
        unit = "pips"
    else:
        distance = (price - market.pivot) * 10000
        unit = "pips"
    
    ema_signal = ""
    if market.ema_8 > 0 and market.ema_20 > 0:
        if price > market.ema_8:
            ema_signal = "📈 Breakout: Above 8 EMA"
        else:
            ema_signal = "📉 Breakout: Below 8 EMA"
        
        if price > market.ema_20:
            ema_signal += "\n📊 Trend: Bullish (Above 20 EMA)"
        else:
            ema_signal += "\n📊 Trend: Bearish (Below 20 EMA)"
    
    if price > market.tc:
        if price > market.r1 and price > market.ema_8 and price > market.ema_20:
            return "STRONG BUY", f"🟢 Price above TC, R1 and both EMAs\n{ema_signal}\n+{distance:.1f} {unit} from pivot"
        elif price > market.ema_8:
            return "BUY", f"🟢 Price above TC and 8 EMA\n{ema_signal}\n+{distance:.1f} {unit} from pivot"
        else:
            return "BUY (Weak)", f"🟡 Price above TC but below 8 EMA\n{ema_signal}\n+{distance:.1f} {unit} from pivot"
    
    elif price < market.bc:
        if price < market.s1 and price < market.ema_8 and price < market.ema_20:
            return "STRONG SELL", f"🔴 Price below BC, S1 and both EMAs\n{ema_signal}\n{distance:.1f} {unit} from pivot"
        elif price < market.ema_8:
            return "SELL", f"🔴 Price below BC and 8 EMA\n{ema_signal}\n{distance:.1f} {unit} from pivot"
        else:
            return "SELL (Weak)", f"🟡 Price below BC but above 8 EMA\n{ema_signal}\n{distance:.1f} {unit} from pivot"
    
    else:
        if price > market.pivot and price > market.ema_8:
            return "NEUTRAL (Bullish)", f"⚪ In CPR, above pivot & 8 EMA\n{ema_signal}\n+{distance:.1f} {unit}"
        elif price < market.pivot and price < market.ema_8:
            return "NEUTRAL (Bearish)", f"⚪ In CPR, below pivot & 8 EMA\n{ema_signal}\n{distance:.1f} {unit}"
        else:
            return "NEUTRAL", f"⚪ In CPR zone\n{ema_signal}\n{distance:+.1f} {unit}"

# ============================================
# UPDATE MARKET DATA
# ============================================
def update_market_data(pair):
    """Update data for a specific pair"""
    try:
        data = get_historical_data(pair)
        if not data:
            return False
        
        market = market_data[pair]
        market.current_price = data['current']
        market.prev_high = data['prev_high']
        market.prev_low = data['prev_low']
        market.prev_close = data['prev_close']
        
        price_history[pair].append(market.current_price)
        
        levels = calculate_cpr(market.prev_high, market.prev_low, market.prev_close)
        market.pivot = levels['pivot']
        market.tc = levels['tc']
        market.bc = levels['bc']
        market.r1 = levels['r1']
        market.r2 = levels['r2']
        market.r3 = levels['r3']
        market.s1 = levels['s1']
        market.s2 = levels['s2']
        market.s3 = levels['s3']
        
        update_ema_values(pair)
        market.last_update = datetime.now()
        
        return True
    except Exception as e:
        logger.error(f"❌ Error updating {pair}: {e}")
        return False

# ============================================
# TELEGRAM BOT COMMANDS
# ============================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if chat_id not in subscribers:
        subscribers[chat_id] = {'pairs': [], 'alerts': False}
        save_subscribers()
    
    welcome_text = """
🎯 *Multi-Currency Forex Trading Bot*

*Top 10 Forex Pairs Available:*
EUR/USD, GBP/USD, USD/JPY, USD/CHF
AUD/USD, USD/CAD, NZD/USD, EUR/GBP
EUR/JPY, GBP/JPY

*Commands:*
/select - Choose currency pairs to track
/levels - Get levels for selected pairs
/subscribe - Enable alerts
/unsubscribe - Disable alerts
/mypairs - Show your selected pairs
/help - Show this help

*Quick Access:*
Just type pair name (e.g., EUR/USD) to get instant levels!

Ready to trade! 🚀
    """
    bot.send_message(chat_id, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['select'])
def select_pairs(message):
    chat_id = message.chat.id
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    
    for pair in FOREX_PAIRS.keys():
        callback_data = f"pair_{pair.replace('/', '_')}"
        buttons.append(types.InlineKeyboardButton(pair, callback_data=callback_data))
    
    markup.add(*buttons)
    markup.add(types.InlineKeyboardButton("✅ Done", callback_data="pair_done"))
    
    bot.send_message(
        chat_id,
        "🔍 *Select Currency Pairs to Track:*\n\nClick on pairs you want to follow:",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('pair_'))
def handle_pair_selection(call):
    chat_id = call.message.chat.id
    
    if chat_id not in subscribers:
        subscribers[chat_id] = {'pairs': [], 'alerts': False}
    
    if call.data == 'pair_done':
        bot.answer_callback_query(call.id, "Selection saved!")
        save_subscribers()
        pairs_list = "\n".join([f"• {p}" for p in subscribers[chat_id]['pairs']])
        if pairs_list:
            bot.send_message(chat_id, f"✅ *Your Selected Pairs:*\n{pairs_list}\n\nUse /levels to see analysis!", parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "⚠️ No pairs selected. Use /select to choose pairs.")
        return
    
    pair = call.data.replace('pair_', '').replace('_', '/')
    
    if pair in subscribers[chat_id]['pairs']:
        subscribers[chat_id]['pairs'].remove(pair)
        bot.answer_callback_query(call.id, f"❌ Removed {pair}")
    else:
        subscribers[chat_id]['pairs'].append(pair)
        bot.answer_callback_query(call.id, f"✅ Added {pair}")

@bot.message_handler(commands=['levels'])
def show_all_levels(message):
    chat_id = message.chat.id
    
    if chat_id not in subscribers or not subscribers[chat_id]['pairs']:
        bot.send_message(chat_id, "⚠️ No pairs selected! Use /select to choose pairs first.")
        return
    
    for pair in subscribers[chat_id]['pairs']:
        show_pair_levels(chat_id, pair)
        time.sleep(1)

def show_pair_levels(chat_id, pair):
    """Show levels for a specific pair"""
    market = market_data[pair]
    
    if market.pivot == 0:
        bot.send_message(chat_id, f"⏳ Calculating levels for {pair}... Try again in 10 seconds.")
        return
    
    def distance_format(level):
        if 'JPY' in pair:
            return (level - market.current_price) * 100
        else:
            return (level - market.current_price) * 10000
    
    signal, reason = get_trading_signal(pair)
    
    if "BUY" in signal:
        signal_emoji = "🟢"
    elif "SELL" in signal:
        signal_emoji = "🔴"
    else:
        signal_emoji = "⚪"
    
    if 'JPY' in pair:
        price_fmt = ".2f"
        pip_unit = "pips"
    else:
        price_fmt = ".5f"
        pip_unit = "pips"
    
    levels_text = f"""
{signal_emoji} *{pair} ANALYSIS* {signal_emoji}
⏰ {datetime.now().strftime('%H:%M:%S')} UTC

💱 *Current: {market.current_price:{price_fmt}}*

*{signal_emoji} SIGNAL: {signal}*
{reason}

━━━━━━━━━━━━━━━━━━━━
📊 *EMA INDICATORS*
━━━━━━━━━━━━━━━━━━━━
📈 8 EMA: {market.ema_8:{price_fmt}} ({distance_format(market.ema_8):+.1f} {pip_unit})
📊 20 EMA: {market.ema_20:{price_fmt}} ({distance_format(market.ema_20):+.1f} {pip_unit})

━━━━━━━━━━━━━━━━━━━━
📍 *CPR LEVELS*
━━━━━━━━━━━━━━━━━━━━
🔴 TC: {market.tc:{price_fmt}} ({distance_format(market.tc):+.1f} {pip_unit})
🟢 PP: {market.pivot:{price_fmt}} ({distance_format(market.pivot):+.1f} {pip_unit})
🔵 BC: {market.bc:{price_fmt}} ({distance_format(market.bc):+.1f} {pip_unit})

━━━━━━━━━━━━━━━━━━━━
🔺 *RESISTANCE*
━━━━━━━━━━━━━━━━━━━━
R3: {market.r3:{price_fmt}} ({distance_format(market.r3):+.1f})
R2: {market.r2:{price_fmt}} ({distance_format(market.r2):+.1f})
R1: {market.r1:{price_fmt}} ({distance_format(market.r1):+.1f})

━━━━━━━━━━━━━━━━━━━━
🔻 *SUPPORT*
━━━━━━━━━━━━━━━━━━━━
S1: {market.s1:{price_fmt}} ({distance_format(market.s1):+.1f})
S2: {market.s2:{price_fmt}} ({distance_format(market.s2):+.1f})
S3: {market.s3:{price_fmt}} ({distance_format(market.s3):+.1f})
    """
    bot.send_message(chat_id, levels_text, parse_mode='Markdown')

@bot.message_handler(commands=['mypairs'])
def show_my_pairs(message):
    chat_id = message.chat.id
    
    if chat_id not in subscribers or not subscribers[chat_id]['pairs']:
        bot.send_message(chat_id, "⚠️ No pairs selected. Use /select to choose pairs.")
        return
    
    pairs_list = "\n".join([f"• {p}" for p in subscribers[chat_id]['pairs']])
    alerts_status = "✅ Enabled" if subscribers[chat_id]['alerts'] else "❌ Disabled"
    
    text = f"""
📊 *Your Selected Pairs:*
{pairs_list}

🔔 Alerts: {alerts_status}

Use /levels to see analysis for all pairs!
    """
    bot.send_message(chat_id, text, parse_mode='Markdown')

@bot.message_handler(commands=['subscribe'])
def subscribe_alerts(message):
    chat_id = message.chat.id
    if chat_id not in subscribers:
        subscribers[chat_id] = {'pairs': [], 'alerts': True}
    else:
        subscribers[chat_id]['alerts'] = True
    save_subscribers()
    bot.send_message(chat_id, "✅ Alerts enabled! You'll get notifications when price touches key levels.")

@bot.message_handler(commands=['unsubscribe'])
def unsubscribe_alerts(message):
    chat_id = message.chat.id
    if chat_id in subscribers:
        subscribers[chat_id]['alerts'] = False
    save_subscribers()
    bot.send_message(chat_id, "❌ Alerts disabled.")

@bot.message_handler(commands=['help'])
def help_command(message):
    send_welcome(message)

@bot.message_handler(func=lambda message: message.text.upper() in FOREX_PAIRS.keys())
def handle_pair_request(message):
    pair = message.text.upper()
    chat_id = message.chat.id
    show_pair_levels(chat_id, pair)

# ============================================
# MONITORING LOOP
# ============================================
def monitoring_loop():
    """Update all pairs data"""
    logger.info("🔄 Starting multi-currency monitoring...")
    
    while True:
        try:
            for pair in FOREX_PAIRS.keys():
                update_market_data(pair)
                time.sleep(2)
            
            logger.info(f"✅ All pairs updated at {datetime.now().strftime('%H:%M:%S')}")
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"❌ Monitoring error: {e}")
            time.sleep(60)

def bot_polling():
    """Run bot polling in a thread"""
    logger.info("🤖 Starting bot polling...")
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            logger.error(f"❌ Bot polling error: {e}")
            time.sleep(15)

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🤖 Multi-Currency Forex Bot Starting...")
    logger.info("=" * 50)
    logger.info("💱 Tracking 10 Major Forex Pairs")
    logger.info("📊 Strategy: CPR + 8/20 EMA")
    logger.info(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)
    
    # Create necessary directories
    os.makedirs('data', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Initialize users.json if it doesn't exist
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w') as f:
            json.dump({}, f)
    
    # Start monitoring thread
    monitor_thread = Thread(target=monitoring_loop, daemon=True)
    monitor_thread.start()
    
    # Start bot polling thread
    bot_thread = Thread(target=bot_polling, daemon=True)
    bot_thread.start()
    
    logger.info("✅ Bot running! Starting web server...")
    logger.info("=" * 50)
    
    # Run Flask web server (required for Render)

    app.run(host='0.0.0.0', port=PORT, debug=False)
