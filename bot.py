import os
import json
import re
import time
import threading
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
API_PASSPHRASE = os.getenv("API_PASSPHRASE")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_HOST = "https://clob.polymarket.com"

MAX_TRADES_PER_SCAN = 20
MAX_RETRIES = 3
REQUEST_TIMEOUT = 15
STUCK_THRESHOLD = 600

CATEGORIES = {
    "All": None,
    "Weather": "84",
    "Sports": "1",
    "Politics": "2",
    "Crypto": "21",
    "Finance": "120",
    "Tech": "1401",
    "AI": "439",
    "Elections": "144",
    "Geopolitics": "100265",
    "Business": "107",
    "Culture": "596",
    "Entertainment": "286",
}

WEATHER_SUBCATEGORIES = {
    "All Weather": None,
    "Daily Temperature": "Daily Temperature",
    "Precipitation": "Precipitation",
    "Earthquakes": "Earthquakes",
    "Hurricanes": "Hurricanes",
    "Tornadoes": "Tornadoes",
    "Volcanoes": "Volcanoes",
    "Pandemics": "Pandemics",
    "Global": "Global",
}


class TradingBot:
    def __init__(self):
        self.running = False
        self.thread = None
        self.logs = []
        self.max_logs = 300
        self.scanning = False
        self.last_scan_time = None
        self.last_scan_count = 0
        self.last_trade_count = 0
        self._clob_client = None
        self.last_activity = time.time()
        self._lock = threading.Lock()

    def log(self, msg, level="INFO"):
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": msg,
        }
        with self._lock:
            self.logs.insert(0, entry)
            if len(self.logs) > self.max_logs:
                self.logs = self.logs[: self.max_logs]
        print(f"[{entry['time']}] [{level}] {msg}")

    def _get_clob_client(self):
        if self._clob_client:
            return self._clob_client
        try:
            from py_clob_client_v2 import ClobClient
            from py_clob_client_v2.clob_types import ApiCreds

            self._clob_client = ClobClient(
                CLOB_HOST,
                key=PRIVATE_KEY,
                chain_id=CHAIN_ID,
                creds=ApiCreds(
                    api_key=API_KEY,
                    api_secret=API_SECRET,
                    api_passphrase=API_PASSPHRASE,
                ),
                signature_type=3,
            )
            return self._clob_client
        except Exception as e:
            self.log(f"Failed to init CLOB client: {e}", "ERROR")
            return None

    def _get_token_prices(self, market):
        try:
            outcome_prices = market.get("outcomePrices")
            if outcome_prices:
                if isinstance(outcome_prices, str):
                    prices = json.loads(outcome_prices)
                else:
                    prices = outcome_prices
                if len(prices) >= 2:
                    return float(prices[0]), float(prices[1])
        except (ValueError, TypeError, IndexError):
            pass
        return None, None

    def _get_token_id(self, market, side):
        clob_token_ids = market.get("clobTokenIds")
        if not clob_token_ids:
            return None
        if isinstance(clob_token_ids, str):
            clob_token_ids = json.loads(clob_token_ids)
        if len(clob_token_ids) < 2:
            return None
        if side == "YES":
            return clob_token_ids[0]
        return clob_token_ids[1]

    def _fetch_markets(self, tag_id=None, limit=100, offset=0):
        for attempt in range(MAX_RETRIES):
            try:
                params = {
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                    "offset": offset,
                }
                if tag_id:
                    params["tag_id"] = tag_id
                resp = requests.get(f"{GAMMA_API}/markets", params=params, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.Timeout:
                self.log(f"API timeout (attempt {attempt+1}/{MAX_RETRIES})", "WARN")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 * (attempt + 1))
            except Exception as e:
                self.log(f"API error: {e}", "ERROR")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 * (attempt + 1))
        return []

    def _filter_markets(self, markets, weather_sub=None, target_date=None):
        filtered = []
        for market in markets:
            if weather_sub and weather_sub != "All Weather":
                q = market.get("question", "").lower()

                if weather_sub == "Daily Temperature":
                    if "highest temperature" not in q and "lowest temperature" not in q:
                        continue
                elif weather_sub == "Precipitation":
                    if "precipitation" not in q:
                        continue
                elif weather_sub == "Earthquakes":
                    if "earthquake" not in q:
                        continue
                elif weather_sub == "Hurricanes":
                    if "hurricane" not in q:
                        continue
                elif weather_sub == "Tornadoes":
                    if "tornado" not in q:
                        continue
                elif weather_sub == "Volcanoes":
                    if "volcano" not in q and "eruption" not in q:
                        continue
                elif weather_sub == "Pandemics":
                    if "pandemic" not in q and "measles" not in q and "ebola" not in q and "hantavirus" not in q:
                        continue
                elif weather_sub == "Global":
                    if "hottest" not in q and "arctic" not in q and "temperature increase" not in q:
                        continue

            if target_date and target_date != "all":
                q_full = market.get("question", "")
                date_str = self._format_date_for_match(target_date)
                if date_str and date_str.lower() not in q_full.lower():
                    continue

            filtered.append(market)
        return filtered

    def _format_date_for_match(self, date_str):
        try:
            from datetime import datetime as dt
            if date_str == "all":
                return None
            d = dt.strptime(date_str, "%Y-%m-%d")
            return f"{d.strftime('%B')} {d.day}"
        except Exception:
            return date_str

    def _extract_event_date(self, question):
        m = re.search(r'on\s+(\w+\s+\d+)', question)
        if m:
            return m.group(1)
        return None

    def _place_trade(self, client, market, token_id, trade_price, side, amount_usdt, dry_run=True):
        try:
            question = market.get("question", "Unknown")
            condition_id = market.get("conditionId", "")

            if trade_price <= 0:
                self.log(f"Price is 0, skip: {question}", "WARN")
                return False

            if trade_price > 0.99:
                self.log(f"Price too high ({trade_price}), skip: {question[:50]}", "WARN")
                return False

            if amount_usdt <= 0:
                self.log(f"Invalid amount ({amount_usdt}), skip: {question[:50]}", "WARN")
                return False

            size = amount_usdt / trade_price
            event_date = self._extract_event_date(question)

            if dry_run:
                self.log(
                    f"[DRY RUN] Would place {side} order: {question[:60]}... | "
                    f"Price: ${trade_price:.2f} | Size: {size:.2f} | Cost: ~${amount_usdt:.2f}",
                    "DRYRUN"
                )
                from config import save_trade
                save_trade(
                    {
                        "question": question,
                        "condition_id": condition_id,
                        "side": side,
                        "token_id": token_id,
                        "price": trade_price,
                        "size": round(size, 2),
                        "cost_usdt": amount_usdt,
                        "order_id": "DRY_RUN",
                        "status": "SIMULATED",
                        "resolves_at": event_date,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                return True

            tick_size = str(market.get("minimum_tick_size", "0.01"))
            neg_risk = market.get("neg_risk", False)

            self.log(
                f"LIVE TRADE: Placing {side} order: {question[:60]}... | "
                f"Price: ${trade_price:.2f} | Size: {size:.2f} | Cost: ~${amount_usdt:.2f}",
                "TRADE"
            )

            from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
            from py_clob_client_v2.order_builder.constants import BUY

            response = client.create_and_post_order(
                OrderArgs(
                    token_id=token_id,
                    price=trade_price,
                    size=size,
                    side=BUY,
                ),
                options=PartialCreateOrderOptions(
                    tick_size=tick_size,
                    neg_risk=neg_risk,
                ),
                order_type=OrderType.GTC,
            )

            order_id = response.get("orderID", "N/A")
            status = response.get("status", "N/A")
            self.log(f"Order CONFIRMED! ID: {order_id} | Status: {status}", "TRADE")

            from config import save_trade

            save_trade(
                {
                    "question": question,
                    "condition_id": condition_id,
                    "side": side,
                    "token_id": token_id,
                    "price": trade_price,
                    "size": round(size, 2),
                    "cost_usdt": amount_usdt,
                    "order_id": order_id,
                    "status": status,
                    "resolves_at": event_date,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            return True

        except Exception as e:
            self.log(f"Trade FAILED: {e}", "ERROR")
            return False

    def _scan_once(self, target_cents, trade_side, amount_usdt, category="All", weather_sub="All Weather", dry_run=True, target_date="all", max_cents=98):
        from config import load_trades

        self.scanning = True
        self.last_activity = time.time()
        target_price = target_cents / 100.0
        max_price = max_cents / 100.0
        cat_info = f" | Category: {category}"
        mode_info = " | MODE: DRY RUN" if dry_run else " | MODE: LIVE"
        date_info = f" | Date: {target_date}" if target_date != "all" else ""
        if category == "Weather" and weather_sub != "All Weather":
            cat_info += f" > {weather_sub}"
        self.log(f"Scan started | Side: {trade_side} | Price: {target_cents}-{max_cents} cents (${target_price:.2f}-${max_price:.2f}){cat_info}{date_info}{mode_info}")

        try:
            traded = load_trades()
            traded_ids = {t.get("condition_id") for t in traded}

            if not dry_run:
                client = self._get_clob_client()
                if not client:
                    self.log("No CLOB client, aborting scan", "ERROR")
                    self.scanning = False
                    return 0, 0
            else:
                client = None

            tag_id = CATEGORIES.get(category)
            page_offset = 0
            total = 0
            trades = 0
            base_traded = set()

            while self.running:
                markets = self._fetch_markets(tag_id=tag_id, limit=100, offset=page_offset)
                self.last_activity = time.time()
                if not markets:
                    break
                self.log(f"Fetched {len(markets)} markets (page {page_offset // 100 + 1})", "SCAN")

                if len(markets) < 100:
                    pass

                sub = weather_sub if category == "Weather" else None
                filtered = self._filter_markets(markets, weather_sub=sub, target_date=target_date)
                self.log(f"After filter: {len(filtered)} / {len(markets)} markets", "SCAN")

                for market in filtered:
                    if not self.running:
                        break

                    if trades >= MAX_TRADES_PER_SCAN:
                        self.log(f"Max trades per scan reached ({MAX_TRADES_PER_SCAN}), stopping", "WARN")
                        break

                    total += 1
                    self.last_activity = time.time()
                    condition_id = market.get("conditionId", "")
                    question = market.get("question", "?")
                    question_short = question[:50]

                    if condition_id in traded_ids:
                        continue

                    if not market.get("enableOrderBook", False):
                        continue

                    yes_price, no_price = self._get_token_prices(market)
                    if yes_price is None:
                        continue

                    check_price = no_price if trade_side == "NO" else yes_price

                    if check_price >= max_price:
                        continue

                    if not check_price >= target_price:
                        continue

                    try:
                        from city_timezones import extract_city_from_question, get_city_utc_offset, is_after_3pm_local
                        city = extract_city_from_question(question)
                        if city:
                            city_offset = get_city_utc_offset(city)
                            if city_offset is not None and not is_after_3pm_local(city_offset):
                                self.log(f"Skipping (before 3PM local): {city} | {question_short}", "SCAN")
                                continue
                    except Exception as e:
                        self.log(f"Timezone check failed: {e}", "WARN")

                    base_key = re.sub(r'\s+between\s+\d+[-–]?\d*°[CF]', '', question)
                    base_key = re.sub(r'\s+\d+[-–]?\d*°[CF]', '', base_key)
                    base_key = re.sub(r'\s+', ' ', base_key).strip()

                    if base_key in base_traded:
                        continue

                    token_id = self._get_token_id(market, trade_side)
                    if not token_id:
                        continue

                    base_traded.add(base_key)
                    self.log(
                        f"MATCH: {question[:80]}... | YES: ${yes_price:.2f} | NO: ${no_price:.2f} | {trade_side}: ${check_price:.2f}",
                        "MATCH",
                    )

                    ok = self._place_trade(
                        client, market, token_id, check_price, trade_side, amount_usdt, dry_run
                    )
                    if ok:
                        traded_ids.add(condition_id)
                        trades += 1

                if trades >= MAX_TRADES_PER_SCAN:
                    break

                if len(markets) < 100:
                    break

                page_offset += 100

            self.log(f"Scan done | Markets: {total} | Trades: {trades}")
            return total, trades

        except Exception as e:
            self.log(f"Scan CRASHED: {e}", "ERROR")
            return total if 'total' in dir() else 0, trades if 'trades' in dir() else 0
        finally:
            self.scanning = False

    def _bot_loop(self):
        from config import load_config

        self.log("Bot thread started")

        if not all([PRIVATE_KEY, API_KEY, API_SECRET, API_PASSPHRASE, WALLET_ADDRESS]):
            self.log("Missing credentials in .env! Stop the bot and configure .env first.", "ERROR")
            self.running = False
            return

        while self.running:
            try:
                cfg = load_config()
                target_cents = cfg.get("target_price_cents", 97)
                max_cents = cfg.get("max_price_cents", 98)
                trade_side = cfg.get("trade_side", "NO")
                amount_usdt = cfg.get("trade_amount_usdt", 5.0)
                interval = cfg.get("scan_interval_seconds", 60)
                category = cfg.get("selected_category", "All")
                weather_sub = cfg.get("weather_subcategory", "All Weather")
                dry_run = cfg.get("dry_run", True)
                target_date = cfg.get("target_date", "all")

                total, trades = self._scan_once(target_cents, trade_side, amount_usdt, category, weather_sub, dry_run, target_date, max_cents)
                self.last_scan_time = datetime.now().strftime("%H:%M:%S")
                self.last_scan_count = total
                self.last_trade_count = trades
                self.last_activity = time.time()

                for _ in range(interval):
                    if not self.running:
                        break
                    time.sleep(1)

            except Exception as e:
                self.log(f"Bot loop error (auto-restarting): {e}", "ERROR")
                self.scanning = False
                time.sleep(10)

        self.log("Bot thread stopped")

    def _watchdog(self):
        while True:
            time.sleep(120)
            if self.running and self.last_activity:
                elapsed = time.time() - self.last_activity
                if elapsed > STUCK_THRESHOLD:
                    self.log(f"WATCHDOG: Bot stuck for {int(elapsed)}s, forcing restart", "ERROR")
                    self.running = False
                    self.scanning = False
                    time.sleep(3)
                    self.running = True
                    self._clob_client = None
                    self.thread = threading.Thread(target=self._bot_loop, daemon=True)
                    self.thread.start()
                    self.log("WATCHDOG: Bot restarted", "INFO")

    def start(self):
        if self.running:
            return False
        self.running = True
        self._clob_client = None
        self.last_activity = time.time()
        self.thread = threading.Thread(target=self._bot_loop, daemon=True)
        self.thread.start()
        if not hasattr(self, '_watchdog_thread') or self._watchdog_thread is None or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(target=self._watchdog, daemon=True)
            self._watchdog_thread.start()
        return True

    def stop(self):
        if not self.running:
            return False
        self.running = False
        self.scanning = False
        if self.thread:
            self.thread.join(timeout=10)
            self.thread = None
        return True

    def status(self):
        return {
            "running": self.running,
            "scanning": self.scanning,
            "last_scan_time": self.last_scan_time,
            "last_scan_count": self.last_scan_count,
            "last_trade_count": self.last_trade_count,
        }

    def get_logs(self, count=50):
        with self._lock:
            return self.logs[:count]

    @staticmethod
    def setup_api_keys():
        if not PRIVATE_KEY:
            return None, "PRIVATE_KEY not set in .env"
        try:
            from py_clob_client_v2 import ClobClient

            client = ClobClient(CLOB_HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID)
            creds = client.create_or_derive_api_key()
            return creds, None
        except Exception as e:
            return None, str(e)


bot = TradingBot()
