from pydantic import BaseModel


class TopicResult(BaseModel):
    topic_id: int
    keywords: str
    weight: float

