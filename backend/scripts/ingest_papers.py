import os
import sys
import json
import time
import csv
import random
import requests
from datetime import datetime
from dotenv import load_dotenv

# Reconfigure stdout/stderr to UTF-8 to support unicode characters on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Load env variables from .env
load_dotenv()

# Adjust path to find backend files
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import init_db, SessionLocal, Paper, CitationEdge
from novelty import score_novelty

# Configure environment/API keys
S2_API_KEY = os.environ.get("S2_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

CHROMA_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chroma_db"))

# List of topics to search Semantic Scholar for
TOPICS = [
    "attention mechanism transformer",
    "crispr cas9 gene editing",
    "quantum computing hardware",
    "thermonuclear fusion energy",
    "mrna vaccine immunotherapy",
    "large language models deep learning",
    "graphene nanotechnology",
    "solid state battery lithium",
]

def get_cd_index_path():
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "cd_index.csv")

def download_cd_index():
    csv_path = get_cd_index_path()
    if os.path.exists(csv_path):
        print(f"  ✓ CD index file already exists at {csv_path}")
        return csv_path
    
    url = "https://api.figshare.com/v2/articles/12923183"
    try:
        print("  Downloading CD index metadata from Figshare...")
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        files = data.get("files", [])
        if files:
            download_url = files[0].get("download_url")
            print(f"  Downloading CD Index dataset from {download_url} (this might take a while)...")
            r_file = requests.get(download_url, stream=True, timeout=60)
            r_file.raise_for_status()
            with open(csv_path, "wb") as f:
                for chunk in r_file.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"  ✓ CD Index saved to {csv_path}")
            return csv_path
    except Exception as e:
        print(f"  ✗ Could not download CD index: {e}. Falling back to simulated CD indices.")
    return None


# In ingest_papers.py
def fetch_arxiv_papers(topic: str, max_results: int = 50) -> list:
    """Fetch papers from arXiv API (no key needed)"""
    import urllib.request, urllib.parse, xml.etree.ElementTree as ET
    from datetime import datetime
    
    query = urllib.parse.quote(topic)
    url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results={max_results}&sortBy=relevance"
    
    try:
        with urllib.request.urlopen(url) as resp:
            tree = ET.parse(resp)
        
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers = []
        for entry in tree.getroot().findall("atom:entry", ns):
            id_el = entry.find("atom:id", ns)
            if id_el is None or not id_el.text:
                continue
            arxiv_id = id_el.text.split("/abs/")[-1].split("v")[0]
            
            title_el = entry.find("atom:title", ns)
            title = title_el.text.strip().replace("\n", " ") if title_el is not None else "Untitled"
            
            summary_el = entry.find("atom:summary", ns)
            abstract = summary_el.text.strip().replace("\n", " ") if summary_el is not None else ""
            
            pub_el = entry.find("atom:published", ns)
            year = int(pub_el.text[:4]) if pub_el is not None else datetime.now().year
            
            doi = None
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "doi":
                    href = link.get("href")
                    if href:
                        doi = href.replace("https://doi.org/", "")
            
            papers.append({
                "paperId": f"arxiv:{arxiv_id}",
                "externalIds": {"DOI": doi, "ArXiv": arxiv_id},
                "title": title,
                "abstract": abstract,
                "year": year,
                "fieldsOfStudy": [],
                "citationCount": 0,
                "influentialCitationCount": 0,
                "citationVelocity": 0.0
            })
        return papers
    except Exception as e:
        print(f"  ✗ arXiv search failed: {e}")
        return []

def fetch_wiki_summary(concept: str) -> str:
    title = concept.replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    headers = {
        "User-Agent": "AdjacencyMapper/1.0 (info@example.com)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.ok:
            data = resp.json()
            return data.get("extract", "")[:500]
    except Exception:
        pass
    return ""

def fetch_openalex_papers(query: str, limit: int = 40) -> list:
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per_page": limit,
    }
    headers = {
        "User-Agent": "mailto:info@example.com (Adjacency Mapper Client)"
    }
    try:
        print(f"  Searching OpenAlex for '{query}'...")
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        
        papers = []
        current_year = datetime.now().year
        for work in results:
            inverted = work.get("abstract_inverted_index") or {}
            words = {}
            for word, positions in inverted.items():
                for pos in positions:
                    words[pos] = word
            abstract = " ".join(words[p] for p in sorted(words)) if words else ""
            
            concepts = work.get("concepts", [])
            fields_of_study = [c.get("display_name") for c in concepts if c.get("display_name")]
            
            ext_ids = work.get("ids", {})
            doi_raw = ext_ids.get("doi")
            doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None
            
            arxiv = None
            if "arxiv" in ext_ids:
                arxiv = ext_ids.get("arxiv").replace("https://arxiv.org/abs/", "")
                
            citations = work.get("cited_by_count", 0)
            pub_year = work.get("publication_year")
            age = max(1, current_year - (pub_year or current_year))
            velocity = citations / age
            
            papers.append({
                "paperId": work.get("id"),
                "externalIds": {"DOI": doi, "ArXiv": arxiv},
                "title": work.get("title", "Untitled"),
                "abstract": abstract,
                "year": pub_year,
                "fieldsOfStudy": fields_of_study,
                "citationCount": citations,
                "influentialCitationCount": int(citations * 0.1),
                "citationVelocity": velocity
            })
        return papers
    except Exception as e:
        print(f"  ✗ OpenAlex search failed for query '{query}': {e}")
        return []

def fetch_semantic_scholar_papers(query: str, limit: int = 40) -> list:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY
    
    current_year = datetime.now().year
    year_range = f"{current_year-5}-{current_year}"
    
    params = {
        "query": query,
        "limit": limit,
        "year": year_range,
        "fields": "paperId,externalIds,title,abstract,year,fieldsOfStudy,citationCount,influentialCitationCount,citationVelocity",
    }
    
    try:
        print(f"  Searching Semantic Scholar for '{query}'...")
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("data", [])
    except Exception as e:
        print(f"  ✗ Semantic Scholar search failed for query '{query}': {e}")
        print("  → Falling back to OpenAlex and arXiv APIs...")
        oa_papers = fetch_openalex_papers(query, limit)
        ax_papers = fetch_arxiv_papers(query, limit)
        
        seen_titles = set()
        merged = []
        for p in oa_papers + ax_papers:
            norm_title = p.get("title", "").strip().lower()
            if norm_title and norm_title not in seen_titles:
                seen_titles.add(norm_title)
                merged.append(p)
        return merged

def load_cd_index_map(csv_path):
    if not csv_path:
        return {}
    try:
        print("  Loading CD Index CSV into memory...")
        cd_map = {}
        # Open using latin-1 encoding to prevent binary/unicode continuation byte crashes
        with open(csv_path, mode="r", encoding="latin-1") as f:
            reader = csv.DictReader(f)
            for row in reader:
                doi = row.get("doi")
                cd_val = row.get("cd_index")
                if doi and cd_val:
                    try:
                        cd_map[doi.strip()] = float(cd_val)
                    except ValueError:
                        pass
        return cd_map
    except Exception as e:
        print(f"  ✗ Failed to parse CD Index CSV: {e}")
        return {}

def compute_percentiles(session):
    papers = session.query(Paper).all()
    if not papers:
        return
    
    velocities = [p.citation_velocity or 0.0 for p in papers]
    cd_indices = [p.cd_index or 0.0 for p in papers]
    
    velocities.sort()
    cd_indices.sort()
    
    n = len(papers)
    for p in papers:
        v = p.citation_velocity or 0.0
        v_idx = velocities.index(v)
        p.citation_velocity_percentile = (v_idx / n) * 100.0
        
        c = p.cd_index or 0.0
        c_idx = cd_indices.index(c)
        p.cd_index_percentile = (c_idx / n) * 100.0
        
        # Recalculate composite breakthrough score
        novelty = p.novelty_score or 0.5
        p.breakthrough_score = (
            0.4 * p.citation_velocity_percentile + 
            0.3 * (novelty * 100.0) + 
            0.3 * p.cd_index_percentile
        )
    session.commit()
    print("  ✓ Computed percentiles and updated breakthrough scores.")

from embeddings import generate_local_embedding

def generate_embedding(text: str) -> list:
    return generate_local_embedding(text)


def run_ingestion():
    print("Starting Breakthrough Radar Ingestion Pipeline...")
    init_db()
    session = SessionLocal()
    
    # 1. CD Index download
    cd_path = download_cd_index()
    cd_map = load_cd_index_map(cd_path)
    
    # 2. Ingest papers from Semantic Scholar
    new_papers = []
    for topic in TOPICS:
        papers_data = fetch_semantic_scholar_papers(topic, limit=20)
        # Avoid rate limits
        time.sleep(1.0)
        
        for pdata in papers_data:
            corpus_id = pdata.get("paperId")
            if not corpus_id:
                continue
            
            # Check duplicate
            existing = session.query(Paper).filter_by(corpus_id=corpus_id).first()
            if existing:
                continue
            
            ext_ids = pdata.get("externalIds") or {}
            doi = ext_ids.get("DOI")
            arxiv_id = ext_ids.get("ArXiv")
            
            # Retrieve or simulate CD index
            cd_val = cd_map.get(doi) if doi else None
            if cd_val is None:
                # Mock a CD index value for MVP if missing
                cd_val = random.uniform(-0.3, 0.7)
                
            fields_list = pdata.get("fieldsOfStudy") or []
            abstract_text = pdata.get("abstract")
            
            paper = Paper(
                corpus_id=corpus_id,
                doi=doi,
                arxiv_id=arxiv_id,
                title=pdata.get("title", "Untitled"),
                abstract=abstract_text,
                year=pdata.get("year"),
                fields_of_study=json.dumps(fields_list),
                citation_count=pdata.get("citationCount", 0),
                citation_velocity=pdata.get("citationVelocity", 0.0),
                influential_citation_count=pdata.get("influentialCitationCount", 0),
                cd_index=cd_val,
                novelty_scored=0
            )
            session.add(paper)
            new_papers.append(paper)
            
        session.commit()
    
    print(f"  Total new papers ingested: {len(new_papers)}")
    
    # 3. Compute Percentiles
    compute_percentiles(session)
    
    # 4. Novelty scoring with Gemini
    unscored = session.query(Paper).filter_by(novelty_scored=0).all()
    if unscored:
        print(f"  Scoring novelty for {len(unscored)} papers...")
        # To avoid massive API usage, limit to top 15 by velocity/citation for novelty evaluation in one run
        unscored.sort(key=lambda x: x.citation_velocity or 0.0, reverse=True)
        
        for paper in unscored[:15]:
            # Retrieve 3 historic papers as context (or simulate)
            if paper.year is not None:
                prior_papers = session.query(Paper).filter(Paper.year <= paper.year, Paper.corpus_id != paper.corpus_id).limit(3).all()
            else:
                prior_papers = session.query(Paper).filter(Paper.corpus_id != paper.corpus_id).limit(3).all()
            priors = "\n\n".join([f"Prior Title: {p.title}\nPrior Abstract: {p.abstract or ''}" for p in prior_papers]) if prior_papers else "None available."
            
            score = score_novelty(paper.abstract, priors)
            paper.novelty_score = score
            paper.novelty_scored = 1
            # Add small delay to stay under Gemini free tier RPM
            time.sleep(1.0)
            
        session.commit()
        # Recalculate percentiles with new novelty scores
        compute_percentiles(session)
        
    # 5. Populate SQLite Embeddings
    missing_embeddings = session.query(Paper).filter(Paper.embedding == None).all()
    if missing_embeddings:
        print(f"  Generating Gemini embeddings for {len(missing_embeddings)} papers...")
        for p in missing_embeddings:
            if p.abstract:
                emb = generate_embedding(p.abstract)
                p.embedding = json.dumps(emb)
                time.sleep(0.5)
        session.commit()
    
    # 6. Ingest citation edges for the graph layer
    all_ids = [p.corpus_id for p in session.query(Paper.corpus_id).all()]
    print(f"  Fetching citation edges for {min(len(all_ids), 30)} papers...")
    ingest_citation_edges(session, all_ids[:30], s2_api_key=S2_API_KEY)

    # 7. Build FAISS vector index
    from vector_index import build_faiss_index
    build_faiss_index(session)

    # 8. Extract concepts and populate Concept taxonomy
    from concept_walker import populate_concepts_from_db
    populate_concepts_from_db(session)

    session.close()
    print("Ingestion Pipeline Completed Successfully!")


def ingest_citation_edges(session, paper_ids: list, s2_api_key: str | None = None) -> None:
    """
    For each paper corpus_id, fetch its references from OpenAlex and store as CitationEdges.
    Safe to call multiple times — skips papers that already have edges stored.
    """
    import urllib.parse

    for corpus_id in paper_ids:
        # Skip if we already have edges for this paper
        existing = session.query(CitationEdge).filter_by(source_corpus_id=corpus_id).first()
        if existing:
            continue

        paper = session.query(Paper).filter_by(corpus_id=corpus_id).first()
        if not paper:
            continue

        headers = {"User-Agent": "mailto:info@example.com (Adjacency Mapper Client)"}
        url = None

        if corpus_id.startswith("https://openalex.org/") or corpus_id.startswith("W"):
            work_id = corpus_id
            if not work_id.startswith("https://"):
                work_id = f"https://openalex.org/{work_id}"
            url = f"https://api.openalex.org/works/{work_id}"
        elif paper.doi:
            url = f"https://api.openalex.org/works/https://doi.org/{paper.doi.strip()}"
        elif paper.arxiv_id:
            clean_arxiv = paper.arxiv_id.strip()
            if not clean_arxiv.startswith("arXiv:"):
                clean_arxiv = f"arXiv:{clean_arxiv}"
            url = f"https://api.openalex.org/works?filter=arxiv:{clean_arxiv}"
        else:
            encoded_title = urllib.parse.quote(paper.title)
            url = f"https://api.openalex.org/works?search={encoded_title}&per_page=1"

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 429:
                print("  OpenAlex rate-limited, waiting 2s...")
                time.sleep(2)
                resp = requests.get(url, headers=headers, timeout=10)
            if not resp.ok:
                continue

            data = resp.json()
            if "results" in data:
                results = data.get("results", [])
                if not results:
                    continue
                work = results[0]
            else:
                work = data

            referenced_works = work.get("referenced_works", [])
            source_year = paper.year

            new_edges = []
            for ref_id in referenced_works:
                if not ref_id or ref_id == corpus_id:
                    continue
                new_edges.append(
                    CitationEdge(
                        source_corpus_id=corpus_id,
                        target_corpus_id=ref_id,
                        source_year=source_year,
                    )
                )

            if new_edges:
                try:
                    session.bulk_save_objects(new_edges)
                    session.commit()
                    print(f"  ✓ Inserted {len(new_edges)} citation edges for {corpus_id} from OpenAlex")
                except Exception:
                    session.rollback()
                    # print(f"  ✗ Failed to insert edges for {corpus_id} (likely duplicate constraint, skipping)")

            time.sleep(0.2)  # Polite delay

        except Exception as e:
            print(f"  ✗ OpenAlex edge fetch failed for {corpus_id}: {e}")

if __name__ == "__main__":
    run_ingestion()
