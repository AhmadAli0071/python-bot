import requests
from flask import Flask, render_template, request, jsonify
from config import load_config, save_config, load_trades
from bot import bot, CATEGORIES, WEATHER_SUBCATEGORIES

CLOB_API = "https://clob.polymarket.com"


def check_trade_resolution(trades):
    if not trades:
        return trades

    condition_ids = list({t.get("condition_id", "") for t in trades if t.get("condition_id")})
    if not condition_ids:
        return trades

    resolved_map = {}
    for cid in condition_ids:
        try:
            resp = requests.get(f"{CLOB_API}/markets?condition_ids={cid}", timeout=10)
            data = resp.json()
            markets = data.get("data", [])
            for m in markets:
                if m.get("condition_id") != cid:
                    continue
                tokens = m.get("tokens", [])
                winner_token = None
                for tok in tokens:
                    if tok.get("winner"):
                        winner_token = tok.get("token_id")
                        break
                if winner_token:
                    resolved_map[cid] = winner_token
        except Exception:
            pass

    for t in trades:
        cid = t.get("condition_id", "")
        t["resolution"] = "PENDING"
        if cid in resolved_map:
            if t.get("token_id") == resolved_map[cid]:
                t["resolution"] = "WIN"
            else:
                t["resolution"] = "LOSS"

    return trades

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def get_config():
    cfg = load_config()
    return jsonify(cfg)


@app.route("/api/config", methods=["POST"])
def update_config():
    data = request.json
    cfg = load_config()
    if "target_price_cents" in data:
        val = int(data["target_price_cents"])
        if 1 <= val <= 99:
            cfg["target_price_cents"] = val
    if "max_price_cents" in data:
        val = int(data["max_price_cents"])
        if 1 <= val <= 100:
            cfg["max_price_cents"] = val
    if "trade_side" in data:
        side = data["trade_side"].upper()
        if side in ("YES", "NO"):
            cfg["trade_side"] = side
    if "trade_amount_usdt" in data:
        val = float(data["trade_amount_usdt"])
        if val > 0:
            cfg["trade_amount_usdt"] = val
    if "scan_interval_seconds" in data:
        val = int(data["scan_interval_seconds"])
        if val >= 10:
            cfg["scan_interval_seconds"] = val
    if "selected_category" in data:
        cat = data["selected_category"]
        if cat in CATEGORIES:
            cfg["selected_category"] = cat
    if "weather_subcategory" in data:
        sub = data["weather_subcategory"]
        if sub in WEATHER_SUBCATEGORIES:
            cfg["weather_subcategory"] = sub
    if "dry_run" in data:
        cfg["dry_run"] = bool(data["dry_run"])
    if "target_date" in data:
        cfg["target_date"] = data["target_date"]
    save_config(cfg)
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/start", methods=["POST"])
def start_bot():
    ok = bot.start()
    return jsonify({"ok": ok, "running": bot.running})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    ok = bot.stop()
    return jsonify({"ok": ok, "running": bot.running})


@app.route("/api/status", methods=["GET"])
def get_status():
    cfg = load_config()
    status = bot.status()
    return jsonify({**status, "config": cfg})


@app.route("/api/logs", methods=["GET"])
def get_logs():
    count = request.args.get("count", 50, type=int)
    return jsonify(bot.get_logs(count))


@app.route("/api/trades", methods=["GET"])
def get_trades():
    trades = load_trades()
    count = request.args.get("count", 50, type=int)
    return jsonify(trades[:count])


@app.route("/api/trades/resolve", methods=["POST"])
def resolve_trades():
    trades = load_trades()
    trades = check_trade_resolution(trades)
    count = request.json.get("count", 50) if request.is_json else 50
    return jsonify(trades[:count])


@app.route("/api/categories", methods=["GET"])
def get_categories():
    return jsonify({
        "categories": list(CATEGORIES.keys()),
        "weather_subcategories": list(WEATHER_SUBCATEGORIES.keys()),
    })


@app.route("/api/setup", methods=["POST"])
def setup_keys():
    creds, err = bot.setup_api_keys()
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "creds": creds})


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5000))
    print(f"Starting Polymarket Bot UI on port {port}...")
    print(f"Open http://0.0.0.0:{port} in your browser")
    app.run(host="0.0.0.0", port=port, debug=False)
