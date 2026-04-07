/* Crash Detector - Frontend App */

const API_BASE = location.origin;

const INDICATOR_CONFIG = {
  vix: { name: 'VIX', unit: '', thresholds: [20, 30, 40, 50] },
  fear_greed: { name: 'Fear & Greed', unit: '', thresholds: [25, 40, 60, 75] },
  rsi: { name: 'RSI (SPY)', unit: '', thresholds: [30, 40, 60, 70] },
  credit_spread: { name: 'HY Spread', unit: 'bps', thresholds: [300, 400, 500, 700] },
  ma_deviation: { name: 'MA200 乖離', unit: '%', thresholds: [-10, -5, 5, 10] },
  yield_curve: { name: 'Yield Curve', unit: '', thresholds: [-0.5, 0, 0.5, 1.0] },
};

const SCORE_COLORS = {
  red: '#ef4444',
  orange: '#f97316',
  yellow: '#eab308',
  green: '#22c55e',
  purple: '#a855f7',
};

const GEO_NAMES = { wti: 'WTI原油', gold: 'Gold', usdjpy: 'USD/JPY' };

let gaugeChart = null;

async function fetchJSON(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

function initGauge() {
  const el = document.getElementById('gaugeChart');
  if (!el) return;
  gaugeChart = echarts.init(el);
}

function updateGauge(score, color) {
  if (!gaugeChart) return;
  gaugeChart.setOption({
    series: [{
      type: 'gauge',
      min: 0, max: 100,
      splitNumber: 5,
      progress: { show: true, width: 18, roundCap: true },
      axisLine: { lineStyle: { width: 18, color: [[0.2, '#ef4444'], [0.4, '#f97316'], [0.6, '#eab308'], [0.8, '#22c55e'], [1, '#a855f7']] } },
      axisTick: { show: false },
      splitLine: { length: 10, lineStyle: { width: 2, color: '#334155' } },
      axisLabel: { distance: 25, color: '#64748b', fontSize: 11 },
      pointer: { length: '60%', width: 5, itemStyle: { color: SCORE_COLORS[color] || '#eab308' } },
      anchor: { show: true, size: 14, itemStyle: { borderWidth: 3, borderColor: SCORE_COLORS[color] || '#eab308' } },
      title: { show: false },
      detail: { show: false },
      data: [{ value: score }],
    }],
  });
}

function getIndicatorStatus(key, value) {
  if (value == null) return { text: 'N/A', cls: 'status-neutral' };
  const cfg = INDICATOR_CONFIG[key];
  if (!cfg) return { text: '', cls: 'status-neutral' };
  const t = cfg.thresholds;

  if (key === 'vix') {
    if (value >= 40) return { text: '極度の恐怖', cls: 'status-danger' };
    if (value >= 30) return { text: '警戒', cls: 'status-warning' };
    if (value >= 20) return { text: '通常', cls: 'status-neutral' };
    return { text: '安定', cls: 'status-safe' };
  }
  if (key === 'fear_greed') {
    if (value <= 25) return { text: '極度の恐怖', cls: 'status-danger' };
    if (value <= 40) return { text: '恐怖', cls: 'status-warning' };
    if (value <= 60) return { text: '中立', cls: 'status-neutral' };
    return { text: '強欲', cls: 'status-hot' };
  }
  if (key === 'rsi') {
    if (value < 30) return { text: '売られすぎ', cls: 'status-danger' };
    if (value < 40) return { text: '弱い', cls: 'status-warning' };
    if (value < 60) return { text: '中立', cls: 'status-neutral' };
    if (value < 70) return { text: '強い', cls: 'status-safe' };
    return { text: '買われすぎ', cls: 'status-hot' };
  }
  if (key === 'credit_spread') {
    if (value >= 500) return { text: '危険', cls: 'status-danger' };
    if (value >= 400) return { text: '警戒', cls: 'status-warning' };
    if (value >= 300) return { text: '注意', cls: 'status-neutral' };
    return { text: '安定', cls: 'status-safe' };
  }
  if (key === 'ma_deviation') {
    if (value <= -10) return { text: '大幅下方乖離', cls: 'status-danger' };
    if (value <= -5) return { text: '下方乖離', cls: 'status-warning' };
    if (value <= 5) return { text: '適正', cls: 'status-neutral' };
    return { text: '上方乖離', cls: 'status-hot' };
  }
  if (key === 'yield_curve') {
    if (value < 0) return { text: '逆イールド', cls: 'status-danger' };
    if (value < 0.5) return { text: 'フラット', cls: 'status-warning' };
    return { text: '順イールド', cls: 'status-safe' };
  }
  return { text: '', cls: 'status-neutral' };
}

function renderIndicators(indicators) {
  const grid = document.getElementById('indicatorGrid');
  if (!grid) return;
  grid.innerHTML = '';

  for (const [key, cfg] of Object.entries(INDICATOR_CONFIG)) {
    const data = indicators[key] || {};
    const value = data.value;
    const status = getIndicatorStatus(key, value);
    const displayVal = value != null ? (typeof value === 'number' ? value.toFixed(1) : value) : '--';
    const sub = data.source ? `Source: ${data.source}` : (data.error ? data.error.substring(0, 30) : '');

    const card = document.createElement('div');
    card.className = 'indicator-card';
    card.innerHTML = `
      <div class="indicator-name">${cfg.name}</div>
      <div class="indicator-value">${displayVal}${cfg.unit ? '<small style="font-size:0.5em;color:#64748b;margin-left:2px">' + cfg.unit + '</small>' : ''}</div>
      <span class="indicator-status ${status.cls}">${status.text}</span>
      <div class="indicator-sub">${sub}</div>
    `;
    grid.appendChild(card);
  }
}

function renderSignals(bottomSignals) {
  const section = document.getElementById('signalSection');
  const conditions = document.getElementById('signalConditions');
  const count = document.getElementById('signalCount');
  const title = document.getElementById('signalTitle');
  if (!section || !conditions) return;

  count.textContent = `${bottomSignals.met_count}/${bottomSignals.total_conditions}`;
  title.textContent = bottomSignals.alert_level;

  if (bottomSignals.met_count > 0) {
    section.style.display = 'block';
  } else {
    section.style.display = 'none';
    return;
  }

  conditions.innerHTML = '';
  for (const [, cond] of Object.entries(bottomSignals.conditions)) {
    const item = document.createElement('div');
    item.className = 'condition-item';
    const icon = cond.met ? '🔴' : '⚪';
    const val = cond.value != null ? (typeof cond.value === 'number' ? cond.value.toFixed(1) : cond.value) : '--';
    item.innerHTML = `
      <span class="condition-icon">${icon}</span>
      <span>${cond.label}</span>
      <span class="condition-value">${val}</span>
    `;
    conditions.appendChild(item);
  }
}

function renderSectors(data) {
  const grid = document.getElementById('sectorGrid');
  if (!grid || !data.sectors) return;
  grid.innerHTML = '';

  for (const [name, info] of Object.entries(data.sectors)) {
    if (info.error) continue;
    const change = info.change_1d;
    const card = document.createElement('div');
    const cls = change >= 0 ? 'sector-positive' : 'sector-negative';
    const color = change >= 0 ? 'color-green' : 'color-red';
    card.className = `sector-card ${cls}`;
    card.innerHTML = `
      <div class="sector-name">${name}</div>
      <div class="sector-change ${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</div>
      <div class="sector-ticker">${info.ticker} $${info.price}</div>
    `;
    grid.appendChild(card);
  }
}

function renderWatchlist(data) {
  const grid = document.getElementById('watchlistGrid');
  if (!grid) return;
  grid.innerHTML = '';

  for (const [ticker, info] of Object.entries(data)) {
    if (info.error) continue;
    const dd = info.drawdown_pct;
    const ddCls = dd <= -30 ? 'drawdown-deep' : dd <= -15 ? 'drawdown-moderate' : 'drawdown-mild';
    const card = document.createElement('div');
    card.className = 'watchlist-card';
    card.innerHTML = `
      <div class="watchlist-left">
        <div class="wl-ticker">${ticker}</div>
        <div class="wl-label">${info.label}</div>
      </div>
      <div class="watchlist-right">
        <div class="wl-price">$${info.price}</div>
        <div class="wl-drawdown ${ddCls}">${dd.toFixed(1)}% from high</div>
      </div>
    `;
    grid.appendChild(card);
  }
}

function renderGeo(data) {
  const grid = document.getElementById('geoGrid');
  if (!grid) return;
  grid.innerHTML = '';

  for (const [key, name] of Object.entries(GEO_NAMES)) {
    const info = data[key];
    if (!info || info.error) continue;
    const change = info.change_pct;
    const color = change >= 0 ? 'color-green' : 'color-red';
    const prefix = key === 'usdjpy' ? '¥' : '$';
    const card = document.createElement('div');
    card.className = 'geo-card';
    card.innerHTML = `
      <div class="geo-name">${name}</div>
      <div class="geo-value">${prefix}${info.value.toFixed(2)}</div>
      <div class="geo-change ${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</div>
    `;
    grid.appendChild(card);
  }
}

// ============================================================
// Investment Advisor Panel
// ============================================================

const SIGNAL_STYLES = {
  STRONG_BUY: { bg: '#991b1b', border: '#ef4444', text: '強い買い', icon: '🔥' },
  BUY:        { bg: '#92400e', border: '#f59e0b', text: '買い',     icon: '📈' },
  CONSIDER:   { bg: '#1e3a5f', border: '#3b82f6', text: '検討',     icon: '🔍' },
  WATCH:      { bg: '#1a2332', border: '#475569', text: '監視',     icon: '👁' },
  WAIT:       { bg: '#1a1a2e', border: '#334155', text: '待機',     icon: '⏳' },
  UNKNOWN:    { bg: '#1a1a2e', border: '#334155', text: '不明',     icon: '❓' },
};

function renderAdvice(advice) {
  const section = document.getElementById('adviceSection');
  if (!section || !advice) return;
  section.style.display = 'block';

  // ヘッドライン
  const headlineEl = document.getElementById('adviceHeadlineText');
  const summaryEl = document.getElementById('adviceSummary');
  const bottomNoteEl = document.getElementById('adviceBottomNote');
  const headlineCard = document.getElementById('adviceHeadline');

  headlineEl.textContent = advice.headline;
  summaryEl.textContent = advice.summary;

  // ヘッドラインの色（urgencyに応じて）
  const topSector = Object.values(advice.sectors).sort((a, b) => {
    const ord = { high: 0, medium: 1, low: 2, none: 3 };
    return (ord[a.urgency] || 3) - (ord[b.urgency] || 3);
  })[0];
  const topStyle = SIGNAL_STYLES[topSector?.signal] || SIGNAL_STYLES.WAIT;
  headlineCard.style.borderColor = topStyle.border;
  headlineCard.style.background = `linear-gradient(135deg, ${topStyle.bg}, #0f172a)`;

  if (advice.bottom_note) {
    bottomNoteEl.style.display = 'block';
    bottomNoteEl.textContent = advice.bottom_note;
  } else {
    bottomNoteEl.style.display = 'none';
  }

  // セクター別カード
  const sectorsEl = document.getElementById('adviceSectors');
  sectorsEl.innerHTML = '';

  for (const [key, sector] of Object.entries(advice.sectors)) {
    const style = SIGNAL_STYLES[sector.signal] || SIGNAL_STYLES.UNKNOWN;
    const card = document.createElement('div');
    card.className = 'advice-sector-card';
    card.style.borderColor = style.border;

    let targetsHtml = '';
    if (sector.buy_targets) {
      targetsHtml = '<div class="advice-targets-list">';
      for (const [label, val] of Object.entries(sector.buy_targets)) {
        const isCurrent = label === 'current';
        targetsHtml += `<div class="target-row ${isCurrent ? 'target-current' : ''}">
          <span class="target-label">${isCurrent ? '現在' : label}</span>
          <span class="target-value">${val}</span>
        </div>`;
      }
      targetsHtml += '</div>';
    }

    // SOXL追加情報（半導体セクター）
    let soxlHtml = '';
    if (sector.soxl) {
      const soxlStyle = SIGNAL_STYLES[sector.soxl.signal] || SIGNAL_STYLES.WATCH;
      soxlHtml = `<div class="soxl-box" style="border-color:${soxlStyle.border}">
        <span class="soxl-signal">${soxlStyle.icon} SOXL: ${sector.soxl.action}</span>
      </div>`;
    }

    card.innerHTML = `
      <div class="advice-sector-header">
        <span class="advice-sector-name">${style.icon} ${sector.sector}</span>
        <span class="advice-signal-badge" style="background:${style.border}">${style.text}</span>
      </div>
      <div class="advice-action">${sector.action}</div>
      <div class="advice-reason">${sector.reason}</div>
      ${soxlHtml}
      ${targetsHtml}
    `;
    sectorsEl.appendChild(card);
  }

  // 為替
  const forexEl = document.getElementById('adviceForex');
  if (advice.forex && advice.forex.usdjpy) {
    forexEl.style.display = 'block';
    const fx = advice.forex;
    forexEl.innerHTML = `
      <div class="forex-card">
        <span class="forex-label">USD/JPY ¥${fx.usdjpy.toFixed(1)}</span>
        <span class="forex-risk forex-risk-${fx.risk_level.toLowerCase()}">${fx.risk_level}</span>
        <span class="forex-note">${fx.note}</span>
        <span class="forex-opp">${fx.opportunity}</span>
      </div>
    `;
  }
}

// ============================================================
// Main refresh
// ============================================================

async function refreshData() {
  const btn = document.querySelector('.btn-refresh');
  if (btn) { btn.disabled = true; btn.textContent = '更新中...'; }

  try {
    const [scoreData, sectorData, geoData, watchData, adviceData] = await Promise.all([
      fetchJSON('/api/score'),
      fetchJSON('/api/sectors'),
      fetchJSON('/api/geopolitical'),
      fetchJSON('/api/watchlist'),
      fetchJSON('/api/advice').catch(() => null),
    ]);

    const cs = scoreData.crash_score;
    document.getElementById('scoreNumber').textContent = cs.score.toFixed(1);
    document.getElementById('scoreLabel').textContent = cs.label;
    document.getElementById('scoreLabel').className = `score-label color-${cs.color}`;
    document.getElementById('scoreAction').textContent = cs.action;
    document.getElementById('updateTime').textContent = new Date(scoreData.timestamp).toLocaleString('ja-JP');

    updateGauge(cs.score, cs.color);
    renderIndicators(scoreData.indicators);
    renderSignals(cs.bottom_signals);
    renderSectors(sectorData);
    renderWatchlist(watchData);
    renderGeo(geoData);

    // Investment Advisor
    if (adviceData && adviceData.advice) {
      renderAdvice(adviceData.advice);
    }
  } catch (e) {
    console.error('Data fetch error:', e);
    document.getElementById('updateTime').textContent = 'エラー: ' + e.message;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '更新'; }
  }
}

window.addEventListener('DOMContentLoaded', () => {
  initGauge();
  refreshData();
});

window.addEventListener('resize', () => {
  if (gaugeChart) gaugeChart.resize();
});
