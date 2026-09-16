"""
Arkham Exchange Flow Alert Bot - ban CLI (khong can trang web).
Dung chung logic voi app.py qua module arkham_core.py.

Cai dat:
    pip install -r requirements.txt
    cp .env.example .env   # roi dien API key vao
    python bot.py --debug --once   # chay thu, kiem tra JSON response
    python bot.py                  # chay that (vong lap vinh vien)

Muon co giao dien web (dashboard, chinh cau hinh tren trinh duyet)?
    python app.py   # roi mo http://localhost:5000
"""

import argparse
import logging
import time

import requests

import arkham_core as core

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("arkham-bot")


def main() -> None:
    parser = argparse.ArgumentParser(description="Arkham Exchange Flow Alert Bot")
    parser.add_argument("--debug", action="store_true", help="In JSON response goc de doi chieu ten field")
    parser.add_argument("--once", action="store_true", help="Chi quet 1 lan roi thoat")
    args = parser.parse_args()

    cfg = core.config
    log.info(
        "Bat dau bot | timeframe=%s | nguong=$%.0f | ty le mcap=%.2f%% | poll moi %ss",
        cfg.timeframe, cfg.min_usd_threshold, cfg.min_mcap_ratio * 100, cfg.poll_interval_seconds,
    )

    last_alert_time: dict[str, float] = {}

    while True:
        try:
            spikes = core.detect_spikes(debug=args.debug)
            now = time.time()

            for alert in spikes:
                key = f"{alert.symbol}:{alert.direction}"
                last_time = last_alert_time.get(key, 0)
                if now - last_time < cfg.alert_cooldown_seconds:
                    continue

                log.info("SPIKE: %s %s $%.0f", alert.symbol, alert.direction, alert.usd_value)
                core.send_telegram_message(core.format_alert_message(alert))
                last_alert_time[key] = now

            if not spikes:
                log.info("Khong phat hien dot bien nao trong lan quet nay.")

        except requests.HTTPError as e:
            log.error("Loi goi Arkham API: %s", e)
        except Exception:
            log.exception("Loi khong mong muon trong vong quet")

        if args.once:
            break
        time.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    main()
