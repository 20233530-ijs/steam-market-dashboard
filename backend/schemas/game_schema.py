from datetime import datetime

from pydantic import BaseModel


class GameListItem(BaseModel):
    game_id: int
    name: str | None = None
    genre: str | None = None
    price: int | None = None
    owners: str | None = None
    positive_reviews: int
    negative_reviews: int
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
