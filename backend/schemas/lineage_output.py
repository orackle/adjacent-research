from typing import List
from pydantic import BaseModel, Field

class Transition(BaseModel):
    from_id: str = Field(description="Corpus ID of the source citing paper.")
    to_id: str = Field(description="Corpus ID of the target cited paper.")
    leap: str = Field(description="Short phrase identifying the conceptual/technical leap.")

class LineageNarrative(BaseModel):
    narrative: str = Field(description="Compelling 3-5 sentence narrative causal lineage story.")
    pivotal_paper_id: str = Field(description="Corpus ID of the most pivotal bridge paper.")
    transitions: List[Transition] = Field(description="List of transition hops with conceptual leaps.")

class FrontierDirection(BaseModel):
    field: str = Field(description="Specific subfield or application.")
    prediction: str = Field(description="One sentence prediction of the future breakthrough.")
    horizon: str = Field(description="Time horizon (e.g. 1-2 years, 3-5 years, 5-10 years).")
    reasoning: str = Field(description="One sentence reasoning explaining why the lineage points there.")
