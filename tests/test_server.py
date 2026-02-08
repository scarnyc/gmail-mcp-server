"""Tests for the Gmail MCP server integration.

Tests cover:
- Server creation and FastMCP instance
- Tool registration (all 12 tools)
- Tool annotations verification
- Server lifespan and cleanup
- Main entry point validation
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestServerCreation:
    """Tests for server creation and FastMCP instance."""

    def test_create_server_returns_fastmcp_instance(self) -> None:
        """Test that create_server returns a FastMCP instance."""
        from gmail_mcp.server import create_server

        server = create_server()

        assert server is not None
        assert server.name == "gmail-mcp-server"

    def test_module_level_mcp_instance_exists(self) -> None:
        """Test that the module-level mcp instance exists."""
        from gmail_mcp.server import mcp

        assert mcp is not None
        assert mcp.name == "gmail-mcp-server"

    def test_create_server_returns_same_type_as_module_mcp(self) -> None:
        """Test that create_server returns the same type as the module mcp."""
        from gmail_mcp.server import create_server, mcp

        server = create_server()

        assert type(server) is type(mcp)


class TestToolRegistration:
    """Tests for tool registration verification."""

    def test_all_sixteen_tools_registered(self) -> None:
        """Test that all 16 tools are registered (3 auth + 7 read + 6 write)."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()

        assert len(tools) == 16

    def test_read_tools_registered(self) -> None:
        """Test that all 7 read tools are registered."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()
        tool_names = [tool.name for tool in tools]

        read_tools = [
            "gmail_triage_inbox",
            "gmail_summarize_thread",
            "gmail_draft_reply",
            "gmail_search",
            "gmail_chat_inbox",
            "gmail_apply_labels",
            "gmail_download_email",
        ]

        for tool in read_tools:
            assert tool in tool_names, f"Read tool {tool} not registered"

    def test_write_tools_registered(self) -> None:
        """Test that all 6 write tools are registered."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()
        tool_names = [tool.name for tool in tools]

        write_tools = [
            "gmail_send_email",
            "gmail_archive_email",
            "gmail_delete_email",
            "gmail_unsubscribe",
            "gmail_create_label",
            "gmail_organize_labels",
        ]

        for tool in write_tools:
            assert tool in tool_names, f"Write tool {tool} not registered"


class TestToolAnnotations:
    """Tests for tool annotation verification."""

    def test_read_tools_have_readonly_hint(self) -> None:
        """Test that read tools have readOnlyHint=True."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()

        read_only_tools = [
            "gmail_triage_inbox",
            "gmail_summarize_thread",
            "gmail_draft_reply",
            "gmail_search",
            "gmail_chat_inbox",
        ]

        for tool in tools:
            if tool.name in read_only_tools:
                assert tool.annotations is not None, f"{tool.name} has no annotations"
                assert (
                    tool.annotations.readOnlyHint is True
                ), f"{tool.name} should have readOnlyHint=True"

    def test_destructive_tools_have_destructive_hint(self) -> None:
        """Test that destructive tools have destructiveHint=True."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()

        destructive_tools = [
            "gmail_send_email",
            "gmail_archive_email",
            "gmail_delete_email",
            "gmail_unsubscribe",
            "gmail_organize_labels",
        ]

        for tool in tools:
            if tool.name in destructive_tools:
                assert tool.annotations is not None, f"{tool.name} has no annotations"
                assert (
                    tool.annotations.destructiveHint is True
                ), f"{tool.name} should have destructiveHint=True"

    def test_idempotent_tools_have_idempotent_hint(self) -> None:
        """Test that idempotent tools have idempotentHint=True."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()

        idempotent_tools = [
            "gmail_triage_inbox",
            "gmail_summarize_thread",
            "gmail_draft_reply",
            "gmail_search",
            "gmail_chat_inbox",
            "gmail_apply_labels",
            "gmail_archive_email",
        ]

        for tool in tools:
            if tool.name in idempotent_tools:
                assert tool.annotations is not None, f"{tool.name} has no annotations"
                assert (
                    tool.annotations.idempotentHint is True
                ), f"{tool.name} should have idempotentHint=True"

    def test_apply_labels_not_readonly(self) -> None:
        """Test that gmail_apply_labels does not have readOnlyHint=True.

        gmail_apply_labels modifies email labels but doesn't require HITL,
        so it should not be marked as readOnly.
        """
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()

        for tool in tools:
            if tool.name == "gmail_apply_labels":
                # apply_labels is not readOnly (it modifies state)
                # but is also not destructive and is idempotent
                if tool.annotations:
                    read_only = tool.annotations.readOnlyHint
                    assert (
                        read_only is False
                    ), "gmail_apply_labels should not have readOnlyHint=True"
                break


class TestServerLifespan:
    """Tests for server lifespan and cleanup."""

    @pytest.mark.asyncio
    async def test_lifespan_cleans_up_expired_approvals(self) -> None:
        """Test that lifespan cleanup calls approval_manager.cleanup_expired."""
        with patch("gmail_mcp.server.approval_manager") as mock_approval_manager:
            mock_approval_manager.cleanup_expired = MagicMock(return_value=0)

            from gmail_mcp.server import cleanup_resources

            await cleanup_resources()

            mock_approval_manager.cleanup_expired.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_cleans_up_stale_rate_limits(self) -> None:
        """Test that lifespan cleanup calls rate_limiter.cleanup_stale."""
        with patch("gmail_mcp.server.rate_limiter") as mock_rate_limiter:
            mock_rate_limiter.cleanup_stale = MagicMock(return_value=0)

            from gmail_mcp.server import cleanup_resources

            await cleanup_resources()

            mock_rate_limiter.cleanup_stale.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_resources_handles_exceptions(self) -> None:
        """Test that cleanup_resources handles exceptions gracefully."""
        with patch("gmail_mcp.server.approval_manager") as mock_approval_manager:
            with patch("gmail_mcp.server.rate_limiter") as mock_rate_limiter:
                mock_approval_manager.cleanup_expired = MagicMock(
                    side_effect=RuntimeError("Test error")
                )
                mock_rate_limiter.cleanup_stale = MagicMock(return_value=0)

                from gmail_mcp.server import cleanup_resources

                # Should not raise, should handle gracefully
                await cleanup_resources()

                # rate_limiter cleanup should still be called
                mock_rate_limiter.cleanup_stale.assert_called_once()


class TestMainEntryPoint:
    """Tests for the main entry point and environment validation."""

    def test_validate_environment_success(self) -> None:
        """Test validate_environment succeeds with valid env vars."""
        env = {
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-client-secret",
            "TOKEN_ENCRYPTION_KEY": "a" * 64,
        }
        with patch.dict(os.environ, env, clear=False):
            from gmail_mcp.__main__ import validate_environment

            result = validate_environment()

            assert result is True

    def test_validate_environment_missing_client_id(self) -> None:
        """Test validate_environment fails when GOOGLE_CLIENT_ID is missing."""
        env = {
            "GOOGLE_CLIENT_SECRET": "test-secret",
            "TOKEN_ENCRYPTION_KEY": "a" * 64,
        }
        # Remove GOOGLE_CLIENT_ID if it exists
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": ""}, clear=False):
                from importlib import reload

                import gmail_mcp.__main__ as main_module

                reload(main_module)

                result = main_module.validate_environment()

                assert result is False

    def test_validate_environment_missing_client_secret(self) -> None:
        """Test validate_environment fails when GOOGLE_CLIENT_SECRET is missing."""
        env = {
            "GOOGLE_CLIENT_ID": "test-id",
            "TOKEN_ENCRYPTION_KEY": "a" * 64,
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": ""}, clear=False):
                from importlib import reload

                import gmail_mcp.__main__ as main_module

                reload(main_module)

                result = main_module.validate_environment()

                assert result is False

    def test_validate_environment_missing_encryption_key(self) -> None:
        """Test validate_environment fails when TOKEN_ENCRYPTION_KEY is missing."""
        env = {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": ""}, clear=False):
                from importlib import reload

                import gmail_mcp.__main__ as main_module

                reload(main_module)

                result = main_module.validate_environment()

                assert result is False

    def test_validate_environment_invalid_key_length(self) -> None:
        """Test validate_environment fails with invalid encryption key length."""
        env = {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
            "TOKEN_ENCRYPTION_KEY": "tooshort",  # Less than 64 chars
        }
        with patch.dict(os.environ, env, clear=False):
            from importlib import reload

            import gmail_mcp.__main__ as main_module

            reload(main_module)

            result = main_module.validate_environment()

            assert result is False

    def test_validate_environment_key_exactly_64_chars(self) -> None:
        """Test validate_environment succeeds with exactly 64 char key."""
        env = {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
            "TOKEN_ENCRYPTION_KEY": "0" * 64,  # Exactly 64 chars
        }
        with patch.dict(os.environ, env, clear=False):
            from importlib import reload

            import gmail_mcp.__main__ as main_module

            reload(main_module)

            result = main_module.validate_environment()

            assert result is True


class TestServerConfiguration:
    """Tests for server configuration options."""

    def test_server_has_correct_name(self) -> None:
        """Test server is configured with correct name."""
        from gmail_mcp.server import mcp

        assert mcp.name == "gmail-mcp-server"

    def test_server_exposes_tools(self) -> None:
        """Test server exposes tools via _tool_manager."""
        from gmail_mcp.server import mcp

        tools = mcp._tool_manager.list_tools()

        assert len(tools) > 0

    def test_all_tools_have_descriptions(self) -> None:
        """Test all tools have non-empty descriptions."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"
            assert len(tool.description) > 10, f"{tool.name} description is too short"


class TestToolSchemas:
    """Tests for tool input schemas."""

    def test_all_tools_have_input_schemas(self) -> None:
        """Test all tools have input schemas defined."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()

        for tool in tools:
            assert tool.parameters is not None, f"{tool.name} has no input schema"

    def test_write_tools_have_approval_id_parameter(self) -> None:
        """Test all write tools have approval_id parameter."""
        from gmail_mcp.server import create_server

        server = create_server()
        tools = server._tool_manager.list_tools()

        write_tools = [
            "gmail_send_email",
            "gmail_archive_email",
            "gmail_delete_email",
            "gmail_unsubscribe",
            "gmail_create_label",
            "gmail_organize_labels",
        ]

        for tool in tools:
            if tool.name in write_tools:
                schema = tool.parameters
                properties = schema.get("properties", {})
                assert (
                    "approval_id" in properties
                ), f"{tool.name} missing approval_id parameter"
