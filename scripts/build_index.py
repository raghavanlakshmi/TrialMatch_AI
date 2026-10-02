"""Freeze criterion IDs, semantic chunks, and the local cosine Chroma index."""

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.criteria import write_criteria
from src.retrieval import COLLECTION_NAME, DEFAULT_CHROMA_PATH, EMBEDDING_MODEL, build_chunks, write_chunks
from src.trial_loader import load_trials


def build_vector_index(chunks, persist_path: Path = DEFAULT_CHROMA_PATH) -> None:
    import chromadb
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL)
    embeddings = model.encode([chunk.text for chunk in chunks], normalize_embeddings=True, show_progress_bar=True).tolist()
    client = chromadb.PersistentClient(path=str(persist_path))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    for start in range(0, len(chunks), 250):
        batch = chunks[start:start + 250]
        collection.add(
            ids=[chunk.chunk_id for chunk in batch],
            documents=[chunk.text for chunk in batch],
            embeddings=embeddings[start:start + len(batch)],
            metadatas=[{
                "nct_id": chunk.nct_id, "section": chunk.section,
                "criterion_id": chunk.criterion_id or "", "source": chunk.source,
            } for chunk in batch],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-vector", action="store_true", help="Create criteria/chunks without downloading an embedding model.")
    args = parser.parse_args()
    trials = load_trials()
    write_criteria(trials)
    chunks = build_chunks(trials)
    write_chunks(chunks)
    if not args.skip_vector:
        build_vector_index(chunks)
    print(f"Frozen {sum(len(v) for v in __import__('src.criteria', fromlist=['load_criteria']).load_criteria().values())} criteria and {len(chunks)} discovery chunks.")
    print("Built cosine Chroma index." if not args.skip_vector else "Skipped vector index by request.")


if __name__ == "__main__":
    main()
