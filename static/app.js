/* 投資ナビ - Frontend App */

const API_BASE = location.origin;

const INDICATOR_CONFIG = {
  vix: { name: '恐怖指数（VIX）', unit: '', desc: '高いほど市場が怖がっている' },
  fear_greed: { name: '市場心理', unit: '', desc: '低いほど悲観的（0-100）' },
  rsi: { name: '売られすぎ度', unit: '', desc: '30以下は売られすぎ' },
  credit_spread: { name: '信用リスク', unit: 'bps', desc: '高いほど企業の倒産リスク上昇' },
  ma_deviation: { name: '平均からの乖離', unit: '%', desc: 'マイナスが大きいほど割安' },
  yield_curve: { name: '景気見通し', unit: '', desc: 'マイナスは景気後退サイン' },
};

const SIGNAL_STYLES = {
  STRONG_BUY: { color: '#ef4444', bg: 'rgba(239,68,68,0.15)', text: '今すぐ注文', icon: '🔴' },
  BUY:        { color: '#f59e0b', bg: 'rgba(245,158,11,0.15)', text: '今週中に注文',  icon: '🟡' },
  CONSIDER:   { color: '#3b82f6', bg: 'rgba(59,130,246,0.15)', text: 'まだ買わない',  icon: '🔵' },
  WATCH:      { color: '#64748b', bg: 'rgba(100,116,139,0.10)', text: 'まだ買わない', icon: '⚪' },
  WAIT:       { color: '#475569', bg: 'rgba(71,85,105,0.10)',  text: 'まだ買わない',  icon: '⚪' },
  UNKNOWN:    { color: '#475569', bg: 'rgba(71,85,105,0.10)',  text: '判定できず',    icon: '❓' },
};

const GEO_NAMES = { wti: '原油', gold: '金', usdjpy: 'ドル/円' };

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
  const colors = { red: '#ef4444', orange: '#f97316', yellow: '#eab308', green: '#22c55e', purple: '#a855f7' };
  gaugeChart.setOption({
    series: [{
      type: 'gauge', min: 0, max: 100, splitNumber: 5,
      progress: { show: true, width: 14, roundCap: true },
      axisLine: { lineStyle: { width: 14, color: [[0.2,'#ef4444'],[0.4,'#f97316'],[0.6,'#eab308'],[0.8,'#22c55e'],[1,'#a855f7']] } },
      axisTick: { show: false },
      splitLine: { length: 8, lineStyle: { width: 2, color: '#334155' } },
      axisLabel: { distance: 20, color: '#64748b', fontSize: 10 },
      pointer: { length: '55%', width: 4, itemStyle: { color: colors[color] || '#eab308' } },
      anchor: { show: true, size: 10, itemStyle: { borderWidth: 2, borderColor: colors[color] || '#eab308' } },
      title: { show: false }, detail: { show: false },
      data: [{ value: score }],
    }],
  });
}

// ============================================================
// 今日の判断パネル
// ============================================================
function renderToday(advice) {
  if (!advice) return;

  const headline = document.getElementById('todayHeadline');
  const summary = document.getElementById('todaySummary');
  const bottomNote = document.getElementById('todayBottomNote');
  const card = document.getElementById('todayCard');

  // ヘッドラインを初心者向けに
  headline.textContent = advice.headline;
  summary.textContent = advice.summary;

  // 緊急度で色を変える
  const sectors = Object.values(advice.sectors);
  const urgencyOrder = { high: 0, medium: 1, low: 2, none: 3 };
  sectors.sort((a, b) => (urgencyOrder[a.urgency] || 3) - (urgencyOrder[b.urgency] || 3));
  const top = sectors[0];
  const style = SIGNAL_STYLES[top?.signal] || SIGNAL_STYLES.WAIT;
  card.style.borderColor = style.color;
  card.style.background = `linear-gradient(135deg, ${style.bg}, var(--bg-card))`;

  if (advice.bottom_note) {
    bottomNote.style.display = 'block';
    bottomNote.textContent = advice.bottom_note;
  }
}

// ============================================================
// セクター別アドバイス
// ============================================================
function renderAdviceSectors(advice) {
  const section = document.getElementById('adviceSection');
  const container = document.getElementById('adviceSectors');
  if (!section || !advice) return;
  section.style.display = 'block';
  container.innerHTML = '';

  const sectorNames = {
    energy: 'エネルギー（石油・ガス）',
    semiconductor: '半導体（NVIDIA・AI）',
    broad_market: '市場全体（S&P500）',
    gold: 'ゴールド（金）',
  };

  for (const [key, sector] of Object.entries(advice.sectors)) {
    const style = SIGNAL_STYLES[sector.signal] || SIGNAL_STYLES.UNKNOWN;
    const card = document.createElement('div');
    card.className = 'sector-advice-card';
    card.style.borderLeftColor = style.color;

    // 約定ラグ情報
    let lagHtml = '';
    if (sector.signal === 'BUY' || sector.signal === 'STRONG_BUY' || sector.signal === 'CONSIDER') {
      const lagInfo = getLagInfo(key);
      if (lagInfo) {
        lagHtml = `<div class="lag-info">注文から約${lagInfo.days}営業日で購入完了</div>`;
      }
    }

    // SOXLの追加情報
    let soxlHtml = '';
    if (sector.soxl) {
      const sStyle = SIGNAL_STYLES[sector.soxl.signal] || SIGNAL_STYLES.WATCH;
      soxlHtml = `<div class="soxl-note" style="border-color:${sStyle.color}">${sStyle.icon} ${sector.soxl.action}</div>`;
    }

    card.innerHTML = `
      <div class="sa-header">
        <span class="sa-name">${sectorNames[key] || sector.sector}</span>
        <span class="sa-badge" style="background:${style.color}">${style.text}</span>
      </div>
      <div class="sa-action">${sector.action}</div>
      <div class="sa-reason">${sector.reason}</div>
      ${soxlHtml}
      ${lagHtml}
    `;
    container.appendChild(card);
  }

  // 為替
  const forexEl = document.getElementById('adviceForex');
  if (advice.forex && advice.forex.usdjpy) {
    forexEl.style.display = 'block';
    const fx = advice.forex;
    const riskColors = { HIGH: '#ef4444', MEDIUM: '#f59e0b', LOW: '#22c55e', FAVORABLE: '#06b6d4' };
    const riskLabels = { HIGH: '注意', MEDIUM: 'やや注意', LOW: '問題なし', FAVORABLE: '有利' };
    forexEl.innerHTML = `
      <div class="forex-simple">
        <span>ドル円 ¥${fx.usdjpy.toFixed(0)}</span>
        <span class="forex-badge" style="background:${riskColors[fx.risk_level]}">${riskLabels[fx.risk_level]}</span>
        <span class="forex-note-text">${fx.opportunity}</span>
      </div>
    `;
  }
}

function getLagInfo(sectorKey) {
  const map = {
    energy: { days: 1, note: '海外ETF（XLE）は翌営業日に約定' },
    semiconductor: { days: 1, note: '米国株（NVIDIA）は翌営業日に約定' },
    broad_market: { days: 2, note: '投資信託（eMAXIS Slim）は2営業日後に約定' },
    gold: { days: 2, note: 'ゴールドETF（425A）は2営業日後に約定' },
  };
  return map[sectorKey];
}

// ============================================================
// 売りシグナルパネル
// ============================================================

const SELL_STYLES = {
  SELL_STRONG: { color: '#ef4444', bg: 'rgba(239,68,68,0.15)', text: '利確を強く推奨', border: '#ef4444' },
  SELL_PARTIAL: { color: '#f59e0b', bg: 'rgba(245,158,11,0.15)', text: '一部利確を検討', border: '#f59e0b' },
  WATCH:       { color: '#3b82f6', bg: 'rgba(59,130,246,0.10)', text: '利確の準備', border: '#3b82f6' },
  HOLD:        { color: '#22c55e', bg: 'rgba(34,197,94,0.08)', text: '保有継続', border: '#22c55e' },
};

function renderSellSignals(sellData) {
  const section = document.getElementById('sellSection');
  if (!section || !sellData) return;
  section.style.display = 'block';

  const style = SELL_STYLES[sellData.sell_level] || SELL_STYLES.HOLD;

  const card = document.getElementById('sellCard');
  card.style.borderColor = style.border;
  card.style.background = `linear-gradient(135deg, ${style.bg}, var(--bg-card))`;

  document.getElementById('sellBadge').textContent = style.text;
  document.getElementById('sellBadge').style.background = style.color;
  document.getElementById('sellHeadline').textContent = sellData.headline;
  document.getElementById('sellAction').textContent = sellData.action;

  // 条件リスト
  const list = document.getElementById('sellConditions');
  list.innerHTML = '';
  for (const sig of sellData.signals) {
    const icon = sig.met ? (sig.severity === 'high' ? '🔴' : '🟡') : '⚪';
    const item = document.createElement('div');
    item.className = 'sell-condition-item';
    item.innerHTML = `<span>${icon} ${sig.condition}</span><span class="sell-detail">${sig.detail}</span>`;
    list.appendChild(item);
  }

  // カウント
  document.getElementById('sellCount').textContent = `${sellData.met_count}/${sellData.total_conditions}`;

  // ゴールド個別売りシグナル
  const goldSell = document.getElementById('goldSellNote');
  if (sellData.gold_sell && goldSell) {
    goldSell.style.display = 'block';
    const gs = sellData.gold_sell;
    goldSell.innerHTML = `<span class="sa-badge" style="background:${gs.signal === 'SELL_PARTIAL' ? '#f59e0b' : '#3b82f6'}">${gs.signal === 'SELL_PARTIAL' ? '利確' : '準備'}</span> ${gs.action}`;
  } else if (goldSell) {
    goldSell.style.display = 'none';
  }
}

// ============================================================
// 既存パネル（指標・セクター・監視銘柄・地政学）
// ============================================================
function getIndicatorStatus(key, value) {
  if (value == null) return { text: '--', cls: 'status-neutral' };
  if (key === 'vix') {
    if (value >= 40) return { text: 'かなり怖い', cls: 'status-danger' };
    if (value >= 30) return { text: '不安', cls: 'status-warning' };
    if (value >= 20) return { text: 'ふつう', cls: 'status-neutral' };
    return { text: '安心', cls: 'status-safe' };
  }
  if (key === 'fear_greed') {
    if (value <= 25) return { text: 'みんな怖がっている', cls: 'status-danger' };
    if (value <= 40) return { text: '不安気味', cls: 'status-warning' };
    if (value <= 60) return { text: 'ふつう', cls: 'status-neutral' };
    return { text: '楽観的', cls: 'status-hot' };
  }
  if (key === 'rsi') {
    if (value < 30) return { text: '売られすぎ', cls: 'status-danger' };
    if (value < 40) return { text: 'やや弱い', cls: 'status-warning' };
    if (value < 60) return { text: 'ふつう', cls: 'status-neutral' };
    if (value < 70) return { text: '強い', cls: 'status-safe' };
    return { text: '買われすぎ', cls: 'status-hot' };
  }
  if (key === 'credit_spread') {
    if (value >= 500) return { text: '危険', cls: 'status-danger' };
    if (value >= 400) return { text: '注意', cls: 'status-warning' };
    if (value >= 300) return { text: 'やや注意', cls: 'status-neutral' };
    return { text: '安定', cls: 'status-safe' };
  }
  if (key === 'ma_deviation') {
    if (value <= -10) return { text: 'かなり割安', cls: 'status-danger' };
    if (value <= -5) return { text: 'やや割安', cls: 'status-warning' };
    if (value <= 5) return { text: 'ふつう', cls: 'status-neutral' };
    return { text: '割高', cls: 'status-hot' };
  }
  if (key === 'yield_curve') {
    if (value < 0) return { text: '景気後退サイン', cls: 'status-danger' };
    if (value < 0.5) return { text: '微妙', cls: 'status-warning' };
    return { text: '正常', cls: 'status-safe' };
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
    const card = document.createElement('div');
    card.className = 'indicator-card';
    card.innerHTML = `
      <div class="indicator-name">${cfg.name}</div>
      <div class="indicator-value">${displayVal}</div>
      <span class="indicator-status ${status.cls}">${status.text}</span>
      <div class="indicator-desc">${cfg.desc}</div>
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
  const labels = { 'セリングクライマックス': '大暴落の底（歴史的チャンス）', '底打ちシグナル': '底打ちの兆し', '条件未達': '底はまだ先' };
  title.textContent = labels[bottomSignals.alert_level] || bottomSignals.alert_level;

  section.style.display = 'block';
  conditions.innerHTML = '';
  for (const [, cond] of Object.entries(bottomSignals.conditions)) {
    const item = document.createElement('div');
    item.className = 'condition-item';
    const icon = cond.met ? '✅' : '⬜';
    item.innerHTML = `<span>${icon} ${cond.label}</span>`;
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
    const color = change >= 0 ? 'color-green' : 'color-red';
    const card = document.createElement('div');
    card.className = 'sector-card-mini';
    card.innerHTML = `<span>${name}</span><span class="${color}">${change >= 0 ? '+' : ''}${change.toFixed(1)}%</span>`;
    grid.appendChild(card);
  }
}

function renderWatchlist(data) {
  const grid = document.getElementById('watchlistGrid');
  if (!grid) return;
  grid.innerHTML = '';
  const labels = { SOXL: '半導体3倍', NVDA: 'NVIDIA', TQQQ: 'ナスダック3倍', XLE: 'エネルギー', GLD: 'ゴールド' };
  for (const [ticker, info] of Object.entries(data)) {
    if (info.error) continue;
    const dd = info.drawdown_pct;
    const ddColor = dd <= -30 ? '#ef4444' : dd <= -15 ? '#f59e0b' : '#64748b';
    const card = document.createElement('div');
    card.className = 'watch-card';
    card.innerHTML = `
      <div class="watch-top">
        <span class="watch-ticker">${ticker}</span>
        <span class="watch-price">$${info.price}</span>
      </div>
      <div class="watch-bottom">
        <span class="watch-label">${labels[ticker] || info.label}</span>
        <span class="watch-dd" style="color:${ddColor}">高値から${dd.toFixed(0)}%</span>
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
    card.className = 'geo-card-mini';
    card.innerHTML = `<span>${name}</span><span>${prefix}${info.value.toFixed(1)}</span><span class="${color}">${change >= 0 ? '+' : ''}${change.toFixed(1)}%</span>`;
    grid.appendChild(card);
  }
}

// ============================================================
// メイン更新
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
    document.getElementById('scoreNumber').textContent = cs.score.toFixed(0);

    const statusLabels = { '極度の恐怖': 'みんな怖がっている', '恐怖': '不安な空気', '中立': 'ふつう', '強欲': '楽観的', '極度の強欲': '浮かれすぎ' };
    document.getElementById('scoreLabel').textContent = statusLabels[cs.label] || cs.label;
    document.getElementById('scoreLabel').className = `temp-status color-${cs.color}`;

    const actionLabels = { '買い検討ゾーン': 'チャンスが近い', '注視': '注意して見守る', '通常運用': '急がなくてOK', '利確検討': '利益確定を考える', '売り検討ゾーン': '売り時かも' };
    document.getElementById('scoreAction').textContent = actionLabels[cs.action] || cs.action;

    document.getElementById('updateTime').textContent = new Date(scoreData.timestamp).toLocaleString('ja-JP');

    updateGauge(cs.score, cs.color);
    renderIndicators(scoreData.indicators);
    renderSignals(cs.bottom_signals);
    renderSectors(sectorData);
    renderWatchlist(watchData);
    renderGeo(geoData);

    if (adviceData && adviceData.advice) {
      renderToday(adviceData.advice);
      renderAdviceSectors(adviceData.advice);
      renderSellSignals(adviceData.advice.sell_signals);
      loadBudget(adviceData.advice.strategy_params);
    }
  } catch (e) {
    console.error('Data fetch error:', e);
    document.getElementById('todayHeadline').textContent = '読み込みに失敗しました。更新ボタンを押してください。';
    document.getElementById('updateTime').textContent = 'エラー';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '更新'; }
  }
}

// ============================================================
// 資金状況（APIのstrategy_paramsから取得。Claude Codeで報告→自動反映）
// ============================================================

function loadBudget(strategyParams) {
  const fmt = (n) => {
    if (n >= 10000) return `${(n / 10000).toFixed(0)}万円`;
    return `${n.toLocaleString()}円`;
  };

  if (!strategyParams) {
    document.getElementById('totalRemaining').textContent = '読み込み中...';
    return;
  }

  const tranches = strategyParams.tranches || [];
  const nisaBudget = strategyParams.nisa_growth_budget || 2400000;
  const tokuteiBudget = strategyParams.tokutei_budget || 570000;

  let nisaUsed = 0, tokuteiUsed = 0;
  const doneList = [];
  for (const t of tranches) {
    if (t.status === 'done') {
      if (t.account === 'nisa') nisaUsed += t.amount;
      if (t.account === 'tokutei') tokuteiUsed += t.amount;
      doneList.push(t);
    }
  }

  const nisaRemain = nisaBudget - nisaUsed;
  const tokuteiRemain = tokuteiBudget - tokuteiUsed;

  document.getElementById('nisaRemaining').textContent = `残り ${fmt(nisaRemain)}`;
  document.getElementById('tokuteiRemaining').textContent = `残り ${fmt(tokuteiRemain)}`;
  document.getElementById('totalRemaining').textContent = fmt(nisaRemain + tokuteiRemain);

  const nisaStatus = document.getElementById('nisaStatus');
  const tokuteiStatus = document.getElementById('tokuteiStatus');

  if (nisaUsed > 0) {
    nisaStatus.textContent = `${fmt(nisaUsed)} 投入済み`;
    nisaStatus.style.color = '#22c55e';
  } else {
    nisaStatus.textContent = '未投入';
  }

  if (tokuteiUsed > 0) {
    tokuteiStatus.textContent = `${fmt(tokuteiUsed)} 投入済み`;
    tokuteiStatus.style.color = '#22c55e';
  } else {
    tokuteiStatus.textContent = '未投入';
  }

  // 投入履歴を表示
  const historyEl = document.getElementById('investHistory');
  if (historyEl && doneList.length > 0) {
    historyEl.innerHTML = '<div class="history-title">投入履歴</div>' +
      doneList.map(t => `<div class="history-item">✅ ${t.date || ''} ${t.ticker || t.label} ${fmt(t.amount)}</div>`).join('');
    historyEl.style.display = 'block';
  }
}

window.addEventListener('DOMContentLoaded', () => { initGauge(); refreshData(); });
window.addEventListener('resize', () => { if (gaugeChart) gaugeChart.resize(); });
