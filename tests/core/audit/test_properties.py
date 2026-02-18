from hypothesis import given, strategies as st, settings
from ledgermind.core.core.schemas import MemoryEvent, KIND_DECISION
import pytest
import os
from pydantic import ValidationError

@settings(deadline=None, max_examples=20)
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

@settings(deadline=None, max_examples=10)
@given(st.text(min_size=1, max_size=50))
def test_memory_storage_path_robustness(path):
    """Проверяет, что система корректно обрабатывает странные пути."""
    from ledgermind.core.api.memory import Memory
    import os
    try:
        if "\0" not in path and "/" not in path:
            storage = f"/data/data/com.termux/files/home/.gemini/tmp/mem_{path}"
            Memory(storage_path=storage)
    except (ValueError, OSError):
        pass

@st.composite
def complex_memory_operations(draw):
    """Генерирует сложные операции, включая вытеснение нескольких решений."""
    ops = []
    targets = ["auth", "db", "ui"]
    for _ in range(draw(st.integers(min_value=1, max_value=15))):
        op_type = draw(st.sampled_from(["record", "supersede", "branch"]))
        target = draw(st.sampled_from(targets))
        ops.append({"type": op_type, "target": target})
    return ops

@settings(deadline=None, max_examples=15)
@given(complex_memory_operations())
def test_graph_integrity_under_fuzzing(ops):
    """Инвариант: любые операции сохраняют DAG и уникальность активного состояния."""
    from ledgermind.core.api.memory import Memory
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = os.path.join(tmp_dir, "fuzz_test")
        memory = Memory(storage_path=storage)
        
        for op in ops:
            try:
                target = op["target"]
                if op["type"] == "record":
                    memory.record_decision(f"Rec", target, "Long enough rationale for fuzzing")
                elif op["type"] == "supersede":
                    active = memory.semantic.list_active_conflicts(target)
                    if active:
                        memory.supersede_decision(f"Sup", target, "Updated rationale for fuzzing test", active)
                elif op["type"] == "branch":
                    # Имитируем создание параллельной ветки (что должно быть запрещено правилом I4)
                    # Мы делаем это вручную через save, чтобы проверить, что IntegrityChecker поймает это
                    from ledgermind.core.core.schemas import MemoryEvent
                    event = MemoryEvent(
                        source="agent", kind="decision", content="Branch",
                        context={"title": "B", "target": target, "status": "active", "rationale": "Illegal branch"}
                    )
                    # Это должно вызвать ошибку или быть исправлено следующим шагом
                    try:
                        memory.semantic.save(event)
                    except Exception: pass
            except Exception: pass

        # Финальная проверка всех инвариантов
        for target in ["auth", "db", "ui"]:
            active = memory.semantic.list_active_conflicts(target)
            assert len(active) <= 1, f"Fuzzing broke I4 for {target}"
            
        # Проверка на циклы (через инициализацию нового стора)
        from ledgermind.core.stores.semantic_store.integrity import IntegrityChecker
        IntegrityChecker.validate(memory.semantic.repo_path, force=True)
