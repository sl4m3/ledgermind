import pytest
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.core.schemas import MemoryEvent

def test_count_links_for_semantic_batch(tmp_path):
    store = EpisodicStore(db_path=str(tmp_path / "test.db"))

    # Add a few events linked to "doc1"
    store.append(MemoryEvent(source="system", kind="result", content="c1", context={}), linked_id="doc1")
    store.append(MemoryEvent(source="system", kind="result", content="c2", context={}), linked_id="doc1", link_strength=0.5)

    # Add an event linked to "doc2"
    store.append(MemoryEvent(source="system", kind="result", content="c3", context={}), linked_id="doc2")

    # Unlinked event
    store.append(MemoryEvent(source="system", kind="result", content="c4", context={}))

    res = store.count_links_for_semantic_batch(["doc1", "doc2", "doc3"])

    assert res["doc1"][0] == 2
    assert res["doc1"][1] == 1.5

    assert res["doc2"][0] == 1
    assert res["doc2"][1] == 1.0

    assert res["doc3"][0] == 0
    assert res["doc3"][1] == 0.0
