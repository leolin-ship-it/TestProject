/**
 * 風控追殺局分析核心邏輯（對應 convert_to_excel.py）
 */

const COLUMN_MAPPING = {
  walletType: "錢包類型",
  gameEndTime: "結算時間",
  account: "玩家帳號(原)",
  opValue: "操作編號",
  gameId: "遊戲 ID",
  gameName: "遊戲名稱",
  roomName: "房間/廳館",
  tableId: "桌號",
  chairId: "座位",
  category: "遊戲分類",
  language: "語系",
  currency: "幣別",
  gameNo: "局號",
  banker: "莊閒",
  roomType: "房間類型/模式",
  allBet: "投注額",
  revenue: "派彩",
  score: "結算後餘額",
  cellScore: "房間底注",
  profit: "玩家輸贏",
  gameUserNO: "用戶編號",
  orderTime: "下單時間",
  playerAccount: "玩家帳號",
  type: "交易類型",
  originScore: "異動前餘額",
  addScore: "額度異動",
  newScore: "異動後餘額",
  ip: "IP",
  status: "狀態",
  createUser: "建立者",
  agentAccount: "代理帳號",
  orderId: "訂單號",
  channelId: "渠道 ID",
  orderType: "訂單類型",
  orderStatus: "訂單狀態",
  curScore: "當前分數",
  orderIP: "訂單 IP",
  channelName: "渠道名稱",
  timezone: "時區",
};

const KILL_MODES = new Set(["ptk", "K", "T", "B"]);
const ALERT_THRESHOLD = 0.05;

const NUMERIC_COLS = new Set([
  "投注額", "派彩", "結算後餘額", "房間底注", "玩家輸贏",
  "異動前餘額", "額度異動", "異動後餘額", "當前分數",
]);

const DROP_COLUMNS = new Set([
  "渠道 ID", "渠道名稱", "時區", "IP", "訂單 IP", "語系", "錢包類型", "建立者", "RTP(數值)",
]);

const PREFERRED_ORDER = [
  "結算時間", "玩家帳號", "代理帳號", "遊戲名稱", "房間/廳館", "房間類型/模式",
  "局號", "莊閒", "投注額", "派彩", "玩家輸贏", "RTP(%)", "結算後餘額", "交易類型", "額度異動", "狀態", "訂單號",
];

function parseNumeric(value) {
  if (value == null || value === "") return NaN;
  const n = parseFloat(String(value).replace(/,/g, ""));
  return Number.isFinite(n) ? n : NaN;
}

function renameRow(row) {
  const out = {};
  for (const [key, val] of Object.entries(row)) {
    out[COLUMN_MAPPING[key] ?? key] = val;
  }
  return out;
}

function normalizeRows(raw) {
  if (Array.isArray(raw)) return raw;
  if (raw && Array.isArray(raw.rows)) return raw.rows;
  return [];
}

function transformRows(rows) {
  const mapped = rows.map(renameRow);

  for (const row of mapped) {
    for (const col of NUMERIC_COLS) {
      if (col in row) row[col] = parseNumeric(row[col]);
    }
    if ("投注額" in row && "派彩" in row) {
      const bet = row["投注額"];
      const rtp = bet > 0 ? row["派彩"] / bet : 0;
      row["RTP(數值)"] = rtp;
      row["RTP(%)"] = `${(rtp * 100).toFixed(2)}%`;
    }
  }

  mapped.sort((a, b) => {
    const ta = new Date(a["結算時間"] || 0).getTime();
    const tb = new Date(b["結算時間"] || 0).getTime();
    return tb - ta;
  });

  return mapped.map((row) => {
    const cleaned = {};
    for (const [k, v] of Object.entries(row)) {
      if (!DROP_COLUMNS.has(k)) cleaned[k] = v;
    }
    return cleaned;
  });
}

function analyzeRisk(rows) {
  const hasRequired = rows.some(
    (r) => "房間類型/模式" in r && "玩家輸贏" in r && "遊戲名稱" in r
  );
  if (!hasRequired) return [];

  const byGame = new Map();
  for (const row of rows) {
    const game = row["遊戲名稱"] ?? "未知";
    if (!byGame.has(game)) byGame.set(game, []);
    byGame.get(game).push(row);
  }

  const results = [];
  for (const [gameName, group] of byGame) {
    const totalGameRounds = group.length;
    let nonNdRounds = 0;
    let totalKillRounds = 0;
    let winRounds = 0;

    for (const row of group) {
      const mode = String(row["房間類型/模式"] ?? "").trim();
      if (mode !== "N" && mode !== "D") nonNdRounds += 1;
      if (KILL_MODES.has(mode)) {
        totalKillRounds += 1;
        const profit = row["玩家輸贏"];
        if (typeof profit === "number" && profit > 0) winRounds += 1;
      }
    }

    const killRatio = totalGameRounds > 0 ? totalKillRounds / totalGameRounds : 0;
    const winRate = totalKillRounds > 0 ? winRounds / totalKillRounds : 0;

    results.push({
      遊戲名稱: gameName,
      總遊玩局數: totalGameRounds,
      "一般/其他局數": totalGameRounds - totalKillRounds,
      非N與D以外局數: nonNdRounds,
      追殺局總局數: totalKillRounds,
      殺局佔比: `${(killRatio * 100).toFixed(2)}%`,
      玩家贏錢局數: winRounds,
      "破殺率(勝率)": `${(winRate * 100).toFixed(2)}%`,
      winRateNum: winRate,
      killRatioNum: killRatio,
      風控警示: winRate > ALERT_THRESHOLD && totalKillRounds > 0 ? "🚨 異常(需關注)" : "正常",
      isAlert: winRate > ALERT_THRESHOLD && totalKillRounds > 0,
    });
  }

  return results.sort((a, b) => b.winRateNum - a.winRateNum);
}

function computeSummary(analysis) {
  const totalGame = analysis.reduce((s, r) => s + r.總遊玩局數, 0);
  const totalKill = analysis.reduce((s, r) => s + r.追殺局總局數, 0);
  const totalWins = analysis.reduce((s, r) => s + r.玩家贏錢局數, 0);
  const alerts = analysis.filter((r) => r.isAlert).length;

  return {
    gameCount: analysis.length,
    totalGame,
    totalKill,
    totalWins,
    killRatio: totalGame > 0 ? totalKill / totalGame : 0,
    winRate: totalKill > 0 ? totalWins / totalKill : 0,
    alerts,
  };
}

async function fetchJsonFromUrl(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadFromFiles(fileList) {
  const allRows = [];
  for (const file of fileList) {
    const text = await file.text();
    const data = JSON.parse(text);
    allRows.push(...normalizeRows(data));
  }
  return allRows;
}

async function loadFromUrls(urls) {
  const allRows = [];
  for (const url of urls) {
    const data = await fetchJsonFromUrl(url.trim());
    allRows.push(...normalizeRows(data));
  }
  return allRows;
}

function processAll(rawRows) {
  if (!rawRows.length) {
    return { rows: [], analysis: [], summary: null, error: "沒有資料可供分析" };
  }
  const rows = transformRows(rawRows);
  const analysis = analyzeRisk(rows);
  const summary = computeSummary(analysis);
  return { rows, analysis, summary, error: null };
}

window.RiskAnalyzer = {
  processAll,
  loadFromFiles,
  loadFromUrls,
  ALERT_THRESHOLD,
};
