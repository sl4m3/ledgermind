import os
import time
import numpy as np
import logging
import platform
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Lazy loading flags
_TRANSFORMERS_AVAILABLE = None
_LLAMA_AVAILABLE = None
_ANNOY_AVAILABLE = None

def _is_transformers_available():
    # If test has explicitly set the global to False/True, respect it
    if EMBEDDING_AVAILABLE is not None:
        return EMBEDDING_AVAILABLE
        
    global _TRANSFORMERS_AVAILABLE
    if _TRANSFORMERS_AVAILABLE is None:
        try:
            import sentence_transformers
            import transformers
            transformers.logging.set_verbosity_error()
            _TRANSFORMERS_AVAILABLE = True
        except ImportError:
            _TRANSFORMERS_AVAILABLE = False
    return _TRANSFORMERS_AVAILABLE

def _is_llama_available():
    if LLAMA_AVAILABLE is not None:
        return LLAMA_AVAILABLE
        
    global _LLAMA_AVAILABLE
    if _LLAMA_AVAILABLE is None:
        try:
            from llama_cpp import Llama
            _LLAMA_AVAILABLE = True
        except ImportError:
            _LLAMA_AVAILABLE = False
    return _LLAMA_AVAILABLE

def _is_annoy_available():
    if ANNOY_AVAILABLE is not None:
        return ANNOY_AVAILABLE
        
    global _ANNOY_AVAILABLE
    if _ANNOY_AVAILABLE is None:
        try:
            from annoy import AnnoyIndex
            _ANNOY_AVAILABLE = True
        except ImportError:
            _ANNOY_AVAILABLE = False
    return _ANNOY_AVAILABLE

# Compatibility flags (Legacy globals)
# We initialize them to None so tests can still patch them, 
# but the core logic now uses _is_... functions.
EMBEDDING_AVAILABLE = None
LLAMA_AVAILABLE = None
ANNOY_AVAILABLE = None

def _is_llama_available():
    global LLAMA_AVAILABLE
    if LLAMA_AVAILABLE is not None:
        return LLAMA_AVAILABLE
        
    global _LLAMA_AVAILABLE
    if _LLAMA_AVAILABLE is None:
        try:
            from llama_cpp import Llama
            _LLAMA_AVAILABLE = True
        except ImportError:
            _LLAMA_AVAILABLE = False
    return _LLAMA_AVAILABLE

VECTOR_AVAILABLE = True # NumPy is always available

class GGUFEmbeddingAdapter:
    """Adapts llama-cpp-python to match SentenceTransformer's encode API."""
    def __init__(self, model_path: str):
        import contextlib
        import io
        from llama_cpp import Llama
        
        logger.info(f"Loading GGUF Model: {model_path}")
        # Optimized for Termux/Mobile: 4 threads is usually the sweet spot for performance vs heat
        with contextlib.redirect_stderr(io.StringIO()):
            self.client = Llama(
                model_path=model_path, 
                embedding=True, 
                verbose=False, 
                n_ctx=8192, 
                n_gpu_layers=0,
                n_threads=4,
                n_batch=512,
                pooling_type=1 
            )
        self._cache = {}
        self._max_cache = 100
        self.model_path = model_path.lower()
        
        # Robust dimension detection
        try:
            test_emb_res = self.client.create_embedding("test")
            # Handle different response formats
            data = test_emb_res.get('data', [])
            if data and 'embedding' in data[0]:
                raw_emb = data[0]['embedding']
                self.dimension = len(raw_emb)
            else:
                # Fallback: some versions might return different structure
                self.dimension = 1024 # Standard for Jina v5 Small
            
            logger.info(f"GGUF Model Initialized. Dimension: {self.dimension}")
        except Exception as e:
            logger.error(f"Failed to detect GGUF dimension: {e}")
            self.dimension = 1024

    def encode(self, sentences: Any, **kwargs) -> np.ndarray:
        import contextlib
        import io
        
        is_single = isinstance(sentences, str)
        input_list = [sentences] if is_single else sentences
        
        # Task-specific prefix for Jina v5
        prefix = ""
        if "jina-embeddings-v5" in self.model_path:
            prefix = "text-matching: "

        embeddings = []
        with contextlib.redirect_stderr(io.StringIO()):
            for text in input_list:
                if text in self._cache:
                    embeddings.append(self._cache[text])
                    continue
                    
                try:
                    # Apply prefix if needed
                    processed_text = f"{prefix}{text}" if prefix else text
                    res = self.client.create_embedding(processed_text)
                    emb = res['data'][0]['embedding']
                    # If llama-cpp returns a scalar or malformed list, wrap it
                    if not isinstance(emb, list):
                        emb = [emb]
                    
                    # Update cache
                    if len(self._cache) >= self._max_cache:
                        # Basic eviction
                        self._cache.pop(next(iter(self._cache)))
                    self._cache[text] = emb
                    
                    embeddings.append(emb)
                except Exception as e:
                    logger.error(f"GGUF Encoding failed for text: {e}")
                    # Return zero vector on failure to maintain shape
                    embeddings.append([0.0] * self.dimension)
        
        arr = np.array(embeddings).astype('float32')
        return arr[0] if is_single else arr

    def get_sentence_embedding_dimension(self):
        return self.dimension

    def close(self):
        """Explicitly release resources to avoid TypeError in __del__."""
        if hasattr(self, 'client') and self.client:
            try:
                # llama-cpp-python objects sometimes have internal close/del issues
                # during late interpreter shutdown.
                self.client.close()
                self.client = None
            except:
                pass

    def __del__(self):
        self.close()

# Module-level cache for models
_MODEL_CACHE = {}

import atexit
def _cleanup_model_cache():
    global _MODEL_CACHE
    for model in list(_MODEL_CACHE.values()):
        if hasattr(model, 'close'):
            try:
                model.close()
            except Exception:
                pass
    _MODEL_CACHE.clear()

atexit.register(_cleanup_model_cache)

class VectorStore:
    """
    A simple vector store using NumPy for cosine similarity.
    Reliable and stable in environments like Termux.
    """
    def __init__(self, storage_path: str, model_name: str = "../../models/v5-small-text-matching-Q4_K_M.gguf", dimension: int = 384, workers: int = 0):
        self.storage_path = storage_path
        self.index_path = os.path.join(storage_path, "vectors.npy")
        self.meta_path = os.path.join(storage_path, "vector_meta.npy")
        self.model_name = model_name
        self.dimension = dimension
        self.workers = self._resolve_workers(workers)
        self._pool = None
        self._vectors = None # NumPy array of vectors
        self._doc_ids = []
        self._deleted_ids = set()
        self._dirty = False
        self._unsaved_count = 0
        
        # Performance Cache: text -> vector
        self._embedding_cache = {}
        self._max_cache_size = 500

        # Annoy Index for Approximate Nearest Neighbor Search
        self._annoy_index = None
        self._indexed_count = 0

        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)

    def _build_annoy_index(self):
        """Builds an Annoy index for the current vectors."""
        if not _is_annoy_available() or self._vectors is None:
            return

        try:
            from annoy import AnnoyIndex
            logger.info(f"Building Annoy index for {len(self._vectors)} vectors...")
            f = self._vectors.shape[1]
            # 'angular' metric is equivalent to cosine distance for normalized vectors
            t = AnnoyIndex(f, 'angular')

            # Add items to the index
            for i in range(len(self._vectors)):
                t.add_item(i, self._vectors[i])

            # 20 trees provides a good balance between build time and accuracy
            t.build(20)

            annoy_path = os.path.join(self.storage_path, "vectors.ann")
            t.save(annoy_path)

            self._annoy_index = t
            self._indexed_count = len(self._vectors)
            logger.info(f"Built Annoy index for {self._indexed_count} vectors")
        except Exception as e:
            logger.error(f"Failed to build Annoy index: {e}")
            self._annoy_index = None
            self._indexed_count = 0

    def _get_embedding(self, text: str) -> np.ndarray:
        """Internal helper with caching."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        
        # Single-process encoding
        vector = self.model.encode([text])[0].astype('float32')
        
        # Cache management (FIFO-ish)
        if len(self._embedding_cache) >= self._max_cache_size:
            # Simple eviction
            first_key = next(iter(self._embedding_cache))
            del self._embedding_cache[first_key]
            
        self._embedding_cache[text] = vector
        return vector

    def _resolve_workers(self, workers: int) -> int:
        if workers > 0:
            return workers
        
        # Default to 1 (Single-threaded) for safety in constrained environments like Termux
        # or when running parallel tests (to avoid nested multiprocessing).
        # Multi-processing should be explicitly requested by passing workers > 1.
        return 1

    @property
    def model(self):
        cache_key = self.model_name
        if cache_key not in _MODEL_CACHE:
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            
            # Scenario A: GGUF Model (4-bit efficient)
            if self.model_name.lower().endswith(".gguf"):
                if not LLAMA_AVAILABLE:
                    raise ImportError("llama-cpp-python not found. Required for GGUF models. Run: pip install llama-cpp-python")
                
                # Auto-download for known models if file is missing
                if not os.path.exists(self.model_name):
                    self._ensure_model_downloaded(self.model_name)
                    
                _MODEL_CACHE[cache_key] = GGUFEmbeddingAdapter(self.model_name)
                logger.info(f"GGUF Vector Engine Initialized: {self.model_name}")
                return _MODEL_CACHE[cache_key]

            # Scenario B: Standard Transformers Model
            if not EMBEDDING_AVAILABLE:
                raise ImportError("sentence-transformers not found.")
            
            # Advanced model configuration
            model_kwargs = {}
            
            # Special handling for Jina v5 models
            if "jina-embeddings-v5" in self.model_name.lower():
                model_kwargs["default_task"] = "text-matching"
            
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer(
                    self.model_name, 
                    trust_remote_code=True,
                    model_kwargs=model_kwargs
                )
            except Exception as e:
                logger.warning(f"Standard loading failed, trying fallback: {e}")
                # Use module import to avoid UnboundLocalError if shadowing global class
                import sentence_transformers
                model = sentence_transformers.SentenceTransformer(self.model_name, trust_remote_code=True)

            model.show_progress_bar = False
            dim = model.get_sentence_embedding_dimension()
            logger.info(f"Vector Engine Initialized: {self.model_name} | Dimension: {dim} | Task: {model_kwargs.get('default_task', 'auto')}")
            _MODEL_CACHE[cache_key] = model
            
        return _MODEL_CACHE[cache_key]

    def _ensure_model_downloaded(self, model_path: str):
        """Downloads known GGUF models from Hugging Face if they are missing locally."""
        # Mapping of filenames to their direct HF download URLs
        KNOWN_GGUF_MODELS = {
            "v5-small-text-matching-q4_k_m.gguf": "https://huggingface.co/jinaai/jina-embeddings-v5-text-small-text-matching-GGUF/resolve/main/v5-small-text-matching-Q4_K_M.gguf",
            "jina-embeddings-v5-text-small-text-matching-q4_k_m.gguf": "https://huggingface.co/jinaai/jina-embeddings-v5-text-small-text-matching-GGUF/resolve/main/jina-embeddings-v5-text-small-text-matching-Q4_K_M.gguf"
        }

        filename = os.path.basename(model_path).lower()
        if filename not in KNOWN_GGUF_MODELS:
            logger.warning(f"GGUF model {filename} not found locally and no auto-download URL known. Please download it manually.")
            return

        url = KNOWN_GGUF_MODELS[filename]
        logger.info(f"Model missing. Downloading {filename} from Hugging Face...")
        
        try:
            os.makedirs(os.path.dirname(model_path), exist_ok=True)
            
            import httpx
            with open(model_path, "wb") as f:
                with httpx.stream("GET", url, follow_redirects=True, timeout=None) as response:  # nosec B113
                    if response.status_code != 200:
                        raise RuntimeError(f"Failed to download model: HTTP {response.status_code}")
                        
                    total = int(response.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_log_time = time.time()
                    
                    for chunk in response.iter_bytes(chunk_size=1024*1024): # 1MB chunks
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Log progress every 5 seconds to avoid flooding
                        if time.time() - last_log_time > 5.0:
                            progress = (downloaded / total * 100) if total > 0 else 0
                            logger.info(f"Downloading Model: {progress:.1f}% ({downloaded / (1024*1024):.1f} MB)")
                            last_log_time = time.time()
                            
            logger.info(f"Successfully downloaded {filename} to {model_path}")
        except Exception as e:
            if os.path.exists(model_path):
                os.remove(model_path)
            logger.error(f"Failed to auto-download GGUF model: {e}")
            raise RuntimeError(f"GGUF model missing and auto-download failed: {e}")

    def _get_pool(self):
        if not _is_transformers_available() or self.workers <= 1:
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
        if self._pool is not None:
            try:
                self.model.stop_multi_process_pool(self._pool)
                logger.info("Multi-process pool stopped.")
            except Exception as e:
                logger.debug(f"Error stopping pool: {e}")
            self._pool = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


    def load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self._vectors = np.load(self.index_path)
                self._doc_ids = np.load(self.meta_path, allow_pickle=True).tolist()
                self._deleted_ids = set()

                # Check if vectors are normalized (checking first one is usually enough)
                # But to be safe and simple, we normalize everything on load.
                # This ensures backward compatibility and allows dot-product optimization.
                if self._vectors is not None and len(self._vectors) > 0:
                    norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
                    norms[norms == 0] = 1e-9
                    self._vectors = self._vectors / norms

                logger.info(f"Loaded {len(self._doc_ids)} vectors from disk")

                # Load Annoy Index if available
                annoy_path = os.path.join(self.storage_path, "vectors.ann")
                if _is_annoy_available() and os.path.exists(annoy_path) and self._vectors is not None:
                    try:
                        from annoy import AnnoyIndex
                        f = self._vectors.shape[1]
                        t = AnnoyIndex(f, 'angular')
                        t.load(annoy_path)
                        self._annoy_index = t
                        self._indexed_count = t.get_n_items()
                        logger.info(f"Loaded Annoy index with {self._indexed_count} items")
                    except Exception as e:
                        logger.warning(f"Failed to load Annoy index: {e}")
                        self._annoy_index = None
                        self._indexed_count = 0
            except Exception as e:
                logger.error(f"Failed to load vector store: {e}")
                self._vectors = None

    def save(self):
        if self._vectors is not None and self._dirty:
            np.save(self.index_path, self._vectors)
            np.save(self.meta_path, np.array(self._doc_ids, dtype=object))

            # Rebuild Annoy index on save
            self._build_annoy_index()

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
            annoy_path = os.path.join(self.storage_path, "vectors.ann")
            if os.path.exists(annoy_path): os.remove(annoy_path)
            self._annoy_index = None
            self._indexed_count = 0
        else:
            self._vectors = self._vectors[remaining_indices]
            self._doc_ids = [self._doc_ids[i] for i in remaining_indices]
            self._dirty = True
            self.save()

        self._deleted_ids = set()

        # If save failed or wasn't called (shouldn't happen with dirty=True), invalidate index
        if self._dirty:
             self._annoy_index = None
             self._indexed_count = 0

        logger.info("Vector store compaction complete")

    def add_documents(self, documents: List[Dict[str, Any]], embeddings: Optional[List[np.ndarray]] = None):
        if not documents: return
        
        if embeddings is not None:
            new_embeddings = np.array(embeddings).astype('float32')
        elif self.model is not None:
            texts = [doc["content"] for doc in documents]
            pool = self._get_pool()
            if pool:
                # Multi-process encoding for lists of sentences
                new_embeddings = self.model.encode(texts, pool=pool, batch_size=32)
            else:
                # Single-process encoding
                new_embeddings = self.model.encode(texts)
            new_embeddings = np.array(new_embeddings).astype('float32')
        else:
            return
            
        # Ensure 2D array for consistent norm calculations (fix for axis 1 error)
        if new_embeddings.ndim == 1:
            new_embeddings = new_embeddings.reshape(1, -1)

        ids = [doc["id"] for doc in documents]

        # Normalize immediately for dot-product optimization
        norms = np.linalg.norm(new_embeddings, axis=1, keepdims=True)
        # Avoid division by zero
        norms[norms == 0] = 1e-9
        new_embeddings = new_embeddings / norms

        # Dimension check and adjustment
        if self._vectors is not None:
            if self._vectors.shape[1] != new_embeddings.shape[1]:
                logger.warning(f"Vector dimension mismatch ({self._vectors.shape[1]} vs {new_embeddings.shape[1]}). Resetting index.")
                self._vectors = None
                self._doc_ids = []
                self._dirty = True

        if self._vectors is None:
            self._vectors = new_embeddings
        else:
            self._vectors = np.vstack([self._vectors, new_embeddings])
            
        self._doc_ids.extend(ids)
        self._dirty = True
        self._unsaved_count += len(documents)
        
        # Performance optimization: Very high threshold for disk flushes to avoid IO bottleneck
        if self._unsaved_count >= 500:
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
        # If we have vectors, we can search regardless of engine availability (using NumPy)
        if self._vectors is None or len(self._vectors) == 0:
            # If no vectors, we need the engine to encode the query (unless it's already a vector, but search expects string)
            # Check availability only if we really need to encode
            is_gguf = self.model_name.endswith(".gguf")
            if is_gguf and not _is_llama_available():
                return []
            if not is_gguf and not _is_transformers_available():
                return []

        # Use cached embedding helper
        query_vector = self._get_embedding(query)
        
        # Ensure numpy array and flatten if needed
        if not isinstance(query_vector, np.ndarray):
            query_vector = np.array(query_vector).astype('float32')
        query_vector = query_vector.flatten()

        # Normalize query vector for dot product
        q_norm = np.linalg.norm(query_vector)
        if q_norm > 0:
            query_vector = query_vector / q_norm

        # Dimension check (Safe for Mocks and Empty arrays)
        if self._vectors is not None and self._vectors.size > 0:
            try:
                idx_dim = self._vectors.shape[1]
                q_dim = query_vector.shape[0]
                if idx_dim != q_dim and not "Mock" in str(type(query_vector)):
                    logger.warning(f"Search dimension mismatch: index={idx_dim}, query={q_dim}. Skipping vector search.")
                    return []
            except (AttributeError, IndexError):
                pass

        results = []
        annoy_success = False

        # 1. Annoy Search for indexed vectors
        if self._annoy_index is not None and self._indexed_count > 0:
             # Annoy 'angular' distance corresponds to sqrt(2(1-cos(u,v)))
             # Request more items to buffer against deleted ones
             annoy_limit = limit * 2 + 10
             try:
                 indices, distances = self._annoy_index.get_nns_by_vector(query_vector, annoy_limit, include_distances=True)

                 for i, dist in zip(indices, distances):
                     if i >= len(self._doc_ids): continue
                     fid = self._doc_ids[i]
                     if fid in self._deleted_ids: continue

                     # Convert angular distance to cosine similarity
                     # sim = 1 - dist^2 / 2
                     score = 1.0 - (dist ** 2) / 2.0
                     results.append({
                         "id": fid,
                         "score": float(score)
                     })
                 annoy_success = True
             except Exception as e:
                 logger.error(f"Annoy search failed: {e}")
                 # If Annoy fails, we will fallback to full scan
                 results = []

        # 2. Brute force search for unindexed tail (or full fallback)
        start_idx = self._indexed_count if annoy_success else 0

        if start_idx < len(self._vectors):
            tail_vectors = self._vectors[start_idx:]

            # Vectors are pre-normalized, so cosine similarity is just dot product
            similarities = np.dot(tail_vectors, query_vector)
            
            # Get top indices from tail
            # Optimization: Use argpartition for top-k if tail is large
            needed = limit * 2 # fetch a bit more to handle deletions
            if len(similarities) > needed * 2:
                # Top-k unsorted partition
                top_indices = np.argpartition(similarities, -needed)[-needed:]
                # Sort only the top-k
                sorted_top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
                tail_indices = sorted_top_indices
            else:
                tail_indices = np.argsort(similarities)[::-1]

            for idx in tail_indices:
                real_idx = start_idx + idx
                fid = self._doc_ids[real_idx]
                if fid in self._deleted_ids: continue

                results.append({
                    "id": fid,
                    "score": float(similarities[idx])
                })

        # Merge and Sort
        results.sort(key=lambda x: x["score"], reverse=True)

        # Deduplicate by ID? No, original didn't.

        return results[:limit]
