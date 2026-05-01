const state = {
  games: [],
  selectedGameId: null,
};

const elements = {
  apiBaseInput: document.querySelector("#apiBaseInput"),
  refreshButton: document.querySelector("#refreshButton"),
  statusText: document.querySelector("#statusText"),
  totalGames: document.querySelector("#totalGames"),
  totalReviews: document.querySelector("#totalReviews"),
  avgPositive: document.querySelector("#avgPositive"),
  topGenre: document.querySelector("#topGenre"),
  gameSearch: document.querySelector("#gameSearch"),
  gamesList: document.querySelector("#gamesList"),
  selectedTitle: document.querySelector("#selectedTitle"),
  selectedGenre: document.querySelector("#selectedGenre"),
  detailOwners: document.querySelector("#detailOwners"),
  detailPrice: document.querySelector("#detailPrice"),
  detailPositive: document.querySelector("#detailPositive"),
  detailNegative: document.querySelector("#detailNegative"),
  sentimentBars: document.querySelector("#sentimentBars"),
  topicList: document.querySelector("#topicList"),
  correlationList: document.querySelector("#correlationList"),
};

function getApiBase() {
  return elements.apiBaseInput.value.replace(/\/+$/, "");
}

function setStatus(message) {
  elements.statusText.textContent = message;
}

function formatInteger(value) {
  return Number(value || 0).toLocaleString();
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatPrice(value) {
  const cents = Number(value || 0);
  if (cents === 0) {
    return "Free";
  }
  return `$${(cents / 100).toFixed(2)}`;
}

async function request(path) {
  const response = await fetch(`${getApiBase()}${path}`);
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function renderSummary(summary) {
  elements.totalGames.textContent = formatInteger(summary.total_games);
  elements.totalReviews.textContent = formatInteger(summary.total_reviews);
  elements.avgPositive.textContent = formatPercent(summary.average_positive_ratio);
  elements.topGenre.textContent = summary.top_genre || "-";
}

function renderGames() {
  const term = elements.gameSearch.value.trim().toLowerCase();
  const games = state.games.filter((game) => {
    return !term || `${game.name || ""} ${game.genre || ""}`.toLowerCase().includes(term);
  });

  if (games.length === 0) {
    elements.gamesList.innerHTML = '<div class="empty">No games found</div>';
    return;
  }

  elements.gamesList.innerHTML = games
    .map((game) => {
      const active = game.game_id === state.selectedGameId ? " active" : "";
      return `
        <button class="game-row${active}" type="button" data-game-id="${game.game_id}">
          <span>
            <strong>${escapeHtml(game.name || "Untitled")}</strong><br />
            ${escapeHtml(game.genre || "Unknown genre")}
          </span>
          <span>${formatInteger(game.positive_reviews)} / ${formatInteger(game.negative_reviews)}</span>
        </button>
      `;
    })
    .join("");
}

function renderSentiment(sentiment) {
  const rows = [
    ["Positive", sentiment.positive_ratio, sentiment.positive_count, ""],
    ["Neutral", sentiment.neutral_ratio, sentiment.neutral_count, "neutral"],
    ["Negative", sentiment.negative_ratio, sentiment.negative_count, "negative"],
  ];

  elements.sentimentBars.innerHTML = rows
    .map(([label, ratio, count, className]) => {
      const width = Math.max(0, Math.min(100, Number(ratio || 0) * 100));
      return `
        <div class="bar-row">
          <div class="bar-label">
            <strong>${label}</strong>
            <span>${formatPercent(ratio)} (${formatInteger(count)})</span>
          </div>
          <div class="bar-track"><div class="bar-fill ${className}" style="width: ${width}%"></div></div>
        </div>
      `;
    })
    .join("");
}

function renderTopics(topics) {
  if (!topics.length) {
    elements.topicList.innerHTML = '<div class="empty">No topic data</div>';
    return;
  }

  elements.topicList.innerHTML = topics
    .map((topic) => {
      return `
        <div class="topic-row">
          <strong>Topic ${topic.topic_id}</strong>
          <span>${escapeHtml(topic.keywords)}</span>
        </div>
      `;
    })
    .join("");
}

function renderCorrelations(correlations) {
  if (!correlations.length) {
    elements.correlationList.innerHTML = '<div class="empty">No correlation data</div>';
    return;
  }

  elements.correlationList.innerHTML = correlations
    .slice(0, 12)
    .map((item) => {
      return `
        <div class="correlation-row">
          <strong>${escapeHtml(item.feature_x)} vs ${escapeHtml(item.feature_y)}</strong>
          <div class="correlation-meta">
            <span>r=${Number(item.correlation_value).toFixed(3)}</span>
            <span>p=${Number(item.p_value).toFixed(3)} | n=${formatInteger(item.sample_size)}</span>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderSelectedGame(detail) {
  elements.selectedTitle.textContent = detail.name || `Game ${detail.game_id}`;
  elements.selectedGenre.textContent = detail.genre || "Unknown genre";
  elements.detailOwners.textContent = detail.owners || "-";
  elements.detailPrice.textContent = formatPrice(detail.price);
  elements.detailPositive.textContent = formatInteger(detail.positive_reviews);
  elements.detailNegative.textContent = formatInteger(detail.negative_reviews);
}

function renderEmptySelection() {
  elements.selectedTitle.textContent = "Select a game";
  elements.selectedGenre.textContent = "No game selected";
  elements.detailOwners.textContent = "-";
  elements.detailPrice.textContent = "-";
  elements.detailPositive.textContent = "-";
  elements.detailNegative.textContent = "-";
  elements.sentimentBars.innerHTML = '<div class="empty">Choose a game to load sentiment</div>';
  elements.topicList.innerHTML = '<div class="empty">Choose a game to load topics</div>';
}

async function selectGame(gameId) {
  state.selectedGameId = gameId;
  renderGames();
  setStatus("Loading game detail...");

  const [detail, sentimentResult, topicResult] = await Promise.allSettled([
    request(`/games/${gameId}`),
    request(`/games/${gameId}/sentiment`),
    request(`/games/${gameId}/topics`),
  ]);

  if (detail.status === "fulfilled") {
    renderSelectedGame(detail.value);
  }

  if (sentimentResult.status === "fulfilled") {
    renderSentiment(sentimentResult.value);
  } else {
    elements.sentimentBars.innerHTML = '<div class="empty">No sentiment data</div>';
  }

  if (topicResult.status === "fulfilled") {
    renderTopics(topicResult.value);
  } else {
    elements.topicList.innerHTML = '<div class="empty">No topic data</div>';
  }

  setStatus("Ready");
}

async function loadDashboard() {
  setStatus("Loading dashboard...");
  localStorage.setItem("steamDashboardApiBase", getApiBase());
  renderEmptySelection();

  const [summary, games, correlations] = await Promise.all([
    request("/dashboard/summary"),
    request("/games"),
    request("/analysis/correlation"),
  ]);

  state.games = games;
  state.selectedGameId = games[0]?.game_id || null;
  renderSummary(summary);
  renderGames();
  renderCorrelations(correlations);

  if (state.selectedGameId) {
    await selectGame(state.selectedGameId);
  } else {
    setStatus("No games available");
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

elements.refreshButton.addEventListener("click", () => {
  loadDashboard().catch((error) => setStatus(error.message));
});

elements.gameSearch.addEventListener("input", renderGames);

elements.gamesList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-game-id]");
  if (!button) {
    return;
  }
  selectGame(Number(button.dataset.gameId)).catch((error) => setStatus(error.message));
});

const savedApiBase = localStorage.getItem("steamDashboardApiBase");
if (savedApiBase) {
  elements.apiBaseInput.value = savedApiBase;
}

loadDashboard().catch((error) => setStatus(error.message));
