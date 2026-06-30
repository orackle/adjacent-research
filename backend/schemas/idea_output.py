from pydantic import BaseModel, Field

class AdjacentIdea(BaseModel):
    title: str = Field(description="Short title of the proposed adjacent research idea.")
    description: str = Field(description="2-3 sentences explaining the research idea.")
    novelty_rationale: str = Field(description="1 sentence explaining the conceptual gap it bridges.")
    confidence: int = Field(ge=0, le=100, description="Confidence score from 0 to 100.")
