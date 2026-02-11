"""Tests for Gmail thread operations (list_threads labelIds handling)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gmail_mcp.gmail.threads import list_threads


class TestListThreadsLabelIds:
    """Verify labelIds parameter is passed correctly to the Gmail API."""

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        """Create a mock Gmail API service."""
        service = MagicMock()
        # Chain: service.users().threads().list()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "threads": [{"id": "t1", "snippet": "hello"}],
        }
        mock_list.list_next = MagicMock(return_value=None)
        service.users().threads().list.return_value = mock_list
        service.users().threads().list_next.return_value = None
        return service

    def test_label_ids_passed_via_dict_unpacking(self, mock_service: MagicMock) -> None:
        """When label_ids is provided, labelIds should be in the API call."""
        list_threads(mock_service, label_ids=["INBOX", "UNREAD"])

        call_kwargs = mock_service.users().threads().list.call_args
        assert call_kwargs.kwargs.get("labelIds") == ["INBOX", "UNREAD"]

    def test_no_label_ids_omits_parameter(self, mock_service: MagicMock) -> None:
        """When label_ids is None, labelIds should NOT appear in API call."""
        list_threads(mock_service, label_ids=None)

        call_kwargs = mock_service.users().threads().list.call_args
        assert "labelIds" not in call_kwargs.kwargs

    def test_empty_label_ids_omits_parameter(self, mock_service: MagicMock) -> None:
        """When label_ids is an empty list, labelIds should NOT appear."""
        list_threads(mock_service, label_ids=[])

        call_kwargs = mock_service.users().threads().list.call_args
        assert "labelIds" not in call_kwargs.kwargs

    def test_single_label_id(self, mock_service: MagicMock) -> None:
        """Single label should be passed as a one-element list."""
        list_threads(mock_service, label_ids=["INBOX"])

        call_kwargs = mock_service.users().threads().list.call_args
        assert call_kwargs.kwargs.get("labelIds") == ["INBOX"]
