const MIN_SAMPLE_SIZE = 1000;
const PAGE_SIZE = 20;

const state = {
  games: [],
  selectedGameId: null,
  currentPage: 1,
};

const elements = {
  apiBaseInput: document.querySelector("#apiBaseInput"),
  loadButton: document.querySelector("#loadButton"),
  statusMessage: document.querySelector("#statusMessage"),
  gameSearchInput: document.querySelector("#gameSearchInput"),
  gamesContainer: document.querySelector("#gamesContainer"),
  selectedGameBadge: document.querySelector("#selectedGameBadge"),
  gameDetailContainer: document.querySelector("#gameDetailContainer"),
  sentimentReliability: document.querySelector("#sentimentReliability"),
  sentimentContainer: document.querySelector("#sentimentContainer"),
  topicsContainer: document.querySelector("#topicsContainer"),
  correlationContainer: document.querySelector("#correlationContainer"),
  logList: document.querySelector("#logList"),
};

function getApiBase() {
  return elements.apiBaseInput.value.trim().replace(/\/+$/, "");
}

function setStatus(message, isError = false) {
  elements.statusMessage.textContent = message;
  elements.statusMessage.classList.toggle("error", isError);
}

function resetLog() {
  elements.logList.innerHTML = "";
}

function logResult(label, payload, status = "success") {
  const labels = { success: "success", empty: "no data", error: "failed" };
  const item = document.createElement("li");
  item.textContent = `${label}: ${labels[status]}`;
  elements.logList.appendChild(item);
  console[status === "error" ? "error" : "log"](`[${label}]`, payload);
}

async function requestJson(path, label) {
  const response = await fetch(`${getApiBase()}${path}`);
  if (!response.ok) {
    const error = new Error(`${label} request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  const data = await response.json();
  logResult(`${label} ${path}`, data);
  return data;
}

async function requestOptional(path, label) {
  try {
    return await requestJson(path, label);
  } catch (error) {
    logResult(`${label} ${path}`, error, error.status === 404 ? "empty" : "error");
    return null;
  }
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.results)) return value.results;
  if (Array.isArray(value?.data)) return value.data;
  return value ? [value] : [];
}

function pick(object, keys, fallback = "-") {
  for (const key of keys) {
    const value = object?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return fallback;
}

function getGameId(game) {
  return pick(game, ["app_id", "game_id", "id"], null);
}

function escapeHtml(value) {
  return String(value ?? "-")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  if (value === "-" || value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : String(value);
}

function formatRatio(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(1)}%` : "-";
}

function formatCurrency(value) {
  if (value === "-" || value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (number === 0) return "Free";
  return `$${(number / 100).toFixed(2)}`;
}

function formatOwners(value) {
  const owners = String(value ?? "-");
  return owners === "-" ? "-" : `${owners} users`;
}

function hasMarketData(game) {
  return (
    pick(game, ["owners", "owner_count"], null) !== null ||
    pick(game, ["price", "initial_price"], null) !== null ||
    Number(pick(game, ["positive_reviews", "positive", "positive_count"], 0)) > 0 ||
    Number(pick(game, ["negative_reviews", "negative", "negative_count"], 0)) > 0
  );
}

function getReliability(sampleSize) {
  const size = Number(sampleSize || 0);
  if (size < 1000) return "Low";
  if (size < 5000) return "Medium";
  return "High";
}

function warningBox(message) {
  const text = message || "The current sample size is small, so reliability may be low.";
  return `<div class="warning-box">${escapeHtml(text)}</div>`;
}

function getFilteredGames() {
  const searchTerm = elements.gameSearchInput.value.trim().toLowerCase();
  return state.games.filter((game) => {
    const name = pick(game, ["name", "title"], "");
    const genre = pick(game, ["genre", "genres"], "");
    return `${name} ${genre}`.toLowerCase().includes(searchTerm);
  });
}

function renderPagination(totalItems) {
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
  state.currentPage = Math.min(Math.max(1, state.currentPage), totalPages);
  const start = totalItems === 0 ? 0 : (state.currentPage - 1) * PAGE_SIZE + 1;
  const end = Math.min(totalItems, state.currentPage * PAGE_SIZE);

  return `
    <div class="pagination">
      <span>${formatNumber(start)}-${formatNumber(end)} / ${formatNumber(totalItems)} games</span>
      <div class="pagination-buttons">
        <button type="button" data-page-action="prev" ${state.currentPage <= 1 ? "disabled" : ""}>Prev</button>
        <span>Page ${state.currentPage} / ${totalPages}</span>
        <button type="button" data-page-action="next" ${state.currentPage >= totalPages ? "disabled" : ""}>Next</button>
      </div>
    </div>
  `;
}

function renderGames() {
  const games = getFilteredGames();
  if (games.length === 0) {
    elements.gamesContainer.innerHTML = '<p class="empty-message">No games to display.</p>';
    return;
  }

  const startIndex = (state.currentPage - 1) * PAGE_SIZE;
  const rows = games
    .slice(startIndex, startIndex + PAGE_SIZE)
    .map((game) => {
      const gameId = getGameId(game);
      const active = String(gameId) === String(state.selectedGameId) ? " active" : "";
      const dataStatus = hasMarketData(game) ? "Enriched" : "Seed only";
      return `
        <tr>
          <td><button class="game-button${active}" type="button" data-game-id="${escapeHtml(gameId)}">${escapeHtml(pick(game, ["name", "title"]))}</button></td>
          <td>${escapeHtml(pick(game, ["genre", "genres"]))}</td>
          <td>${formatCurrency(pick(game, ["price", "initial_price"]))}</td>
          <td>${formatOwners(pick(game, ["owners", "owner_count"]))}</td>
          <td>${formatNumber(pick(game, ["positive_reviews", "positive", "positive_count"]))}</td>
          <td>${formatNumber(pick(game, ["negative_reviews", "negative", "negative_count"]))}</td>
          <td>${dataStatus}</td>
        </tr>
      `;
    })
    .join("");

  elements.gamesContainer.innerHTML = `
    ${renderPagination(games.length)}
    <table>
      <thead><tr><th>Game</th><th>Genre</th><th>Price</th><th>Owners</th><th>Positive</th><th>Negative</th><th>Status</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderGameDetail(detail) {
  if (!detail) {
    elements.selectedGameBadge.textContent = "No selection";
    elements.gameDetailContainer.innerHTML = '<p class="empty-message">Select a game to view details.</p>';
    return;
  }

  elements.selectedGameBadge.textContent = pick(detail, ["name", "title"]);
  const fields = [
    ["App ID", pick(detail, ["app_id", "game_id", "id"])],
    ["Genre", pick(detail, ["genre", "genres"])],
    ["Price", formatCurrency(pick(detail, ["price", "initial_price"]))],
    ["Owners", formatOwners(pick(detail, ["owners", "owner_count"]))],
    ["Positive reviews", formatNumber(pick(detail, ["positive_reviews", "positive", "positive_count"]))],
    ["Negative reviews", formatNumber(pick(detail, ["negative_reviews", "negative", "negative_count"]))],
    ["Average playtime", `${formatNumber(pick(detail, ["average_playtime", "playtime_average"]))} min`],
    ["Developer", pick(detail, ["developer", "developers"])],
  ];

  elements.gameDetailContainer.innerHTML = fields
    .map(([label, value]) => `
      <div class="detail-item">
        <span class="detail-label">${escapeHtml(label)}</span>
        <span class="detail-value">${escapeHtml(value)}</span>
      </div>
    `)
    .join("");
}

function normalizeSentiment(data) {
  const source = asArray(data)[0] || data || {};
  const total = Number(pick(source, ["total", "total_count"], 0));
  return {
    total,
    reliability: pick(source, ["reliability"], getReliability(total)),
    warning: pick(source, ["warning"], total < MIN_SAMPLE_SIZE ? "The current sample size is small, so reliability may be low." : ""),
    rows: [
      ["Positive", pick(source, ["positive_ratio"], 0), pick(source, ["positive", "positive_count"], 0), ""],
      ["Neutral", pick(source, ["neutral_ratio"], 0), pick(source, ["neutral", "neutral_count"], 0), "neutral"],
      ["Negative", pick(source, ["negative_ratio"], 0), pick(source, ["negative", "negative_count"], 0), "negative"],
    ],
  };
}

function renderSentiment(data) {
  if (!data) {
    elements.sentimentReliability.textContent = "Reliability -";
    elements.sentimentContainer.innerHTML = '<p class="empty-message">No sentiment data for this selection.</p>';
    return;
  }

  const sentiment = normalizeSentiment(data);
  elements.sentimentReliability.textContent = `Reliability ${sentiment.reliability} - total ${formatNumber(sentiment.total)}`;

  const warning = sentiment.warning && sentiment.warning !== "-" ? warningBox(sentiment.warning) : "";
  const bars = sentiment.rows
    .map(([label, ratio, count, className]) => {
      const width = Math.max(0, Math.min(100, Number(ratio || 0) * 100));
      return `
        <div class="bar-row">
          <div class="bar-label"><strong>${label}</strong><span>${formatRatio(ratio)} - ${formatNumber(count)} reviews</span></div>
          <div class="bar-track"><div class="bar-fill ${className}" style="width: ${width}%"></div></div>
        </div>
      `;
    })
    .join("");

  elements.sentimentContainer.innerHTML = `${warning}${bars}`;
}

function renderTopics(data) {
  const topics = asArray(data).slice(0, 5);
  if (topics.length === 0) {
    elements.topicsContainer.innerHTML = '<p class="empty-message">No topic data for this selection.</p>';
    return;
  }

  elements.topicsContainer.innerHTML = topics
    .map((topic, index) => {
      const topicId = pick(topic, ["topic_id", "id"], index + 1);
      const keywords = pick(topic, ["keywords", "topic_keywords", "terms", "name"]);
      const weight = pick(topic, ["weight_percent", "weight", "topic_weight", "score"], 0);
      const sampleSize = pick(topic, ["sample_size", "n", "count"], 0);
      const reliability = pick(topic, ["reliability"], getReliability(sampleSize));
      const warning = pick(topic, ["warning"], "");
      return `
        <article class="topic-item">
          ${warning && warning !== "-" ? warningBox(warning) : ""}
          <strong class="topic-title">Topic ${escapeHtml(topicId)} - ${formatRatio(weight)} - Reliability ${escapeHtml(reliability)}</strong>
          <span>${escapeHtml(keywords)}</span>
        </article>
      `;
    })
    .join("");
}

function renderCorrelations(data) {
  const rows = asArray(data);
  if (rows.length === 0) {
    elements.correlationContainer.innerHTML = '<p class="empty-message">No correlation data.</p>';
    return;
  }

  const tableRows = rows
    .map((row) => {
      const featureA = pick(row, ["feature_x", "feature_a", "x"]);
      const featureB = pick(row, ["feature_y", "feature_b", "y"]);
      const correlation = pick(row, ["correlation", "correlation_value", "value"]);
      const pValue = pick(row, ["p_value", "p"]);
      const sampleSize = pick(row, ["sample_size", "n", "count"]);
      const reliability = pick(row, ["reliability"], getReliability(sampleSize));
      const warning = pick(row, ["warning"], "");
      return `<tr><td>${escapeHtml(featureA)}</td><td>${escapeHtml(featureB)}</td><td>${escapeHtml(formatNumber(correlation))}</td><td>${escapeHtml(formatNumber(pValue))}</td><td>${formatNumber(sampleSize)}</td><td>${escapeHtml(reliability)}</td><td>${warning && warning !== "-" ? escapeHtml(warning) : "-"}</td></tr>`;
    })
    .join("");

  elements.correlationContainer.innerHTML = `
    <table>
      <thead><tr><th>Feature A</th><th>Feature B</th><th>Correlation</th><th>p-value</th><th>Sample size</th><th>Reliability</th><th>Warning</th></tr></thead>
      <tbody>${tableRows}</tbody>
    </table>
  `;
}

async function loadGames() {
  const games = await requestJson("/games", "games");
  state.games = asArray(games);
  state.currentPage = 1;
  renderGames();
  return state.games;
}

async function loadGameDetail(gameId, updateAnalysis = true) {
  state.selectedGameId = gameId;
  renderGames();

  const detail = await requestOptional(`/games/${gameId}`, "game detail");
  if (detail) renderGameDetail(detail);

  if (!updateAnalysis) return;

  const sentiment = await requestOptional(`/games/${gameId}/sentiment`, "game sentiment");
  renderSentiment(sentiment);

  const topics = await requestOptional(`/games/${gameId}/topics`, "game topics");
  renderTopics(topics);
}

async function loadDashboard() {
  resetLog();
  setStatus("Loading data...");
  elements.loadButton.disabled = true;
  localStorage.setItem("steamTrendApiBase", getApiBase());

  try {
    await requestJson("/health", "health");
    const games = await loadGames();
    const sentiment = await requestOptional("/analysis/sentiment", "overall sentiment");
    const topics = await requestOptional("/analysis/topics?limit=5", "overall topics");
    const correlations = await requestOptional("/analysis/correlation", "correlation");

    renderSentiment(sentiment);
    renderTopics(topics);
    renderCorrelations(correlations);

    if (games.length > 0) {
      await loadGameDetail(getGameId(games[0]), false);
    } else {
      renderGameDetail(null);
    }

    setStatus("Data loaded.");
  } catch (error) {
    console.error("[dashboard load failed]", error);
    setStatus(error.message || "Failed to load data.", true);
  } finally {
    elements.loadButton.disabled = false;
  }
}

elements.loadButton.addEventListener("click", loadDashboard);

elements.gameSearchInput.addEventListener("input", () => {
  state.currentPage = 1;
  renderGames();
});

elements.gamesContainer.addEventListener("click", (event) => {
  const pageButton = event.target.closest("[data-page-action]");
  if (pageButton) {
    state.currentPage += pageButton.dataset.pageAction === "next" ? 1 : -1;
    renderGames();
    return;
  }

  const gameButton = event.target.closest("[data-game-id]");
  if (gameButton) loadGameDetail(gameButton.dataset.gameId);
});

const savedApiBase = localStorage.getItem("steamTrendApiBase");
if (savedApiBase) {
  elements.apiBaseInput.value = savedApiBase;
}
