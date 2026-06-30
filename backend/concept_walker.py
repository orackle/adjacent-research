import json
import logging
import urllib.parse
import requests
from typing import List, Tuple
from sqlalchemy.orm import Session
from database import Concept, PaperConcept, Paper

logger = logging.getLogger(__name__)

def populate_concepts_from_db(db: Session):
    """
    Reads papers from database, parses fields_of_study,
    and inserts records into concepts and paper_concepts.
    """
    logger.info("Starting Concept and Paper-Concept database population...")
    papers = db.query(Paper).all()
    if not papers:
        logger.warning("No papers in database to extract concepts from.")
        return

    # Extract unique concept names
    concept_names = set()
    for paper in papers:
        if paper.fields_of_study:
            try:
                fields = json.loads(paper.fields_of_study)
                for f in fields:
                    if isinstance(f, str):
                        concept_names.add(f.strip())
            except Exception:
                continue

    logger.info(f"Extracted {len(concept_names)} unique concepts from papers.")

    # Insert unique concepts
    for name in concept_names:
        existing = db.query(Concept).filter_by(name=name).first()
        if existing:
            continue

        # Try to resolve concept level and hierarchy from OpenAlex concept endpoint
        level = 3  # default level
        ancestors = []
        descendants = []
        
        try:
            encoded_name = urllib.parse.quote(name)
            url = f"https://api.openalex.org/concepts?filter=display_name:{encoded_name}"
            headers = {"User-Agent": "mailto:info@example.com (Adjacency Mapper Client)"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.ok:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    concept_data = results[0]
                    level = concept_data.get("level", 3)
                    # ancestors are ancestral concepts
                    ancestors = [a.get("display_name") for a in (concept_data.get("ancestors") or [])]
        except Exception as e:
            logger.warning(f"Failed to fetch concept details for '{name}': {e}")

        new_concept = Concept(
            concept_id=f"concept_{name.lower().replace(' ', '_')}",
            name=name,
            level=level,
            ancestors=json.dumps(ancestors),
            descendants=json.dumps(descendants)
        )
        db.add(new_concept)
    
    db.commit()

    # Populate paper_concepts linkages
    for paper in papers:
        if not paper.fields_of_study:
            continue
        try:
            fields = json.loads(paper.fields_of_study)
            for f in fields:
                if not isinstance(f, str):
                    continue
                f_name = f.strip()
                concept = db.query(Concept).filter_by(name=f_name).first()
                if not concept:
                    continue
                
                # Check duplicates
                existing_link = db.query(PaperConcept).filter_by(
                    paper_id=paper.corpus_id, concept_id=concept.concept_id
                ).first()
                if existing_link:
                    continue

                new_link = PaperConcept(
                    paper_id=paper.corpus_id,
                    concept_id=concept.concept_id,
                    score=1.0  # default binary score
                )
                db.add(new_link)
        except Exception:
            continue
            
    db.commit()
    logger.info("Concept and Paper-Concept linkages populated successfully.")


def find_conceptual_gaps(seed_concept_name: str, db: Session, limit: int = 5) -> List[str]:
    """
    Find sibling concepts S of seed concept C that rarely or never co-occur in the same papers.
    """
    # 1. Find seed concept
    seed_concept = db.query(Concept).filter_by(name=seed_concept_name).first()
    if not seed_concept:
        # Try fuzzy match
        seed_concept = db.query(Concept).filter(Concept.name.like(f"%{seed_concept_name}%")).first()
    
    if not seed_concept:
        # Concept walker defaults to sibling concepts of matching level
        siblings = db.query(Concept).filter_by(level=3).limit(limit).all()
        return [s.name for s in siblings]

    # Find siblings: sharing similar level and matching ancestor where possible
    seed_ancestors = []
    if seed_concept.ancestors:
        try:
            seed_ancestors = json.loads(seed_concept.ancestors)
        except Exception:
            pass

    # Find concepts at same level
    query = db.query(Concept).filter(Concept.level == seed_concept.level, Concept.concept_id != seed_concept.concept_id)
    candidates = query.all()

    # Find papers matching seed concept
    seed_paper_ids = [pc.paper_id for pc in db.query(PaperConcept).filter_by(concept_id=seed_concept.concept_id).all()]
    if not seed_paper_ids:
        # Fallback to general sibling concepts
        return [c.name for c in candidates[:limit]]

    # For each candidate sibling, check co-occurrence in seed papers
    gaps = []
    for cand in candidates:
        cand_paper_ids = [pc.paper_id for pc in db.query(PaperConcept).filter_by(concept_id=cand.concept_id).all()]
        if not cand_paper_ids:
            continue

        intersection = set(seed_paper_ids).intersection(set(cand_paper_ids))
        # If intersection is empty or very small, it's a co-occurrence gap!
        co_occurrence_ratio = len(intersection) / len(seed_paper_ids)
        if co_occurrence_ratio < 0.05:  # Less than 5% overlap
            gaps.append((cand.name, co_occurrence_ratio))

    # Sort gaps by lowest co-occurrence ratio
    gaps.sort(key=lambda x: x[1])
    return [g[0] for g in gaps[:limit]]
