import sys
sys.path.insert(0, "/Users/voolf/Documents/opencode/OCVoice")

from unittest.mock import MagicMock, patch

import httpx
import pytest

from ocvoice.opencode.client import OpenCodeClient


class TestProjectMethods:
    """Test list_projects() and get_current_project().

    @contract: All tests use mocked httpx.Client
    @desc: Tests project listing, current project retrieval, error handling,
           and project name extraction from worktree path.
    @tags: test, client, project
    """

    @patch("httpx.Client")
    def test_list_projects(self, mock_client_class):
        mock = MagicMock()
        mock_client_class.return_value = mock
        mock.get.return_value.json.return_value = [
            {"id": "proj-1", "worktree": "/home/user/projects/my-app"},
            {"id": "proj-2", "worktree": "/home/user/projects/other-app"},
        ]
        mock.get.return_value.raise_for_status = MagicMock()

        client = OpenCodeClient(base_url="http://127.0.0.1:4096")
        result = client.list_projects()

        assert len(result) == 2
        assert result[0]["id"] == "proj-1"
        assert result[1]["worktree"] == "/home/user/projects/other-app"
        mock.get.assert_called_once_with("/project")

    @patch("httpx.Client")
    def test_get_current_project(self, mock_client_class):
        mock = MagicMock()
        mock_client_class.return_value = mock
        mock.get.return_value.json.return_value = {
            "id": "proj-1",
            "worktree": "/home/user/projects/my-app",
            "vcs": "git",
        }
        mock.get.return_value.raise_for_status = MagicMock()

        client = OpenCodeClient(base_url="http://127.0.0.1:4096")
        result = client.get_current_project()

        assert result["id"] == "proj-1"
        assert result["worktree"] == "/home/user/projects/my-app"
        mock.get.assert_called_once_with("/project/current")

    @patch("httpx.Client")
    def test_list_projects_http_error(self, mock_client_class):
        mock = MagicMock()
        mock_client_class.return_value = mock
        mock.get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock()
        )

        client = OpenCodeClient(base_url="http://127.0.0.1:4096")
        with pytest.raises(httpx.HTTPStatusError):
            client.list_projects()

    @patch("httpx.Client")
    def test_get_current_project_extracts_name(self, mock_client_class):
        mock = MagicMock()
        mock_client_class.return_value = mock
        mock.get.return_value.json.return_value = {
            "id": "proj-1",
            "worktree": "/Users/me/code/my-awesome-project",
        }
        mock.get.return_value.raise_for_status = MagicMock()

        client = OpenCodeClient(base_url="http://127.0.0.1:4096")
        proj = client.get_current_project()
        name = proj.get("worktree", "?").split("/")[-1]
        assert name == "my-awesome-project"
