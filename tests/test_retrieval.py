from src.criteria import load_criteria
from src.retrieval import BM25Retriever, build_chunks, load_chunks, reciprocal_rank_fusion
from src.schemas import RetrievalChunk
from src.trial_loader import load_trials


def chunk(chunk_id, nct_id):
    return RetrievalChunk(chunk_id=chunk_id, text="synthetic", nct_id=nct_id, section="trial_summary")


def test_rrf_rewards_a_chunk_ranked_in_both_lists():
    shared = chunk("shared", "NCT00000001")
    one_list = chunk("single", "NCT00000002")
    result = reciprocal_rank_fusion(
        [{"chunk": one_list, "score": 10}, {"chunk": shared, "score": 9}],
        [{"chunk": shared, "score": 0.8}],
    )
    assert result[0]["nct_id"] == "NCT00000001"


def test_discovery_chunks_have_metadata_and_exclude_exclusion_criteria():
    chunks = load_chunks()
    criteria = load_criteria()
    assert chunks and all(c.source == "ClinicalTrials.gov" for c in chunks)
    assert {c.section for c in chunks} == {"trial_summary", "inclusion"}
    assert all(c.criterion_id is None or c.criterion_id.startswith("INC-") for c in chunks)
    assert any(item.type == "exclusion" for values in criteria.values() for item in values)
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_bm25_returns_scores_and_expected_metadata():
    results = BM25Retriever(load_chunks()).search("colorectal KRAS G12C", 5)
    assert len(results) == 5
    assert all(isinstance(item["score"], float) for item in results)
    assert all(item["chunk"].nct_id.startswith("NCT") for item in results)
