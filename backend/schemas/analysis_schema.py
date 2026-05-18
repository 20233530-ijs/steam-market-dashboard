from pydantic import BaseModel


class CorrelationResult(BaseModel):
    feature_x: str
    feature_y: str
    correlation_value: float
    p_value: float
    sample_size: int
    min_sample_size: int
    reliability: str
    warning: str | None = None


class SentimentOverview(BaseModel):
    positive: int
    neutral: int
    negative: int
    total: int
    positive_ratio: float
    neutral_ratio: float
    negative_ratio: float
    min_sample_size: int
    reliability: str
    warning: str | None = None


class TopicOverview(BaseModel):
    topic_id: int
    keywords: list[str]
    weight: float
    weight_percent: float
    sample_size: int
    min_sample_size: int
    reliability: str
    warning: str | None = None


class TrendPoint(BaseModel):
    period: str
    review_count: int
    positive_reviews: int
    negative_reviews: int
    positive_ratio: float


class GenreTrendSeries(BaseModel):
    genre: str
    data: list[TrendPoint]


class AnalysisTrendsResponse(BaseModel):
    market: list[TrendPoint]
    top_genres: list[GenreTrendSeries]


class PriceReviewPoint(BaseModel):
    game_id: int
    name: str | None = None
    genre: str | None = None
    price: int | None = None
    total_reviews: int
    positive_ratio: float


class ReviewInsightCategory(BaseModel):
    category: str
    positive_count: int
    negative_count: int
    neutral_count: int
    positive_ratio: float
    negative_ratio: float
    keywords: list[str]


class ReviewInsightsResponse(BaseModel):
    game_id: int
    topic_sentiment_available: bool = False
    message: str | None = None
    satisfaction_factors: list[ReviewInsightCategory]
    dissatisfaction_factors: list[ReviewInsightCategory]
    topics: list[ReviewInsightCategory]


class TopicClusterNode(BaseModel):
    id: str
    label: str
    weight: float
    topic_id: int | None = None


class TopicClusterLink(BaseModel):
    source: str
    target: str
    value: float


class TopicClusterResponse(BaseModel):
    nodes: list[TopicClusterNode]
    links: list[TopicClusterLink]


class GenreStatsItem(BaseModel):
    genre: str
    game_count: int
    avg_price: float
    avg_review_count: float
    avg_positive_ratio: float


class GenreStatsResponse(BaseModel):
    items: list[GenreStatsItem]


class PriceBandStatsItem(BaseModel):
    price_band: str
    game_count: int
    avg_review_count: float
    avg_positive_ratio: float


class PriceBandStatsResponse(BaseModel):
    items: list[PriceBandStatsItem]


class PlatformStatsItem(BaseModel):
    platform: str
    game_count: int
    avg_positive_ratio: float


class PlatformStatsResponse(BaseModel):
    items: list[PlatformStatsItem]
