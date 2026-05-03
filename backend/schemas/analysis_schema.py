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
