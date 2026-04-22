/* 投資ナビ - Frontend App v2（2026-04-22 刷新）
 * 新API構造: action_list / portfolio / buyback / tsumitate_warning / macro_signals
 */

const API_BASE = location.origin;

const INDICATOR_CONFIG = {
  vix: { name: '恐怖指数（VIX）', desc: '高いほど市場が怖がっている' },
  fear_greed: { name: '市場心理', desc: '低いほど悲観的（0-100）' },
  rsi: { name: '売られすぎ度', desc: '30以下は売られすぎ、75以上は買われすぎ' },
  credit_spread: { name: '信用リスク', desc: '高いほど企業の倒産リスク上昇' },
  ma_deviation: { name: '平均からの乖離', desc: 'マイナスが大きいほど割安' },
  yield_curve: { name: '景気見通し', desc: 'マイナスは景気後退サイン' },
};

const URGENCY_STYLES = {
  high:   { color: '#ef4444', bg: 'rgba(239,68,68,0.15)',  label: '今すぐ' },
  medium: { color: '#f59e0b', bg: 'rgba(245,158,11,0.15)', label: '今週中' },
  low:    { color: '#3b82f6', bg: 'rgba(59,130,246,0.12)', label: '準備' },
  none:   { color: '#64748b', bg: 'rgba(100,116,139,0.10)',label: '待機' },
};

const ACTION_TYPE_LABEL = {
  sell: '売り',
  buy: '買い発動',
  buy_wait: '買い待機',
  buyback: '買い戻し',
  watch: '利確準備',
  hold: '保有継続',
};

const GEO_NAMES = { wti: '原油', gold: '金', usdjpy: 'ドル/円' };

let gaugeChart = null;

async function fetchJSON(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

function fmtYen(n) {
  if (n == null) return '--';
  if (n >= 10000) return `${(n / 10000).toFixed(0)}万円`;
  return `${n.toLocaleString()}円`;
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
// ヘッドライン
// ============================================================
function renderToday(advice) {
  const headline = document.getElementById('todayHeadline');
  const summary = document.getElementById('todaySummary');
  const bottomNote = document.getElementById('todayBottomNote');
  const card = document.getElementById('todayCard');

  headline.textContent = advice.headline || '条件待機中';
  summary.textContent = advice.summary || '';

  // 最優先アクションの緊急度で色を変える
  const top = (advice.action_list || [])[0];
  const urgency = top ? top.urgency : 'none';
  const style = URGENCY_STYLES[urgency] || URGENCY_STYLES.none;
  card.style.borderColor = style.color;
  card.style.background = `linear-gradient(135deg, ${style.bg}, var(--bg-card))`;

  if (advice.bottom_note) {
    bottomNote.style.display = 'block';
    bottomNote.textContent = advice.bottom_note;
  } else {
    bottomNote.style.display = 'none';
  }
}

// ============================================================
// つみたて枠警告
// ============================================================
function renderTsumitateWarning(warn) {
  const section = document.getElementById('tsumitateWarning');
  if (!warn) { section.style.display = 'none'; return; }
  section.style.display = 'block';
  const card = document.getElementById('tsumitateCard');
  card.className = 'tsumitate-card ' + (warn.level === 'WARNING' ? 'tsu-warning' : 'tsu-caution');
  document.getElementById('tsumitateHeadline').textContent = warn.headline;
  document.getElementById('tsumitateDetail').textContent = warn.detail;
  document.getElementById('tsumitateGuide').textContent = warn.guide || '';
  const list = document.getElementById('tsumitateList');
  list.innerHTML = '';
  if (warn.holdings_note) {
    for (const [key, text] of Object.entries(warn.holdings_note)) {
      const li = document.createElement('div');
      li.className = 'tsumitate-item';
      li.textContent = '・' + text;
      list.appendChild(li);
    }
  }
}

// ============================================================
// 今日のアクション（action_list）
// ============================================================
function renderActionList(actions) {
  const container = document.getElementById('actionList');
  container.innerHTML = '';
  if (!actions || actions.length === 0) {
    container.innerHTML = '<div class="action-empty">アクションなし</div>';
    return;
  }

  for (const a of actions) {
    const style = URGENCY_STYLES[a.urgency] || URGENCY_STYLES.none;
    const typeLabel = ACTION_TYPE_LABEL[a.type] || a.type;
    const card = document.createElement('div');
    card.className = 'action-card';
    card.style.borderLeftColor = style.color;

    const readyBadge = a.ready
      ? `<span class="action-badge ready" style="background:${style.color}">${style.label}</span>`
      : `<span class="action-badge waiting">待機</span>`;

    // 注文手順詳細
    let orderDetail = '';
    if (a.broker) {
      orderDetail = `
        <div class="action-order">
          <span class="action-order-item"><b>証券会社:</b> ${a.broker}</span>
          ${a.broker_section ? `<span class="action-order-item"><b>画面:</b> ${a.broker_section}</span>` : ''}
          ${a.search_keyword ? `<span class="action-order-item"><b>検索:</b> ${a.search_keyword}</span>` : ''}
          ${a.order_method ? `<span class="action-order-item"><b>注文:</b> ${a.order_method}</span>` : ''}
        </div>
      `;
    }

    // 進捗（買い待機の場合）
    let progressHtml = '';
    if (a.progress_text) {
      progressHtml = `<div class="action-progress">${a.progress_text}</div>`;
    }

    // 税金注記
    let taxHtml = '';
    if (a.tax_note) {
      taxHtml = `<div class="action-tax">${a.tax_note}</div>`;
    }

    card.innerHTML = `
      <div class="action-header">
        <span class="action-type type-${a.type}">${typeLabel}</span>
        ${readyBadge}
      </div>
      <div class="action-title">${a.title}</div>
      ${a.condition_text ? `<div class="action-condition">条件: ${a.condition_text}</div>` : ''}
      ${progressHtml}
      ${a.detail ? `<div class="action-detail">${a.detail}</div>` : ''}
      ${orderDetail}
      ${taxHtml}
    `;
    container.appendChild(card);
  }
}

// ============================================================
// ポートフォリオ（口座枠別）
// ============================================================
function renderPortfolio(portfolio) {
  const container = document.getElementById('portfolioCards');
  container.innerHTML = '';
  if (!portfolio || !portfolio.accounts) return;

  const accounts = portfolio.accounts;
  for (const [key, acc] of Object.entries(accounts)) {
    const card = document.createElement('div');
    card.className = 'portfolio-card';

    // 使用状況バー
    const usedPct = Math.min(100, (acc.used / acc.total) * 100);

    // 銘柄ごとの売り判定表示
    const holdingsHtml = (acc.holdings && acc.holdings.length > 0)
      ? acc.holdings.map(h => {
          const profitColor = h.profit_pct != null
            ? (h.profit_pct >= 0 ? 'color-green' : 'color-red')
            : 'color-muted';
          const profitText = h.profit_pct != null
            ? `${h.profit_pct >= 0 ? '+' : ''}${h.profit_pct.toFixed(1)}%`
            : '--';
          const valueText = h.estimated_value ? fmtYen(h.estimated_value) : fmtYen(h.invested_amount);
          const sellDecisionBadge = getDecisionBadge(h.decision);
          return `
            <div class="holding-row">
              <div class="holding-top">
                <span class="holding-name">${h.short_name}</span>
                ${sellDecisionBadge}
              </div>
              <div class="holding-middle">
                <span class="holding-invested">投入 ${fmtYen(h.invested_amount)}</span>
                <span class="holding-value">現在 ${valueText}</span>
                <span class="holding-profit ${profitColor}">${profitText}</span>
              </div>
              <div class="holding-reason">${h.reason || ''}</div>
            </div>
          `;
        }).join('')
      : '<div class="holding-empty">未投入</div>';

    card.innerHTML = `
      <div class="portfolio-header">
        <div>
          <div class="portfolio-label">${acc.label}</div>
          <div class="portfolio-broker">${acc.broker}${acc.tax_free ? ' / 非課税' : ' / 課税20.315%'}</div>
        </div>
        <div class="portfolio-amounts">
          <div class="portfolio-remaining">残り ${fmtYen(acc.remaining)}</div>
          <div class="portfolio-used">使用 ${fmtYen(acc.used)} / ${fmtYen(acc.total)}</div>
        </div>
      </div>
      <div class="portfolio-bar">
        <div class="portfolio-bar-fill" style="width:${usedPct}%"></div>
      </div>
      <div class="portfolio-holdings">${holdingsHtml}</div>
    `;
    container.appendChild(card);
  }
}

function getDecisionBadge(decision) {
  const map = {
    'HOLD':        { color: '#22c55e', text: '保有継続' },
    'WATCH':       { color: '#3b82f6', text: '利確準備' },
    'SELL_30':     { color: '#f59e0b', text: '30%利確' },
    'SELL_50':     { color: '#f59e0b', text: '50%利確' },
    'SELL_70':     { color: '#ef4444', text: '70%利確' },
    'SELL_HALF':   { color: '#f59e0b', text: '半分利確' },
    'SELL_ALL':    { color: '#ef4444', text: '全利確' },
  };
  const s = map[decision] || { color: '#64748b', text: '--' };
  return `<span class="holding-badge" style="background:${s.color}">${s.text}</span>`;
}

// ============================================================
// 買い戻しキュー
// ============================================================
function renderBuyback(buyback) {
  const section = document.getElementById('buybackSection');
  if (!buyback || !buyback.entries || buyback.entries.length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = 'block';
  const card = document.getElementById('buybackCard');

  let html = `<div class="buyback-summary">
    <span>予約残高: <b>${fmtYen(buyback.total_pending)}</b></span>
    <span>予約件数: <b>${buyback.queue_count}</b></span>
  </div>`;

  for (const entry of buyback.entries) {
    html += `<div class="buyback-entry">
      <div class="buyback-entry-header">
        <span class="buyback-sold">${entry.sold_date} ${fmtYen(entry.sold_amount)}利確分</span>
        <span class="buyback-reason">${entry.reason || ''}</span>
      </div>
      <div class="buyback-stages">`;
    for (const stage of entry.stages) {
      const status = stage.status === 'pending' ? '待機中' : (stage.status === 'done' ? '実行済み' : stage.status);
      const statusClass = stage.status === 'pending' ? 'stage-pending' : 'stage-done';
      html += `<div class="buyback-stage ${statusClass}">
        <div class="stage-top">
          <span class="stage-label">${stage.label}</span>
          <span class="stage-amount">${fmtYen(stage.amount)}</span>
          <span class="stage-status">${status}</span>
        </div>
        <div class="stage-condition">${stage.condition_text}</div>
      </div>`;
    }
    html += `</div></div>`;
  }

  card.innerHTML = html;
}

// ============================================================
// マクロ過熱シグナル
// ============================================================
function renderMacro(macro) {
  if (!macro) return;
  const label = document.getElementById('macroLabel');
  const count = document.getElementById('macroCount');
  const conditions = document.getElementById('macroConditions');

  const met = macro.met_count || 0;
  count.textContent = `${met}/${macro.total || 5}`;

  if (met >= 4) { label.textContent = '過熱警戒'; label.className = 'macro-label hot'; }
  else if (met >= 2) { label.textContent = 'やや過熱'; label.className = 'macro-label warm'; }
  else { label.textContent = '平常'; label.className = 'macro-label cool'; }

  conditions.innerHTML = '';
  for (const s of macro.signals || []) {
    const icon = s.met ? (s.severity === 'high' ? '🔴' : '🟡') : '⚪';
    const row = document.createElement('div');
    row.className = 'macro-row' + (s.met ? ' met' : '');
    row.innerHTML = `
      <div class="macro-row-top">
        <span>${icon} ${s.label}</span>
      </div>
      <div class="macro-row-detail">${s.detail}</div>
    `;
    conditions.appendChild(row);
  }
}

// ============================================================
// セクター参考情報
// ============================================================
function renderSectorInfo(sectors, forex) {
  const container = document.getElementById('sectorInfoCards');
  container.innerHTML = '';
  if (!sectors) return;

  for (const [key, sec] of Object.entries(sectors)) {
    const card = document.createElement('div');
    card.className = 'sector-info-card';
    card.innerHTML = `
      <div class="sector-info-label">${sec.label}</div>
      <div class="sector-info-status">${sec.status}</div>
      <div class="sector-info-comment">${sec.comment}</div>
    `;
    container.appendChild(card);
  }

  const forexEl = document.getElementById('adviceForex');
  if (forex && forex.usdjpy) {
    forexEl.style.display = 'block';
    const riskColors = { HIGH: '#ef4444', MEDIUM: '#f59e0b', LOW: '#22c55e', FAVORABLE: '#06b6d4' };
    const riskLabels = { HIGH: '注意', MEDIUM: 'やや注意', LOW: '問題なし', FAVORABLE: '有利' };
    forexEl.innerHTML = `
      <div class="forex-simple">
        <span>ドル円 ¥${forex.usdjpy.toFixed(1)}</span>
        <span class="forex-badge" style="background:${riskColors[forex.risk_level]}">${riskLabels[forex.risk_level]}</span>
        <span class="forex-note-text">${forex.opportunity}</span>
      </div>
    `;
  }
}

// ============================================================
// 詳細データ（既存）
// ============================================================
function getIndicatorStatus(key, value) {
  if (value == null) return { text: '--', cls: 'status-neutral' };
  if (key === 'vix') {
    if (value >= 40) return { text: 'かなり怖い', cls: 'status-danger' };
    if (value >= 30) return { text: '不安', cls: 'status-warning' };
    if (value >= 20) return { text: 'ふつう', cls: 'status-neutral' };
    if (value <= 12) return { text: '油断', cls: 'status-hot' };
    return { text: '安心', cls: 'status-safe' };
  }
  if (key === 'fear_greed') {
    if (value <= 25) return { text: 'みんな怖がっている', cls: 'status-danger' };
    if (value <= 40) return { text: '不安気味', cls: 'status-warning' };
    if (value <= 60) return { text: 'ふつう', cls: 'status-neutral' };
    if (value >= 80) return { text: '極度の強欲', cls: 'status-hot' };
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
  if (!section || !conditions || !bottomSignals) return;

  count.textContent = `${bottomSignals.met_count}/${bottomSignals.total_conditions}`;
  const labels = { 'セリングクライマックス': '大暴落の底（歴史的チャンス）', '底打ちシグナル': '底打ちの兆し', '条件未達': '底はまだ先' };
  title.textContent = labels[bottomSignals.alert_level] || bottomSignals.alert_level;

  section.style.display = 'block';
  conditions.innerHTML = '';
  for (const [, cond] of Object.entries(bottomSignals.conditions || {})) {
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
  const labels = {
    SPY: 'S&P500 ETF',
    SOXL: '半導体3倍', NVDA: 'NVIDIA', TQQQ: 'ナスダック3倍',
    XLE: 'エネルギー', GLD: 'ゴールド',
  };
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
      const advice = adviceData.advice;
      renderToday(advice);
      renderTsumitateWarning(advice.tsumitate_warning);
      renderActionList(advice.action_list);
      renderPortfolio(advice.portfolio);
      renderBuyback(advice.buyback);
      renderMacro(advice.macro_signals);
      renderSectorInfo(advice.sectors, advice.forex);
    }
  } catch (e) {
    console.error('Data fetch error:', e);
    document.getElementById('todayHeadline').textContent = '読み込みに失敗しました。更新ボタンを押してください。';
    document.getElementById('updateTime').textContent = 'エラー';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '更新'; }
  }
}

window.addEventListener('DOMContentLoaded', () => { initGauge(); refreshData(); });
window.addEventListener('resize', () => { if (gaugeChart) gaugeChart.resize(); });
