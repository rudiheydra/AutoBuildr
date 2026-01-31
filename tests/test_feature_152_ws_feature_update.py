"""
Tests for Feature #152: Feature UI updates within 1 second of WS message.

Verifies that the backend emits `feature_update` WebSocket messages when
individual features change status, and that the frontend can rely on
these messages to invalidate React Query caches for sub-second UI updates.

Test structure:
- TestFeatureUpdateWebSocketEmission: Verify backend emits feature_update
- TestFeatureStatusDetection: Verify _get_feature_statuses() helper
- TestPollingWithFeatureUpdates: Verify poll_progress emits feature_update messages
- TestFrontendHandling: Verify frontend handler invalidates correct query keys
"""

import asyncio
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Test _get_feature_statuses helper
# =============================================================================

class TestFeatureStatusDetection:
    """Test the _get_feature_statuses function that reads feature statuses from DB."""

    def test_returns_empty_dict_when_no_db(self, tmp_path):
        """Should return empty dict when features.db doesn't exist."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from server.websocket import _get_feature_statuses

        result = _get_feature_statuses(tmp_path)
        assert result == {}

    def test_returns_feature_statuses(self, tmp_path):
        """Should return dict of feature_id -> passes for all features."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from server.websocket import _get_feature_statuses

        # Create a test database
        db_file = tmp_path / "features.db"
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE features (
                id INTEGER PRIMARY KEY,
                name TEXT,
                passes BOOLEAN DEFAULT 0,
                in_progress BOOLEAN DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO features (id, name, passes) VALUES (1, 'Feature A', 1)")
        conn.execute("INSERT INTO features (id, name, passes) VALUES (2, 'Feature B', 0)")
        conn.execute("INSERT INTO features (id, name, passes) VALUES (3, 'Feature C', 1)")
        conn.commit()
        conn.close()

        result = _get_feature_statuses(tmp_path)
        assert result == {1: True, 2: False, 3: True}

    def test_detects_status_change(self, tmp_path):
        """Should detect when a feature's passes status changes."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from server.websocket import _get_feature_statuses

        db_file = tmp_path / "features.db"
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE features (
                id INTEGER PRIMARY KEY,
                name TEXT,
                passes BOOLEAN DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO features (id, name, passes) VALUES (1, 'Feature A', 0)")
        conn.commit()

        # Initial snapshot
        snapshot1 = _get_feature_statuses(tmp_path)
        assert snapshot1 == {1: False}

        # Update feature to passing
        conn.execute("UPDATE features SET passes = 1 WHERE id = 1")
        conn.commit()
        conn.close()

        # New snapshot shows change
        snapshot2 = _get_feature_statuses(tmp_path)
        assert snapshot2 == {1: True}
        assert snapshot1[1] != snapshot2[1]


# =============================================================================
# Test poll_progress emits feature_update messages
# =============================================================================

class TestPollingWithFeatureUpdates:
    """Test that poll_progress emits feature_update WS messages on status changes."""

    @pytest.mark.asyncio
    async def test_emits_feature_update_on_status_change(self, tmp_path):
        """poll_progress should emit feature_update when a feature's passes changes."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from server.websocket import poll_progress

        # Create test DB
        db_file = tmp_path / "features.db"
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE features (
                id INTEGER PRIMARY KEY,
                name TEXT,
                passes BOOLEAN DEFAULT 0,
                in_progress BOOLEAN DEFAULT 0,
                priority INTEGER DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO features (id, name, passes, priority) VALUES (1, 'Feature A', 0, 1)")
        conn.execute("INSERT INTO features (id, name, passes, priority) VALUES (2, 'Feature B', 0, 2)")
        conn.commit()

        # Mock WebSocket
        ws = AsyncMock()
        sent_messages = []

        async def capture_send(msg):
            sent_messages.append(msg)

        ws.send_json = capture_send

        # Patch count_passing_tests
        call_count = 0

        def mock_count(project_dir):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return 0, 0, 2  # Initial: 0 passing
            else:
                return 1, 0, 2  # After change: 1 passing

        with patch('server.websocket._get_count_passing_tests', return_value=mock_count):
            # Run poll_progress for a short time
            task = asyncio.create_task(poll_progress(ws, "test-project", tmp_path))

            # Wait for first poll cycle
            await asyncio.sleep(1.5)

            # Change feature 1 to passing
            conn.execute("UPDATE features SET passes = 1 WHERE id = 1")
            conn.commit()

            # Wait for the poll to detect the change
            await asyncio.sleep(1.5)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        conn.close()

        # Verify feature_update message was sent
        feature_updates = [m for m in sent_messages if m.get("type") == "feature_update"]
        assert len(feature_updates) >= 1, f"Expected at least 1 feature_update, got {len(feature_updates)}: {sent_messages}"

        # Verify the feature_update has correct structure
        fu = feature_updates[-1]
        assert fu["feature_id"] == 1
        assert fu["passes"] is True

    @pytest.mark.asyncio
    async def test_no_feature_update_when_no_change(self, tmp_path):
        """poll_progress should NOT emit feature_update if nothing changed."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from server.websocket import poll_progress

        # Create test DB with stable state
        db_file = tmp_path / "features.db"
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE features (
                id INTEGER PRIMARY KEY,
                name TEXT,
                passes BOOLEAN DEFAULT 0,
                in_progress BOOLEAN DEFAULT 0,
                priority INTEGER DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO features (id, name, passes, priority) VALUES (1, 'Feature A', 1, 1)")
        conn.commit()
        conn.close()

        ws = AsyncMock()
        sent_messages = []

        async def capture_send(msg):
            sent_messages.append(msg)

        ws.send_json = capture_send

        def mock_count(project_dir):
            return 1, 0, 1

        with patch('server.websocket._get_count_passing_tests', return_value=mock_count):
            task = asyncio.create_task(poll_progress(ws, "test-project", tmp_path))

            # Let it run for 3 poll cycles (>3 seconds)
            await asyncio.sleep(3.5)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # After initial progress message, there should be NO feature_update messages
        # (The first cycle initializes feature statuses; subsequent cycles should see no change)
        feature_updates = [m for m in sent_messages if m.get("type") == "feature_update"]
        # Initial cycle won't emit feature_update since last_feature_statuses is empty
        assert len(feature_updates) == 0, f"Expected 0 feature_updates when nothing changed, got {len(feature_updates)}"

    @pytest.mark.asyncio
    async def test_feature_update_has_correct_message_format(self, tmp_path):
        """feature_update message must match WSFeatureUpdateMessage schema."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from server.websocket import poll_progress

        db_file = tmp_path / "features.db"
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE features (
                id INTEGER PRIMARY KEY,
                name TEXT,
                passes BOOLEAN DEFAULT 0,
                in_progress BOOLEAN DEFAULT 0,
                priority INTEGER DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO features (id, name, passes, priority) VALUES (42, 'Test Feature', 0, 1)")
        conn.commit()

        ws = AsyncMock()
        sent_messages = []

        async def capture_send(msg):
            sent_messages.append(msg)

        ws.send_json = capture_send

        call_count = 0

        def mock_count(project_dir):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return 0, 0, 1
            return 1, 0, 1

        with patch('server.websocket._get_count_passing_tests', return_value=mock_count):
            task = asyncio.create_task(poll_progress(ws, "test-project", tmp_path))
            await asyncio.sleep(1.5)

            # Change feature status
            conn.execute("UPDATE features SET passes = 1 WHERE id = 42")
            conn.commit()

            await asyncio.sleep(1.5)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        conn.close()

        feature_updates = [m for m in sent_messages if m.get("type") == "feature_update"]
        assert len(feature_updates) >= 1

        msg = feature_updates[0]
        # Must have exactly these fields matching WSFeatureUpdateMessage schema
        assert msg["type"] == "feature_update"
        assert "feature_id" in msg
        assert "passes" in msg
        assert isinstance(msg["feature_id"], int)
        assert isinstance(msg["passes"], bool)


# =============================================================================
# Test frontend WebSocket handler (React Query invalidation)
# =============================================================================

class TestFrontendHandling:
    """Verify the frontend handler structure for feature_update messages."""

    def test_usewebsocket_handles_feature_update(self):
        """The useWebSocket hook should handle feature_update by invalidating queries."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        # Read the useWebSocket.ts file and verify the handler exists
        ws_hook_path = root / "ui" / "src" / "hooks" / "useWebSocket.ts"
        content = ws_hook_path.read_text()

        # Verify feature_update case exists
        assert "case 'feature_update':" in content, "useWebSocket must handle feature_update"

        # Verify it invalidates the features query
        assert "invalidateQueries" in content, "Handler must call invalidateQueries"
        assert "['features'" in content, "Handler must invalidate features query key"

        # Verify it also invalidates dependencyGraph
        assert "['dependencyGraph'" in content, "Handler must invalidate dependencyGraph query key"

        # Verify it handles specific feature detail queries too
        assert "message.feature_id" in content, "Handler must use feature_id from message"

    def test_types_define_feature_update_message(self):
        """The types file must define WSFeatureUpdateMessage interface."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        types_path = root / "ui" / "src" / "lib" / "types.ts"
        content = types_path.read_text()

        assert "WSFeatureUpdateMessage" in content
        assert "type: 'feature_update'" in content
        assert "feature_id: number" in content
        assert "passes: boolean" in content


# =============================================================================
# Test polling interval is within 1 second
# =============================================================================

class TestPollingInterval:
    """Verify the polling interval is <= 1 second for Feature #152 requirement."""

    def test_polling_uses_1_second_interval(self):
        """poll_progress must use asyncio.sleep(1) or less for sub-second updates."""
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        ws_path = root / "server" / "websocket.py"
        content = ws_path.read_text()

        # Find the sleep call inside poll_progress function
        # It should be asyncio.sleep(1) not asyncio.sleep(2) or more
        import re
        # Find the poll_progress function and its sleep call
        poll_func_match = re.search(
            r'async def poll_progress\(.*?\n(.*?)(?=\nasync def|\nclass |\Z)',
            content,
            re.DOTALL
        )
        assert poll_func_match, "poll_progress function must exist"

        func_body = poll_func_match.group(1)
        sleep_matches = re.findall(r'asyncio\.sleep\((\d+(?:\.\d+)?)\)', func_body)
        assert len(sleep_matches) >= 1, "poll_progress must have an asyncio.sleep call"

        # Verify the sleep interval is <= 1 second
        for sleep_val in sleep_matches:
            assert float(sleep_val) <= 1.0, \
                f"Poll interval must be <= 1 second, found asyncio.sleep({sleep_val})"


# =============================================================================
# Test backend schema definition
# =============================================================================

class TestWSFeatureUpdateSchema:
    """Verify the backend Pydantic schema matches the message format."""

    def test_ws_feature_update_message_schema(self):
        """WSFeatureUpdateMessage schema must define type, feature_id, passes."""
        import sys
        import importlib.util
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        # Import from the legacy schemas.py file directly (not the schemas package)
        spec = importlib.util.spec_from_file_location(
            "legacy_schemas",
            root / "server" / "schemas.py"
        )
        legacy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy)
        WSFeatureUpdateMessage = legacy.WSFeatureUpdateMessage

        # Create a valid message
        msg = WSFeatureUpdateMessage(feature_id=42, passes=True)
        assert msg.type == "feature_update"
        assert msg.feature_id == 42
        assert msg.passes is True

        # Verify JSON serialization
        data = msg.model_dump()
        assert data["type"] == "feature_update"
        assert data["feature_id"] == 42
        assert data["passes"] is True


# =============================================================================
# Integration test: Full end-to-end WS message flow timing
# =============================================================================

class TestEndToEndTiming:
    """Verify that feature_update reaches the client within 1 second of DB change."""

    @pytest.mark.asyncio
    async def test_feature_update_arrives_within_1_second(self, tmp_path):
        """
        Simulate: DB change -> poll_progress detects -> WS message emitted.
        The total time from DB change to WS message must be < 1 second.
        """
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from server.websocket import poll_progress

        db_file = tmp_path / "features.db"
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE features (
                id INTEGER PRIMARY KEY,
                name TEXT,
                passes BOOLEAN DEFAULT 0,
                in_progress BOOLEAN DEFAULT 0,
                priority INTEGER DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO features (id, name, passes, priority) VALUES (1, 'Feature A', 0, 1)")
        conn.commit()

        ws = AsyncMock()
        feature_update_time = None

        async def capture_send(msg):
            nonlocal feature_update_time
            if msg.get("type") == "feature_update" and msg.get("feature_id") == 1:
                feature_update_time = time.monotonic()

        ws.send_json = capture_send

        def mock_count(project_dir):
            return 0, 0, 1

        with patch('server.websocket._get_count_passing_tests', return_value=mock_count):
            task = asyncio.create_task(poll_progress(ws, "test-project", tmp_path))

            # Wait for initial snapshot
            await asyncio.sleep(1.5)

            # Record the time of DB change
            db_change_time = time.monotonic()
            conn.execute("UPDATE features SET passes = 1 WHERE id = 1")
            conn.commit()

            # Wait for detection (should be within 1 poll cycle = 1 second)
            await asyncio.sleep(2.0)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        conn.close()

        assert feature_update_time is not None, "feature_update message was never sent"
        latency = feature_update_time - db_change_time
        # The feature_update should arrive within ~1 second (1 poll cycle)
        # We allow 1.5s to account for asyncio scheduling overhead
        assert latency < 1.5, f"feature_update latency was {latency:.2f}s, expected < 1.5s"
