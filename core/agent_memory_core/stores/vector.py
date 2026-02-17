import os
import numpy as np
import logging
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
    def __init__(self, storage_path: str, model_name: str = "all-MiniLM-L6-v2", dimension: int = 384):
        self.storage_path = storage_path
        self.index_path = os.path.join(storage_path, "vectors.npy")
        self.meta_path = os.path.join(storage_path, "vector_meta.npy")
        self.model_name = model_name
        self.dimension = dimension
        self._model = None
        self._vectors = None # NumPy array of vectors
        self._doc_ids = []

        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)

    @property
    def model(self):
        if not EMBEDDING_AVAILABLE:
            raise ImportError("Embedding model dependencies (sentence-transformers) not found.")
        if self._model is None:
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            self._model = SentenceTransformer(self.model_name)
            self._model.show_progress_bar = False
        return self._model

    def load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self._vectors = np.load(self.index_path)
                self._doc_ids = np.load(self.meta_path, allow_pickle=True).tolist()
                logger.info(f"Loaded {len(self._doc_ids)} vectors from disk")
            except Exception as e:
                logger.error(f"Failed to load vector store: {e}")
                self._vectors = None

    def save(self):
        if self._vectors is not None:
            np.save(self.index_path, self._vectors)
            np.save(self.meta_path, np.array(self._doc_ids, dtype=object))

    def add_documents(self, documents: List[Dict[str, Any]]):
        if not documents or not EMBEDDING_AVAILABLE: return
        
        texts = [doc["content"] for doc in documents]
        ids = [doc["id"] for doc in documents]
        
        new_embeddings = self.model.encode(texts)
        new_embeddings = np.array(new_embeddings).astype('float32')

        if self._vectors is None:
            self._vectors = new_embeddings
        else:
            self._vectors = np.vstack([self._vectors, new_embeddings])
            
        self._doc_ids.extend(ids)
        self.save()

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
        top_indices = np.argsort(similarities)[::-1][:limit]
        
        results = []
        for idx in top_indices:
            results.append({
                "id": self._doc_ids[idx],
                "score": float(similarities[idx])
            })
        return results
