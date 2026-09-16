"""
Logic dung chung: goi Arkham API, phat hien dot bien dong tien, gui Telegram.
Duoc dung boi ca bot.py (CLI) va app.py (web app).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

log = logging.getLogger("arkham-bot")

ARKHAM_BASE_URL = "https://api.arkm.com"
ENV_PATH = Path(__file__).parent / ".env"


# ---------------------------------------------------------------------------
# Config - co the doi khi dang chay (tu web UI), co lock de an toan giua
# request thread cua Flask va background polling thread.
# ---------------------------------------------------------------------------

class Config:
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.arkham_api_key = os.environ.get("ARKHAM_API_KEY", "")
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.telegram_enabled = bool(self.telegram_bot_token and self.telegram_chat_id)

        # Danh sach token ID (CoinGecko-style id, VD "bitcoin", "power-protocol")
        # cach nhau boi dau phay. Neu KHONG rong: bot CHI quet dung cac token
        # nay (bo qua toan bo pham vi thi truong + bo qua bo loc market cap).
        # Neu rong: quet toan bo thi truong nhu binh thuong (che do mac dinh).
        self.watchlist = os.environ.get("WATCHLIST", "")

        self.timeframe = os.environ.get("TIMEFRAME", "1h")
        self.min_usd_threshold = float(os.environ.get("MIN_USD_THRESHOLD", "50000"))
        self.min_mcap_ratio = float(os.environ.get("MIN_MCAP_RATIO", "0.015"))
        # Ty le tang toi thieu so voi ky truoc de coi la "dot bien" (0.5 = tang >= 50%).
        # Day la dieu kien CHINH - tranh viec token lon (BTC/ETH/USDT...) bi bao lien tuc
        # chi vi dong tien tuyet doi cua no luon lon, du khong co gi bat thuong.
        self.min_surge_ratio = float(os.environ.get("MIN_SURGE_RATIO", "0.5"))
        # DIEU KIEN CHINH de loai coin top: tu dong lay market cap cua coin
        # dung thu hang nay (VD 100) tu CoinGecko (mien phi, khong can key),
        # cap nhat moi gio - tu dieu chinh theo thi truong that thay vi so
        # USD co dinh de bi lac hau. Dat 0 de tat, chi dung MAX_MARKET_CAP thu cong.
        self.exclude_top_rank = int(os.environ.get("EXCLUDE_TOP_RANK", "100"))
        # Nguong du phong (USD) - dung khi EXCLUDE_TOP_RANK=0, hoac khi
        # khong goi duoc CoinGecko (mat mang, rate limit...).
        self.max_market_cap = float(os.environ.get("MAX_MARKET_CAP", "3000000000"))
        self.top_n = int(os.environ.get("TOP_N", "30"))
        self.poll_interval_seconds = int(os.environ.get("POLL_INTERVAL_SECONDS", "180"))
        self.alert_cooldown_seconds = int(os.environ.get("ALERT_COOLDOWN_SECONDS", "3600"))

    def as_dict(self) -> dict:
        with self._lock:
            return {
                "watchlist": self.watchlist,
                "timeframe": self.timeframe,
                "min_usd_threshold": self.min_usd_threshold,
                "min_mcap_ratio": self.min_mcap_ratio,
                "min_surge_ratio": self.min_surge_ratio,
                "exclude_top_rank": self.exclude_top_rank,
                "max_market_cap": self.max_market_cap,
                "top_n": self.top_n,
                "poll_interval_seconds": self.poll_interval_seconds,
                "alert_cooldown_seconds": self.alert_cooldown_seconds,
                "telegram_enabled": self.telegram_enabled,
                "has_arkham_key": bool(self.arkham_api_key),
                "has_telegram_config": bool(self.telegram_bot_token and self.telegram_chat_id),
            }

    def update(self, data: dict) -> None:
        with self._lock:
            if "watchlist" in data:
                self.watchlist = str(data["watchlist"]).strip()
            if "timeframe" in data and data["timeframe"] in ("1h", "6h", "12h", "24h", "7d"):
                self.timeframe = data["timeframe"]
            if "min_usd_threshold" in data:
                self.min_usd_threshold = max(0.0, float(data["min_usd_threshold"]))
            if "min_mcap_ratio" in data:
                self.min_mcap_ratio = max(0.0, float(data["min_mcap_ratio"]))
            if "min_surge_ratio" in data:
                self.min_surge_ratio = max(0.0, float(data["min_surge_ratio"]))
            if "exclude_top_rank" in data:
                self.exclude_top_rank = max(0, int(data["exclude_top_rank"]))
            if "max_market_cap" in data:
                self.max_market_cap = max(0.0, float(data["max_market_cap"]))
            if "top_n" in data:
                self.top_n = max(1, min(500, int(data["top_n"])))
            if "poll_interval_seconds" in data:
                self.poll_interval_seconds = max(30, int(data["poll_interval_seconds"]))
            if "alert_cooldown_seconds" in data:
                self.alert_cooldown_seconds = max(0, int(data["alert_cooldown_seconds"]))
            if "telegram_enabled" in data:
                self.telegram_enabled = bool(data["telegram_enabled"])
        self._persist_to_env()

    def _persist_to_env(self) -> None:
        """Ghi lai cau hinh vao .env de giu nguyen sau khi restart app."""
        lines = []
        if ENV_PATH.exists():
            lines = ENV_PATH.read_text().splitlines()

        values = {
            "WATCHLIST": self.watchlist,
            "TIMEFRAME": self.timeframe,
            "MIN_USD_THRESHOLD": str(self.min_usd_threshold),
            "MIN_MCAP_RATIO": str(self.min_mcap_ratio),
            "MIN_SURGE_RATIO": str(self.min_surge_ratio),
            "EXCLUDE_TOP_RANK": str(self.exclude_top_rank),
            "MAX_MARKET_CAP": str(self.max_market_cap),
            "TOP_N": str(self.top_n),
            "POLL_INTERVAL_SECONDS": str(self.poll_interval_seconds),
            "ALERT_COOLDOWN_SECONDS": str(self.alert_cooldown_seconds),
        }
        seen = set()
        new_lines = []
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else None
            if key in values:
                new_lines.append(f"{key}={values[key]}")
                seen.add(key)
            else:
                new_lines.append(line)
        for key, val in values.items():
            if key not in seen:
                new_lines.append(f"{key}={val}")

        try:
            ENV_PATH.write_text("\n".join(new_lines) + "\n")
        except OSError as e:
            log.warning("Khong the ghi .env: %s", e)


config = Config()


# ---------------------------------------------------------------------------
# Du lieu
# ---------------------------------------------------------------------------

@dataclass
class FlowAlert:
    symbol: str
    name: str
    direction: str  # "inflow" (vao san) hoac "outflow" (ra san)
    usd_value: float
    previous_usd_value: float | None
    market_cap: float | None
    timeframe: str
    detected_at: float = field(default_factory=time.time)

    @property
    def surge_ratio(self) -> float | None:
        """% tang so voi ky truoc. None neu khong co du lieu ky truoc."""
        if self.previous_usd_value is None or self.previous_usd_value <= 0:
            return None
        return (self.usd_value - self.previous_usd_value) / self.previous_usd_value

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "direction": self.direction,
            "usd_value": self.usd_value,
            "previous_usd_value": self.previous_usd_value,
            "surge_ratio": self.surge_ratio,
            "market_cap": self.market_cap,
            "timeframe": self.timeframe,
            "detected_at": self.detected_at,
        }


# ---------------------------------------------------------------------------
# Nguong loai coin top - tu dong lay tu CoinGecko (mien phi, khong can key)
# ---------------------------------------------------------------------------

_rank_cutoff_cache: dict = {"value": None, "fetched_at": 0.0, "rank": None}
RANK_CUTOFF_CACHE_SECONDS = 3600  # lam moi moi 1 gio, khong can goi lien tuc


def fetch_market_cap_at_rank(rank: int) -> float | None:
    """Lay market cap cua coin dung thu hang 'rank' theo CoinGecko (VD rank=100)."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 1, "page": rank},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return data[0].get("market_cap")
    except requests.RequestException as e:
        log.warning("Khong lay duoc market cap hang #%d tu CoinGecko: %s", rank, e)
    return None


_symbol_resolve_cache: dict[str, str] = {}


def search_tokens(query: str, limit: int = 8) -> list[dict]:
    """
    Tim coin qua CoinGecko Search API (mien phi, khong can key).
    Tra ve list {id, symbol, name, market_cap_rank}, sap xep coin pho bien
    (market cap rank thap = lon) len truoc. Dung cho o tim kiem tren web UI.
    """
    query = query.strip()
    if not query:
        return []
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": query},
            timeout=10,
        )
        resp.raise_for_status()
        coins = resp.json().get("coins", [])
        coins.sort(key=lambda c: (c.get("market_cap_rank") is None, c.get("market_cap_rank", 10**9)))
        return [
            {
                "id": c.get("id"),
                "symbol": (c.get("symbol") or "").upper(),
                "name": c.get("name"),
                "market_cap_rank": c.get("market_cap_rank"),
            }
            for c in coins[:limit]
        ]
    except requests.RequestException as e:
        log.warning("Tim kiem token '%s' that bai: %s", query, e)
        return []


def resolve_token_id(query: str) -> str:
    """
    Nguoi dung go ticker (VD "BTC") hoac da go dung ID (VD "bitcoin") deu duoc.
    Tra cuu qua CoinGecko Search API de doi ticker -> ID chuan, uu tien coin
    pho bien nhat neu trung ten. Ket qua duoc cache lai, chi tra cuu 1 lan
    cho moi tu khoa. Neu tra cuu that bai/khong tim thay: dung nguyen text
    goc - van hoat dong binh thuong neu nguoi dung da go dung ID san.
    """
    key = query.strip().lower()
    if not key:
        return query
    if key in _symbol_resolve_cache:
        return _symbol_resolve_cache[key]

    results = search_tokens(query, limit=1)
    resolved = results[0]["id"] if results else query.strip()
    if results:
        log.info("Da tra cuu '%s' -> id '%s'", query, resolved)

    _symbol_resolve_cache[key] = resolved
    return resolved


def resolve_watchlist_ids() -> list[str]:
    """Danh sach ID da duoc tra cuu/chuan hoa tu watchlist nguoi dung nhap."""
    return [resolve_token_id(t) for t in get_watchlist()]


def get_effective_max_market_cap() -> float:
    """
    Neu config.exclude_top_rank > 0: tu dong dung market cap cua coin dung
    thu hang do (cache 1 gio) lam nguong loai tru - luon dung theo thi truong
    that. Neu tat tinh nang nay hoac khong lay duoc du lieu (mat mang,
    CoinGecko rate-limit...): dung nguong USD thu cong (config.max_market_cap).
    """
    if config.exclude_top_rank > 0:
        now = time.time()
        cache = _rank_cutoff_cache
        stale = (
            cache["value"] is None
            or cache["rank"] != config.exclude_top_rank
            or now - cache["fetched_at"] > RANK_CUTOFF_CACHE_SECONDS
        )
        if stale:
            fetched = fetch_market_cap_at_rank(config.exclude_top_rank)
            if fetched:
                cache["value"] = fetched
                cache["fetched_at"] = now
                cache["rank"] = config.exclude_top_rank
                log.info("Da cap nhat nguong 'ngoai top %d': $%.0f", config.exclude_top_rank, fetched)
        if cache["value"] is not None:
            return cache["value"]
    return config.max_market_cap


# ---------------------------------------------------------------------------
# Goi Arkham API
# ---------------------------------------------------------------------------

def arkham_get(path: str, params: dict) -> dict:
    if not config.arkham_api_key:
        raise RuntimeError("Thieu ARKHAM_API_KEY - dien vao .env hoac trang Settings.")
    resp = requests.get(
        f"{ARKHAM_BASE_URL}{path}",
        headers={"API-Key": config.arkham_api_key},
        params=params,
        timeout=15,
    )
    if not resp.ok:
        # In ra noi dung loi that su tu Arkham (khong chi ma HTTP) de biet
        # chinh xac tham so nao sai.
        log.error("Arkham API tra ve loi %s cho %s | params=%s | body=%s",
                   resp.status_code, resp.url, params, resp.text[:2000])
    resp.raise_for_status()
    return resp.json()


def get_watchlist() -> list[str]:
    """Danh sach token ID nguoi dung tu them (rong = quet toan bo thi truong)."""
    return [t.strip() for t in config.watchlist.split(",") if t.strip()]


WATCHLIST_SCAN_SIZE = 300  # size lon hon khi quet watchlist, tang co hoi tim thay dung token


def fetch_top_flow(order_by_agg: str, size: int | None = None, debug: bool = False) -> list:
    """
    LUU Y QUAN TRONG: da test thuc te va xac nhan Arkham /token/top KHONG ho
    tro loc theo tham so "tokens" nhu tai lieu cong dong ghi (truyen tokens=
    khong co tac dung, API van tra ve ket qua xep hang binh thuong, bo qua
    tham so nay). Vi vay che do Watchlist phai quet mot danh sach du lon roi
    tu loc phia code (xem detect_spikes), khong the loc thang tu API.
    """
    params = {
        "timeframe": config.timeframe,
        "orderByAgg": order_by_agg,
        "orderByDesc": "true",  # true = lay gia tri cao nhat truoc (top inflow/outflow)
        "orderByPercent": "false",  # false = xep hang theo gia tri USD tuyet doi, khong phai %
        "from": 0,  # vi tri bat dau phan trang (khong phai dia chi vi)
        "size": size if size is not None else config.top_n,
    }
    data = arkham_get("/token/top", params)

    if debug:
        log.info(
            "RAW RESPONSE (%s):\n%s",
            order_by_agg, json.dumps(data, indent=2)[:3000],
        )

    if isinstance(data, dict):
        for key in ("tokens", "data", "results"):
            if key in data:
                return data[key]
        return []
    return data


def parse_token_row(row: dict, direction: str) -> FlowAlert | None:
    """
    Cau truc thuc te tra ve tu /token/top (xac nhan qua --debug):
    {
      "token": {"id": "tether", "symbol": "usdt", "marketCap": 183334173286.15},
      "current": {"price": ..., "inflowCexVolume": ..., "outflowCexVolume": ..., ...},
      "previous": {... cung cac field nhu current, cua ky truoc ...}
    }
    """
    token = row.get("token") or {}
    current = row.get("current") or {}
    previous = row.get("previous") or {}

    symbol = (token.get("symbol") or token.get("id") or "?").upper()
    name = token.get("id") or symbol

    field_name = "inflowCexVolume" if direction == "inflow" else "outflowCexVolume"
    usd_value = current.get(field_name)
    if usd_value is None:
        return None
    prev_value = previous.get(field_name)

    market_cap = token.get("marketCap")

    return FlowAlert(
        symbol=symbol,
        name=name,
        direction=direction,
        usd_value=abs(float(usd_value)),
        previous_usd_value=float(prev_value) if prev_value is not None else None,
        market_cap=float(market_cap) if market_cap else None,
        timeframe=config.timeframe,
    )


def is_spike(alert: FlowAlert) -> bool:
    """
    Dinh nghia "dot bien" (khac voi "von dang lon nen dong tien von da lon"):
    - Neu co du lieu ky truoc: PHAI tang toi thieu min_surge_ratio so voi ky
      truoc moi tinh la dot bien. Day la dieu kien chinh, giup loai bo viec
      BTC/ETH/USDT... bi bao lien tuc chi vi ban than no von co volume lon.
    - Neu KHONG co du lieu ky truoc (token moi xuat hien, previous=0/None):
      dung nguong USD tuyet doi hoac ty le % market cap lam phuong an du phong.
    """
    ratio = alert.surge_ratio
    if ratio is not None:
        return ratio >= config.min_surge_ratio

    if alert.usd_value >= config.min_usd_threshold:
        return True
    if alert.market_cap and alert.market_cap > 0:
        if (alert.usd_value / alert.market_cap) >= config.min_mcap_ratio:
            return True
    return False


def detect_spikes(debug: bool = False) -> list[FlowAlert]:
    spikes: list[FlowAlert] = []
    watchlist = get_watchlist()

    if watchlist:
        # CHE DO WATCHLIST: chi quet dung cac token nguoi dung chi dinh.
        # Tu dong doi ticker (VD "BTC") sang ID chuan Arkham can (VD "bitcoin")
        # qua CoinGecko - nguoi dung khong can tu tra ID.
        # Arkham /token/top KHONG ho tro loc server-side theo token cu the (da
        # test thuc te xac nhan), nen phai quet mot danh sach lon (top 300 ca
        # 2 chieu) roi TU LOC PHIA CODE theo dung watchlist - khong ap dung
        # bo loc market cap vi nguoi dung da chu dong chon coin nay.
        resolved_ids = resolve_watchlist_ids()
        watch_ids = {w.lower() for w in resolved_ids}
        watch_symbols = {w.upper() for w in watchlist}  # phong khi nguoi dung go dung ticker

        found = set()
        for order_by_agg, direction in (("inflowCex", "inflow"), ("outflowCex", "outflow")):
            rows = fetch_top_flow(order_by_agg, size=WATCHLIST_SCAN_SIZE, debug=debug)
            for row in rows:
                token = row.get("token") or {}
                tid = (token.get("id") or "").lower()
                tsym = (token.get("symbol") or "").upper()
                if tid not in watch_ids and tsym not in watch_symbols:
                    continue
                found.add(tid or tsym)
                alert = parse_token_row(row, direction)
                if alert and is_spike(alert):
                    spikes.append(alert)

        missing = watch_ids - found
        if missing:
            log.warning(
                "Watchlist: khong thay du lieu cho %s trong top %d ket qua ca 2 chieu "
                "(volume qua thap trong khung gio nay, hoac sai ID/ticker).",
                sorted(missing), WATCHLIST_SCAN_SIZE,
            )
        return spikes

    # CHE DO MAC DINH: quet toan bo thi truong, loai coin top theo market cap
    effective_max_mcap = get_effective_max_market_cap()
    for order_by_agg, direction in (("inflowCex", "inflow"), ("outflowCex", "outflow")):
        rows = fetch_top_flow(order_by_agg, debug=debug)
        for row in rows:
            alert = parse_token_row(row, direction)
            if not alert:
                continue
            # Bo qua coin top (BTC/ETH/USDT...) - nguong lay tu CoinGecko theo
            # config.exclude_top_rank, hoac config.max_market_cap neu tat/loi.
            if alert.market_cap and alert.market_cap >= effective_max_mcap:
                continue
            if is_spike(alert):
                spikes.append(alert)
    return spikes


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram_message(text: str) -> bool:
    if not (config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id):
        return False
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": config.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("Gui Telegram that bai: %s", e)
        return False


def format_alert_message(alert: FlowAlert) -> str:
    icon = "🔴" if alert.direction == "inflow" else "🟢"
    label = "NẠP VÀO SÀN (có thể chuẩn bị bán)" if alert.direction == "inflow" else "RÚT KHỎI SÀN (tích lũy)"

    mcap_line = ""
    if alert.market_cap:
        pct = alert.usd_value / alert.market_cap * 100
        mcap_line = f"\n📊 Market Cap: ${alert.market_cap:,.0f}  (~{pct:.2f}% mcap)"

    surge_line = ""
    ratio = alert.surge_ratio
    if ratio is not None:
        surge_line = f"\n📈 Tăng *{ratio * 100:+.0f}%* so với kỳ trước (${alert.previous_usd_value:,.0f})"

    return (
        f"{icon} *{label}*\n"
        f"🪙 Token: *{alert.symbol}* ({alert.name})\n"
        f"💰 Giá trị: *${alert.usd_value:,.0f}*\n"
        f"⏱ Khung thời gian: {alert.timeframe}"
        f"{surge_line}"
        f"{mcap_line}"
    )
