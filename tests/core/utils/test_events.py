import asyncio
import pytest
from unittest.mock import Mock, AsyncMock
from ledgermind.core.utils.events import EventEmitter

@pytest.fixture
def emitter():
    return EventEmitter()

@pytest.mark.asyncio
async def test_subscribe_callback(emitter):
    """Test that a callback is added to the subscribers list."""
    mock_callback = Mock()
    emitter.subscribe(mock_callback)

    assert mock_callback in emitter._subscribers

@pytest.mark.asyncio
async def test_subscribe_duplicate_callback(emitter):
    """Test that a duplicate callback is not added to the subscribers list."""
    mock_callback = Mock()
    emitter.subscribe(mock_callback)
    emitter.subscribe(mock_callback)

    assert len(emitter._subscribers) == 1
    assert emitter._subscribers[0] == mock_callback

@pytest.mark.asyncio
async def test_emit_synchronous_callback(emitter):
    """Test that a synchronous callback is executed when an event is emitted."""
    mock_callback = Mock()
    emitter.subscribe(mock_callback)

    event_type = "test_event"
    data = {"key": "value"}
    emitter.emit(event_type, data)

    mock_callback.assert_called_once_with(event_type, data)

@pytest.mark.asyncio
async def test_emit_asynchronous_callback(emitter):
    """Test that an asynchronous callback is executed when an event is emitted."""
    mock_callback = AsyncMock()
    emitter.subscribe(mock_callback)

    event_type = "test_event"
    data = {"key": "value"}
    emitter.emit(event_type, data)

    # Allow async tasks to run
    await asyncio.sleep(0)

    mock_callback.assert_called_once_with(event_type, data)

@pytest.mark.asyncio
async def test_emit_multiple_callbacks(emitter):
    """Test that all callbacks are executed when an event is emitted."""
    mock_callback1 = Mock()
    mock_callback2 = AsyncMock()

    emitter.subscribe(mock_callback1)
    emitter.subscribe(mock_callback2)

    event_type = "test_event"
    data = {"key": "value"}
    emitter.emit(event_type, data)

    # Allow async tasks to run
    await asyncio.sleep(0)

    mock_callback1.assert_called_once_with(event_type, data)
    mock_callback2.assert_called_once_with(event_type, data)

@pytest.mark.asyncio
async def test_emit_exception_handling(emitter, caplog):
    """Test that an exception in a callback is handled and logged."""
    mock_callback = Mock(side_effect=Exception("Test Error"))
    emitter.subscribe(mock_callback)

    event_type = "test_event"
    data = {"key": "value"}

    # Should not raise exception
    emitter.emit(event_type, data)

    mock_callback.assert_called_once_with(event_type, data)
    assert "Error in event subscriber: Test Error" in caplog.text
