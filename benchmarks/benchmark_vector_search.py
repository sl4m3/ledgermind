import sys
import os
import time
import numpy as np
import shutil
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from ledgermind.core.stores.vector import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("benchmark")

def run_benchmark():
    base_dir = "bench_temp"
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir)
    os.makedirs(base_dir)

    # Initialize store
    # We use a fake model name or handle embedding generation manually to avoid downloading models
    # However, VectorStore expects a valid model name for SentenceTransformer or GGUF.
    # To bypass model loading, we can mock the model or just use a small one.
    # But wait, VectorStore uses `self.model.encode`.
    # Let's see if we can just inject vectors directly.
    # The `add_documents` method calls `self.model.encode`.
    # But we can manipulate `_vectors` directly for benchmarking the search part.

    store = VectorStore(storage_path=base_dir, model_name="all-MiniLM-L6-v2")

    # Mock the internal vectors to avoid using the model for 20k items (which would be slow)
    dim = 384
    count = 20000
    logger.info(f"Generating {count} random vectors of dimension {dim}...")

    vectors = np.random.rand(count, dim).astype('float32')
    # Normalize them to simulate embeddings
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / norms

    store._vectors = vectors
    store._doc_ids = [f"doc_{i}" for i in range(count)]
    store._dirty = True

    # Build Annoy Index
    logger.info("Building Annoy Index...")
    store.save()

    # We also need a query vector
    query_text = "test query"
    # We'll use the real model for the query to get a valid vector, or just mock it.
    # But `search` calls `self._get_embedding(query)`.
    # Let's mock `_get_embedding` or `model.encode`.

    # Mocking _get_embedding to return a random vector
    original_get_embedding = store._get_embedding

    fake_query_vector = np.random.rand(dim).astype('float32')
    fake_query_vector /= np.linalg.norm(fake_query_vector)

    store._get_embedding = lambda text: fake_query_vector

    logger.info("Starting benchmark...")
    start_time = time.time()
    iterations = 100

    for i in range(iterations):
        results = store.search("test query", limit=10)
        if len(results) != 10:
            logger.warning(f"Expected 10 results, got {len(results)}")

    end_time = time.time()
    avg_time = (end_time - start_time) / iterations

    print(f"Benchmark Results:")
    print(f"Total Vectors: {count}")
    print(f"Iterations: {iterations}")
    print(f"Total Time: {end_time - start_time:.4f}s")
    print(f"Average Search Time: {avg_time:.6f}s")

    # Cleanup
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir)

if __name__ == "__main__":
    run_benchmark()
