import pytest
from ledgermind.core.reasoning.pipeline import LifecyclePipeline

def test_pipeline_creation():
    pipeline = LifecyclePipeline()
    assert pipeline.decay_engine is not None
    assert pipeline.merge_engine is not None
    assert pipeline.promotion_engine is not None

def test_pipeline_run():
    pipeline = LifecyclePipeline()
    result = pipeline.run([])
    assert result.merge_count >= 0
    assert result.decay_count >= 0
    assert result.promote_count >= 0
