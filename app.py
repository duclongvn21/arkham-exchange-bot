"""
Arkham Exchange Flow Monitor - Web App
=======================================

Chay: python app.py
Mo trinh duyet: http://localhost:5000
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from flask import Flask, jsonify, render_template, request

import arkham_core as core

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("arkham-web")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# State dung chung giua background thread va Flask request thread
# ---------------------------------------------------------------------------

MAX_ALERTS_STORED = 500

state_lock = threading.Lock()
alerts_history: deque = deque(maxlen=MAX_ALERTS_STORED)
last_alert_time: dict[str, float] = {}

status = {
    "running": True,
    "last_scan_at": None,
    "next_scan_at": None,
    "last_error": None,
    "scans_done": 0,
}


def worker_loop() -> None:
    while True:
        try:
            spikes = core.detect_spikes()
            now = time.time()

            with state_lock:
                status["last_error"] = None

            for alert in spikes:
                key = f"{alert.symbol}:{alert.direction}"
                with state_lock:
                    last_time = last_alert_time.get(key, 0)
                if now - last_time < core.config.alert_cooldown_seconds:
                    continue

                log.info("SPIKE: %s %s $%.0f", alert.symbol, alert.direction, alert.usd_value)

                with state_lock:
                    alerts_history.appendleft(alert.to_dict())
                    last_alert_time[key] = now

                core.send_telegram_message(core.format_alert_message(alert))

            with state_lock:
                status["scans_done"] += 1
                status["last_scan_at"] = now
                status["next_scan_at"] = now + core.config.poll_interval_seconds

        except Exception as e:
            log.exception("Loi trong vong quet")
            with state_lock:
                status["last_error"] = str(e)
                status["last_scan_at"] = time.time()
                status["next_scan_at"] = time.time() + core.config.poll_interval_seconds

        time.sleep(core.config.poll_interval_seconds)


# ---------------------------------------------------------------------------
# Routes - trang web
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


# ---------------------------------------------------------------------------
# Routes - API (JSON, dung boi JS phia client)
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    with state_lock:
        s = dict(status)
    s["config"] = core.config.as_dict()
    s["total_alerts"] = len(alerts_history)
    # An toan: khong goi CoinGecko that su o day (chi doc cache co san tu
    # lan quet gan nhat) de tranh spam khi dashboard tu refresh moi 15s.
    cache = core._rank_cutoff_cache
    s["effective_max_market_cap"] = cache["value"] if cache["value"] is not None else core.config.max_market_cap
    return jsonify(s)


@app.route("/api/alerts")
def api_alerts():
    limit = min(int(request.args.get("limit", 100)), MAX_ALERTS_STORED)
    direction = request.args.get("direction")  # "inflow" | "outflow" | None
    with state_lock:
        items = list(alerts_history)
    if direction in ("inflow", "outflow"):
        items = [a for a in items if a["direction"] == direction]
    return jsonify(items[:limit])


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        core.config.update(data)
        log.info("Cau hinh da cap nhat: %s", core.config.as_dict())
    return jsonify(core.config.as_dict())


@app.route("/api/scan-now", methods=["POST"])
def api_scan_now():
    """Kich hoat quet ngay lap tuc thay vi doi het chu ky poll."""
    threading.Thread(target=worker_loop_once, daemon=True).start()
    return jsonify({"ok": True})


def worker_loop_once() -> None:
    try:
        spikes = core.detect_spikes()
        now = time.time()
        for alert in spikes:
            key = f"{alert.symbol}:{alert.direction}"
            with state_lock:
                last_time = last_alert_time.get(key, 0)
            if now - last_time < core.config.alert_cooldown_seconds:
                continue
            with state_lock:
                alerts_history.appendleft(alert.to_dict())
                last_alert_time[key] = now
            core.send_telegram_message(core.format_alert_message(alert))
        with state_lock:
            status["scans_done"] += 1
            status["last_scan_at"] = now
            status["last_error"] = None
    except Exception as e:
        log.exception("Loi khi quet thu cong")
        with state_lock:
            status["last_error"] = str(e)


# ---------------------------------------------------------------------------
# Khoi dong
# ---------------------------------------------------------------------------

def start_background_worker() -> None:
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
    log.info("Background worker da khoi dong (poll moi %ss)", core.config.poll_interval_seconds)


if __name__ == "__main__":
    start_background_worker()
    app.run(host="0.0.0.0", port=5000, debug=False)
