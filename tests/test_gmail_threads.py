"""Tests for Gmail thread operations (list_threads label filtering)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gmail_mcp.gmail.threads import list_threads


class TestListThreadsLabelFiltering:
    """Verify label_ids are merged into the q parameter as label: filters.

    The labelIds URL parameter causes ValueError in list_next() pagination
    because parse_unique_urlencoded() rejects repeated URL keys.  Labels
    are instead encoded as ``label:X label:Y`` in the q parameter.
    """

    @pytest.fixture
    def mock_service(self) -> MagicMock:
        """Create a mock Gmail API service."""
        service = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "threads": [{"id": "t1", "snippet": "hello"}],
        }
        service.users().threads().list.return_value = mock_list
        service.users().threads().list_next.return_value = None
        return service

    def test_label_ids_merged_into_query(self, mock_service: MagicMock) -> None:
        """label_ids should be converted to label: filters in q param."""
        list_threads(mock_service, label_ids=["INBOX", "UNREAD"])

        call_kwargs = mock_service.users().threads().list.call_args.kwargs
        assert "labelIds" not in call_kwargs
        assert "label:INBOX" in call_kwargs["q"]
        assert "label:UNREAD" in call_kwargs["q"]

    def test_label_ids_appended_to_existing_query(
        self, mock_service: MagicMock
    ) -> None:
        """label: filters should be appended to existing query string."""
        list_threads(mock_service, query="is:important", label_ids=["INBOX"])

        call_kwargs = mock_service.users().threads().list.call_args.kwargs
        assert call_kwargs["q"] == "is:important label:INBOX"

    def test_no_label_ids_passes_query_unchanged(self, mock_service: MagicMock) -> None:
        """When label_ids is None, q should be the original query."""
        list_threads(mock_service, query="from:test@example.com")

        call_kwargs = mock_service.users().threads().list.call_args.kwargs
        assert call_kwargs["q"] == "from:test@example.com"
        assert "labelIds" not in call_kwargs

    def test_empty_label_ids_passes_query_unchanged(
        self, mock_service: MagicMock
    ) -> None:
        """When label_ids is empty, q should be the original query."""
        list_threads(mock_service, query="subject:test", label_ids=[])

        call_kwargs = mock_service.users().threads().list.call_args.kwargs
        assert call_kwargs["q"] == "subject:test"
        assert "labelIds" not in call_kwargs

    def test_single_label_id(self, mock_service: MagicMock) -> None:
        """Single label should produce single label: filter."""
        list_threads(mock_service, label_ids=["INBOX"])

        call_kwargs = mock_service.users().threads().list.call_args.kwargs
        assert call_kwargs["q"] == "label:INBOX"
        assert "labelIds" not in call_kwargs

    def test_empty_query_with_labels_no_leading_space(
        self, mock_service: MagicMock
    ) -> None:
        """Empty query + labels should not have leading whitespace."""
        list_threads(mock_service, query="", label_ids=["SENT"])

        call_kwargs = mock_service.users().threads().list.call_args.kwargs
        assert call_kwargs["q"] == "label:SENT"
