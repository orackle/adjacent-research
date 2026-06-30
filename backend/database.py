import os
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

backend_dir = Path(__file__).parent.resolve()
db_path = backend_dir / "breakthrough_radar.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{db_path}")

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    corpus_id = Column(String, unique=True, index=True, nullable=False)
    doi = Column(String, nullable=True)
    arxiv_id = Column(String, nullable=True)
    title = Column(String, nullable=False)
    abstract = Column(String, nullable=True)
    year = Column(Integer, index=True, nullable=True)
    fields_of_study = Column(String, nullable=True)  # JSON array stored as string
    citation_count = Column(Integer, default=0)
    citation_velocity = Column(Float, default=0.0)
    influential_citation_count = Column(Integer, default=0)
    cd_index = Column(Float, nullable=True)
    novelty_score = Column(Float, nullable=True)
    breakthrough_score = Column(Float, index=True, nullable=True)
    citation_velocity_percentile = Column(Float, default=0.0)
    cd_index_percentile = Column(Float, default=0.0)
    one_line_reason = Column(String, nullable=True)
    context_summary = Column(String, nullable=True)
    novelty_scored = Column(Integer, default=0)  # 0 = False, 1 = True
    embedding = Column(String, nullable=True)  # JSON-serialized float array
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Ensure indexes exist on year, breakthrough_score, and corpus_id
# (corpus_id index is created via index=True on Column, year via index=True on Column, breakthrough_score via index=True on Column)


class CitationEdge(Base):
    """Directed citation edge: source (citing paper) → target (cited paper)."""
    __tablename__ = "citation_edges"

    id = Column(Integer, primary_key=True)
    source_corpus_id = Column(String, index=True, nullable=False)  # citing paper
    target_corpus_id = Column(String, index=True, nullable=False)  # cited paper
    source_year = Column(Integer, nullable=True)                   # year of source paper

    __table_args__ = (
        UniqueConstraint("source_corpus_id", "target_corpus_id", name="uq_citation_edge"),
    )


class PrecomputedAdjacency(Base):
    __tablename__ = "precomputed_adjacencies"

    seed_hash = Column(String, primary_key=True, index=True)
    idea_json = Column(String, nullable=False)  # stores list of adjacent ideas
    engines_used = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PrecomputedLineage(Base):
    __tablename__ = "precomputed_lineages"

    query_hash = Column(String, primary_key=True, index=True)
    chain_json = Column(String, nullable=False)
    narrative = Column(String, nullable=False)
    frontier_json = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)



class Concept(Base):
    __tablename__ = "concepts"

    concept_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    level = Column(Integer, index=True, nullable=True)
    ancestors = Column(String, nullable=True)  # JSON text
    descendants = Column(String, nullable=True)  # JSON text


class PaperConcept(Base):
    __tablename__ = "paper_concepts"

    id = Column(Integer, primary_key=True)
    paper_id = Column(String, index=True, nullable=False)  # references Paper.corpus_id
    concept_id = Column(String, index=True, nullable=False)  # references Concept.concept_id
    score = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("paper_id", "concept_id", name="uq_paper_concept"),
    )




def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
