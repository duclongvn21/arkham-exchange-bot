const ExchangeFlowApp = (() => {
  const REFRESH_MS = 10000;
  let currentFilter = "all";

  function fmtUsd(v) {
    if (v == null) return "—";
    return "$" + Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  function fmtTime(unixSeconds) {
    if (!unixSeconds) return "—";
    const d = new Date(unixSeconds * 1000);
    return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function fmtRelative(unixSeconds) {
    if (!unixSeconds) return "—";
    const diff = Math.max(0, Math.floor(Date.now() / 1000 - unixSeconds));
    if (diff < 60) return `${diff} giây trước`;
    if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
    return `${Math.floor(diff / 3600)} giờ trước`;
  }

  async function fetchJSON(url, options) {
    const resp = await fetch(url, options);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  function setConnStatus(ok, errorMsg) {
    const el = document.getElementById("conn-status");
    if (!el) return;
    if (ok) {
      el.innerHTML = '<span class="dot dot-ok"></span> Đang hoạt động';
    } else {
      el.innerHTML = '<span class="dot dot-error"></span> Lỗi kết nối';
    }
    el.title = errorMsg || "";
  }

  // -------------------------------------------------------------------
  // Dashboard
  // -------------------------------------------------------------------

  function renderAlerts(alerts) {
    const body = document.getElementById("alerts-body");
    if (!body) return;

    const filtered = currentFilter === "all"
      ? alerts
      : alerts.filter((a) => a.direction === currentFilter);

    if (filtered.length === 0) {
      body.innerHTML = '<tr><td colspan="7" class="empty-row">Chưa có cảnh báo nào phù hợp bộ lọc.</td></tr>';
      return;
    }

    body.innerHTML = filtered.map((a, idx) => {
      const badgeClass = a.direction === "inflow" ? "badge-inflow" : "badge-outflow";
      const badgeIcon = a.direction === "inflow" ? "🔴" : "🟢";
      const badgeText = a.direction === "inflow" ? "Vào sàn" : "Ra sàn";
      const mcapPct = a.market_cap ? ((a.usd_value / a.market_cap) * 100).toFixed(2) + "%" : "—";
      const surgeText = (a.surge_ratio != null)
        ? `<span style="color:var(--red)">+${(a.surge_ratio * 100).toFixed(0)}%</span> so kỳ trước`
        : "(token mới, không có kỳ trước)";
      return `
        <tr data-idx="${idx}">
          <td title="${fmtTime(a.detected_at)}">${fmtRelative(a.detected_at)}</td>
          <td><strong>${escapeHtml(a.symbol)}</strong> <span style="color:var(--text-dim)">${escapeHtml(a.name || "")}</span></td>
          <td><span class="badge ${badgeClass}">${badgeIcon} ${badgeText}</span></td>
          <td>${fmtUsd(a.usd_value)}</td>
          <td>${surgeText}</td>
          <td>${mcapPct}</td>
          <td>${escapeHtml(a.timeframe)}</td>
        </tr>
      `;
    }).join("");

    body.querySelectorAll("tr[data-idx]").forEach((row) => {
      row.addEventListener("click", () => openCoinModal(filtered[parseInt(row.dataset.idx, 10)]));
    });
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : String(s);
    return div.innerHTML;
  }

  // -------------------------------------------------------------------
  // Coin detail modal + bieu do nen (ve SVG thuan, khong can thu vien ngoai)
  // -------------------------------------------------------------------

  let coinModalSeq = 0; // chong race-condition khi bam nhanh nhieu coin lien tiep

  function fmtUsdCompact(v) {
    if (v == null) return "—";
    const n = Number(v);
    if (n >= 1) return "$" + n.toLocaleString("en-US", { maximumFractionDigits: n >= 100 ? 0 : 4 });
    return "$" + n.toPrecision(4);
  }

  function renderCandlestickSVG(candles) {
    const svg = document.getElementById("coin-candlestick-chart");
    const W = 900, H = 280, padY = 20;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    if (!candles || candles.length === 0) {
      svg.innerHTML = `<text x="${W/2}" y="${H/2}" fill="#8b92a3" font-size="13" text-anchor="middle">Không có dữ liệu biểu đồ</text>`;
      return;
    }

    const highs = candles.map((c) => c[2]);
    const lows = candles.map((c) => c[3]);
    let minP = Math.min(...lows), maxP = Math.max(...highs);
    if (minP === maxP) { minP *= 0.98; maxP *= 1.02; }
    const scaleY = (p) => H - padY - ((p - minP) / (maxP - minP)) * (H - padY * 2);

    const n = candles.length;
    const slot = W / n;
    const bodyW = Math.max(1, slot * 0.6);

    let svgContent = "";
    candles.forEach((c, i) => {
      const [, open, high, low, close] = c;
      const x = i * slot + slot / 2;
      const isUp = close >= open;
      const color = isUp ? "#4caf7d" : "#ef5350";
      const yHigh = scaleY(high), yLow = scaleY(low);
      const yOpen = scaleY(open), yClose = scaleY(close);
      const yTop = Math.min(yOpen, yClose);
      const bodyH = Math.max(1, Math.abs(yClose - yOpen));
      svgContent += `<line x1="${x}" y1="${yHigh}" x2="${x}" y2="${yLow}" stroke="${color}" stroke-width="1" />`;
      svgContent += `<rect x="${x - bodyW/2}" y="${yTop}" width="${bodyW}" height="${bodyH}" fill="${color}" />`;
    });
    svg.innerHTML = svgContent;
  }

  function renderCoinInfo(alert) {
    const el = document.getElementById("coin-modal-info");
    const directionLabel = alert.direction === "inflow" ? "🔴 Nạp vào sàn" : "🟢 Rút khỏi sàn";
    const surgeText = alert.surge_ratio != null ? `+${(alert.surge_ratio * 100).toFixed(0)}%` : "—";
    const prevText = alert.previous_usd_value != null ? fmtUsd(alert.previous_usd_value) : "(không có dữ liệu)";
    el.innerHTML = `
      <div class="coin-detail-item"><div class="cdi-label">Chiều</div><div class="cdi-value">${directionLabel}</div></div>
      <div class="coin-detail-item"><div class="cdi-label">Giá trị hiện tại</div><div class="cdi-value">${fmtUsd(alert.usd_value)}</div></div>
      <div class="coin-detail-item"><div class="cdi-label">Kỳ trước</div><div class="cdi-value">${prevText}</div></div>
      <div class="coin-detail-item"><div class="cdi-label">Thay đổi</div><div class="cdi-value">${surgeText}</div></div>
    `;
  }

  async function openCoinModal(alert) {
    const overlay = document.getElementById("coin-modal-overlay");
    const title = document.getElementById("coin-modal-title");
    const statusEl = document.getElementById("coin-chart-status");

    title.textContent = `${alert.symbol} · ${alert.name || ""}`;
    renderCoinInfo(alert);
    renderCandlestickSVG([]);
    statusEl.textContent = "Đang tải biểu đồ giá...";
    overlay.hidden = false;

    const mySeq = ++coinModalSeq;
    try {
      // alert.name la CoinGecko-style id (VD "bitcoin", "lobster-2") Arkham tra ve
      const candles = await fetchJSON(`/api/token-ohlc?id=${encodeURIComponent(alert.name)}&days=7`);
      if (mySeq !== coinModalSeq) return; // da mo coin khac trong luc cho
      if (!candles || candles.length === 0) {
        statusEl.textContent = "Không lấy được dữ liệu biểu đồ giá cho token này (CoinGecko không có dữ liệu hoặc ID không khớp).";
      } else {
        statusEl.textContent = "";
      }
      renderCandlestickSVG(candles);
    } catch (e) {
      if (mySeq !== coinModalSeq) return;
      statusEl.textContent = "Lỗi tải biểu đồ: " + e.message;
    }
  }

  function closeCoinModal() {
    document.getElementById("coin-modal-overlay").hidden = true;
  }

  function initCoinModal() {
    document.getElementById("coin-modal-close").addEventListener("click", closeCoinModal);
    document.getElementById("coin-modal-overlay").addEventListener("click", (e) => {
      if (e.target.id === "coin-modal-overlay") closeCoinModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeCoinModal();
    });
  }

  async function refreshDashboard() {
    try {
      const [status, alerts] = await Promise.all([
        fetchJSON("/api/status"),
        fetchJSON("/api/alerts?limit=100"),
      ]);

      setConnStatus(!status.last_error, status.last_error);

      const errBanner = document.getElementById("error-banner");
      if (status.last_error) {
        errBanner.hidden = false;
        errBanner.textContent = "⚠️ " + status.last_error;
      } else {
        errBanner.hidden = true;
      }

      document.getElementById("stat-total").textContent = alerts.length;
      document.getElementById("stat-inflow").textContent = alerts.filter((a) => a.direction === "inflow").length;
      document.getElementById("stat-outflow").textContent = alerts.filter((a) => a.direction === "outflow").length;
      document.getElementById("stat-lastscan").textContent = status.last_scan_at ? fmtRelative(status.last_scan_at) : "Chưa quét";
      const cutoffEl = document.getElementById("stat-mcap-cutoff");
      const cutoffLabelEl = document.getElementById("stat-mcap-cutoff-label");
      const watchlist = (status.config && status.config.watchlist) || "";
      const watchedTokens = watchlist.split(",").map((t) => t.trim()).filter(Boolean);
      if (cutoffEl && cutoffLabelEl) {
        if (watchedTokens.length > 0) {
          cutoffLabelEl.textContent = "Chế độ Watchlist";
          cutoffEl.textContent = `${watchedTokens.length} coin`;
          cutoffEl.title = watchedTokens.join(", ");
        } else {
          cutoffLabelEl.textContent = "Đang loại trừ Market Cap ≥";
          cutoffEl.textContent = status.effective_max_market_cap ? fmtUsd(status.effective_max_market_cap) : "—";
          cutoffEl.title = status.config && status.config.exclude_top_rank > 0
            ? `Tự động theo Top ${status.config.exclude_top_rank} (CoinGecko)`
            : "Dùng ngưỡng thủ công";
        }
      }

      renderAlerts(alerts);
    } catch (e) {
      setConnStatus(false, e.message);
    }
  }

  function initDashboard() {
    refreshDashboard();
    setInterval(refreshDashboard, REFRESH_MS);
    initCoinModal();

    document.querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentFilter = btn.dataset.filter;
        refreshDashboard();
      });
    });

    document.getElementById("scan-now-btn").addEventListener("click", async (e) => {
      const btn = e.target;
      btn.disabled = true;
      btn.textContent = "Đang quét...";
      try {
        await fetchJSON("/api/scan-now", { method: "POST" });
        setTimeout(refreshDashboard, 2500);
      } finally {
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = "Quét ngay";
        }, 2500);
      }
    });
  }

  // -------------------------------------------------------------------
  // Settings
  // -------------------------------------------------------------------

  let watchlistItems = []; // [{id, label}]

  function renderWatchlistChips() {
    const el = document.getElementById("watchlist-chips");
    if (!el) return;
    if (watchlistItems.length === 0) {
      el.innerHTML = '<span class="hint">Chưa có coin nào trong watchlist — đang quét toàn thị trường.</span>';
      return;
    }
    el.innerHTML = watchlistItems.map((item, idx) => `
      <span class="watchlist-chip">
        ${escapeHtml(item.label)}
        <button type="button" data-idx="${idx}" title="Xóa khỏi watchlist">×</button>
      </span>
    `).join("");
    el.querySelectorAll("button[data-idx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        watchlistItems.splice(parseInt(btn.dataset.idx, 10), 1);
        renderWatchlistChips();
        saveWatchlist();
      });
    });
  }

  async function saveWatchlist() {
    const watchlist = watchlistItems.map((item) => item.id).join(", ");
    await fetchJSON("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ watchlist }),
    });
  }

  function addToWatchlist(id, label) {
    const exists = watchlistItems.some((item) => item.id.toLowerCase() === id.toLowerCase());
    if (exists) return;
    watchlistItems.push({ id, label });
    renderWatchlistChips();
    saveWatchlist();
  }

  let watchlistSearchSeq = 0; // chong race-condition khi go nhanh (ket qua cu ve sau ket qua moi)

  async function runWatchlistSearch() {
    const input = document.getElementById("watchlist-search-input");
    const resultsEl = document.getElementById("watchlist-search-results");
    const query = input.value.trim();
    if (!query) {
      resultsEl.hidden = true;
      return;
    }
    const mySeq = ++watchlistSearchSeq;
    let results;
    try {
      results = await fetchJSON(`/api/search-token?q=${encodeURIComponent(query)}`);
    } catch (e) {
      if (mySeq !== watchlistSearchSeq) return; // co request moi hon da chay sau, bo qua ket qua cu nay
      resultsEl.hidden = false;
      resultsEl.innerHTML = `<div class="watchlist-result-empty">Lỗi tìm kiếm: ${escapeHtml(e.message)}</div>`;
      return;
    }
    if (mySeq !== watchlistSearchSeq) return; // co request moi hon da chay sau, bo qua ket qua cu nay
    resultsEl.hidden = false;
    if (results.length === 0) {
      resultsEl.innerHTML = '<div class="watchlist-result-empty">Không tìm thấy coin nào khớp.</div>';
      return;
    }
    resultsEl.innerHTML = results.map((r, idx) => `
      <div class="watchlist-result-item" data-idx="${idx}">
        <span><strong>${escapeHtml(r.symbol)}</strong><span class="wri-name">${escapeHtml(r.name)}</span></span>
        <span class="wri-rank">${r.market_cap_rank ? "#" + r.market_cap_rank : ""}</span>
      </div>
    `).join("");
    resultsEl.querySelectorAll(".watchlist-result-item").forEach((row, idx) => {
      row.addEventListener("click", () => {
        const r = results[idx];
        addToWatchlist(r.id, `${r.symbol} ${r.name}`);
        input.value = "";
        resultsEl.hidden = true;
      });
    });
  }

  function initWatchlistSearch() {
    document.getElementById("watchlist-search-btn").addEventListener("click", runWatchlistSearch);
    const input = document.getElementById("watchlist-search-input");
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runWatchlistSearch();
      }
    });

    // Tu dong goi y khi dang go (debounce 400ms, tu 2 ky tu tro len)
    let debounceTimer = null;
    input.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      const resultsEl = document.getElementById("watchlist-search-results");
      if (input.value.trim().length < 2) {
        if (resultsEl) resultsEl.hidden = true;
        return;
      }
      debounceTimer = setTimeout(runWatchlistSearch, 400);
    });
    document.addEventListener("click", (e) => {
      const resultsEl = document.getElementById("watchlist-search-results");
      if (resultsEl && !resultsEl.hidden && !e.target.closest(".watchlist-search-row") && !e.target.closest(".watchlist-results")) {
        resultsEl.hidden = true;
      }
    });
  }

  async function loadSettings() {
    const cfg = await fetchJSON("/api/config");
    watchlistItems = (cfg.watchlist || "")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
      .map((t) => ({ id: t, label: t }));
    renderWatchlistChips();
    document.getElementById("timeframe").value = cfg.timeframe;
    document.getElementById("exclude_top_rank").value = cfg.exclude_top_rank;
    document.getElementById("max_market_cap").value = cfg.max_market_cap;
    document.getElementById("min_surge_ratio").value = (cfg.min_surge_ratio * 100).toFixed(0);
    document.getElementById("min_usd_threshold").value = cfg.min_usd_threshold;
    document.getElementById("min_mcap_ratio").value = (cfg.min_mcap_ratio * 100).toFixed(2);
    document.getElementById("top_n").value = cfg.top_n;
    document.getElementById("poll_interval_seconds").value = cfg.poll_interval_seconds;
    document.getElementById("alert_cooldown_seconds").value = cfg.alert_cooldown_seconds;
    document.getElementById("telegram_enabled").checked = cfg.telegram_enabled;

    const hint = document.getElementById("telegram-hint");
    hint.textContent = cfg.has_telegram_config
      ? "Đã có cấu hình bot token + chat ID trong .env."
      : "Chưa cấu hình TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID trong .env — bật ở đây cũng sẽ không gửi được cho đến khi bạn điền vào .env.";

    const keyStatus = document.getElementById("config-status");
    keyStatus.textContent = cfg.has_arkham_key
      ? "✓ Arkham API key đã được cấu hình."
      : "⚠️ Chưa có ARKHAM_API_KEY trong .env — bot sẽ không quét được cho đến khi bạn thêm vào.";
  }

  function initSettings() {
    loadSettings();
    initWatchlistSearch();

    document.getElementById("settings-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = {
        timeframe: document.getElementById("timeframe").value,
        exclude_top_rank: parseInt(document.getElementById("exclude_top_rank").value, 10) || 0,
        max_market_cap: parseFloat(document.getElementById("max_market_cap").value) || 0,
        min_surge_ratio: (parseFloat(document.getElementById("min_surge_ratio").value) || 0) / 100,
        min_usd_threshold: parseFloat(document.getElementById("min_usd_threshold").value) || 0,
        min_mcap_ratio: (parseFloat(document.getElementById("min_mcap_ratio").value) || 0) / 100,
        top_n: parseInt(document.getElementById("top_n").value, 10) || 30,
        poll_interval_seconds: parseInt(document.getElementById("poll_interval_seconds").value, 10) || 180,
        alert_cooldown_seconds: parseInt(document.getElementById("alert_cooldown_seconds").value, 10) || 3600,
        telegram_enabled: document.getElementById("telegram_enabled").checked,
      };

      const banner = document.getElementById("save-banner");
      try {
        await fetchJSON("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        banner.hidden = false;
        banner.textContent = "✓ Đã lưu cài đặt. Áp dụng từ lần quét tiếp theo.";
        setTimeout(() => { banner.hidden = true; }, 4000);
      } catch (err) {
        banner.hidden = false;
        banner.style.background = "var(--red-bg)";
        banner.style.color = "var(--red)";
        banner.textContent = "✗ Lỗi khi lưu: " + err.message;
      }
    });
  }

  async function pingStatus() {
    try {
      const status = await fetchJSON("/api/status");
      setConnStatus(!status.last_error, status.last_error);
    } catch (e) {
      setConnStatus(false, e.message);
    }
  }

  return { initDashboard, initSettings, pingStatus };
})();

// Cap nhat pill trang thai o header tren moi trang (ke ca khong phai dashboard)
document.addEventListener("DOMContentLoaded", () => {
  ExchangeFlowApp.pingStatus();
  setInterval(ExchangeFlowApp.pingStatus, 15000);
});
