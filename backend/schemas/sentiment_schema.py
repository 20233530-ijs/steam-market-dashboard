from pydantic import BaseModel


class SentimentSummary(BaseModel):
    positive_count: int
    neutral_count: int
    negative_count: int
    positive_ratio: float
    neutral_ratio: float
    negative_ratio: float
    average_compound: float

