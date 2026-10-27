from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from ledgermind_inference.model_fingerprint import model_tree_fingerprint
from ledgermind_inference.openai_vectorizer import OpenAIEmbeddingVectorizer
from ledgermind_local.installer.embeddings.service import EmbeddingService


def test_tree_fingerprint_preserves_existing_algorithm_and_is_relocatable(tmp_path: Path):
    tree=tmp_path/"original"
    copy=tmp_path/"copy"
    for directory in (tree,copy):
        directory.mkdir()
        (directory/"config.json").write_bytes(b'{"prompts":{"document":"passage: "}}')
        (directory/"model.safetensors").write_bytes(b"actual-model-bytes")
    old=hashlib.sha256()
    for item in sorted(tree.rglob("*")):
        old.update(str(item.relative_to(tree)).encode())
        old.update(item.read_bytes())
    assert model_tree_fingerprint(tree)=="sha256:"+old.hexdigest()
    assert model_tree_fingerprint(copy)==model_tree_fingerprint(tree)
    (copy/"config.json").write_bytes(b"different-encoder-configuration")
    assert model_tree_fingerprint(copy)!=model_tree_fingerprint(tree)


def test_loaded_identity_is_exposed_to_real_api_vectorizer_without_alias_fallback(tmp_path: Path):
    (tmp_path/"model.safetensors").write_bytes(b"pinned-test-model")
    fingerprint=model_tree_fingerprint(tmp_path)
    roles=[]
    def backend(texts,*,role=None):
        roles.append(role)
        return [[1.,0.] for _ in texts]
    service=EmbeddingService(backend=backend,model="serving-alias",dimensions=2,device="cpu",
        token="local-test-token",embedding_fingerprint=fingerprint)
    endpoint=service.start()
    vectorizer=OpenAIEmbeddingVectorizer(endpoint=endpoint+"/v1",token="local-test-token",
        model="serving-alias",dimensions=2,batch_size=4,timeout_seconds=5)
    try:
        assert vectorizer.fingerprint==fingerprint
        with urlopen(endpoint+"/health/ready",timeout=5) as response:
            ready=json.load(response)
        assert ready["embedding_fingerprint"]!=service.model
        assert ready["embedding_dimensions"]==2
        assert "local-test-token" not in json.dumps(ready)
        assert str(tmp_path) not in json.dumps(ready)
        assert vectorizer.encode(["query"],role="passage")==[[1.,0.]]
        assert roles==["passage"]
        with urlopen(endpoint+"/health",timeout=5) as response:
            assert json.load(response)["model"]=="serving-alias"
    finally:
        vectorizer.close()
        service.stop()


@pytest.mark.parametrize("fingerprint",[None,"","unknown"])
def test_ready_fails_closed_without_model_identity(fingerprint):
    service=EmbeddingService(backend=lambda texts:[],model="alias-is-not-identity",dimensions=2,
        device="cpu",embedding_fingerprint=fingerprint)
    endpoint=service.start()
    try:
        with pytest.raises(HTTPError) as error:
            urlopen(endpoint+"/health/ready",timeout=5)
        assert error.value.code==503
        with urlopen(endpoint+"/health/live",timeout=5) as response:
            assert json.load(response)=={"status":"ok"}
    finally:
        service.stop()
