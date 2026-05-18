from datetime import date, datetime

from pydantic import BaseModel


class GameListItem(BaseModel):
    game_id: int
    name: str | None = None
    genre: str | None = None
    price: int | None = None
    is_free: bool | None = None
    header_image: str | None = None
    capsule_image: str | None = None
    website: str | None = None
    is_windows: bool | None = None
    is_mac: bool | None = None
    is_linux: bool | None = None
    metacritic_score: int | None = None
    owners: str | None = None
    positive_reviews: int
    negative_reviews: int
    total_reviews: int = 0
    positive_ratio: float = 0.0
    average_playtime: int | None = None


class GameDetail(GameListItem):
    release_date: str | None = None
    developer: str | None = None
    publisher: str | None = None
    languages: str | None = None
    tags: str | None = None
    peak_players: int | None = None
    collected_at: datetime | None = None


class DashboardSummary(BaseModel):
    total_games: int
    total_reviews: int
    average_positive_ratio: float
    top_genre: str
    period: dict | None = None
    previous_period: dict | None = None
    changes: dict | None = None


class DistributionItem(BaseModel):
    label: str
    count: int


class GameSearchCursor(BaseModel):
    cursor_value: str
    cursor_id: int


class GameSearchResponse(BaseModel):
    items: list[GameListItem]
    total_count: int | None = None
    page: int
    limit: int
    next_cursor: GameSearchCursor | None = None
    genre_distribution: list[DistributionItem]
    positive_ratio_distribution: list[DistributionItem]


class GenreSummary(BaseModel):
    genre: str
    game_count: int


class GameHistoryPoint(BaseModel):
    period: date
    review_count: int
    positive_reviews: int
    negative_reviews: int
    positive_ratio: float
    price: int | None = None
    discount_percent: int | None = None
    final_price: int | None = None
    owners: str | None = None
    peak_players: int | None = None


class GameRankingItem(GameListItem):
    rank: int
    metric_value: float


class WishlistItem(GameListItem):
    price_change_30d: int | None = None
    review_change_30d: int = 0


class WishlistRequest(BaseModel):
    game_id: int


class WishlistResponse(BaseModel):
    items: list[WishlistItem]


class WishlistCompareItem(BaseModel):
    game_id: int
    name: str | None = None
    positive_ratio: float
    total_reviews: int
    price: int | None = None


class NotificationItem(BaseModel):
    notification_id: int
    game_id: int | None = None
    game_name: str | None = None
    type: str
    title: str
    message: str | None = None
    created_at: datetime
    read_at: datetime | None = None
