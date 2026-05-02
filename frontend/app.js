const state = {
  games: [],
  selectedGameId: null,
};

const elements = {
  apiBaseInput: document.querySelector("#apiBaseInput"),
  loadButton: document.querySelector("#loadButton"),
  statusMessage: document.querySelector("#statusMessage"),
  gameSearchInput: document.querySelector("#gameSearchInput"),
  gamesContainer: document.querySelector("#gamesContainer"),
  selectedGameBadge: document.querySelector("#selectedGameBadge"),
  gameDetailContainer: document.querySelector("#gameDetailContainer"),
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

function logResult(label, payload, isError = false) {
  const item = document.createElement("li");
  item.textContent = `${label}: ${isError ? "실패" : "성공"}`;
  elements.logList.appendChild(item);
  console[isError ? "error" : "log"](`[${label}]`, payload);
}

function resetLog() {
  elements.logList.innerHTML = "";
}

async function requestJson(path, label) {
  const url = `${getApiBase()}${path}`;
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`${label} 요청 실패 (${response.status})`);
  }

  const data = await response.json();
  logResult(`${label} ${path}`, data);
  return data;
}

// Some backend routes may not exist yet. Keep each request isolated so one failure
// does not stop the rest of the dashboard from rendering.
async function requestOptional(path, label) {
  try {
    return await requestJson(path, label);
  } catch (error) {
    logResult(`${label} ${path}`, error, true);
    return null;
  }
}

function asArray(value) {
  if (Array.isArray(value)) {
    return value;
  }
  if (Array.isArray(value?.items)) {
    return value.items;
  }
  if (Array.isArray(value?.results)) {
    return value.results;
  }
  if (Array.isArray(value?.data)) {
    return value.data;
  }
  return value ? [value] : [];
}

function pick(object, keys, fallback = "-") {
  for (const key of keys) {
    const value = object?.[key];
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return fallback;
}

function getGameId(game) {
  return pick(game, ["app_id", "game_id", "id"], null);
}

function formatNumber(value) {
  if (value === "-" || value === null || value === undefined || value === "") {
    return "-";
  }
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : String(value);
}

function formatRatio(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return `${Math.round(number * 100)}%`;
}

function escapeHtml(value) {
  return String(value ?? "-")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderError(container, message) {
  container.innerHTML = `<div class="error-box">${escapeHtml(message)}</div>`;
}

function renderGames() {
  const searchTerm = elements.gameSearchInput.value.trim().toLowerCase();
  const filteredGames = state.games.filter((game) => {
    const name = pick(game, ["name", "title"], "");
    const genre = pick(game, ["genre", "genres"], "");
    return `${name} ${genre}`.toLowerCase().includes(searchTerm);
  });

  if (filteredGames.length === 0) {
    elements.gamesContainer.innerHTML = '<p class="empty-message">표시할 게임 목록이 없습니다.</p>';
    return;
  }

  const rows = filteredGames
    .map((game) => {
      const gameId = getGameId(game);
      const name = pick(game, ["name", "title"]);
      const genre = pick(game, ["genre", "genres"]);
      const positive = formatNumber(pick(game, ["positive_reviews", "positive", "positive_count"]));
      const negative = formatNumber(pick(game, ["negative_reviews", "negative", "negative_count"]));
      const active = String(gameId) === String(state.selectedGameId) ? " active" : "";

      return `
        <tr>
          <td>
            <button class="game-button${active}" type="button" data-game-id="${escapeHtml(gameId)}">
              ${escapeHtml(name)}
            </button>
          </td>
          <td>${escapeHtml(genre)}</td>
          <td>${positive}</td>
          <td>${negative}</td>
        </tr>
      `;
    })
    .join("");

  elements.gamesContainer.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>게임</th>
          <th>장르</th>
          <th>긍정 리뷰</th>
          <th>부정 리뷰</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderGameDetail(detail) {
  if (!detail) {
    elements.selectedGameBadge.textContent = "선택 없음";
    elements.gameDetailContainer.innerHTML =
      '<p class="empty-message">게임 목록에서 게임을 선택하면 상세 정보가 표시됩니다.</p>';
    return;
  }

  const name = pick(detail, ["name", "title"]);
  elements.selectedGameBadge.textContent = name;

  const fields = [
    ["App ID", pick(detail, ["app_id", "game_id", "id"])],
    ["장르", pick(detail, ["genre", "genres"])],
    ["가격", pick(detail, ["price", "initial_price"])],
    ["보유자", pick(detail, ["owners", "owner_count"])],
    ["긍정 리뷰", pick(detail, ["positive_reviews", "positive", "positive_count"])],
    ["부정 리뷰", pick(detail, ["negative_reviews", "negative", "negative_count"])],
    ["평균 플레이타임", pick(detail, ["average_playtime", "playtime_average"])],
    ["개발사", pick(detail, ["developer", "developers"])],
  ];

  elements.gameDetailContainer.innerHTML = fields
    .map(
      ([label, value]) => `
        <div class="detail-item">
          <span class="detail-label">${escapeHtml(label)}</span>
          <span class="detail-value">${escapeHtml(formatNumber(value))}</span>
        </div>
      `,
    )
    .join("");
}

function normalizeSentiment(data) {
  const rows = asArray(data);
  if (rows.length > 1) {
    const total = rows.reduce((sum, row) => sum + Number(pick(row, ["count", "value"], 0)), 0);
    return rows.map((row) => {
      const label = pick(row, ["label", "sentiment", "sentiment_label"]);
      const count = Number(pick(row, ["count", "value"], 0));
      return { label, ratio: total > 0 ? count / total : 0, count };
    });
  }

  const source = rows[0] || data || {};
  return [
    {
      label: "positive",
      ratio: pick(source, ["positive_ratio"], 0),
      count: pick(source, ["positive_count", "positive"], 0),
    },
    {
      label: "neutral",
      ratio: pick(source, ["neutral_ratio"], 0),
      count: pick(source, ["neutral_count", "neutral"], 0),
    },
    {
      label: "negative",
      ratio: pick(source, ["negative_ratio"], 0),
      count: pick(source, ["negative_count", "negative"], 0),
    },
  ];
}

function renderSentiment(data) {
  if (!data) {
    elements.sentimentContainer.innerHTML = '<p class="empty-message">감성 분석 데이터가 없습니다.</p>';
    return;
  }

  const rows = normalizeSentiment(data);
  elements.sentimentContainer.innerHTML = rows
    .map((row) => {
      const label = String(row.label || "-");
      const ratio = Number(row.ratio || 0);
      const width = Math.max(0, Math.min(100, ratio * 100));
      const className = label.includes("neg") ? "negative" : label.includes("neu") ? "neutral" : "";

      return `
        <div class="bar-row">
          <div class="bar-label">
            <strong>${escapeHtml(label)}</strong>
            <span>${formatRatio(ratio)} / ${formatNumber(row.count)}</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill ${className}" style="width: ${width}%"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderTopics(data) {
  const topics = asArray(data);
  if (topics.length === 0) {
    elements.topicsContainer.innerHTML = '<p class="empty-message">토픽 데이터가 없습니다.</p>';
    return;
  }

  elements.topicsContainer.innerHTML = topics
    .map((topic, index) => {
      const topicId = pick(topic, ["topic_id", "id"], index + 1);
      const keywords = pick(topic, ["keywords", "topic_keywords", "terms", "name"]);
      const weight = pick(topic, ["weight", "topic_weight", "score"], "-");

      return `
        <article class="topic-item">
          <strong class="topic-title">Topic ${escapeHtml(topicId)} · weight ${escapeHtml(formatNumber(weight))}</strong>
          <span>${escapeHtml(keywords)}</span>
        </article>
      `;
    })
    .join("");
}

function renderCorrelations(data) {
  const rows = asArray(data);
  if (rows.length === 0) {
    elements.correlationContainer.innerHTML = '<p class="empty-message">상관분석 결과가 없습니다.</p>';
    return;
  }

  const tableRows = rows
    .map((row) => {
      const featureA = pick(row, ["feature_x", "feature_a", "x"]);
      const featureB = pick(row, ["feature_y", "feature_b", "y"]);
      const correlation = pick(row, ["correlation", "correlation_value", "value"]);
      const pValue = pick(row, ["p_value", "p"]);
      const sampleSize = pick(row, ["sample_size", "n", "count"]);

      return `
        <tr>
          <td>${escapeHtml(featureA)}</td>
          <td>${escapeHtml(featureB)}</td>
          <td>${escapeHtml(formatNumber(correlation))}</td>
          <td>${escapeHtml(formatNumber(pValue))}</td>
          <td>${escapeHtml(formatNumber(sampleSize))}</td>
        </tr>
      `;
    })
    .join("");

  elements.correlationContainer.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Feature A</th>
          <th>Feature B</th>
          <th>Correlation</th>
          <th>p-value</th>
          <th>Sample size</th>
        </tr>
      </thead>
      <tbody>${tableRows}</tbody>
    </table>
  `;
}

async function loadGames() {
  const games = await requestJson("/games", "게임 목록");
  state.games = asArray(games);
  renderGames();
  return state.games;
}

async function loadGameDetail(gameId) {
  state.selectedGameId = gameId;
  renderGames();

  const detail = await requestOptional(`/games/${gameId}`, "게임 상세");
  if (detail) {
    renderGameDetail(detail);
  } else {
    renderError(elements.gameDetailContainer, "게임 상세 정보를 불러오지 못했습니다.");
  }

  const sentiment = await requestOptional(`/games/${gameId}/sentiment`, "게임별 감성 분석");
  if (sentiment) {
    renderSentiment(sentiment);
  }

  const topics = await requestOptional(`/games/${gameId}/topics`, "게임별 주요 토픽");
  if (topics) {
    renderTopics(topics);
  }
}

async function loadDashboard() {
  resetLog();
  setStatus("데이터를 불러오는 중입니다...");
  elements.loadButton.disabled = true;
  localStorage.setItem("steamTrendApiBase", getApiBase());

  try {
    const games = await loadGames();
    const sentiment = await requestOptional("/analysis/sentiment", "전체 감성 분석");
    const topics = await requestOptional("/analysis/topics", "전체 주요 토픽");
    const correlations = await requestOptional("/analysis/correlation", "상관분석");

    if (sentiment) {
      renderSentiment(sentiment);
    } else {
      elements.sentimentContainer.innerHTML =
        '<p class="empty-message">전체 감성 분석 API가 없거나 응답이 없습니다. 게임을 선택하면 게임별 감성을 시도합니다.</p>';
    }

    if (topics) {
      renderTopics(topics);
    } else {
      elements.topicsContainer.innerHTML =
        '<p class="empty-message">전체 토픽 API가 없거나 응답이 없습니다. 게임을 선택하면 게임별 토픽을 시도합니다.</p>';
    }

    renderCorrelations(correlations);

    if (games.length > 0) {
      await loadGameDetail(getGameId(games[0]));
    } else {
      renderGameDetail(null);
    }

    setStatus("데이터 불러오기가 완료되었습니다.");
  } catch (error) {
    console.error("[대시보드 로드 실패]", error);
    setStatus(error.message || "데이터를 불러오지 못했습니다.", true);
  } finally {
    elements.loadButton.disabled = false;
  }
}

elements.loadButton.addEventListener("click", loadDashboard);

elements.gameSearchInput.addEventListener("input", renderGames);

elements.gamesContainer.addEventListener("click", (event) => {
  const button = event.target.closest("[data-game-id]");
  if (!button) {
    return;
  }
  loadGameDetail(button.dataset.gameId);
});

const savedApiBase = localStorage.getItem("steamTrendApiBase");
if (savedApiBase) {
  elements.apiBaseInput.value = savedApiBase;
}
