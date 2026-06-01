import { useEffect, useMemo, useState } from 'react'
import './HomePage.css'
import {
  getCorrelationAnalysis,
  getDashboardSummary,
  getGameRankings,
  getGenreStats,
  type CorrelationResult,
  type DashboardSummary,
  type Game,
  type GenreStat,
} from './api'
import { formatGenreLabel, formatGenreList } from './utils/genre'
import { formatPriceLabel } from './utils/price'

type HomeTopGame = {
  id: string
  rank: number
  name: string
  genre: string
  price: string
  positiveRate: number
  reviewCount: number
  image?: string
}

type GenreView = {
  name: string
  count: number
  ratio: number
}

type PriceSentimentBand = {
  id: string
  label: string
  positiveRate: number
  negativeRate: number
  reviewCount: number
}

type InsightView = {
  title: string
  description: string
  icon: string
}

type PriceBandConfig = {
  id: string
  label: string
  min: number
  max: number
  isFree?: boolean
}

type SentimentCountResult = {
  positiveCount: number
  negativeCount: number
  totalCount: number
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  'https://steam-market-dashboard-production.up.railway.app'

const PRICE_BANDS: PriceBandConfig[] = [
  {
    id: 'free',
    label: '무료',
    min: 0,
    max: 0,
    isFree: true,
  },
  {
    id: 'under10',
    label: '$0~10',
    min: 0,
    max: 10,
  },
  {
    id: 'under30',
    label: '$10~30',
    min: 10,
    max: 30,
  },
  {
    id: 'under60',
    label: '$30~60',
    min: 30,
    max: 60,
  },
  {
    id: 'over60',
    label: '$60 이상',
    min: 60,
    max: Number.POSITIVE_INFINITY,
  },
]

function HomePage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [rankingGames, setRankingGames] = useState<Game[]>([])
  const [allGames, setAllGames] = useState<Game[]>([])
  const [genreStats, setGenreStats] = useState<GenreStat[]>([])
  const [correlations, setCorrelations] = useState<CorrelationResult[]>([])
  const [loading, setLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')
  const [isTopGamesModalOpen, setIsTopGamesModalOpen] = useState(false)

  useEffect(() => {
    async function loadHomeData() {
      try {
        setLoading(true)
        setErrorMessage('')

        const [summaryResult, rankingResult, allGamesResult, genreStatsResult, correlationResult] =
          await Promise.allSettled([
            getDashboardSummary(),
            getGameRankings(),
            getAllGamesForHome(),
            getGenreStats(),
            getCorrelationAnalysis(),
          ])

        if (summaryResult.status === 'fulfilled') {
          setSummary(summaryResult.value)
        }

        if (rankingResult.status === 'fulfilled') {
          setRankingGames(rankingResult.value)
        }

        if (allGamesResult.status === 'fulfilled') {
          setAllGames(allGamesResult.value)
        }

        if (genreStatsResult.status === 'fulfilled') {
          setGenreStats(genreStatsResult.value)
        }

        if (correlationResult.status === 'fulfilled') {
          setCorrelations(correlationResult.value)
        }

        if (
          summaryResult.status === 'rejected' &&
          rankingResult.status === 'rejected' &&
          allGamesResult.status === 'rejected' &&
          genreStatsResult.status === 'rejected' &&
          correlationResult.status === 'rejected'
        ) {
          setErrorMessage('홈 화면 데이터를 불러오지 못했습니다.')
        }
      } catch (error) {
        console.error(error)
        setErrorMessage('홈 화면 데이터를 불러오지 못했습니다.')
      } finally {
        setLoading(false)
      }
    }

    loadHomeData()
  }, [])

  useEffect(() => {
    if (!isTopGamesModalOpen) {
      return
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsTopGamesModalOpen(false)
      }
    }

    const originalOverflow = document.body.style.overflow

    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = originalOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isTopGamesModalOpen])

  const homeGameSource = useMemo(() => {
    return allGames.length > 0 ? allGames : rankingGames
  }, [allGames, rankingGames])

  const allTopGames = useMemo(() => {
    return normalizeTopGames(homeGameSource)
  }, [homeGameSource])

  const topGames = useMemo(() => {
    return allTopGames.slice(0, 10)
  }, [allTopGames])

  const genres = useMemo(() => {
    return normalizeGenres(genreStats, homeGameSource).slice(0, 8)
  }, [genreStats, homeGameSource])

  const priceSentimentBands = useMemo(() => {
    return normalizePriceSentimentBands(homeGameSource)
  }, [homeGameSource])

  const totalGames =
    readNumber(summary, ['total_games', 'totalGames', 'game_count']) || homeGameSource.length

  const totalReviews =
    readNumber(summary, ['total_reviews', 'totalReviews', 'review_count']) ||
    homeGameSource.reduce((sum, game) => sum + getReliableReviewCount(game), 0)

  const averagePositiveRate =
    normalizeRatio(
      readField(summary, ['average_positive_rate', 'positive_rate', 'positiveRate']),
    ) || calculateAveragePositiveRate(homeGameSource)

  const averagePrice =
    normalizePrice(readField(summary, ['average_price', 'average_price_usd'])) ||
    calculateAveragePrice(homeGameSource)

  const insights = useMemo(() => {
    return createInsights({
      totalReviews,
      averagePositiveRate,
      averagePrice,
      genres,
      correlations,
    })
  }, [totalReviews, averagePositiveRate, averagePrice, genres, correlations])

  if (loading) {
    return (
      <section className="status-card">
        <strong>홈 화면 데이터를 불러오는 중입니다...</strong>
        <p>백엔드 API에서 메인 대시보드 데이터를 가져오고 있습니다.</p>
      </section>
    )
  }

  if (errorMessage) {
    return (
      <section className="status-card error">
        <strong>데이터 로드 실패</strong>
        <p>{errorMessage}</p>
      </section>
    )
  }

  return (
    <div className="home-page-v2">
      <section className="home-v2-summary-grid">
        <MetricCard
          title="전체 분석 게임 수"
          value={formatNumber(totalGames)}
          description="전체 게임 데이터 기준"
          icon="🎮"
        />

        <MetricCard
          title="전체 리뷰 수"
          value={formatNumber(totalReviews)}
          description="긍정/부정 리뷰 합산"
          icon="💬"
        />

        <MetricCard
          title="평균 긍정비율"
          value={`${averagePositiveRate.toFixed(1)}%`}
          description="게임별 긍정 비율 평균"
          icon="👍"
        />

        <MetricCard
          title="평균 가격"
          value={formatPriceLabel(averagePrice, averagePrice <= 0)}
          description="원화 환산 + 달러 기준"
          icon="🏷️"
        />
      </section>

      <section className="home-v2-main-grid">
        <article className="home-v2-card top-games-card">
          <div className="home-v2-card-header">
            <div>
              <h2>인기 게임 TOP 10</h2>
              <p>리뷰 수와 긍정 비율을 기준으로 상위 게임을 확인합니다.</p>
            </div>

            <button
              type="button"
              onClick={() => setIsTopGamesModalOpen(true)}
              disabled={topGames.length === 0}
            >
              더보기 →
            </button>
          </div>

          <div className="home-v2-table">
            <div className="home-v2-table-head">
              <span>순위</span>
              <span>게임</span>
              <span>가격</span>
              <span>긍정 비율</span>
            </div>

            {topGames.length > 0 ? (
              topGames.map((game) => (
                <div className="home-v2-table-row" key={game.id}>
                  <span className="home-v2-rank">{game.rank}</span>

                  <div className="home-v2-game-cell">
                    <div className="home-v2-game-thumb">
                      {game.image ? (
                        <img src={game.image} alt={`${game.name} 이미지`} />
                      ) : (
                        <span>{game.name.slice(0, 2)}</span>
                      )}
                    </div>

                    <div className="home-v2-game-text">
                      <strong>{game.name}</strong>
                      <p>{game.genre}</p>
                    </div>
                  </div>

                  <span className="home-v2-price">{game.price}</span>

                  <div className="home-v2-rate-cell">
                    <strong>{game.positiveRate.toFixed(1)}%</strong>
                    <div>
                      <span
                        style={{
                          width: `${Math.min(game.positiveRate, 100)}%`,
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <p className="home-v2-empty">표시할 게임 데이터가 없습니다.</p>
            )}
          </div>
        </article>

        <article className="home-v2-card genre-card">
          <div className="home-v2-card-header compact">
            <div>
              <h2>장르별 비중</h2>
              <p>시장 내 주요 장르 분포를 확인합니다.</p>
            </div>
          </div>

          <div className="home-v2-genre-layout">
            <div className="home-v2-donut" style={{ background: createGenreGradient(genres) }}>
              <div>
                <span>전체</span>
                <strong>{formatNumber(totalGames)}</strong>
                <em>게임</em>
              </div>
            </div>

            <div className="home-v2-genre-list">
              {genres.length > 0 ? (
                genres.map((genre, index) => (
                  <div className="home-v2-genre-row" key={genre.name}>
                    <span className={`genre-dot-${index + 1}`} />
                    <p>{genre.name}</p>
                    <strong>{genre.ratio.toFixed(1)}%</strong>
                  </div>
                ))
              ) : (
                <p className="home-v2-empty">장르 데이터가 없습니다.</p>
              )}
            </div>
          </div>
        </article>

        <article className="home-v2-card price-sentiment-card">
          <div className="home-v2-card-header">
            <div>
              <h2>가격대별 반응 비교</h2>
              <p>가격 구간별 긍정·부정 리뷰 비율을 비교합니다.</p>
            </div>
          </div>

          <div className="home-v2-price-sentiment-chart">
            {priceSentimentBands.length > 0 ? (
              priceSentimentBands.map((band) => (
                <div className="home-v2-price-sentiment-row" key={band.id}>
                  <div className="home-v2-price-sentiment-head">
                    <strong>{band.label}</strong>

                    <div>
                      <span className="positive">긍정 {band.positiveRate.toFixed(1)}%</span>
                      <span className="negative">부정 {band.negativeRate.toFixed(1)}%</span>
                    </div>
                  </div>

                  <div
                    className="home-v2-price-sentiment-track"
                    title={`${band.label} / 긍정 ${band.positiveRate.toFixed(
                      1,
                    )}% / 부정 ${band.negativeRate.toFixed(1)}% / 리뷰 ${formatNumber(
                      band.reviewCount,
                    )}건`}
                  >
                    <span
                      className="positive"
                      style={{
                        width: `${Math.max(0, Math.min(100, band.positiveRate))}%`,
                      }}
                    />
                    <span
                      className="negative"
                      style={{
                        width: `${Math.max(0, Math.min(100, band.negativeRate))}%`,
                      }}
                    />
                  </div>

                  <p>리뷰 {formatNumber(band.reviewCount)}건 기준</p>
                </div>
              ))
            ) : (
              <p className="home-v2-empty">가격대별 감성 데이터가 없습니다.</p>
            )}
          </div>
        </article>
      </section>

      <section className="home-v2-insight-card">
        <div className="home-v2-card-header">
          <div>
            <h2>핵심 인사이트</h2>
            <p>현재 API 데이터에서 확인할 수 있는 주요 해석입니다.</p>
          </div>
        </div>

        <div className="home-v2-insight-grid">
          {insights.map((insight) => (
            <div className="home-v2-insight-item" key={insight.title}>
              <div className="home-v2-insight-icon">{insight.icon}</div>
              <div>
                <strong>{insight.title}</strong>
                <p>{insight.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {isTopGamesModalOpen && (
        <div
          className="home-v2-modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setIsTopGamesModalOpen(false)
            }
          }}
        >
          <section
            className="home-v2-top-games-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="top-games-modal-title"
          >
            <div className="home-v2-modal-header">
              <div>
                <h2 id="top-games-modal-title">인기 게임 TOP 10</h2>
                <p>
                  홈 화면에 표시된 인기 게임 10개를 더 자세히 확인할 수 있습니다.
                  리뷰 수와 긍정 비율을 함께 표시합니다.
                </p>
              </div>

              <button
                type="button"
                className="home-v2-modal-close"
                onClick={() => setIsTopGamesModalOpen(false)}
                aria-label="인기 게임 TOP 10 닫기"
              >
                ×
              </button>
            </div>

            <div className="home-v2-modal-table-wrap">
              <div className="home-v2-modal-table">
                <div className="home-v2-modal-table-head">
                  <span>순위</span>
                  <span>게임</span>
                  <span>장르</span>
                  <span>가격</span>
                  <span>긍정 비율</span>
                  <span>리뷰 수</span>
                </div>

                {topGames.map((game) => (
                  <div className="home-v2-modal-table-row" key={game.id}>
                    <span className="home-v2-modal-rank">{game.rank}</span>

                    <div className="home-v2-modal-game-cell">
                      <div className="home-v2-modal-game-thumb">
                        {game.image ? (
                          <img src={game.image} alt={`${game.name} 이미지`} />
                        ) : (
                          <span>{game.name.slice(0, 2)}</span>
                        )}
                      </div>

                      <strong>{game.name}</strong>
                    </div>

                    <span>{game.genre}</span>
                    <span>{game.price}</span>
                    <strong className="home-v2-modal-positive">
                      {game.positiveRate.toFixed(1)}%
                    </strong>
                    <span>{formatNumber(game.reviewCount)}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

function MetricCard({
  title,
  value,
  description,
  icon,
}: {
  title: string
  value: string
  description: string
  icon: string
}) {
  return (
    <article className="home-v2-metric-card">
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        <p>{description}</p>
      </div>

      <em>{icon}</em>
    </article>
  )
}

async function getAllGamesForHome(): Promise<Game[]> {
  const response = await fetch(`${API_BASE_URL}/games`)

  if (!response.ok) {
    throw new Error(`/games API error: ${response.status}`)
  }

  const data = await response.json()

  if (Array.isArray(data)) {
    return data as Game[]
  }

  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    const candidates = [record.items, record.results, record.data, record.games]

    for (const candidate of candidates) {
      if (Array.isArray(candidate)) {
        return candidate as Game[]
      }
    }
  }

  return []
}

function normalizeTopGames(games: Game[]): HomeTopGame[] {
  return [...games]
    .filter((game) => getReliableReviewCount(game) > 0)
    .sort((a, b) => getReliableReviewCount(b) - getReliableReviewCount(a))
    .map((game, index) => {
      const id = String(getGameId(game) ?? index)
      const price = getPrice(game)
      const isFree = getBoolean(game, ['is_free', 'free', 'isFree']) || price <= 0

      return {
        id,
        rank: index + 1,
        name: getGameName(game),
        genre: getPrimaryGenre(game),
        price: formatPriceLabel(price, isFree),
        positiveRate: getPositiveRate(game),
        reviewCount: getReliableReviewCount(game),
        image: getGameImage(game),
      }
    })
}

function normalizeGenres(genreStats: GenreStat[], games: Game[]): GenreView[] {
  if (genreStats.length > 0) {
    const totalCount = genreStats.reduce((sum, item) => {
      return sum + toNumber(readField(item, ['count', 'game_count']))
    }, 0)

    return genreStats
      .map((item) => {
        const rawName = String(readField(item, ['genre', 'name']) ?? '기타')
        const count = toNumber(readField(item, ['count', 'game_count']))
        const ratio =
          normalizeRatio(readField(item, ['ratio', 'percent', 'percentage'])) ||
          (totalCount > 0 ? (count / totalCount) * 100 : 0)

        return {
          name: formatGenreLabel(rawName),
          count,
          ratio,
        }
      })
      .filter((item) => item.ratio > 0)
      .sort((a, b) => b.ratio - a.ratio)
  }

  const map = new Map<string, number>()

  games.forEach((game) => {
    const genre = getPrimaryGenre(game)

    if (!genre || genre === '장르 없음') {
      return
    }

    map.set(genre, (map.get(genre) ?? 0) + 1)
  })

  const total = [...map.values()].reduce((sum, count) => sum + count, 0)

  return [...map.entries()]
    .map(([name, count]) => ({
      name,
      count,
      ratio: total > 0 ? (count / total) * 100 : 0,
    }))
    .sort((a, b) => b.ratio - a.ratio)
}

function normalizePriceSentimentBands(games: Game[]): PriceSentimentBand[] {
  const bandMap = new Map<
    string,
    {
      config: PriceBandConfig
      positiveCount: number
      negativeCount: number
      reviewCount: number
    }
  >()

  PRICE_BANDS.forEach((config) => {
    bandMap.set(config.id, {
      config,
      positiveCount: 0,
      negativeCount: 0,
      reviewCount: 0,
    })
  })

  games.forEach((game) => {
    const price = getPrice(game)
    const isFree = getBoolean(game, ['is_free', 'free', 'isFree']) || price <= 0
    const band = findPriceBand(price, isFree)
    const savedBand = bandMap.get(band.id)

    if (!savedBand) {
      return
    }

    const sentimentCounts = getSentimentCounts(game)

    if (sentimentCounts.totalCount <= 0) {
      return
    }

    savedBand.positiveCount += sentimentCounts.positiveCount
    savedBand.negativeCount += sentimentCounts.negativeCount
    savedBand.reviewCount += sentimentCounts.totalCount
  })

  return Array.from(bandMap.values())
    .filter((band) => band.reviewCount > 0)
    .map((band) => {
      const positiveRate =
        band.reviewCount > 0 ? (band.positiveCount / band.reviewCount) * 100 : 0
      const negativeRate =
        band.reviewCount > 0 ? (band.negativeCount / band.reviewCount) * 100 : 0

      return {
        id: band.config.id,
        label: band.config.label,
        positiveRate,
        negativeRate,
        reviewCount: band.reviewCount,
      }
    })
}

function getSentimentCounts(game: Game): SentimentCountResult {
  const positiveReviews = toNumber(readField(game, ['positive_reviews', 'positiveReviews']))
  const negativeReviews = toNumber(readField(game, ['negative_reviews', 'negativeReviews']))
  const totalReviews = toNumber(
    readField(game, ['total_reviews', 'totalReviews', 'review_count', 'reviewCount', 'reviews']),
  )
  const positiveRatio = normalizeRatio(
    readField(game, ['positive_ratio', 'positiveRate', 'positive_rate', 'positive_percent']),
  )

  if (positiveReviews > 0 && negativeReviews > 0) {
    return {
      positiveCount: positiveReviews,
      negativeCount: negativeReviews,
      totalCount: positiveReviews + negativeReviews,
    }
  }

  if (positiveReviews > 0 && totalReviews > positiveReviews) {
    return {
      positiveCount: positiveReviews,
      negativeCount: Math.max(0, totalReviews - positiveReviews),
      totalCount: totalReviews,
    }
  }

  if (negativeReviews > 0 && totalReviews > negativeReviews) {
    return {
      positiveCount: Math.max(0, totalReviews - negativeReviews),
      negativeCount: negativeReviews,
      totalCount: totalReviews,
    }
  }

  if (totalReviews > 0 && positiveRatio > 0) {
    const positiveCount = Math.round(totalReviews * (positiveRatio / 100))
    const negativeCount = Math.max(0, totalReviews - positiveCount)

    return {
      positiveCount,
      negativeCount,
      totalCount: totalReviews,
    }
  }

  if (positiveReviews > 0 && negativeReviews === 0 && totalReviews === positiveReviews) {
    return {
      positiveCount: positiveReviews,
      negativeCount: 0,
      totalCount: positiveReviews,
    }
  }

  if (positiveReviews > 0 || negativeReviews > 0) {
    return {
      positiveCount: positiveReviews,
      negativeCount: negativeReviews,
      totalCount: positiveReviews + negativeReviews,
    }
  }

  return {
    positiveCount: 0,
    negativeCount: 0,
    totalCount: 0,
  }
}

function findPriceBand(price: number, isFree: boolean): PriceBandConfig {
  if (isFree || price <= 0) {
    return PRICE_BANDS[0]
  }

  return (
    PRICE_BANDS.find((band) => {
      if (band.isFree) {
        return false
      }

      return price > band.min && price <= band.max
    }) ?? PRICE_BANDS[PRICE_BANDS.length - 1]
  )
}

function createInsights({
  totalReviews,
  averagePositiveRate,
  averagePrice,
  genres,
  correlations,
}: {
  totalReviews: number
  averagePositiveRate: number
  averagePrice: number
  genres: GenreView[]
  correlations: CorrelationResult[]
}): InsightView[] {
  const topGenre = genres[0]?.name ?? '주요 장르'
  const topGenreRatio = genres[0]?.ratio ?? 0
  const correlation = normalizeCorrelation(correlations)[0]

  return [
    {
      title: '리뷰 규모 확인',
      description: `현재 분석 리뷰 수는 약 ${formatNumber(
        totalReviews,
      )}건으로, 시장 반응을 비교하기에 충분한 규모입니다.`,
      icon: '📈',
    },
    {
      title: '긍정 비율 흐름',
      description: `평균 긍정 비율은 ${averagePositiveRate.toFixed(
        1,
      )}%로, 전반적인 사용자 만족도를 핵심 지표로 활용할 수 있습니다.`,
      icon: '👍',
    },
    {
      title: `${topGenre} 강세`,
      description: `${topGenre} 장르가 전체의 ${topGenreRatio.toFixed(
        1,
      )}%를 차지해 주요 분석 축으로 활용하기 좋습니다.`,
      icon: '🎮',
    },
    {
      title: '가격대별 반응',
      description: correlation
        ? `${correlation.item1}와 ${correlation.item2}의 관계를 참고해 가격대별 사용자 반응을 비교할 수 있습니다.`
        : `평균 가격은 ${formatPriceLabel(
            averagePrice,
            averagePrice <= 0,
          )}이며, 가격 구간별 긍정·부정 비율을 비교할 수 있습니다.`,
      icon: '🏷️',
    },
  ]
}

function normalizeCorrelation(items: CorrelationResult[]) {
  return items
    .map((item) => {
      const item1 = formatMetricName(
        readField(item, ['feature_x', 'item1', 'x', 'variable_1']),
      )
      const item2 = formatMetricName(
        readField(item, ['feature_y', 'item2', 'y', 'variable_2']),
      )
      const value = toNumber(
        readField(item, [
          'correlation',
          'correlation_value',
          'correlation_coefficient',
          'coefficient',
          'value',
        ]),
      )

      return { item1, item2, value }
    })
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
}

function createGenreGradient(genres: GenreView[]) {
  if (genres.length === 0) {
    return 'conic-gradient(#e5e7eb 0% 100%)'
  }

  const colors = [
    '#6068f6',
    '#66a9e8',
    '#6fc486',
    '#8b63e8',
    '#f28b3c',
    '#df5d69',
    '#9ca3af',
    '#d1d5db',
  ]

  let start = 0

  const parts = genres.map((genre, index) => {
    const end = start + genre.ratio
    const part = `${colors[index % colors.length]} ${start}% ${end}%`
    start = end
    return part
  })

  if (start < 100) {
    parts.push(`#e5e7eb ${start}% 100%`)
  }

  return `conic-gradient(${parts.join(', ')})`
}

function calculateAveragePositiveRate(games: Game[]) {
  const validGames = games.filter((game) => getReliableReviewCount(game) > 0)

  if (validGames.length === 0) {
    return 0
  }

  const total = validGames.reduce((sum, game) => sum + getPositiveRate(game), 0)

  return total / validGames.length
}

function calculateAveragePrice(games: Game[]) {
  const pricedGames = games.filter((game) => getPrice(game) > 0)

  if (pricedGames.length === 0) {
    return 0
  }

  const total = pricedGames.reduce((sum, game) => sum + getPrice(game), 0)

  return total / pricedGames.length
}

function getGameId(game: Game) {
  return readField(game, ['game_id', 'id', 'app_id', 'appid', 'steam_appid'])
}

function getGameName(game: Game) {
  return String(readField(game, ['name', 'title']) ?? '이름 없음')
}

function getPrimaryGenre(game: Game) {
  const genres = formatGenreList(readField(game, ['genres', 'genre']))
  return genres[0] ?? '장르 없음'
}

function getGameImage(game: Game) {
  const capsuleImage = readField(game, ['capsule_image'])
  const headerImage = readField(game, ['header_image'])
  const image = readField(game, ['image'])

  if (typeof capsuleImage === 'string' && capsuleImage) {
    return capsuleImage
  }

  if (typeof headerImage === 'string' && headerImage) {
    return headerImage
  }

  if (typeof image === 'string' && image) {
    return image
  }

  const gameId = getGameId(game)

  if (!gameId) {
    return undefined
  }

  return `https://cdn.cloudflare.steamstatic.com/steam/apps/${gameId}/capsule_184x69.jpg`
}

function getReliableReviewCount(game: Game) {
  const positive = toNumber(readField(game, ['positive_reviews', 'positiveReviews']))
  const negative = toNumber(readField(game, ['negative_reviews', 'negativeReviews']))
  const total = toNumber(
    readField(game, ['total_reviews', 'totalReviews', 'review_count', 'reviewCount', 'reviews']),
  )

  return total || positive + negative
}

function getPositiveRate(game: Game) {
  const sentimentCounts = getSentimentCounts(game)

  if (sentimentCounts.totalCount > 0) {
    return (sentimentCounts.positiveCount / sentimentCounts.totalCount) * 100
  }

  return normalizeRatio(
    readField(game, ['positive_ratio', 'positiveRate', 'positive_rate', 'positive_percent']),
  )
}

function getPrice(game: Game) {
  return normalizePrice(readField(game, ['price', 'price_usd', 'current_price', 'final_price']))
}

function getBoolean(value: unknown, keys: string[]) {
  const field = readField(value, keys)

  if (typeof field === 'boolean') {
    return field
  }

  if (typeof field === 'number') {
    return field === 1
  }

  if (typeof field === 'string') {
    const normalized = field.trim().toLowerCase()
    return normalized === 'true' || normalized === '1' || normalized === 'yes'
  }

  return false
}

function normalizePrice(value: unknown) {
  const number = toNumber(value)

  if (number > 1000) {
    return number / 100
  }

  return number
}

function readNumber(value: unknown, keys: string[]) {
  const number = toNumber(readField(value, keys))
  return number > 0 ? number : 0
}

function readField(value: unknown, keys: string[]) {
  if (!value || typeof value !== 'object') {
    return undefined
  }

  const record = value as Record<string, unknown>

  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) {
      return record[key]
    }
  }

  return undefined
}

function normalizeRatio(value: unknown) {
  const number = toNumber(value)

  if (number > 0 && number <= 1) {
    return number * 100
  }

  return number
}

function toNumber(value: unknown) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }

  if (typeof value === 'string') {
    const parsed = Number(value.replaceAll(',', '').replace('%', '').replace('$', '').trim())

    return Number.isFinite(parsed) ? parsed : 0
  }

  return 0
}

function formatNumber(value: number) {
  return Math.round(value).toLocaleString()
}

function formatMetricName(value: unknown) {
  const raw = String(value ?? '').trim()
  const lower = raw.toLowerCase()

  const map: Record<string, string> = {
    price: '가격',
    price_usd: '가격',
    review_count: '리뷰 수',
    total_reviews: '리뷰 수',
    owners_value: '보유자 수',
    positive_ratio: '긍정 비율',
    sentiment_positive_ratio: '긍정 리뷰 비율',
    sentiment_negative_ratio: '부정 리뷰 비율',
    sentiment_compound_mean: '종합 감성 점수',
  }

  if (map[lower]) {
    return map[lower]
  }

  if (lower.startsWith('genre::')) {
    return `${formatGenreLabel(raw.replace(/^genre::/i, ''))} 장르`
  }

  return raw || '항목'
}

export default HomePage
