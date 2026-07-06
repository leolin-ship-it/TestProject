/** UI 邏輯與 Chart.js 渲染 */

let chartInstance = null;
let lastResult = null;

const $ = (sel) => document.querySelector(sel);

function showStatus(msg, type = "info") {
  const el = $("#status");
  el.textContent = msg;
  el.className = `show ${type}`;
}

function hideStatus() {
  $("#status").className = "";
}

function showSections(show) {
  for (const id of ["summarySection", "chartSection", "resultSection", "detailSection"]) {
    $(`#${id}`).classList.toggle("hidden", !show);
  }
}

function renderSummary(summary) {
  const grid = $("#statsGrid");
  const items = [
    { label: "分析遊戲數", value: summary.gameCount },
    { label: "總遊玩局數", value: summary.totalGame.toLocaleString() },
    { label: "追殺局總數", value: summary.totalKill.toLocaleString() },
    { label: "追殺局佔比", value: `${(summary.killRatio * 100).toFixed(2)}%` },
    { label: "平均破殺率", value: `${(summary.winRate * 100).toFixed(2)}%` },
    { label: "異常遊戲數", value: summary.alerts, alert: summary.alerts > 0 },
  ];
  grid.innerHTML = items.map((it) => `
    <div class="stat-box${it.alert ? " alert" : ""}">
      <div class="value">${it.value}</div>
      <div class="label">${it.label}</div>
    </div>
  `).join("");
}

function renderChart(analysis) {
  const ctx = $("#riskChart").getContext("2d");
  if (chartInstance) chartInstance.destroy();

  const labels = analysis.map((r) => r.遊戲名稱);
  const killData = analysis.map((r) => r.追殺局總局數);
  const normalData = analysis.map((r) => r["一般/其他局數"]);

  chartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "追殺局",
          data: killData,
          backgroundColor: "rgba(239, 68, 68, 0.75)",
        },
        {
          label: "一般/其他局",
          data: normalData,
          backgroundColor: "rgba(34, 197, 94, 0.75)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#e7ecf3" } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: {
          stacked: true,
          ticks: { color: "#8b9cb3", maxRotation: 45 },
          grid: { color: "rgba(45, 58, 79, 0.5)" },
        },
        y: {
          stacked: true,
          ticks: { color: "#8b9cb3" },
          grid: { color: "rgba(45, 58, 79, 0.5)" },
        },
      },
    },
  });
}

function renderTable(analysis) {
  const body = $("#resultBody");
  body.innerHTML = analysis.map((r) => `
    <tr class="${r.isAlert ? "alert-row" : ""}">
      <td>${esc(r.遊戲名稱)}</td>
      <td>${r.總遊玩局數}</td>
      <td>${r.追殺局總局數}</td>
      <td>${r.殺局佔比}</td>
      <td>${r.玩家贏錢局數}</td>
      <td>${r["破殺率(勝率)"]}</td>
      <td><span class="badge ${r.isAlert ? "badge-warn" : "badge-ok"}">${esc(r.風控警示)}</span></td>
    </tr>
  `).join("");
}

function renderDetail(rows) {
  const preview = rows.slice(0, 100);
  if (!preview.length) return;

  const cols = Object.keys(preview[0]);
  $("#detailHead").innerHTML = `<tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>`;
  $("#detailBody").innerHTML = preview.map((row) =>
    `<tr>${cols.map((c) => `<td>${esc(row[c])}</td>`).join("")}</tr>`
  ).join("");
}

function esc(val) {
  if (val == null) return "";
  return String(val)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function displayResult(result) {
  lastResult = result;
  if (result.error) {
    showStatus(result.error, "error");
    showSections(false);
    return;
  }

  const alertCount = result.analysis.filter((r) => r.isAlert).length;
  showStatus(
    `✅ 分析完成：${result.rows.length} 筆資料，${result.analysis.length} 款遊戲${alertCount ? `，${alertCount} 款異常` : ""}`,
    alertCount ? "error" : "success"
  );

  renderSummary(result.summary);
  renderChart(result.analysis);
  renderTable(result.analysis);
  renderDetail(result.rows);
  showSections(true);
}

async function handleFiles(files) {
  if (!files.length) return;
  showStatus("正在讀取檔案...", "info");
  try {
    const raw = await RiskAnalyzer.loadFromFiles(files);
    displayResult(RiskAnalyzer.processAll(raw));
  } catch (e) {
    showStatus(`❌ 讀取失敗：${e.message}`, "error");
  }
}

async function handleFetch() {
  const url = $("#apiUrl").value.trim();
  if (!url) {
    showStatus("請輸入 API 網址", "error");
    return;
  }
  showStatus("正在從 API 載入...", "info");
  try {
    const raw = await RiskAnalyzer.loadFromUrls([url]);
    displayResult(RiskAnalyzer.processAll(raw));
  } catch (e) {
    showStatus(`❌ API 載入失敗：${e.message}（內網 API 請改用 JSON 上傳）`, "error");
  }
}

async function handleSample() {
  showStatus("正在載入範例資料...", "info");
  try {
    const res = await fetch("sample-data.json");
    const data = await res.json();
    const rows = Array.isArray(data) ? data : (data.rows ?? []);
    displayResult(RiskAnalyzer.processAll(rows));
  } catch (e) {
    showStatus(`❌ 範例載入失敗：${e.message}`, "error");
  }
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function exportHtml() {
  if (!lastResult || lastResult.error) return;
  const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  const rows = lastResult.analysis.map(({ winRateNum, killRatioNum, isAlert, ...rest }) => rest);
  const html = `<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8"><title>風控報告 ${ts}</title>
<style>
body{font-family:"Microsoft JhengHei",sans-serif;padding:2rem;background:#f5f5f5}
h1{color:#1e3a5f}table{border-collapse:collapse;width:100%;background:#fff;margin-top:1rem}
th,td{border:1px solid #ddd;padding:8px 12px;text-align:left}
th{background:#1e3a5f;color:#fff}.alert{background:#fee2e2}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin:1rem 0}
.box{background:#fff;padding:1rem;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.box strong{display:block;font-size:1.4rem;color:#2563eb}
</style></head><body>
<h1>🎰 風控追殺局分析報告</h1>
<p>產生時間：${new Date().toLocaleString("zh-TW")}</p>
<div class="summary">
  <div class="box"><strong>${lastResult.summary.totalGame}</strong>總遊玩局數</div>
  <div class="box"><strong>${lastResult.summary.totalKill}</strong>追殺局總數</div>
  <div class="box"><strong>${(lastResult.summary.winRate * 100).toFixed(2)}%</strong>平均破殺率</div>
  <div class="box"><strong>${lastResult.summary.alerts}</strong>異常遊戲數</div>
</div>
<table><thead><tr>
  <th>遊戲名稱</th><th>總局數</th><th>追殺局</th><th>殺局佔比</th><th>贏錢局數</th><th>破殺率</th><th>警示</th>
</tr></thead><tbody>
${rows.map((r) => `<tr class="${r["風控警示"].includes("異常") ? "alert" : ""}">
  <td>${esc(r.遊戲名稱)}</td><td>${r.總遊玩局數}</td><td>${r.追殺局總局數}</td>
  <td>${r.殺局佔比}</td><td>${r.玩家贏錢局數}</td><td>${r["破殺率(勝率)"]}</td><td>${esc(r.風控警示)}</td>
</tr>`).join("")}
</tbody></table></body></html>`;
  downloadBlob(html, `風控報告_${ts}.html`, "text/html;charset=utf-8");
}

function exportJson() {
  if (!lastResult || lastResult.error) return;
  const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  const payload = {
    generatedAt: new Date().toISOString(),
    summary: lastResult.summary,
    analysis: lastResult.analysis.map(({ winRateNum, killRatioNum, isAlert, ...rest }) => rest),
  };
  downloadBlob(JSON.stringify(payload, null, 2), `風控分析_${ts}.json`, "application/json");
}

// 事件綁定
const dropZone = $("#dropZone");
const fileInput = $("#fileInput");

dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => handleFiles([...e.target.files]));

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  handleFiles([...e.dataTransfer.files].filter((f) => f.name.endsWith(".json") || f.type.includes("json")));
});

$("#btnFetch").addEventListener("click", handleFetch);
$("#btnSample").addEventListener("click", handleSample);
$("#btnExportHtml").addEventListener("click", exportHtml);
$("#btnExportJson").addEventListener("click", exportJson);

$("#apiUrl").addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleFetch();
});
