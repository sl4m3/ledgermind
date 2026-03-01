"""
Health check endpoints for LedgerMind MCP server.

Provides standardized health endpoints for:
- Load balancers (k8s, nginx, etc.)
- Monitoring systems (Prometheus, CloudWatch, etc.)
- Manual debugging

Endpoints:
- GET /health - Full health check with component status
- GET /health/ready - Readiness probe (k8s style)
- GET /health/live - Liveness probe (k8s style)
"""
from fastapi import FastAPI, HTTPException
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import os
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="LedgerMind Health Check")

# Global memory instance reference (set by main application)
memory_instance = None


def set_memory(memory):
    """
    Set the global memory instance for health checks.

    Call this from your main application initialization.

    Args:
        memory: The Memory instance to monitor
    """
    global memory_instance
    memory_instance = memory
    logger.info("Memory instance set for health checks")


def _check_filesystem(path: str) -> Dict[str, Any]:
    """
    Check filesystem accessibility and metadata.

    Args:
        path: File or directory path to check

    Returns:
        Dict with accessibility and metadata
    """
    try:
        if not os.path.exists(path):
            return {
                "accessible": False,
                "error": "Path does not exist",
                "path": path
            }

        stat = os.stat(path)
        return {
            "accessible": True,
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
            "is_directory": os.path.isdir(path),
            "is_file": os.path.isfile(path)
        }
    except Exception as e:
        return {
            "accessible": False,
            "error": str(e),
            "path": path
        }


def _check_database(db_path: str) -> Dict[str, Any]:
    """
    Check database file health.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Dict with database status
    """
    try:
        if not os.path.exists(db_path):
            return {
                "accessible": False,
                "error": "Database file does not exist"
            }

        # Check if file is readable
        if not os.access(db_path, os.R_OK):
            return {
                "accessible": False,
                "error": "Database file not readable"
            }

        # Check file size
        size = os.path.getsize(db_path)
        if size == 0:
            return {
                "accessible": True,
                "status": "empty",
                "warning": "Database file is empty"
            }

        # Check if file is locked (basic check)
        lock_file = db_path + "-wal"
        if os.path.exists(lock_file):
            wal_stat = os.stat(lock_file)
            wal_age = (datetime.now(timezone.utc).timestamp() - wal_stat.st_mtime)
            return {
                "accessible": True,
                "status": "active",
                "has_wal": True,
                "wal_age_seconds": int(wal_age)
            }

        return {
            "accessible": True,
            "status": "healthy",
            "size_bytes": size
        }

    except Exception as e:
        return {
            "accessible": False,
            "error": str(e)
        }


def _check_git_repo(repo_path: str) -> Dict[str, Any]:
    """
    Check Git repository health.

    Args:
        repo_path: Path to Git repository

    Returns:
        Dict with Git status
    """
    try:
        git_dir = os.path.join(repo_path, ".git")

        if not os.path.exists(git_dir):
            return {
                "status": "not_initialized",
                "accessible": False
            }

        if not os.path.isdir(git_dir):
            return {
                "status": "corrupted",
                "accessible": False
            }

        # Try to get HEAD (quick health check)
        import subprocess
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                head = result.stdout.strip()
                return {
                    "status": "healthy",
                    "accessible": True,
                    "head_commit": head[:12]  # First 12 chars
                }
            else:
                return {
                    "status": "error",
                    "accessible": False,
                    "error": result.stderr[:100]
                }

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            return {
                "status": "timeout",
                "accessible": False,
                "error": str(e)[:100]
            }

    except Exception as e:
        return {
            "status": "error",
            "accessible": False,
            "error": str(e)[:100]
        }


def _check_vector_store(vector_path: str) -> Dict[str, Any]:
    """
    Check vector store health.

    Args:
        vector_path: Path to vector store directory

    Returns:
        Dict with vector store status
    """
    try:
        if not os.path.exists(vector_path):
            return {
                "status": "disabled",
                "accessible": False
            }

        # Check for vector files
        vector_file = os.path.join(vector_path, "vectors.npy")
        meta_file = os.path.join(vector_path, "vector_meta.npy")

        files_exist = {
            "vectors": os.path.exists(vector_file),
            "metadata": os.path.exists(meta_file)
        }

        if not any(files_exist.values()):
            return {
                "status": "empty",
                "accessible": True,
                "files": files_exist
            }

        # Check vector dimensions
        import numpy as np
        vectors = np.load(vector_file)
        doc_count = len(vectors)

        return {
            "status": "healthy",
            "accessible": True,
            "document_count": doc_count,
            "dimensions": vectors.shape[1] if vectors.ndim > 1 else 0,
            "size_mb": os.path.getsize(vector_file) / (1024 * 1024)
        }

    except Exception as e:
        return {
            "status": "error",
            "accessible": False,
            "error": str(e)[:100]
        }


@app.get("/")
def health_check():
    """
    Comprehensive health check.

    Returns 200 if healthy, 503 if unhealthy.

    Checks all components:
    - Episodic store (database)
    - Semantic store (file system + Git)
    - Vector store
    - Background worker
    - Memory instance availability

    Response format matches Kubernetes health check conventions.
    """
    if memory_instance is None:
        raise HTTPException(
            status_code=503,
            detail="Memory instance not initialized"
        )

    status = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {}
    }

    # Check overall status
    any_unhealthy = False

    # ===== Check 1: Memory Instance =====
    status["components"]["memory"] = {
        "status": "available"
    }

    # ===== Check 2: Episodic Store =====
    try:
        db_check = _check_database(memory_instance.episodic.db_path)

        if not db_check["accessible"]:
            status["components"]["episodic"] = db_check
            any_unhealthy = True
        else:
            # Get count for additional context
            try:
                event_count = memory_instance.episodic.count_events()
                db_check["events_count"] = event_count
                status["components"]["episodic"] = db_check
            except Exception:
                status["components"]["episodic"] = db_check

    except Exception as e:
        status["components"]["episodic"] = {
            "status": "error",
            "error": str(e)
        }
        any_unhealthy = True

    # ===== Check 3: Semantic Store =====
    try:
        semantic_check = _check_filesystem(memory_instance.semantic.repo_path)

        if not semantic_check["accessible"]:
            status["components"]["semantic"] = semantic_check
            any_unhealthy = True
        else:
            # Get decision count
            try:
                decision_count = len(memory_instance.semantic.list_decisions())
                semantic_check["decisions_count"] = decision_count
                status["components"]["semantic"] = semantic_check
            except Exception:
                status["components"]["semantic"] = semantic_check

    except Exception as e:
        status["components"]["semantic"] = {
            "status": "error",
            "error": str(e)
        }
        any_unhealthy = True

    # ===== Check 4: Git Repository =====
    try:
        git_check = _check_git_repo(memory_instance.semantic.repo_path)
        status["components"]["git"] = git_check
        if git_check["status"] != "healthy":
            any_unhealthy = True
    except Exception as e:
        status["components"]["git"] = {
            "status": "error",
            "error": str(e)
        }
        any_unhealthy = True

    # ===== Check 5: Vector Store =====
    try:
        vector_check = _check_vector_store(
            os.path.join(memory_instance.storage_path, "vector_index")
        )
        status["components"]["vector"] = vector_check
        if vector_check["status"] == "error":
            any_unhealthy = True
    except Exception as e:
        status["components"]["vector"] = {
            "status": "error",
            "error": str(e)
        }
        any_unhealthy = True

    # ===== Check 6: Background Worker =====
    if hasattr(memory_instance, 'background_worker'):
        worker = memory_instance.background_worker

        status["components"]["background_worker"] = {
            "status": worker.status,
            "last_run": worker.last_run
        }

        if getattr(worker, 'errors', None):
            status["components"]["background_worker"]["recent_errors"] = worker.errors[-5:]
            if worker.status == "stopped" and worker.errors:
                any_unhealthy = True

    # ===== Determine Overall Status =====
    if any_unhealthy:
        status["status"] = "unhealthy"
        raise HTTPException(status_code=503, detail=status)

    # ===== Check System Resources =====
    try:
        import psutil
        # Some platforms (like Android/Termux) restrict access to /proc/stat
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
        except (PermissionError, OSError):
            cpu_percent = None

        try:
            memory_info = psutil.virtual_memory()
            memory_percent = memory_info.percent
        except (PermissionError, OSError):
            memory_percent = None

        try:
            disk_usage = psutil.disk_usage('/').percent
        except (PermissionError, OSError):
            disk_usage = None

        status["system"] = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "disk_usage": disk_usage
        }
    except ImportError:
        # psutil not installed, skip system checks
        pass

    return status


@app.get("/ready")
def readiness_check():
    """
    Readiness probe (Kubernetes-style).

    Returns 200 if service is ready to accept traffic,
    503 if not ready.

    Readiness means: all components initialized and ready to process requests.
    """
    if memory_instance is None:
        raise HTTPException(status_code=503, detail="Memory instance not initialized")

    # Quick checks only (expensive checks in /health)
    try:
        # Check if we can query (basic read test)
        _ = memory_instance.episodic.count_events()

        # Check if we can write (basic write test - create temp event)
        from ledgermind.core.core.schemas import MemoryEvent
        test_event = MemoryEvent(
            source="system",
            kind="task",
            content="Readiness probe"
        )
        _ = memory_instance.episodic.append(test_event)

        return {
            "status": "ready",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "error": str(e)[:200],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@app.get("/live")
def liveness_check():
    """
    Liveness probe (Kubernetes-style).

    Returns 200 if the service is running (even if degraded),
    never returns 503.

    Liveness means: process is alive and responding.
    This is lighter than /health and used for container restart policies.
    """
    # Always return 200 if we're running
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/dependencies")
def dependencies_check():
    """
    Check external dependencies availability.

    Optional endpoint for advanced monitoring.
    """
    deps_status = {}

    # Check Git availability
    git_available = memory_instance._git_available if memory_instance else False
    deps_status["git"] = {
        "status": "available" if git_available else "unavailable"
    }

    # Check vector model
    if memory_instance and hasattr(memory_instance, 'vector'):
        vector_available = getattr(memory_instance.vector, '_model', None) is not None
        deps_status["vector_model"] = {
            "status": "loaded" if vector_available else "not_loaded"
        }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": deps_status
    }
