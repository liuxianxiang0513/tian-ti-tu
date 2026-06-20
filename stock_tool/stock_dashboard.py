# -*- coding: utf-8 -*-
"""
涨停板天梯图 - 交互式仪表盘 v3

从 akshare 获取涨停数据，生成精美的交互式 HTML 仪表盘。
- 浅色主题，清晰可读
- 高板位股票：卡片展示
- 低板位股票：可排序表格
- 搜索、筛选、排序全支持
- 浏览器原生渲染，永不模糊

用法:
  python stock_dashboard.py              # 当天数据
  python stock_dashboard.py 20260618     # 指定日期
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread

# Windows 编码修复
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    import akshare as ak
except ImportError:
    print("需要 akshare: pip install akshare")
    sys.exit(1)
try:
    import pandas as pd
except ImportError:
    print("需要 pandas: pip install pandas")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════

def fetch_data(date_str: str) -> tuple:
    """获取涨停数据，自动回退到最近交易日"""
    original = date_str
    for i in range(8):
        try:
            print(f"获取涨停数据: {date_str} ...", end=" ")
            df = ak.stock_zt_pool_em(date=date_str)
            if df is not None and not df.empty:
                print(f"OK ({len(df)} 只)")
                return df, date_str
            print("无数据")
        except Exception as e:
            print(f"失败: {e}")
        dt = datetime.strptime(date_str, "%Y%m%d") - timedelta(days=1)
        date_str = dt.strftime("%Y%m%d")
    raise RuntimeError(f"连续 8 天无数据（从 {original} 起）")


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """清洗并整理数据"""
    df = df.copy()
    for col in ['连板数', '炸板次数']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    for col in ['换手率', '封板资金', '成交额', '流通市值', '总市值']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    for col in ['首次封板时间', '最后封板时间']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(r'1900-01-01\s*', '', regex=True).str.strip()

    # 涨停统计清洗
    if '涨停统计' in df.columns:
        df['涨停统计'] = df['涨停统计'].astype(str).replace('nan', '')

    # 按连板数降序，同时按封板时间升序
    df = df.sort_values(['连板数', '首次封板时间'], ascending=[False, True]).reset_index(drop=True)
    return df


def fmt_money(val) -> str:
    """格式化金额"""
    v = float(val or 0)
    if v >= 1e8: return f"{v/1e8:.1f}亿"
    if v >= 1e4: return f"{v/1e4:.0f}万"
    return f"{v:.0f}"


def fmt_time(raw) -> str:
    """格式化时间 HH:MM"""
    s = str(raw or '').strip()
    if not s or s in ('nan', ''): return '-'
    if len(s) >= 4:
        return f"{s[:2]}:{s[2:4]}"
    return s


# ═══════════════════════════════════════════
# HTML 模板
# ═══════════════════════════════════════════

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>涨停板天梯图 - ${date_cn}</title>
<style>
  :root {
    --bg: #f0f2f5;
    --card-bg: #ffffff;
    --border: #e4e6ed;
    --text: #1a1a2e;
    --text2: #555770;
    --text3: #8e90a6;
    --accent: #3b82f6;
    --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
    --shadow-lg: 0 4px 16px rgba(0,0,0,0.10);
    --radius: 10px;
    --t4: #e74c3c;
    --t3: #f39c12;
    --t2: #3498db;
    --t1: #7f8c8d;
    --success: #27ae60;
    --warn: #f39c12;
    --danger: #e74c3c;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    min-height: 100vh;
  }
  .app { max-width:1600px; margin:0 auto; padding:24px; }

  /* header */
  .header {
    background: var(--card-bg);
    border-radius: var(--radius);
    padding: 24px 32px;
    margin-bottom: 20px;
    box-shadow: var(--shadow);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
  }
  .header-left h1 { font-size: 28px; font-weight: 700; color: var(--text); margin-bottom:4px; }
  .header-left .sub {
    font-size: 16px; color: var(--text3); font-weight: 600;
  }
  .header-right { display:flex; gap:10px; align-items:center; }
  .btn {
    padding: 8px 18px;
    border-radius: 8px;
    border: none;
    font-size: 16px;
    cursor: pointer;
    font-weight: 600;
    transition: all .15s;
    font-family: inherit;
  }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover { background: #2563eb; }
  .btn-outline { background: #fff; color: var(--text2); border: 1px solid var(--border); }
  .btn-outline:hover { background: #f8f9fb; }
  .btn-export { background: #10b981; color: #fff; }
  .btn-export:hover { background: #059669; }

  /* stats */
  .stats-bar {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .stat-item {
    background: var(--card-bg);
    border-radius: var(--radius);
    padding: 16px 20px;
    box-shadow: var(--shadow);
    flex: 1;
    min-width: 100px;
    text-align: center;
  }
  .stat-item .num { font-size: 32px; font-weight: 700; }
  .stat-item .lbl { font-size: 14px; color: var(--text3); margin-top:2px; font-weight: 600; }

  /* toolbar */
  .toolbar {
    background: var(--card-bg);
    border-radius: var(--radius);
    padding: 12px 20px;
    margin-bottom: 20px;
    box-shadow: var(--shadow);
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  .search-box {
    flex: 1; min-width: 200px;
    padding: 9px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 16px;
    outline: none;
    font-family: inherit;
  }
  .search-box:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(59,130,246,0.12); }
  .filter-select {
    padding: 9px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 16px;
    background: #fff;
    cursor: pointer;
    outline: none;
    font-family: inherit;
  }
  .result-hint { font-size: 15px; color: var(--text3); white-space: nowrap; font-weight: 600; }

  /* tier toggle group */
  .tier-toggles { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
  .tier-toggle {
    display:inline-flex; align-items:center; gap:3px;
    padding:5px 14px; border-radius:16px; border:1.5px solid var(--border);
    font-size:15px; cursor:pointer; user-select:none;
    transition:all .15s; background:#fff; white-space:nowrap;
  }
  .tier-toggle:hover { border-color: var(--accent); }
  .tier-toggle.active { background:#eef2ff; border-color:var(--accent); font-weight:600; }
  .tier-toggle .dot { font-size:12px; }

  /* tier section */
  .tier-section { margin-bottom: 24px; }
  .tier-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    padding: 0 4px;
  }
  .tier-dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .tier-label { font-size: 20px; font-weight: 700; }
  .tier-count { font-size: 15px; color: var(--text3); font-weight: 600; }

  /* card grid */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 10px;
  }
  .card-grid.featured { grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }
  .first-tier-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 10px;
  }
  @media (max-width:1400px) {
    .first-tier-grid { grid-template-columns: repeat(5, 1fr); }
  }
  @media (max-width:1000px) {
    .first-tier-grid { grid-template-columns: repeat(3, 1fr); }
  }

  .card {
    background: var(--card-bg);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 14px 16px;
    border-left: 4px solid transparent;
    cursor: pointer;
    transition: all .15s;
    position: relative;
    overflow: hidden;
  }
  .card:hover { box-shadow: var(--shadow-lg); transform: translateY(-1px); }
  .card.tier4 { border-left-color: var(--t4); }
  .card.tier3 { border-left-color: var(--t3); }
  .card.tier2 { border-left-color: var(--t2); }
  .card.tier1 { border-left-color: var(--t1); }

  .card-top { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px; }
  .card-name { font-size: 18px; font-weight: 700; color: var(--text); }
  .card-badge {
    font-size: 13px; padding: 2px 10px; border-radius: 10px;
    font-weight: 600; white-space: nowrap;
  }
  .badge-t4 { background: #fde8e8; color: var(--t4); }
  .badge-t3 { background: #fef3c7; color: #b45309; }
  .badge-t2 { background: #dbeafe; color: #1e40af; }
  .badge-t1 { background: #f3f4f6; color: var(--text3); }

  .card-code { font-size: 14px; color: var(--text3); margin-bottom:4px; font-weight: 600; }
  .card-industry { font-size: 14px; color: var(--text2); margin-bottom:8px; font-weight: 600; }

  .card-divider { height:1px; background: var(--border); margin:8px 0; }

  .card-row { display:flex; justify-content:space-between; align-items:center; font-size:14px; margin-bottom:3px; font-weight: 500; }
  .card-row .label { color: var(--text3); }
  .card-row .value { font-weight: 600; color: var(--text2); }
  .card-row .value.highlight { color: var(--warn); }
  .card-row .value.danger { color: var(--danger); }

  /* footer */
  .footer {
    text-align: center;
    padding: 24px;
    font-size: 14px;
    color: var(--text3);
  }

  /* responsive */
  @media (max-width:768px) {
    .app { padding:12px; }
    .header { padding:16px 20px; }
    .card-grid { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }
    .card-grid.featured { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
    .first-tier-grid { grid-template-columns: repeat(2, 1fr); }
    .header-left h1 { font-size:24px; }
    .stat-item .num { font-size:26px; }
  }
</style>
<script src="https://cdn.bootcdn.net/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
</head>
<body>

<div class="app">
  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <h1>📈 涨停板天梯图</h1>
      <div class="sub">${date_cn} 星期${weekday} · 数据来源：东方财富 · ${data_time}</div>
    </div>
    <div class="header-right">
      <button class="btn btn-export" onclick="exportImage()">📸 导出图片</button>
      <button class="btn btn-outline" onclick="resetFilters()">🔄 重置筛选</button>
      <button class="btn btn-primary" onclick="location.reload()">刷新数据</button>
    </div>
  </div>

  <!-- Stats Bar -->
  <div class="stats-bar" id="statsBar"></div>

  <!-- Toolbar -->
  <div class="toolbar">
    <input type="text" class="search-box" placeholder="🔍 搜索股票名称 / 代码 ..." oninput="applyFilters()" id="searchInput">
    <div class="tier-toggles" id="tierToggles">
      <span style="font-size:14px;color:var(--text3);margin-right:4px;font-weight:600">连板:</span>
      <label class="tier-toggle active" data-tier="4" onclick="toggleTier(this)"><span class="dot">🔴</span>4板</label>
      <label class="tier-toggle active" data-tier="3" onclick="toggleTier(this)"><span class="dot">🟠</span>3板</label>
      <label class="tier-toggle active" data-tier="2" onclick="toggleTier(this)"><span class="dot">🔵</span>2板</label>
      <label class="tier-toggle active" data-tier="1" onclick="toggleTier(this)"><span class="dot">⚪</span>首板</label>
    </div>
    <select class="filter-select" onchange="applyFilters()" id="industryFilter">
      <option value="all">全部行业</option>
    </select>
    <span class="result-hint" id="resultHint"></span>
  </div>

  <!-- Cards (高板位) -->
  <div id="cardsArea"></div>

  <!-- 首板 (7列网格) -->
  <div id="tableArea"></div>

  <!-- Footer -->
  <div class="footer">
    涨停板天梯图 · 数据实时获取 · ${date_cn}
  </div>
</div>

<script>
const ALL_DATA = ${stock_data};

// ── utils ──
function fmtMoney(v) {
  if (!v && v!==0) return '-';
  if (v>=1e8) return (v/1e8).toFixed(1)+'亿';
  if (v>=1e4) return Math.round(v/1e4)+'万';
  return Math.round(v).toLocaleString();
}

function fmtTime(s) {
  if (!s || s==='nan' || s==='-') return '-';
  s = String(s).trim();
  if (s.length>=4) return s.slice(0,2)+':'+s.slice(2,4);
  return s;
}

// ── init ──
let activeTiers = new Set([1,2,3,4]);

function toggleTier(el) {
  el.classList.toggle('active');
  const t = parseInt(el.dataset.tier);
  if (el.classList.contains('active')) activeTiers.add(t);
  else activeTiers.delete(t);
  applyFilters();
}

function getFilteredData() {
  const search = (document.getElementById('searchInput')?.value||'').toLowerCase();
  const indF = document.getElementById('industryFilter')?.value||'all';

  return ALL_DATA.filter(d => {
    if (search && !d.名称.toLowerCase().includes(search) && !d.代码.toLowerCase().includes(search)) return false;
    if (activeTiers.size>0 && !activeTiers.has(d.连板数)) return false;
    if (indF!=='all' && d.所属行业!==indF) return false;
    return true;
  });
}

function buildIndustries() {
  const s = new Set();
  ALL_DATA.forEach(d => { if (d.所属行业 && d.所属行业!=='nan') s.add(d.所属行业); });
  const sel = document.getElementById('industryFilter');
  const cur = sel.value;
  [...s].sort().forEach(ind => {
    const o = document.createElement('option');
    o.value = ind; o.textContent = ind;
    sel.appendChild(o);
  });
  sel.value = cur;
}

function buildStats(filtered) {
  const total = filtered.length;
  const maxTier = total ? Math.max(...filtered.map(d=>d.连板数)) : 0;
  const tierCounts = {};
  filtered.forEach(d => { tierCounts[d.连板数] = (tierCounts[d.连板数]||0)+1; });

  const colors = {4:'#e74c3c',3:'#f39c12',2:'#3498db',1:'#7f8c8d'};

  let html = `<div class="stat-item"><div class="num" style="color:var(--accent)">${total}</div><div class="lbl">涨停总数</div></div>`;
  html += `<div class="stat-item"><div class="num" style="color:var(--t4)">${maxTier}</div><div class="lbl">最高连板</div></div>`;
  for (const t of [4,3,2,1]) {
    const n = tierCounts[t]||0;
    const c = colors[t]||'#999';
    html += `<div class="stat-item"><div class="num" style="color:${c}">${n}</div><div class="lbl">${t}板</div></div>`;
  }
  document.getElementById('statsBar').innerHTML = html;
}

function buildCards(filtered) {
  const highTier = filtered.filter(d=>d.连板数>=2);
  if (!highTier.length) { document.getElementById('cardsArea').innerHTML=''; return; }

  // Group by tier
  const groups = {};
  highTier.forEach(d => {
    if (!groups[d.连板数]) groups[d.连板数] = [];
    groups[d.连板数].push(d);
  });

  const tierNames = {6:'六板',5:'五板',4:'四板',3:'三板',2:'二板'};
  const tierBadgeCls = {4:'t4',3:'t3',2:'t2',1:'t1'};

  let html = '';
  for (const tier of Object.keys(groups).sort((a,b)=>b-a)) {
    const t = parseInt(tier);
    const g = groups[t];
    html += `<div class="tier-section">
      <div class="tier-header">
        <div class="tier-dot" style="background:var(--t${Math.min(t,4)})"></div>
        <span class="tier-label">${tierNames[t]||t+'板'} (${g.length}只)</span>
      </div>
      <div class="card-grid featured">`;

    g.forEach(d => {
      const badge = d.涨停统计 && d.涨停统计!=='nan' ? d.涨停统计 : '';
      const ind = d.所属行业 && d.所属行业!=='nan' ? d.所属行业 : '-';
      const ft = fmtTime(d.首次封板时间);
      const turnover = parseFloat(d.换手率||0);
      const fund = parseFloat(d.封板资金||0);
      const amount = parseFloat(d.成交额||0);
      const sealRatio = fund>0 && amount>0 ? (fund/amount) : 0;
      const srCls = sealRatio>=3?'highlight':(sealRatio<1?'danger':'');
      const boom = parseInt(d.炸板次数||0);
      const toCls = turnover>=10?'danger':(turnover>=5?'highlight':'');

      html += `<div class="card tier${Math.min(t,4)}" onclick="this.classList.toggle('expanded')">
        <div class="card-top">
          <span class="card-name">${d.名称}</span>
          ${badge ? `<span class="card-badge badge-t${Math.min(t,4)}">${badge}</span>` : ''}
        </div>
        <div class="card-code">${d.代码} · ${ind.slice(0,6)}</div>
        <div class="card-divider"></div>
        <div class="card-row"><span class="label">⏰ 封板</span><span class="value">${ft}</span></div>
        <div class="card-row"><span class="label">🔄 换手</span><span class="value ${toCls}">${turnover.toFixed(1)}%</span></div>
        <div class="card-row"><span class="label">💰 封板资金</span><span class="value">${fmtMoney(fund)}</span></div>
        <div class="card-row"><span class="label">🔒 封单/成交</span><span class="value ${srCls}">${sealRatio>0 ? (sealRatio*100).toFixed(1)+'%' : '-'}</span></div>
        ${boom>0 ? `<div class="card-row"><span class="label">💥 炸板</span><span class="value danger">${boom}次</span></div>` : ''}
      </div>`;
    });

    html += `</div></div>`;
  }
  document.getElementById('cardsArea').innerHTML = html;
}

function buildTable(filtered) {
  const firstTier = filtered.filter(d=>d.连板数<=1);
  if (!firstTier.length) { document.getElementById('tableArea').innerHTML=''; return; }

  let html = '<div class="tier-section"><div class="tier-header"><div class="tier-dot" style="background:var(--t1)"></div><span class="tier-label">首板 (' + firstTier.length + '只)</span></div><div class="first-tier-grid">';

  firstTier.forEach(d => {
    const ind = d.所属行业 && d.所属行业!=='nan' ? d.所属行业 : '-';
    const ft = fmtTime(d.首次封板时间);
    const turnover = parseFloat(d.换手率||0);
    const fund = parseFloat(d.封板资金||0);
    const amount = parseFloat(d.成交额||0);
    const boom = parseInt(d.炸板次数||0);
    const sealRatio = fund>0 && amount>0 ? (fund/amount) : 0;
    const srCls = sealRatio>=3?'highlight':(sealRatio<1?'danger':'');
    const toCls = turnover>=10?'danger':(turnover>=8?'highlight':'');

    html += '<div class="card tier1"><div class="card-top"><span class="card-name">' + d.名称 + '</span></div><div class="card-code">' + d.代码 + ' · ' + ind.slice(0,6) + '</div><div class="card-divider"></div><div class="card-row"><span class="label">封板</span><span class="value">' + ft + '</span></div><div class="card-row"><span class="label">换手</span><span class="value ' + toCls + '">' + turnover.toFixed(1) + '%</span></div><div class="card-row"><span class="label">封板资金</span><span class="value">' + fmtMoney(fund) + '</span></div><div class="card-row"><span class="label">封单/成交</span><span class="value ' + srCls + '">' + (sealRatio>0 ? (sealRatio*100).toFixed(1)+'%' : '-') + '</span></div><div class="card-row"><span class="label">成交额</span><span class="value" style="color:var(--text3)">' + fmtMoney(amount) + '</span></div>' + (boom>0 ? '<div class="card-row"><span class="label">炸板</span><span class="value danger">' + boom + '次</span></div>' : '') + '</div>';
  });

  html += '</div></div>';
  document.getElementById('tableArea').innerHTML = html;
}

function exportImage() {
  const btn = document.querySelector('.btn-export');
  if (btn) btn.textContent = '生成中...';
  html2canvas(document.querySelector('.app'), {
    backgroundColor: '#f0f2f5',
    scale: 2,
    useCORS: true,
    logging: false
  }).then(canvas => {
    const link = document.createElement('a');
    link.download = '天梯图_' + new Date().toISOString().slice(0,10).replace(/-/g,'') + '.png';
    link.href = canvas.toDataURL('image/png');
    link.click();
    if (btn) btn.textContent = '📸 导出图片';
  }).catch(err => {
    alert('导出失败: ' + err.message);
    if (btn) btn.textContent = '📸 导出图片';
  });
}

function applyFilters() {
  const filtered = getFilteredData();
  buildStats(filtered);
  buildCards(filtered);
  buildTable(filtered);
  document.getElementById('resultHint').textContent = `显示 ${filtered.length} / ${ALL_DATA.length} 只`;
}

function resetFilters() {
  document.getElementById('searchInput').value = '';
  document.getElementById('industryFilter').value = 'all';
  document.querySelectorAll('.tier-toggle').forEach(el => { el.classList.add('active'); });
  activeTiers = new Set([1,2,3,4]);
  applyFilters();
}

// ── boot ──
document.addEventListener('DOMContentLoaded', () => {
  buildIndustries();
  applyFilters();
});

// keyboard shortcut: Ctrl+F / / to focus search
document.addEventListener('keydown', e => {
  if ((e.ctrlKey && e.key==='f') || (e.key==='/' && document.activeElement===document.body)) {
    e.preventDefault();
    document.getElementById('searchInput').focus();
  }
});
</script>

</body>
</html>'''


def generate_html(df: pd.DataFrame, date_str: str) -> str:
    """生成完整的 HTML 仪表盘"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    date_cn = dt.strftime("%Y年%m月%d日")
    wd = ["一", "二", "三", "四", "五", "六", "日"][dt.weekday()]
    data_time = datetime.now().strftime("%H:%M:%S")

    # 构建 JSON 数据
    records = []
    keep_cols = [
        '代码', '名称', '涨跌幅', '最新价', '成交额', '流通市值', '总市值',
        '换手率', '封板资金', '首次封板时间', '最后封板时间', '炸板次数',
        '涨停统计', '连板数', '所属行业'
    ]
    for _, row in df.iterrows():
        rec = {}
        for col in keep_cols:
            if col in df.columns:
                val = row[col]
                if isinstance(val, (pd.Timestamp,)):
                    val = str(val)
                elif pd.isna(val):
                    val = ''
                elif isinstance(val, (int, float)):
                    pass
                else:
                    val = str(val)
                rec[col] = val
        records.append(rec)

    json_data = json.dumps(records, ensure_ascii=False, indent=2)

    html = HTML_TEMPLATE
    html = html.replace('${date_cn}', date_cn)
    html = html.replace('${weekday}', wd)
    html = html.replace('${data_time}', data_time)
    html = html.replace('${stock_data}', json_data)

    return html


# ═══════════════════════════════════════════
# 本地服务器
# ═══════════════════════════════════════════

class DashboardServer:
    """轻量本地 HTTP 服务器，让仪表盘像真正的软件一样运行"""

    def __init__(self, html_content: str, port: int = 8765):
        self.html = html_content
        self.port = port

        parent = self

        class Handler(SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/' or self.path == '/index.html':
                    content = parent.html.encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', len(content))
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    super().do_GET()

            def log_message(self, format, *args):
                pass  # 静默模式

        self.handler = Handler

    def start(self):
        """启动服务器（非阻塞）"""
        self.server = HTTPServer(('127.0.0.1', self.port), self.handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        """停止服务器"""
        self.server.shutdown()


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="涨停板天梯图 - 交互式仪表盘",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python stock_dashboard.py              # 当天数据
  python stock_dashboard.py 20260618     # 指定日期
  python stock_dashboard.py -p 8888      # 自定义端口
  python stock_dashboard.py -o chart.html # 仅生成文件
        """)
    parser.add_argument("date", nargs="?", default=None, help="日期 YYYYMMDD")
    parser.add_argument("-p", "--port", type=int, default=8765, help="HTTP 端口 (默认 8765)")
    parser.add_argument("-o", "--output", default=None, help="仅生成 HTML 文件，不启动服务器")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y%m%d")

    print("=" * 56)
    print("  📈 涨停板天梯图 - 交互式仪表盘 v3")
    print("=" * 56)

    # 获取数据
    df, actual_date = fetch_data(date_str)
    df = clean_data(df)

    print()
    for tier in sorted(df['连板数'].unique(), reverse=True):
        names = df[df['连板数'] == tier]['名称'].tolist()
        tag = f"{tier}板" if tier > 1 else "首板"
        print(f"  {tag:>3s} ({len(names):>2d}只): {', '.join(names[:10])}{'...' if len(names) > 10 else ''}")

    # 生成 HTML
    print(f"\n🎨 生成仪表盘中...")
    html = generate_html(df, actual_date)

    # 保存文件
    out_path = args.output or os.path.join(SCRIPT_DIR, f"天梯图_{actual_date}.html")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ HTML 已保存: {out_path}")

    if args.output:
        print("   仅生成文件模式，不启动服务器。")
        return

    # 启动服务器
    print(f"\n🚀 启动本地服务器: http://127.0.0.1:{args.port}")
    server = DashboardServer(html, args.port)
    server.start()

    # 打开浏览器
    url = f"http://127.0.0.1:{args.port}"
    print(f"🌐 正在打开浏览器...")
    time.sleep(1)
    webbrowser.open(url)

    print(f"""
╔══════════════════════════════════════════════════════╗
║  ✅ 仪表盘已启动！                                    ║
║                                                      ║
║  地址: {url:<42s} ║
║                                                      ║
║  功能:                                                ║
║  · 🔍 搜索股票名称/代码                               ║
║  · 📋 按连板数/行业筛选                               ║
║  · ↕️ 点击表头排序                                    ║
║  · ⌨️ 按 / 快速聚焦搜索框                             ║
║  · 📊 实时统计数据                                    ║
║                                                      ║
║  按 Ctrl+C 停止服务器                                 ║
╚══════════════════════════════════════════════════════╝
""")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 正在关闭...")
        server.stop()
        print("✅ 已停止")


if __name__ == "__main__":
    main()
