#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socket import error as SocketError

from smart_ac_core import Scenario, SmartACModel


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Project Smart-AC ダッシュボード</title>
  <style>
    :root {
      --bg: #f7f3ea;
      --panel: #fffdf7;
      --ink: #1c242d;
      --muted: #5b6775;
      --line: #d8d0c2;
      --accent: #136f63;
      --accent2: #2563eb;
      --danger: #d94841;
      --gold: #d97706;
      --soft: #c2410c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Helvetica, Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(19, 111, 99, 0.09), transparent 28%),
        radial-gradient(circle at top right, rgba(217, 119, 6, 0.08), transparent 24%),
        linear-gradient(180deg, #fbfaf5 0%, var(--bg) 100%);
    }
    .shell { width: min(1280px, calc(100vw - 24px)); margin: 0 auto; padding: 24px 0 56px; }
    .hero, .experiment-panel, .grid, .notes {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 16px;
      align-items: start;
    }
    .panel {
      background: color-mix(in srgb, var(--panel) 92%, white);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 12px 32px rgba(28, 36, 45, 0.06);
    }
    .hero h1 { margin: 0 0 10px; font-size: clamp(30px, 4vw, 44px); line-height: 1.02; letter-spacing: -0.03em; }
    .hero p { margin: 0; color: var(--muted); line-height: 1.55; }
    .meta { display: grid; gap: 12px; }
    .meta strong, .field label, .card .label, .mini .k, .status-box strong, th {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .meta span { font-size: 18px; font-weight: 600; }
    .experiment-panel, .cards, .grid, .notes { margin-top: 16px; }
    .parameter-groups { display: grid; gap: 14px; }
    .parameter-group {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: rgba(255,255,255,0.58);
    }
    .parameter-group h3 {
      margin: 0 0 4px;
      font-size: 16px;
      color: var(--ink);
    }
    .parameter-group p {
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .field input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      background: rgba(255,255,255,0.8);
      font-size: 14px;
      color: var(--ink);
    }
    .field small { display: block; margin-top: 5px; color: var(--muted); font-size: 12px; line-height: 1.35; }
    .button-row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; align-items: center; }
    button {
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    .primary { background: linear-gradient(135deg, #136f63, #0f766e); color: white; }
    .secondary { background: rgba(37, 99, 235, 0.12); color: #1d4ed8; }
    .ghost { background: rgba(28, 36, 45, 0.06); color: var(--ink); }
    .status-box {
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(19, 111, 99, 0.08);
      border: 1px solid rgba(19, 111, 99, 0.16);
    }
    .status-box.warn {
      background: rgba(217, 72, 65, 0.08);
      border-color: rgba(217, 72, 65, 0.18);
    }
    .status-box.soft {
      background: rgba(194, 65, 12, 0.10);
      border-color: rgba(194, 65, 12, 0.22);
    }
    .status-box span { font-size: 15px; line-height: 1.5; color: var(--ink); }
    .status-box small {
      display: block;
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
    .card { background: rgba(255,255,255,0.72); border: 1px solid var(--line); border-radius: 16px; padding: 14px; }
    .card .value { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }
    .value-row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
    .mode-badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid rgba(19, 111, 99, 0.22);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      line-height: 1;
      color: var(--accent);
      background: rgba(19, 111, 99, 0.10);
    }
    .mode-badge.soft {
      border-color: rgba(194, 65, 12, 0.26);
      color: var(--soft);
      background: rgba(194, 65, 12, 0.10);
    }
    .mode-badge.fallback {
      border-color: rgba(217, 72, 65, 0.26);
      color: var(--danger);
      background: rgba(217, 72, 65, 0.10);
    }
    .grid { grid-template-columns: 1fr 1fr; }
    .notes { grid-template-columns: 1fr 1fr; }
    .chart-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .chart-title h2 { margin: 0; font-size: 18px; }
    .chart-title span { color: var(--muted); font-size: 13px; }
    canvas {
      width: 100%;
      height: 290px;
      display: block;
      border-radius: 12px;
      background: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(248,246,240,0.92));
    }
    .slider-wrap { margin-top: 18px; }
    .slider-label { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; color: var(--muted); }
    input[type="range"] { width: 100%; accent-color: var(--accent2); }
    .step-info { margin-top: 12px; display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
    .mini { background: rgba(255,255,255,0.65); border: 1px solid var(--line); border-radius: 14px; padding: 10px 12px; }
    .mini .v { font-size: 21px; font-weight: 700; }
    .bars { margin-top: 12px; display: grid; grid-template-columns: repeat(9, minmax(0, 1fr)); gap: 8px; align-items: end; height: 160px; }
    .bar { position: relative; border-radius: 12px 12px 8px 8px; background: linear-gradient(180deg, rgba(37, 99, 235, 0.28), rgba(37, 99, 235, 0.86)); min-height: 8px; }
    .bar.first { background: linear-gradient(180deg, rgba(217, 72, 65, 0.32), rgba(217, 72, 65, 0.92)); box-shadow: 0 0 0 2px rgba(217, 72, 65, 0.14); }
    .bar-label { position: absolute; left: 50%; transform: translateX(-50%); bottom: -22px; font-size: 11px; color: var(--muted); white-space: nowrap; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 8px; table-layout: fixed; }
    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    code {
      padding: 2px 6px;
      border-radius: 999px;
      background: rgba(28, 36, 45, 0.06);
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 12px;
      white-space: normal;
    }
    .terms-table col:nth-child(1) { width: 22%; }
    .terms-table col:nth-child(2) { width: 29%; }
    .terms-table col:nth-child(3) { width: 25%; }
    .terms-table col:nth-child(4) { width: 24%; }
    .notes ul { margin: 10px 0 0; padding-left: 18px; color: var(--muted); line-height: 1.55; }
    .equation-list { display: grid; gap: 12px; margin-top: 10px; }
    .equation-card {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      background: rgba(255,255,255,0.7);
    }
    .equation-title {
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
      font-weight: 700;
    }
    .equation-math {
      font-family: "Cambria Math", "Times New Roman", serif;
      font-size: 21px;
      line-height: 1.45;
      color: #0f172a;
      overflow-wrap: anywhere;
    }
    .equation-note {
      margin-top: 8px;
      font-size: 13px;
      line-height: 1.5;
      color: var(--muted);
    }
    .equation-vars {
      margin-top: 10px;
      display: grid;
      gap: 6px;
    }
    .equation-var {
      display: grid;
      grid-template-columns: minmax(96px, 120px) 1fr;
      gap: 10px;
      align-items: start;
      padding-top: 6px;
      border-top: 1px dashed rgba(216, 208, 194, 0.9);
    }
    .equation-var code {
      display: inline-block;
      border-radius: 10px;
      background: rgba(19, 111, 99, 0.08);
      color: #0f4c45;
    }
    .equation-var span {
      font-size: 13px;
      line-height: 1.45;
      color: var(--ink);
    }
    .alpha-guide {
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(37, 99, 235, 0.06);
      border: 1px solid rgba(37, 99, 235, 0.12);
      font-size: 12px;
      line-height: 1.5;
      color: var(--ink);
    }
    .alpha-guide strong {
      display: inline;
      margin: 0;
      color: #1d4ed8;
      font-size: 12px;
      letter-spacing: 0;
      text-transform: none;
    }
    @media (max-width: 980px) {
      .hero, .experiment-panel, .grid, .notes { grid-template-columns: 1fr; }
      .form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .cards, .step-info { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .bars { grid-template-columns: repeat(6, minmax(0, 1fr)); }
    }
    @media (max-width: 640px) {
      .shell { width: min(100vw - 16px, 1280px); padding-top: 16px; }
      .form-grid { grid-template-columns: 1fr; }
      .cards, .step-info, .bars { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panel { padding: 14px; border-radius: 16px; }
      canvas { height: 240px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="panel">
        <h1>Project Smart-AC</h1>
        <p>このダッシュボードは、部屋の温度制御を題材に、予測ホライズン、Receding Horizon、モデルずれ、オフセット補正 <code>z[k]</code> を目で追える学習用 UI です。外気温予報を見て先回りする MPC と、予報を使わず現在の誤差だけを見る PID 制御の違いを、同じ Python モデルで比較します。</p>
      </div>
      <div class="panel meta">
        <div><strong>寒波到来</strong><span id="meta-front"></span></div>
        <div><strong>予測ホライズン</strong><span id="meta-horizon"></span></div>
        <div><strong>今回の要点</strong><span id="meta-summary" style="font-size:16px; font-weight:600; line-height:1.45;"></span></div>
      </div>
    </section>

    <section class="experiment-panel">
      <div class="panel">
        <div class="chart-title">
          <h2>実験パラメータ</h2>
          <span>数値を変えたら「リセット」で Python 側で再計算します</span>
        </div>
        <div class="parameter-groups">
          <div class="parameter-group">
            <h3>時間とイベント</h3>
            <p>実験の長さ、先読みの長さ、寒波イベントの開始位置と強さを決めます。</p>
            <div class="form-grid">
              <div class="field"><label for="steps-input">総ステップ数</label><input id="steps-input" type="number" min="24" max="180" step="1"><small>10分刻みの実験長さです。</small></div>
              <div class="field"><label for="horizon-input">MPCホライズン</label><input id="horizon-input" type="number" min="3" max="48" step="1"><small>何ステップ先まで最適化するか。</small></div>
              <div class="field"><label for="cold-front-step-input">寒波開始 step</label><input id="cold-front-step-input" type="number" min="0" max="180" step="1"><small>寒波イベントを何 step 目から始めるか。</small></div>
              <div class="field"><label for="cold-front-min-temp-input">寒波最低外気温</label><input id="cold-front-min-temp-input" type="number" min="-20" max="10" step="0.5"><small>寒波の底で何℃まで下がるか。</small></div>
            </div>
          </div>
          <div class="parameter-group">
            <h3>快適条件と制約</h3>
            <p>守りたい温度帯と絶対に割りたくない安全下限を指定します。</p>
            <div class="form-grid">
              <div class="field"><label for="comfort-low-input">快適温度 下限</label><input id="comfort-low-input" type="number" min="18" max="26" step="0.1"><small>CV の下限です。</small></div>
              <div class="field"><label for="comfort-high-input">快適温度 上限</label><input id="comfort-high-input" type="number" min="18" max="28" step="0.1"><small>CV の上限です。</small></div>
              <div class="field"><label for="min-safe-input">安全温度 下限</label><input id="min-safe-input" type="number" min="15" max="22" step="0.1"><small>絶対に下回りたくない制約です。</small></div>
            </div>
          </div>
          <div class="parameter-group">
            <h3>観測と補正</h3>
            <p>センサーのばらつきと、モデル誤差を打ち消す補正の効き方を調整します。</p>
            <div class="form-grid">
              <div class="field"><label for="noise-input">センサーノイズ σ</label><input id="noise-input" type="number" min="0" max="2" step="0.05"><small>観測値 <code>y[k]</code> のばらつき。</small></div>
              <div class="field"><label for="bias-alpha-input">補正ゲイン α</label><input id="bias-alpha-input" type="number" min="0" max="1" step="0.05"><small><code>z[k]</code> の追従の速さ。</small></div>
              <div class="field"><label for="seed-input">乱数シード</label><input id="seed-input" type="number" min="1" max="9999" step="1"><small>同じ条件を再現したいときに使います。</small></div>
            </div>
            <div class="alpha-guide">
              <strong>α = 0</strong> はモデル絶対主義です。予測を信じ切って、実測との差で補正しません。<br>
              <strong>α = 1</strong> は実測絶対主義です。毎回の観測誤差をそのまま最大限に反映します。
            </div>
          </div>
          <div class="parameter-group">
            <h3>MPCモデルと実プラント</h3>
            <p>現実の部屋と、MPC の頭の中のモデルを分けて設定します。両者をずらすと、モデル誤差の影響が見えます。</p>
            <div class="form-grid">
              <div class="field"><label for="model-leak-input">モデル漏れ係数</label><input id="model-leak-input" type="number" min="0.001" max="0.05" step="0.0005"><small>MPC の頭の中の熱損失です。</small></div>
              <div class="field"><label for="plant-leak-input">実プラント漏れ係数</label><input id="plant-leak-input" type="number" min="0.001" max="0.05" step="0.0005"><small>現実の部屋の熱損失です。</small></div>
              <div class="field"><label for="model-gain-input">モデル暖房ゲイン</label><input id="model-gain-input" type="number" min="0.2" max="1.2" step="0.01"><small>MPC の頭の中の暖房の効きです。</small></div>
              <div class="field"><label for="plant-gain-input">実プラント暖房ゲイン</label><input id="plant-gain-input" type="number" min="0.2" max="1.2" step="0.01"><small>現実の部屋の暖房の効きです。</small></div>
            </div>
          </div>
          <div class="parameter-group">
            <h3>PID比較対象</h3>
            <p>MPC と比較する PID 制御器のゲインです。</p>
            <div class="form-grid">
              <div class="field"><label for="pid-kp-input">PID Kp</label><input id="pid-kp-input" type="number" min="0" max="3" step="0.01"><small>比例項の強さ。</small></div>
              <div class="field"><label for="pid-ki-input">PID Ki</label><input id="pid-ki-input" type="number" min="0" max="1" step="0.01"><small>積分項の強さ。</small></div>
              <div class="field"><label for="pid-kd-input">PID Kd</label><input id="pid-kd-input" type="number" min="0" max="3" step="0.01"><small>微分項の強さ。</small></div>
            </div>
          </div>
        </div>
        <div class="button-row">
          <button id="play-btn" class="primary" type="button">再生</button>
          <button id="pause-btn" class="secondary" type="button">停止</button>
          <button id="reset-btn" class="ghost" type="button">リセット</button>
        </div>
      </div>
      <div class="panel">
        <div id="runtime-warning" class="status-box warn" style="display:none; margin-bottom:12px;"><strong>実行方法の警告</strong><span id="runtime-warning-text"></span></div>
        <div id="soft-zone-box" class="status-box soft" style="display:none; margin-bottom:12px;"><strong>ソフト制約ゾーン</strong><span id="soft-zone-text"></span></div>
        <div class="status-box"><strong>実験ステータス</strong><span id="experiment-status"></span></div>
        <div class="status-box" style="margin-top:12px;"><strong>現在反映中の寒波開始</strong><span id="applied-front-step"></span></div>
        <div class="status-box" style="margin-top:12px;"><strong>この例での変数対応</strong><span>CV = 室温 <code>x[k]</code>、MV = エアコン出力 <code>u[k]</code>、外乱 = 外気温予報 <code>Tout[k]</code>、観測値 = ノイズ付き室温 <code>y[k]</code>、補正量 = <code>z[k]</code></span><small><code>α = 0</code> はモデル絶対主義、<code>α = 1</code> は実測絶対主義です。実際にはその中間で、予測と誤差補正のバランスを取ります。</small></div>
        <div class="chart-title" style="margin-top:16px;"><h2>モデル式</h2><span>小さな部屋向けに簡略化した制御ループ</span></div>
        <div id="equations" class="equation-list"></div>
      </div>
    </section>

    <section class="cards">
      <div class="card"><div class="label">温度変動幅</div><div class="value value-row"><span id="mode-badge" class="mode-badge">通常</span><span id="temp-swing"></span></div></div>
      <div class="card"><div class="label">最大オーバーシュート</div><div class="value" id="overshoot"></div></div>
      <div class="card"><div class="label">消費電力量</div><div class="value" id="energy-compare"></div></div>
      <div class="card"><div class="label">快適域逸脱回数</div><div class="value" id="violations"></div></div>
      <div class="card"><div class="label">MPC 平均計算時間</div><div class="value" id="mpc-avg-solve"></div></div>
      <div class="card"><div class="label">MPC 最大計算時間</div><div class="value" id="mpc-max-solve"></div></div>
    </section>

    <section class="grid">
      <div class="panel">
        <div class="chart-title"><h2>室温の時系列</h2><span>MPC 仮想温度、観測温度、PID 仮想温度を比較</span></div>
        <canvas id="temp-chart" width="800" height="290"></canvas>
      </div>
      <div class="panel">
        <div class="chart-title"><h2>操作量と外乱</h2><span>外気温と MPC / PID 出力の比較</span></div>
        <canvas id="power-chart" width="800" height="290"></canvas>
      </div>
    </section>

    <section class="grid">
      <div class="panel">
        <div class="chart-title"><h2>予測誤差とオフセット補正</h2><span><code>z[k]</code> がモデルずれを追いかける様子</span></div>
        <canvas id="bias-chart" width="800" height="290"></canvas>
      </div>
      <div class="panel">
        <div class="chart-title"><h2>予測ホライズンの重ね表示</h2><span>選択 step までの直近予測を半透明で重ねて比較</span></div>
        <canvas id="horizon-chart" width="800" height="290"></canvas>
        <div class="slider-wrap">
          <div class="slider-label"><span>ステップ確認</span><span id="step-readout"></span></div>
          <input id="step-slider" type="range" min="0" max="0" value="0">
        </div>
        <div class="step-info" id="step-info"></div>
        <div class="bars" id="control-bars"></div>
      </div>
    </section>

    <section class="panel" style="margin-top:16px;">
      <div class="chart-title"><h2>MPC の計算時間</h2><span>予測ホライズンを伸ばすと、各 step の最適化負荷がどう増えるか</span></div>
      <canvas id="timing-chart" width="800" height="290"></canvas>
    </section>

    <section class="panel" style="margin-top:16px;">
      <div class="chart-title"><h2>用語対応表</h2><span>制御用語が今回の温度制御で何を指すか</span></div>
      <table class="terms-table">
        <colgroup>
          <col>
          <col>
          <col>
          <col>
        </colgroup>
        <thead><tr><th>用語</th><th>意味</th><th>この例での対象</th><th>変数</th></tr></thead>
        <tbody id="terms-body"></tbody>
      </table>
    </section>

    <section class="notes">
      <div class="panel">
        <div class="chart-title"><h2>なぜ予測がずれても破綻しにくいか</h2><span>今回の例で見える 2 つの補正メカニズム</span></div>
        <ul>
          <li>毎ステップごとに最新の観測温度から解き直し、計画の最初の 1 手だけを実際に送っています。</li>
          <li><code>z[k]</code> は、1 ステップ先予測と実測の差を使って、モデルの癖を徐々に補正します。</li>
          <li>ホライズンのグラフに出ている未来計画は仮の案です。次の計測が来たら捨てて作り直します。</li>
          <li>この例では、あえて実プラントとモデルの係数をずらしてあるので、誤差補正の意味が見えます。</li>
        </ul>
      </div>
    </section>
  </div>
  <script id="dataset" type="application/json">__DATA__</script>
  <script>
    const API_PATH = "__API_PATH__";
    const baseData = JSON.parse(document.getElementById("dataset").textContent);
    let data = JSON.parse(JSON.stringify(baseData));
    let playTimer = null;

    const COLORS = { accent: "#136f63", blue: "#2563eb", red: "#d94841", gold: "#d97706", gray: "#64748b", soft: "#c2410c", comfort: "rgba(47, 133, 90, 0.12)" };

    function setText(id, value) { document.getElementById(id).textContent = value; }
    function showWarning(text) {
      document.getElementById("runtime-warning").style.display = "block";
      setText("runtime-warning-text", text);
    }
    function setSoftZoneState(active, text = "") {
      const box = document.getElementById("soft-zone-box");
      box.style.display = active ? "block" : "none";
      if (active) setText("soft-zone-text", text);
    }

    function seedFormFromConfig(cfg) {
      document.getElementById("steps-input").value = cfg.steps;
      document.getElementById("horizon-input").value = cfg.mpc_horizon_steps;
      document.getElementById("cold-front-step-input").value = cfg.cold_front_start_step;
      document.getElementById("cold-front-min-temp-input").value = cfg.cold_front_min_temp;
      document.getElementById("comfort-low-input").value = cfg.comfort_low;
      document.getElementById("comfort-high-input").value = cfg.comfort_high;
      document.getElementById("min-safe-input").value = cfg.min_safe_temp;
      document.getElementById("noise-input").value = cfg.sensor_noise_sigma;
      document.getElementById("bias-alpha-input").value = cfg.bias_alpha;
      document.getElementById("seed-input").value = cfg.seed;
      document.getElementById("model-leak-input").value = cfg.model_leak_rate;
      document.getElementById("plant-leak-input").value = cfg.plant_leak_rate;
      document.getElementById("model-gain-input").value = cfg.model_heater_gain;
      document.getElementById("plant-gain-input").value = cfg.plant_heater_gain;
      document.getElementById("pid-kp-input").value = cfg.pid_kp;
      document.getElementById("pid-ki-input").value = cfg.pid_ki;
      document.getElementById("pid-kd-input").value = cfg.pid_kd;
    }

    function readNumber(id) { return Number(document.getElementById(id).value); }

    function readConfig() {
      return {
        ...baseData.config,
        steps: Math.max(24, Math.round(readNumber("steps-input"))),
        cold_front_start_step: Math.max(0, Math.round(readNumber("cold-front-step-input"))),
        cold_front_min_temp: readNumber("cold-front-min-temp-input"),
        comfort_low: readNumber("comfort-low-input"),
        comfort_high: readNumber("comfort-high-input"),
        min_safe_temp: readNumber("min-safe-input"),
        sensor_noise_sigma: Math.max(0, readNumber("noise-input")),
        bias_alpha: Math.min(1, Math.max(0, readNumber("bias-alpha-input"))),
        seed: Math.max(1, Math.round(readNumber("seed-input"))),
        model_leak_rate: Math.max(0.001, readNumber("model-leak-input")),
        plant_leak_rate: Math.max(0.001, readNumber("plant-leak-input")),
        model_heater_gain: Math.max(0.2, readNumber("model-gain-input")),
        plant_heater_gain: Math.max(0.2, readNumber("plant-gain-input")),
        mpc_horizon_steps: Math.max(3, Math.round(readNumber("horizon-input"))),
        pid_kp: Math.max(0, readNumber("pid-kp-input")),
        pid_ki: Math.max(0, readNumber("pid-ki-input")),
        pid_kd: Math.max(0, readNumber("pid-kd-input")),
      };
    }

    function setupMeta() {
      const metrics = data.metrics;
      setText("meta-front", `${data.narrative.front_hour.toFixed(2)} 時間後 (step ${data.narrative.front_step})`);
      setText("meta-horizon", `${data.config.mpc_horizon_steps} ステップ = ${(data.config.mpc_horizon_steps * data.config.dt_hours).toFixed(1)} 時間`);
      setText("meta-summary", data.narrative.summary);
      setText("temp-swing", `MPC ${metrics.mpc_temp_swing_c.toFixed(2)} / PID ${metrics.pid_temp_swing_c.toFixed(2)} C`);
      setText("overshoot", `MPC ${metrics.mpc_overshoot_c.toFixed(2)} / PID ${metrics.pid_overshoot_c.toFixed(2)} C`);
      setText("energy-compare", `MPC ${metrics.mpc_energy_kwh.toFixed(2)} / PID ${metrics.pid_energy_kwh.toFixed(2)} kWh`);
      setText("violations", `MPC ${metrics.mpc_violations} / PID ${metrics.pid_violations}`);
      setText("mpc-avg-solve", `${metrics.mpc_avg_solve_time_ms.toFixed(2)} ms`);
      setText("mpc-max-solve", `${metrics.mpc_max_solve_time_ms.toFixed(2)} ms`);
      setText("applied-front-step", `step ${data.config.cold_front_start_step} / ${data.narrative.front_hour.toFixed(2)} 時間後`);
      renderEquations();
      setText("experiment-status", `温度変動幅は MPC ${metrics.mpc_temp_swing_c.toFixed(2)} C、PID ${metrics.pid_temp_swing_c.toFixed(2)} C です。最大オーバーシュートは MPC ${metrics.mpc_overshoot_c.toFixed(2)} C、PID ${metrics.pid_overshoot_c.toFixed(2)} C。平均計算時間は ${metrics.mpc_avg_solve_time_ms.toFixed(2)} ms です。`);
    }

    function renderEquations() {
      const root = document.getElementById("equations");
      root.innerHTML = "";
      for (const equation of data.narrative.equations) {
        const card = document.createElement("div");
        card.className = "equation-card";
        const variablesHtml = (equation.variables || []).map(([name, description]) => `
          <div class="equation-var">
            <code>${name}</code>
            <span>${description}</span>
          </div>
        `).join("");
        card.innerHTML = `
          <div class="equation-title">${equation.title}</div>
          <div class="equation-math">${equation.html}</div>
          <div class="equation-note">${equation.note}</div>
          <div class="equation-vars">${variablesHtml}</div>
        `;
        root.appendChild(card);
      }
    }

    function renderTerms() {
      const body = document.getElementById("terms-body");
      body.innerHTML = "";
      for (const row of data.terms) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td><strong>${row[0]}</strong></td><td>${row[1]}</td><td>${row[2]}</td><td><code>${row[3]}</code></td>`;
        body.appendChild(tr);
      }
    }

    function makeSeries(values, color, label, width = 2, dash = []) { return { values, color, label, width, dash }; }

    function buildSoftConstraintBands() {
      const ranges = [];
      let start = null;
      data.timeline.forEach((row, index) => {
        if (row.mpc_soft_constraint_active) {
          if (start === null) start = index;
        } else if (start !== null) {
          ranges.push({ start, end: index - 1 });
          start = null;
        }
      });
      if (start !== null) ranges.push({ start, end: data.timeline.length - 1 });
      return ranges.map((range, index) => ({
        index: range.start,
        color: COLORS.soft,
        label: index === 0 ? "ソフト制約" : "",
        bandWidth: Math.max(1, range.end - range.start + 1),
        bandColor: "rgba(194, 65, 12, 0.12)",
      }));
    }

    function drawLegend(ctx, items, x, y) {
      ctx.font = "12px Segoe UI";
      items.filter(item => item.label).forEach((item, index) => {
        const yy = y + index * 18;
        ctx.strokeStyle = item.color;
        ctx.lineWidth = item.width || 2;
        ctx.setLineDash(item.dash || []);
        ctx.beginPath();
        ctx.moveTo(x, yy);
        ctx.lineTo(x + 24, yy);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "#435160";
        ctx.fillText(item.label, x + 32, yy + 4);
      });
    }

    function drawLineChart(canvasId, series, options = {}) {
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext("2d");
      const width = canvas.width;
      const height = canvas.height;
      const hasRightAxis = Boolean(options.rightAxis);
      const pad = { top: 20, right: hasRightAxis ? 48 : 18, bottom: 28, left: 42 };
      const chartWidth = width - pad.left - pad.right;
      const chartHeight = height - pad.top - pad.bottom;
      const flat = series.flatMap(item => item.values).filter(value => value !== null && value !== undefined);
      const leftAxis = {
        min: options.minValue !== undefined ? options.minValue : Math.min(...flat),
        max: options.maxValue !== undefined ? options.maxValue : Math.max(...flat),
      };
      leftAxis.domain = leftAxis.max - leftAxis.min || 1;
      const rightAxis = hasRightAxis
        ? {
            min: options.rightAxis.minValue,
            max: options.rightAxis.maxValue,
            label: options.rightAxis.label || "",
          }
        : null;
      if (rightAxis) rightAxis.domain = rightAxis.max - rightAxis.min || 1;
      const yForValue = (value, axisName = "left") => {
        const axis = axisName === "right" && rightAxis ? rightAxis : leftAxis;
        return pad.top + (1 - (value - axis.min) / axis.domain) * chartHeight;
      };

      ctx.clearRect(0, 0, width, height);
      if (options.bands) {
        for (const band of options.bands) {
          const yTop = yForValue(band.max, band.axis || "left");
          const yBottom = yForValue(band.min, band.axis || "left");
          ctx.fillStyle = band.color;
          ctx.fillRect(pad.left, yTop, chartWidth, yBottom - yTop);
        }
      }
      ctx.strokeStyle = "rgba(100, 116, 139, 0.16)";
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i += 1) {
        const yy = pad.top + (i / 4) * chartHeight;
        ctx.beginPath();
        ctx.moveTo(pad.left, yy);
        ctx.lineTo(width - pad.right, yy);
        ctx.stroke();
      }
      if (options.verticalLines) {
        for (const line of options.verticalLines) {
          const x = pad.left + (line.index / Math.max(1, options.length - 1)) * chartWidth;
          if (line.bandWidth && line.bandWidth > 0) {
            const bandRightIndex = Math.min(options.length - 1, line.index + line.bandWidth);
            const xRight = pad.left + (bandRightIndex / Math.max(1, options.length - 1)) * chartWidth;
            ctx.fillStyle = line.bandColor || "rgba(217, 72, 65, 0.08)";
            ctx.fillRect(x, pad.top, Math.max(2, xRight - x), chartHeight);
          }
          ctx.strokeStyle = line.color;
          ctx.setLineDash([5, 5]);
          ctx.beginPath();
          ctx.moveTo(x, pad.top);
          ctx.lineTo(x, pad.top + chartHeight);
          ctx.stroke();
          ctx.setLineDash([]);
          if (line.label) {
            ctx.fillStyle = line.color;
            ctx.font = "bold 12px Segoe UI";
            ctx.fillText(line.label, Math.min(x + 6, width - pad.right - 78), pad.top + 14);
          }
        }
      }
      if (options.referenceLines) {
        for (const line of options.referenceLines) {
          const y = yForValue(line.value, line.axis || "left");
          ctx.strokeStyle = line.color || "rgba(15, 23, 42, 0.35)";
          ctx.lineWidth = line.width || 1.4;
          ctx.setLineDash(line.dash || [4, 4]);
          ctx.beginPath();
          ctx.moveTo(pad.left, y);
          ctx.lineTo(pad.left + chartWidth, y);
          ctx.stroke();
          ctx.setLineDash([]);
          if (line.label) {
            ctx.fillStyle = line.color || "#334155";
            ctx.font = "bold 12px Segoe UI";
            ctx.fillText(line.label, pad.left + 8, y - 6);
          }
        }
      }
      ctx.strokeStyle = "#94a3b8";
      ctx.strokeRect(pad.left, pad.top, chartWidth, chartHeight);
      ctx.fillStyle = "#5b6775";
      ctx.font = "12px Segoe UI";
      ctx.fillText(leftAxis.max.toFixed(1), 6, pad.top + 4);
      ctx.fillText(leftAxis.min.toFixed(1), 6, pad.top + chartHeight);
      if (rightAxis) {
        ctx.textAlign = "right";
        ctx.fillText(rightAxis.max.toFixed(1), width - 6, pad.top + 4);
        ctx.fillText(rightAxis.min.toFixed(1), width - 6, pad.top + chartHeight);
        ctx.textAlign = "left";
      }
      ctx.fillText("時間", width - 32, height - 8);

      function drawSeries(item, endIndex, alpha = 1.0) {
        const lastIndex = Math.min(endIndex, item.values.length - 1);
        if (lastIndex < 0) return;
        ctx.save();
        ctx.globalAlpha = (item.alpha !== undefined ? item.alpha : 1.0) * alpha;
        ctx.strokeStyle = item.color;
        ctx.lineWidth = item.width || 2;
        ctx.setLineDash(item.dash || []);
        let drawing = false;
        item.values.slice(0, lastIndex + 1).forEach((value, index) => {
          if (value === null || value === undefined) {
            if (drawing) {
              ctx.stroke();
              ctx.beginPath();
              drawing = false;
            }
            return;
          }
          const x = pad.left + (index / Math.max(1, item.values.length - 1)) * chartWidth;
          const y = yForValue(value, item.axis || "left");
          if (!drawing) {
            ctx.beginPath();
            ctx.moveTo(x, y);
            drawing = true;
          } else {
            ctx.lineTo(x, y);
          }
        });
        if (drawing) ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }

      const hasReveal = options.revealUntil !== undefined && options.revealUntil !== null;
      for (const item of series) {
        if (hasReveal) {
          const fadedAlpha = item.dash && item.dash.length > 0 ? 0.22 : 0.14;
          drawSeries(item, item.values.length - 1, fadedAlpha);
          drawSeries(item, options.revealUntil, 1.0);
        } else {
          drawSeries(item, item.values.length - 1, 1.0);
        }
      }

      if (options.currentIndex !== undefined && options.currentIndex !== null) {
        const x = pad.left + (options.currentIndex / Math.max(1, options.length - 1)) * chartWidth;
        ctx.strokeStyle = "rgba(15, 23, 42, 0.45)";
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x, pad.top);
        ctx.lineTo(x, pad.top + chartHeight);
        ctx.stroke();
        ctx.setLineDash([]);
        if (options.markerValues) {
          for (const marker of options.markerValues) {
            if (options.currentIndex >= marker.values.length) continue;
            const y = yForValue(marker.values[options.currentIndex], marker.axis || "left");
            ctx.fillStyle = marker.color;
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
      drawLegend(ctx, series, pad.left + 10, pad.top + 16);
    }

    function buildInfoCard(label, value) { return `<div class="mini"><div class="k">${label}</div><div class="v">${value}</div></div>`; }

    function setModeBadge(row) {
      const badge = document.getElementById("mode-badge");
      if (!badge) return;
      const isFallback = Boolean(row && row.mpc_fallback_active);
      const isSoft = Boolean(row && row.mpc_soft_constraint_active);
      let modeClass = "";
      let text = "通常";
      if (isFallback) {
        modeClass = "fallback";
        text = "フォールバック";
      } else if (isSoft) {
        modeClass = "soft";
        text = "ソフト制約";
      }
      badge.className = `mode-badge ${modeClass}`.trim();
      badge.textContent = text;
    }

    function renderControlBars(step) {
      const bars = document.getElementById("control-bars");
      const plan = data.plans[step].planned_controls.slice(0, 9);
      bars.innerHTML = "";
      plan.forEach((value, index) => {
        const div = document.createElement("div");
        div.className = index === 0 ? "bar first" : "bar";
        div.style.height = `${Math.max(8, Math.round(value * 1.35))}px`;
        div.innerHTML = `<span class="bar-label">${index === 0 ? "今すぐ適用" : `+${index}`}: ${value.toFixed(0)}%</span>`;
        bars.appendChild(div);
      });
    }

    function renderCharts(currentStep = null) {
      const timeline = data.timeline;
      const softConstraintBands = buildSoftConstraintBands();
      drawLineChart("temp-chart", [
        makeSeries(timeline.map(row => row.mpc_actual_room_temp_c), COLORS.blue, "MPC 仮想温度", 2.6),
        makeSeries(timeline.map(row => row.mpc_measured_room_temp_c), COLORS.gray, "観測温度", 1.6, [3, 3]),
        makeSeries(timeline.map(row => row.pid_room_temp_c), COLORS.red, "PID 仮想温度", 2.2),
        makeSeries(new Array(timeline.length).fill(data.config.comfort_low), COLORS.accent, "快適下限", 1.5, [6, 4]),
        makeSeries(new Array(timeline.length).fill(data.config.comfort_high), COLORS.accent, "快適上限", 1.5, [6, 4]),
        makeSeries(new Array(timeline.length).fill(data.config.min_safe_temp), COLORS.gold, "安全下限", 1.4, [2, 4]),
      ], {
        minValue: 17, maxValue: 25.5, length: timeline.length,
        bands: [{ min: data.config.comfort_low, max: data.config.comfort_high, color: COLORS.comfort }],
        verticalLines: [{
          index: data.narrative.front_step,
          color: COLORS.red,
          label: "寒波到来",
          bandWidth: 1.5,
          bandColor: "rgba(217, 72, 65, 0.10)",
        }, ...softConstraintBands],
        currentIndex: currentStep, revealUntil: currentStep,
        markerValues: [
          { values: timeline.map(row => row.mpc_actual_room_temp_c), color: COLORS.blue },
          { values: timeline.map(row => row.pid_room_temp_c), color: COLORS.red },
        ],
      });
      drawLineChart("power-chart", [
        makeSeries(timeline.map(row => row.mpc_power_pct), COLORS.blue, "MPC 出力 %", 2.4),
        makeSeries(timeline.map(row => row.pid_power_pct), COLORS.red, "PID 出力 %", 2.2),
        { ...makeSeries(timeline.map(row => row.outdoor_temp_c), COLORS.accent, "外気温 C", 2.0), axis: "right" },
      ], {
        minValue: 0, maxValue: 105,
        rightAxis: { minValue: -8, maxValue: 15, label: "外気温 C" },
        referenceLines: [
          { value: 0, color: "rgba(37, 99, 235, 0.32)", label: "出力 0%", dash: [2, 6] },
          { value: 0, axis: "right", color: "rgba(19, 111, 99, 0.7)", label: "外気温 0℃", dash: [8, 4] },
        ],
        length: timeline.length,
        verticalLines: [{
          index: data.narrative.front_step,
          color: COLORS.red,
          label: "寒波到来",
          bandWidth: 1.5,
          bandColor: "rgba(217, 72, 65, 0.10)",
        }, ...softConstraintBands],
        currentIndex: currentStep, revealUntil: currentStep,
        markerValues: [
          { values: timeline.map(row => row.mpc_power_pct), color: COLORS.blue },
          { values: timeline.map(row => row.pid_power_pct), color: COLORS.red },
          { values: timeline.map(row => row.outdoor_temp_c), color: COLORS.accent, axis: "right" },
        ],
      });
      drawLineChart("bias-chart", [
        makeSeries(timeline.map(row => row.mpc_residual_c), COLORS.red, "1ステップ予測誤差", 2.2),
        makeSeries(timeline.map(row => row.mpc_bias_correction_c), COLORS.blue, "補正量 z[k]", 2.4),
      ], {
        minValue: -1.8, maxValue: 1.8, length: timeline.length,
        verticalLines: [{
          index: data.narrative.front_step,
          color: COLORS.red,
          label: "寒波到来",
          bandWidth: 1.5,
          bandColor: "rgba(217, 72, 65, 0.10)",
        }],
        currentIndex: currentStep, revealUntil: currentStep,
        markerValues: [
          { values: timeline.map(row => row.mpc_residual_c), color: COLORS.red },
          { values: timeline.map(row => row.mpc_bias_correction_c), color: COLORS.blue },
        ],
      });
      const solveTimes = timeline.map(row => row.mpc_solve_time_ms);
      const timingMax = Math.max(1, ...solveTimes);
      drawLineChart("timing-chart", [
        makeSeries(solveTimes, COLORS.gold, "1 step の計算時間 ms", 2.6),
        makeSeries(new Array(timeline.length).fill(data.metrics.mpc_avg_solve_time_ms), COLORS.gray, "平均", 1.5, [6, 4]),
      ], {
        minValue: 0,
        maxValue: Math.max(2, timingMax * 1.15),
        length: timeline.length,
        verticalLines: [{
          index: data.narrative.front_step,
          color: COLORS.red,
          label: "寒波到来",
          bandWidth: 1.5,
          bandColor: "rgba(217, 72, 65, 0.10)",
        }],
        currentIndex: currentStep, revealUntil: currentStep,
        markerValues: [
          { values: solveTimes, color: COLORS.gold },
        ],
      });
      setupMeta();
    }

    function buildHorizonOverlaySeries(step) {
      const recentCount = 6;
      const startStep = Math.max(0, step - recentCount + 1);
      const overlays = [];
      for (let current = startStep; current <= step; current += 1) {
        const plan = data.plans[current];
        const maxLen = data.timeline.length;
        const aligned = new Array(maxLen).fill(null);
        plan.planned_temps.forEach((value, offset) => {
          const index = current + offset;
          if (index < maxLen) aligned[index] = value;
        });
        overlays.push({
          step: current,
          values: aligned,
          alpha: current === step ? 0.95 : 0.16 + 0.10 * (current - startStep),
          width: current === step ? 2.8 : 1.5,
          color: current === step ? COLORS.blue : "rgba(37, 99, 235, 1)",
          label: current === step ? `現在の予測 step ${current}` : (current === startStep ? "過去の予測群" : ""),
        });
      }
      return overlays;
    }

    function renderStep(step) {
      const row = data.timeline[step];
      setText("step-readout", `step ${step} / ${row.hour.toFixed(2)} 時間`);
      setModeBadge(row);
      renderCharts(step);
      if (row.mpc_fallback_active) {
        setSoftZoneState(false);
        setText("experiment-status", `step ${step} はフォールバック中です。現在の仮想室温は ${row.mpc_actual_room_temp_c.toFixed(2)} C、操作量は ${row.mpc_power_pct.toFixed(0)} %、予測誤差は ${row.mpc_residual_c.toFixed(2)} C、計算時間は ${row.mpc_solve_time_ms.toFixed(2)} ms です。`);
      } else if (row.mpc_soft_constraint_active) {
        setSoftZoneState(
          true,
          `ここはソフト制約ゾーンです。安全下限 ${data.config.min_safe_temp.toFixed(1)} C をこの step では守れないため、罰則付きで最善手を選んでいます。現在の短不足は ${row.mpc_soft_constraint_shortfall_c.toFixed(2)} C、操作量は ${row.mpc_power_pct.toFixed(0)} % です。`
        );
        setText("experiment-status", `step ${step} はソフト制約ゾーンです。現在の仮想室温は ${row.mpc_actual_room_temp_c.toFixed(2)} C、操作量は ${row.mpc_power_pct.toFixed(0)} %、予測誤差は ${row.mpc_residual_c.toFixed(2)} C、計算時間は ${row.mpc_solve_time_ms.toFixed(2)} ms です。`);
      } else {
        setSoftZoneState(false);
        setText("experiment-status", `step ${step} を表示中です。現在の仮想室温は ${row.mpc_actual_room_temp_c.toFixed(2)} C、操作量は ${row.mpc_power_pct.toFixed(0)} %、予測誤差は ${row.mpc_residual_c.toFixed(2)} C、計算時間は ${row.mpc_solve_time_ms.toFixed(2)} ms です。`);
      }
      document.getElementById("step-info").innerHTML =
        buildInfoCard("観測温度 y[k]", `${row.mpc_measured_room_temp_c.toFixed(2)} C`) +
        buildInfoCard("仮想温度 x[k]", `${row.mpc_actual_room_temp_c.toFixed(2)} C`) +
        buildInfoCard("操作量 u[k]", `${row.mpc_power_pct.toFixed(0)} %`) +
        buildInfoCard("予測誤差", `${row.mpc_residual_c.toFixed(2)} C`) +
        buildInfoCard("補正 z[k]", `${row.mpc_bias_correction_c.toFixed(2)} C`) +
        buildInfoCard("フォールバック", row.mpc_fallback_active ? "発動中" : "通常") +
        buildInfoCard("ソフト制約", row.mpc_soft_constraint_active ? "発動中" : "通常") +
        buildInfoCard("計算時間", `${row.mpc_solve_time_ms.toFixed(2)} ms`);
      renderControlBars(step);
      const realized = new Array(data.timeline.length).fill(null);
      data.timeline.forEach((timelineRow, index) => {
        realized[index] = timelineRow.mpc_actual_room_temp_c;
      });
      const comfortLow = new Array(data.timeline.length).fill(data.config.comfort_low);
      const comfortHigh = new Array(data.timeline.length).fill(data.config.comfort_high);
      const overlaySeries = buildHorizonOverlaySeries(step).map(item => ({
        values: item.values,
        color: item.color,
        label: item.label,
        width: item.width,
        alpha: item.alpha,
      }));
      drawLineChart("horizon-chart", [
        ...overlaySeries,
        { values: realized, color: COLORS.red, label: "仮想温度推移", width: 2.4 },
        { values: comfortLow, color: COLORS.accent, label: "快適下限", width: 1.4, dash: [6, 4] },
        { values: comfortHigh, color: COLORS.accent, label: "快適上限", width: 1.4, dash: [6, 4] },
      ], {
        minValue: 18,
        maxValue: 25.5,
        length: data.timeline.length,
        currentIndex: step,
        revealUntil: step + data.config.mpc_horizon_steps,
      });
    }

    function setSliderDefaults() {
      const slider = document.getElementById("step-slider");
      slider.max = String(data.timeline.length - 1);
      slider.value = "0";
      renderStep(0);
    }

    function stopPlay() {
      if (playTimer) {
        window.clearInterval(playTimer);
        playTimer = null;
      }
    }

    function startPlay() {
      stopPlay();
      const slider = document.getElementById("step-slider");
      playTimer = window.setInterval(() => {
        const nextValue = Math.min(Number(slider.value) + 1, Number(slider.max));
        slider.value = String(nextValue);
        renderStep(nextValue);
        if (nextValue >= Number(slider.max)) stopPlay();
      }, 350);
    }

    async function runExperiment(statusText) {
      stopPlay();
      setText("experiment-status", statusText || "Python モデルで再計算しています...");
      try {
        const requestConfig = readConfig();
        const response = await fetch(API_PATH, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestConfig),
        });
        if (!response.ok) {
          setText("experiment-status", "再計算に失敗しました。サーバー側ログを確認してください。");
          return;
        }
        data = await response.json();
        renderTerms();
        setSliderDefaults();
        setText(
          "experiment-status",
          `再計算を反映しました。寒波開始は step ${data.config.cold_front_start_step}、表示ラベルも同じ値に更新されています。`
        );
      } catch (error) {
        setText(
          "experiment-status",
          "再計算に失敗しました。index.html を直接開くのではなく、`uv run smart_ac_dashboard.py` で起動した URL を開いてください。"
        );
        showWarning("この画面はサーバー経由で開く必要があります。`uv run smart_ac_dashboard.py` が表示した http://127.0.0.1:xxxx/index.html を開いてください。");
      }
    }

    function resetExperiment() {
      runExperiment("現在の入力値で Python モデルを再計算しています...");
    }

    function init() {
      if (window.location.protocol === "file:") {
        showWarning("いまはファイル直開きです。この状態では『リセット』で Python 再計算できません。`uv run smart_ac_dashboard.py` が表示した URL を開いてください。");
      }
      seedFormFromConfig(baseData.config);
      renderTerms();
      setSliderDefaults();
      document.getElementById("step-slider").addEventListener("input", event => renderStep(Number(event.target.value)));
      document.getElementById("play-btn").addEventListener("click", startPlay);
      document.getElementById("pause-btn").addEventListener("click", stopPlay);
      document.getElementById("reset-btn").addEventListener("click", resetExperiment);
    }

    init();
  </script>
</body>
</html>
"""


def build_html(initial_data: dict, api_path: str = "/api/simulate") -> str:
    return HTML_TEMPLATE.replace("__DATA__", json.dumps(initial_data)).replace("__API_PATH__", api_path)


def generate_dashboard(output_dir: Path, cfg: Scenario) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    initial_data = SmartACModel(cfg).simulate()
    html_path = output_dir / "index.html"
    json_path = output_dir / "dashboard_data.json"
    html_path.write_text(build_html(initial_data), encoding="utf-8")
    json_path.write_text(json.dumps(initial_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return html_path


def bind_server(host: str, port: int, handler: type[SimpleHTTPRequestHandler]) -> ThreadingHTTPServer:
    for candidate_port in range(port, port + 20):
        try:
            return ThreadingHTTPServer((host, candidate_port), handler)
        except OSError as exc:
            if exc.errno != 98:
                raise
    raise SocketError(f"Could not bind an HTTP server on ports {port}-{port + 19}")


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_POST(self) -> None:
        if self.path != "/api/simulate":
            self.send_error(404, "Unknown API endpoint")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
            result = SmartACModel.from_mapping(payload).simulate()
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        except Exception as exc:  # pragma: no cover - defensive for local UI
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_directory(directory: Path, host: str, port: int) -> None:
    handler = partial(DashboardRequestHandler, directory=str(directory))
    with bind_server(host, port, handler) as server:
        bound_host, bound_port = server.server_address
        print(f"Serving dashboard at http://{bound_host}:{bound_port}/index.html")
        print("Press Ctrl-C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and optionally serve the Smart-AC MPC dashboard")
    parser.add_argument("--output-dir", default="artifacts/project_smart_ac_dashboard", help="Output directory")
    parser.add_argument("--build-only", action="store_true", help="Generate files only and exit")
    parser.add_argument("--host", default="127.0.0.1", help="Host for local server")
    parser.add_argument("--port", type=int, default=8765, help="Port for local server")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    html_path = generate_dashboard(output_dir, Scenario())
    print(f"Dashboard HTML: {html_path}")
    print(f"Dashboard JSON: {output_dir / 'dashboard_data.json'}")
    if args.build_only:
        return
    serve_directory(output_dir, args.host, args.port)


if __name__ == "__main__":
    main()
