from pydantic import BaseModel


class CorrelationResult(BaseModel):
    feature_x: str
    feature_y: str
    correlation_value: float
    p_value: float
    sample_size: int
