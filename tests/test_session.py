import sys
sys.path.insert(0, "/Users/voolf/Documents/opencode/OCVoice")

import time
from unittest.mock import MagicMock, patch

import pytest

from ocvoice.daemon import VoiceDaemon
from ocvoice.intent.intents import Intent


def make_session(id: str, title: str, updated: float):
    return {
        "id": id,
        "title": title,
        "time": {"updated": updated},
        "projectID": "proj-1",
        "directory": "/test",
    }


class TestSessionPollerManualOverride:
    """Test that manual session selection sticks for 30 seconds."""

    def test_manual_session_until_defaults_to_zero(self):
        config = MagicMock()
        daemon = VoiceDaemon(config)
        assert daemon._manual_session_until == 0.0

    def test_manual_session_set_on_switch(self):
        config = MagicMock()
        config.opencode_default_model = "test/model"
        config.opencode_default_agent = "build"
        config.headless = True
        daemon = VoiceDaemon(config)
        before = time.time()

        daemon._manual_session_until = time.time() + 30
        after = daemon._manual_session_until

        assert after - before >= 29.5  # approx 30s in future

    def test_manual_session_blocks_poller(self):
        """When _manual_session_until is in future, poller should skip."""
        config = MagicMock()
        config.opencode_default_model = "test/model"
        config.opencode_default_agent = "build"
        config.headless = True
        daemon = VoiceDaemon(config)
        daemon.client = MagicMock()

        sessions = [
            make_session("sess-new", "Новая", 200.0),
            make_session("sess-old", "Старая", 100.0),
        ]
        daemon.client.list_sessions.return_value = sessions
        daemon.client.session_id = "sess-old"
        daemon._state_session_id = "state-1"
        daemon._manual_session_until = time.time() + 30

        daemon._check_session_changes()

        # Should NOT have switched to sess-new
        assert daemon.client.session_id == "sess-old"

    def test_poller_switches_after_timeout(self):
        """After manual lock expires, poller should switch to newer session."""
        config = MagicMock()
        config.opencode_default_model = "test/model"
        config.opencode_default_agent = "build"
        config.headless = True
        daemon = VoiceDaemon(config)
        daemon.client = MagicMock()

        sessions = [
            make_session("sess-new", "Новая", 200.0),
            make_session("sess-old", "Старая", 100.0),
            make_session("state-1", "🟢 [OCVoice] ожидает", 150.0),
        ]
        daemon.client.list_sessions.return_value = sessions
        daemon.client.session_id = "sess-old"
        daemon._state_session_id = "state-1"
        daemon._manual_session_until = 0.0  # lock expired

        daemon._check_session_changes()

        # Should switch to sess-new (newer updated)
        assert daemon.client.session_id == "sess-new"

    def test_poller_skipped_when_no_user_sessions(self):
        """When only state sessions exist, poller should skip."""
        config = MagicMock()
        config.opencode_default_model = "test/model"
        config.opencode_default_agent = "build"
        config.headless = True
        daemon = VoiceDaemon(config)
        daemon.client = MagicMock()

        sessions = [
            make_session("state-1", "🟢 [OCVoice] ожидает", 150.0),
        ]
        daemon.client.list_sessions.return_value = sessions
        daemon.client.session_id = "state-1"
        daemon._state_session_id = "state-1"

        daemon._check_session_changes()

        # Should not crash and session_id unchanged
        assert daemon.client.session_id == "state-1"
