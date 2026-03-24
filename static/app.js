/**
 * Crash Detector - Dashboard App
 */

// 同じサーバーなので相対パス
const API_BASE = '';

// ============================================================
// Data Fetching
// ============================================================

async function fetchJSON(endpoint) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error(`Fetch error: ${endpoint}`, err);
    return null;
  }
}

// ============================================================
// Gauge Chart (ECharts)
// ============================================================

let gaugeChart = null;

function initGauge() {
  const el = document.getElementById('gaugeChart');
  if (!el) return;
  gaugeChart = echarts.init(el);
  renderGauge(50, '読み込み中', '#64748b');
}

function renderGauge(score, label, color) {
  if (!gaugeChart) return;

  const colorMap = {
    red: '#ef4444',
    orange: '#f97316',
    yellow: '#eab308',
    green: '#22c55e',
    purple: '#a855f7',
  };
  const c = colorMap[color] || color || '#64748b';

  gaugeChart.setOption({
    series: [{
      type: 'gauge',
      startAngle: 200,
      endAngle: -20,
      min: 0,
      max: 100,
      splitNumber: 5,
      radius: '95%',
      center: ['50%', '55%'],
      axisLine: {
        lineStyle: {
          width: 20,
          color: [
            [0.2, '#ef4444'],
            [0.4, '#f97316'],
            [0.6, '#eab308'],
            [0.8, '#22c55e'],
            [1, '#a855f7'],
          ],
        },
      },
      pointer: {
        icon: 'path://M2090.36389,615.30999L2## 90.36389,615.30999',
        length: '65%',
        width: 6,
        itemStyle: { color: '#e2e8f0' },
      },
      axisTick: { show: false },
      splitLine: {
        length: 12,
        lineStyle: { width: 2, color: '#2d3748' },
      },
      axisLabel: {
        distance: 28,
        color: '#64748b',
        fontSize: 11,
      },
      title: {
        show: true,
        offsetCenter: [0, '75%'],
        fontSize: 13,
        color: '#94a3b8',
      },
      detail: {
        fontSize: 36,
        fontWeight: 900,
        offsetCenter: [0, '40%'],
        valueAnimation: true,
        color: c,
      },
      data: [{ value: score, name: label }],
    }],
  });
}

// ============================================================
// Render Indicators
// ============================================================

function getIndicatorStatus(key, value) {
  if (value === null || value === undefined) return { label: 'N/A', class: 'status-neutral' };

  const rules = {
    vix: [
      [50, '極度の危機', 'status-danger'],
      [40, 'パニック', 'status-danger'],
      [30, '高不安', 'status-warning'],
      [20, '懸念', 'status-neutral'],
      [0, '平穏', 'status-safe'],
    ],
    fear_greed: [
      [0, '極度の恐怖', 'status-danger', 25],
      [0, '恐怖', 'status-warning', 45],
      [0, '中立', 'status-neutral', 55],
      [0, '強欲', 'status-safe', 75],
      [0, '極度の強欲', 'status-hot', 101],
    ],
    rsi: [
      [0, '極度の売られすぎ', 'status-danger', 20],
      [0, '売られすぎ', 'status-danger', 30],
      [0, 'やや弱気', 'status-warning', 50],
      [0, '中立〜強気', 'status-safe', 70],
      [0, '買われすぎ', 'status-hot', 101],
    ],
    credit_spread: [
      [1000, '危機', 'status-danger'],
      [500, '警戒', 'status-warning'],
      [300, '通常', 'status-neutral'],
      [0, 'タイト', 'status-safe'],
    ],
    ma_deviation: [
      [-20, '大暴落', 'status-danger'],
      [-10, '暴落', 'status-danger'],
      [-5, '調整', 'status-warning'],
      [5, '通常', 'status-neutral'],
      [999, '過熱', 'status-hot'],
    ],
    yield_curve: [
      [-0.5, '深い逆転', 'status-danger'],
      [0, '逆転', 'status-warning'],
      [0.5, '通常', 'status-neutral'],
      [999, '急勾配', 'status-safe'],
    ],
  };

  // VIX / credit_spread: 降順チェック
  if (key === 'vix' || key === 'credit_spread') {
    const r = rules[key];
    for (const [threshold, label, cls] of r) {
      if (value >= threshold) return { label, class: cls };
    }
    return { label: '平穏', class: 'status-safe' };
  }

  // 昇順チェック
  if (rules[key]) {
    const r = rules[key];
    if (key === 'ma_deviation' || key === 'yield_curve') {
      for (const [threshold, label, cls] of r) {
        if (value <= threshold) return { label, class: cls };
      }
    } else {
      for (const [, label, cls, upper] of r) {
        if (value < upper) return { label, class: cls };
      }
    }
  }

  return { label: '--', class: 'status-neutral' };
}

function renderIndicators(indicators) {
  const grid = document.getElementById('indicatorGrid');
  if (!grid) return;

  const items = [
    { key: 'vix', name: 'VIX', unit: '' },
    { key: 'fear_greed', name: 'Fear & Greed', unit: '' },
    { key: 'rsi', name: 'RSI (SPY)', unit: '' },
    { key: 'credit_spread', name: 'HYスプレッド', unit: 'bps' },
    { key: 'ma_deviation', name: 'MA200乖離', unit: '%' },
    { key: 'yield_curve', name: 'YC (10Y-2Y)', unit: '%' },
  ];

  grid.innerHTML = items.map(item => {
    const data = indicators[item.key] || {};
    const value = data.value;
    const status = getIndicatorStatus(item.key, value);
    const displayValue = value !== null && value !== undefined
      ? `${value}${item.unit}`
      : '--';

    return `
      <div class="indicator-card">
        <div class="indicator-name">${item.name}</div>
        <div class="indicator-value">${displayValue}</div>
        <span class="indicator-status ${status.class}">${status.label}</span>
        ${data.source ? `<div class="indicator-sub">${data.source}</div>` : ''}
      </div>
    `;
  }).join('');
}

// ============================================================
// Render Bottom Signals
// ============================================================

function renderSignals(bottomSignals) {
  const section = document.getElementById('signalSection');
  if (!section || !bottomSignals) return;

  const { conditions, met_count, total_conditions, alert, alert_level } = bottomSignals;

  if (met_count > 0) {
    section.style.display = 'block';
  } else {
    section.style.display = 'none';
    return;
  }

  document.getElementById('signalTitle').textContent = alert_level;
  document.getElementById('signalCount').textContent = `${met_count}/${total_conditions}`;

  const container = document.getElementById('signalConditions');
  container.innerHTML = Object.entries(conditions).map(([, cond]) => {
    const icon = cond.met ? '✅' : '❌';
    const valueStr = cond.value !== null ? cond.value : 'N/A';
    return `
      <div class="condition-item">
        <span class="condition-icon">${icon}</span>
        <span>${cond.label}</span>
        <span class="condition-value">${valueStr}</span>
      </div>
    `;
  }).join('');
}

// ============================================================
// Render Sectors
// ============================================================

function renderSectors(data) {
  const grid = document.getElementById('sectorGrid');
  if (!grid || !data || !data.sectors) return;

  const sectorNames = {
    Energy: 'エネルギー', Utilities: '公益', Technology: 'テック',
    Healthcare: 'ヘルスケア', Financials: '金融', RealEstate: '不動産',
    ConsumerDisc: '一般消費', Materials: '素材', Communication: '通信',
    Industrials: '資本財', ConsumerStap: '生活必需',
  };

  grid.innerHTML = Object.entries(data.sectors).map(([key, s]) => {
    if (s.error) return '';
    const change = s.change_1d;
    const cls = change >= 0 ? 'sector-positive' : 'sector-negative';
    const color = change >= 0 ? 'color-green' : 'color-red';
    const sign = change >= 0 ? '+' : '';
    return `
      <div class="sector-card ${cls}">
        <div class="sector-name">${sectorNames[key] || key}</div>
        <div class="sector-change ${color}">${sign}${change}%</div>
        <div class="sector-ticker">${s.ticker} $${s.price}</div>
      </div>
    `;
  }).join('');
}

// ============================================================
// Render Watchlist
// ============================================================

function renderWatchlist(data) {
  const grid = document.getElementById('watchlistGrid');
  if (!grid || !data) return;

  grid.innerHTML = Object.entries(data).map(([ticker, item]) => {
    if (item.error || ticker === 'source') return '';
    const dd = item.drawdown_pct || 0;
    const ddClass = dd <= -50 ? 'drawdown-deep'
      : dd <= -20 ? 'drawdown-moderate'
      : 'drawdown-mild';

    return `
      <div class="watchlist-card">
        <div class="watchlist-left">
          <div class="wl-ticker">${ticker}</div>
          <div class="wl-label">${item.label}</div>
        </div>
        <div class="watchlist-right">
          <div class="wl-price">$${item.price}</div>
          <div class="wl-drawdown ${ddClass}">${dd}% (52w高値比)</div>
          <div class="indicator-sub">52w高値: $${item.high_52w}</div>
        </div>
      </div>
    `;
  }).join('');
}

// ============================================================
// Render Geopolitical
// ============================================================

function renderGeo(data) {
  const grid = document.getElementById('geoGrid');
  if (!grid || !data) return;

  const names = { wti: 'WTI原油', gold: '金', usdjpy: 'USD/JPY' };
  const units = { wti: '$', gold: '$', usdjpy: '¥' };

  grid.innerHTML = Object.entries(names).map(([key, name]) => {
    const item = data[key];
    if (!item || item.error) return `
      <div class="geo-card">
        <div class="geo-name">${name}</div>
        <div class="geo-value">--</div>
      </div>
    `;

    const change = item.change_pct || 0;
    const color = change >= 0 ? 'color-green' : 'color-red';
    const sign = change >= 0 ? '+' : '';

    return `
      <div class="geo-card">
        <div class="geo-name">${name}</div>
        <div class="geo-value">${units[key]}${item.value}</div>
        <div class="geo-change ${color}">${sign}${change}%</div>
      </div>
    `;
  }).join('');
}

// ============================================================
// Main
// ============================================================

async function refreshData() {
  const btn = document.querySelector('.btn-refresh');
  if (btn) { btn.disabled = true; btn.textContent = '更新中...'; }

  try {
    // 並列取得
    const [scoreData, sectorData, geoData, watchData] = await Promise.all([
      fetchJSON('/api/score'),
      fetchJSON('/api/sectors'),
      fetchJSON('/api/geopolitical'),
      fetchJSON('/api/watchlist'),
    ]);

    if (scoreData) {
      const cs = scoreData.crash_score;
      renderGauge(cs.score, cs.label, cs.color);
      document.getElementById('scoreNumber').textContent = cs.score;
      document.getElementById('scoreNumber').className = `score-number color-${cs.color}`;
      document.getElementById('scoreLabel').textContent = cs.label;
      document.getElementById('scoreAction').textContent = cs.action;
      renderIndicators(scoreData.indicators);
      renderSignals(cs.bottom_signals);
    }

    if (sectorData) renderSectors(sectorData);
    if (geoData) renderGeo(geoData);
    if (watchData) renderWatchlist(watchData);

    document.getElementById('updateTime').textContent =
      `最終更新: ${new Date().toLocaleString('ja-JP')}`;

  } catch (err) {
    console.error('Refresh error:', err);
  }

  if (btn) { btn.disabled = false; btn.textContent = '更新'; }
}

// デモモード（API未接続時）
async function loadDemoData() {
  const demoScore = {
    crash_score: {
      score: 35,
      label: '恐怖',
      color: 'orange',
      action: '注視 - 底打ちシグナルを監視',
      bottom_signals: {
        conditions: {
          vix_gt_40: { label: 'VIX > 40', met: false, value: 32.5 },
          fg_lt_25: { label: 'Fear&Greed < 25', met: true, value: 18 },
          rsi_lt_30: { label: 'RSI < 30', met: true, value: 27.3 },
          aaii_gt_50: { label: 'AAII弱気 > 50%', met: false, value: null },
          pcr_gt_1_2: { label: 'PCR > 1.2', met: false, value: null },
          ma_lt_neg10: { label: 'MA乖離 < -10%', met: true, value: -12.5 },
          cs_gt_500: { label: 'HYスプレッド > 500bps', met: false, value: 420 },
        },
        met_count: 3,
        total_conditions: 7,
        alert: true,
        alert_level: '底打ちシグナル',
        selling_climax: false,
      },
    },
    indicators: {
      vix: { value: 32.5, source: 'demo' },
      fear_greed: { value: 18, rating: 'Extreme Fear', source: 'demo' },
      rsi: { value: 27.3, source: 'demo' },
      credit_spread: { value: 420, source: 'demo' },
      ma_deviation: { value: -12.5, source: 'demo' },
      yield_curve: { value: -0.22, source: 'demo' },
    },
  };

  const cs = demoScore.crash_score;
  renderGauge(cs.score, cs.label, cs.color);
  document.getElementById('scoreNumber').textContent = cs.score;
  document.getElementById('scoreNumber').className = `score-number color-${cs.color}`;
  document.getElementById('scoreLabel').textContent = cs.label;
  document.getElementById('scoreAction').textContent = cs.action;
  renderIndicators(demoScore.indicators);
  renderSignals(cs.bottom_signals);

  // Demo sectors
  renderSectors({
    sectors: {
      Energy: { ticker: 'XLE', price: 92.50, change_1d: 3.2, change_1w: 5.1, change_1m: 8.4 },
      Utilities: { ticker: 'XLU', price: 71.20, change_1d: 1.8, change_1w: 2.1, change_1m: 3.5 },
      Technology: { ticker: 'XLK', price: 185.30, change_1d: -4.5, change_1w: -8.2, change_1m: -15.3 },
      Healthcare: { ticker: 'XLV', price: 140.80, change_1d: 0.3, change_1w: -1.2, change_1m: -2.8 },
      Financials: { ticker: 'XLF', price: 38.90, change_1d: -2.1, change_1w: -4.5, change_1m: -7.2 },
      Communication: { ticker: 'XLC', price: 78.40, change_1d: -3.8, change_1w: -6.9, change_1m: -12.1 },
    },
  });

  // Demo watchlist
  renderWatchlist({
    SOXL: { label: '半導体3倍レバ', price: 18.50, high_52w: 72.30, drawdown_pct: -74.4 },
    NVDA: { label: 'NVIDIA', price: 85.20, high_52w: 152.80, drawdown_pct: -44.2 },
    TQQQ: { label: 'ナスダック3倍レバ', price: 32.10, high_52w: 88.40, drawdown_pct: -63.7 },
    XLE: { label: 'エネルギーETF', price: 92.50, high_52w: 98.20, drawdown_pct: -5.8 },
  });

  // Demo geo
  renderGeo({
    wti: { value: 92.30, change_pct: 2.1 },
    gold: { value: 2180, change_pct: 0.8 },
    usdjpy: { value: 148.50, change_pct: -0.3 },
  });

  document.getElementById('updateTime').textContent = 'デモデータ表示中（API未接続）';
}

// Init
window.addEventListener('DOMContentLoaded', () => {
  initGauge();
  // まずAPI接続を試す。失敗したらデモモード
  refreshData().then(() => {
    const score = document.getElementById('scoreNumber').textContent;
    if (score === '--') loadDemoData();
  });
});

// リサイズ対応
window.addEventListener('resize', () => {
  if (gaugeChart) gaugeChart.resize();
});
