import os
import numpy as np
import logging
import platform
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    import transformers
    transformers.logging.set_verbosity_error()
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

VECTOR_AVAILABLE = True # NumPy is always available

class VectorStore:
    """
    A simple vector store using NumPy for cosine similarity.
    Reliable and stable in environments like Termux.
    """
    def __init__(self, storage_path: str, model_name: str = "all-MiniLM-L6-v2", dimension: int = 384, workers: int = 0):
        self.storage_path = storage_path
        self.index_path = os.path.join(storage_path, "vectors.npy")
        self.meta_path = os.path.join(storage_path, "vector_meta.npy")
        self.model_name = model_name
        self.dimension = dimension
        self.workers = self._resolve_workers(workers)
        self._model = None
        self._pool = None
        self._vectors = None # NumPy array of vectors
        self._doc_ids = []
        self._deleted_ids = set()
        self._dirty = False
        self._unsaved_count = 0

        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)

    def _resolve_workers(self, workers: int) -> int:
        if workers > 0:
            return workers
        
        # Default to 1 (Single-threaded) for safety in constrained environments like Termux
        # or when running parallel tests (to avoid nested multiprocessing).
        # Multi-processing should be explicitly requested by passing workers > 1.
        return 1

    @property
    def model(self):
        if not EMBEDDING_AVAILABLE:
            raise ImportError("Embedding model dependencies (sentence-transformers) not found.")
        if self._model is None:
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            self._model = SentenceTransformer(self.model_name)
            self._model.show_progress_bar = False
        return self._model

    def _get_pool(self):
        if not EMBEDDING_AVAILABLE or self.workers <= 1:
            return None
        if self._pool is None:
            try:
                logger.info(f"Starting multi-process pool with {self.workers} workers...")
                # target_devices=None uses all GPUs if available, otherwise CPUs
                # For Termux/Android we explicitly use CPU to avoid issues
                is_android = os.path.exists("/data/data/com.termux") or platform.system() == "Android"
                target_devices = ["cpu"] * self.workers if is_android else None
                
                self._pool = self.model.start_multi_process_pool(target_devices=target_devices)
            except Exception as e:
                logger.warning(f"Failed to start multi-process pool: {e}. Falling back to single-process.")
                self.workers = 1
                self._pool = None
        return self._pool

    def close(self):
        """Stops the multi-process pool and releases resources."""
        self.save()
        if self._pool is not None:
            try:
                self.model.stop_multi_process_pool(self._pool)
                logger.info("Multi-process pool stopped.")
            except Exception as e:
                logger.debug(f"Error stopping pool: {e}")
            self._pool = None

    def load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self._vectors = np.load(self.index_path)
                self._doc_ids = np.load(self.meta_path, allow_pickle=True).tolist()
                self._deleted_ids = set()
                logger.info(f"Loaded {len(self._doc_ids)} vectors from disk")
            except Exception as e:
                logger.error(f"Failed to load vector store: {e}")
                self._vectors = None

    def save(self):
        if self._vectors is not None and self._dirty:
            np.save(self.index_path, self._vectors)
            np.save(self.meta_path, np.array(self._doc_ids, dtype=object))
            self._dirty = False
            self._unsaved_count = 0
            logger.debug("Vector store flushed to disk.")

    def remove_id(self, fid: str):
        """Soft-removes a vector from the store."""
        if fid in self._doc_ids:
            self._deleted_ids.add(fid)
            logger.info(f"Marked vector {fid} as deleted (soft delete)")
            
            # Periodically compact if deleted items > 20% of index
            if len(self._deleted_ids) > max(10, len(self._doc_ids) * 0.2):
                self.compact()

    def compact(self):
        """Physically removes soft-deleted vectors and rebuilds index."""
        if not self._deleted_ids or self._vectors is None:
            return

        logger.info(f"Compacting vector store: removing {len(self._deleted_ids)} items...")
        
        remaining_indices = [i for i, fid in enumerate(self._doc_ids) if fid not in self._deleted_ids]
        
        if not remaining_indices:
            self._vectors = None
            self._doc_ids = []
            if os.path.exists(self.index_path): os.remove(self.index_path)
            if os.path.exists(self.meta_path): os.remove(self.meta_path)
        else:
            self._vectors = self._vectors[remaining_indices]
            self._doc_ids = [self._doc_ids[i] for i in remaining_indices]
            self.save()

        self._deleted_ids = set()
        logger.info("Vector store compaction complete")

    def add_documents(self, documents: List[Dict[str, Any]]):
        if not documents or not EMBEDDING_AVAILABLE: return
        
        texts = [doc["content"] for doc in documents]
        ids = [doc["id"] for doc in documents]
        
        pool = self._get_pool()
        if pool:
            # Multi-process encoding for lists of sentences
            new_embeddings = self.model.encode(texts, pool=pool, batch_size=32)
        else:
            # Single-process encoding
            new_embeddings = self.model.encode(texts)
            
        new_embeddings = np.array(new_embeddings).astype('float32')

        if self._vectors is None:
            self._vectors = new_embeddings
        else:
            self._vectors = np.vstack([self._vectors, new_embeddings])
            
        self._doc_ids.extend(ids)
        self._dirty = True
        self._unsaved_count += len(documents)
        
        if self._unsaved_count >= 50:
            self.save()

    def get_vector(self, fid: str) -> Optional[np.ndarray]:
        """Retrieves the vector for a specific document ID."""
        if self._vectors is None or fid not in self._doc_ids:
            return None
        try:
            idx = self._doc_ids.index(fid)
            if fid in self._deleted_ids: return None
            return self._vectors[idx]
        except ValueError:
            return None

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if self._vectors is None or len(self._vectors) == 0 or not EMBEDDING_AVAILABLE:
            return []

        query_vector = self.model.encode([query])[0].astype('float32')
        
        # Calculate cosine similarity: (A dot B) / (|A| * |B|)
        # Since sentence-transformers usually returns normalized vectors, 
        # it's just a dot product.
        norms = np.linalg.norm(self._vectors, axis=1)
        query_norm = np.linalg.norm(query_vector)
        
        # Dot product
        similarities = np.dot(self._vectors, query_vector) / (norms * query_norm + 1e-9)
        
        # Get top indices
        top_indices = np.argsort(similarities)[::-1]
        
        results = []
        for idx in top_indices:
            fid = self._doc_ids[idx]
            if fid in self._deleted_ids: continue
            
            results.append({
                "id": fid,
                "score": float(similarities[idx])
            })
            if len(results) >= limit: break
            
        return results
