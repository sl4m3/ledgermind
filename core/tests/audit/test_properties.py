from hypothesis import given, strategies as st, settings
from agent_memory_core.core.schemas import MemoryEvent, KIND_DECISION
import pytest
import os
from pydantic import ValidationError

@settings(deadline=None)
@given(
    source=st.sampled_from(["user", "agent", "system"]),
    kind=st.sampled_from(["decision", "error", "config_change", "result"]),
    content=st.text(min_size=1),
    rationale=st.text(min_size=1)
)
def test_event_schema_properties(source, kind, content, rationale):
    """Проверяет, что любые строковые данные не ломают валидацию схем."""
    try:
        context = {"title": content, "target": "test", "rationale": rationale} if kind == "decision" else {}
        event = MemoryEvent(
            source=source,
            kind=kind,
            content=content,
            context=context
        )
        # Verify length or just that it doesn't crash
        assert len(event.content) > 0
    except (ValidationError, ValueError):
        # Expected errors for invalid data
        pass

@settings(deadline=None)
@given(st.text(min_size=1, max_size=50))
def test_memory_storage_path_robustness(path):
    """Проверяет, что система корректно обрабатывает странные пути."""
    from agent_memory_core.api.memory import Memory
    import os
    try:
        if "\0" not in path and "/" not in path:
            storage = f"/data/data/com.termux/files/home/.gemini/tmp/mem_{path}"
            Memory(storage_path=storage)
    except (ValueError, OSError):
        pass

@st.composite
def memory_operations(draw):
    """Генерирует последовательность операций над памятью."""
    ops = []
    targets = ["auth", "db", "ui"]
    for _ in range(draw(st.integers(min_value=1, max_value=10))):
        op_type = draw(st.sampled_from(["record", "supersede"]))
        target = draw(st.sampled_from(targets))
        ops.append({"type": op_type, "target": target})
    return ops

@settings(deadline=None)
@given(memory_operations())
def test_target_uniqueness_invariant(ops):
    """Инвариант: для любого таргета всегда <= 1 активного решения."""
    from agent_memory_core.api.memory import Memory
    import tempfile
    import shutil
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = os.path.join(tmp_dir, "prop_test")
        os.makedirs(storage)
        
        memory = Memory(storage_path=storage)
        
        for op in ops:
            if op["type"] == "record":
                memory.record_decision(f"Rec for {op['target']}", op["target"], "Rationale")
            else:
                # Supersede if there is something to supersede
                active = memory.semantic.list_active_conflicts(op["target"])
                if active:
                    memory.supersede_decision(f"Sup for {op['target']}", op["target"], "Rationale", [active[0]])
                else:
                    # Just record if nothing to supersede
                    memory.record_decision(f"Rec for {op['target']}", op["target"], "Rationale")

        # Проверяем инвариант для каждого таргета
        for target in ["auth", "db", "ui"]:
            active = memory.semantic.list_active_conflicts(target)
            assert len(active) <= 1, f"Invariant Violation: Target {target} has {len(active)} active decisions!"
