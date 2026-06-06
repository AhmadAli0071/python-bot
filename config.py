import json
import os

CONFIG_FILE = "config.json"
TRADES_FILE = "traded_markets.json"

DEFAULT_CONFIG = {
    "target_price_cents": 97,
    "max_price_cents": 98,
    "trade_side": "NO",
    "trade_amount_usdt": 5.0,
    "scan_interval_seconds": 60,
    "bot_running": False,
    "selected_categories": [],
    "selected_category": "Weather",
    "weather_subcategory": "Daily Temperature",
    "dry_run": True,
    "target_date": "all",
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        for key, val in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = val
        return config
    return DEFAULT_CONFIG.copy()


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, "r") as f:
            return json.load(f)
    return []


def save_trade(trade):
    trades = load_trades()
    trades.insert(0, trade)
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)
