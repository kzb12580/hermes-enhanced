"""
Tests for the MCP Transport Enhancement module.

Uses pytest with asyncio.run() for async tests (no pytest-asyncio dependency).
Network-dependent transports are tested via mock/fake HTTP clients.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_transport import (
    HttpTransport,
    McpManager,
    McpServerConfig,
    McpToolSchema,
    McpTransport,
    StdioTransport,
    TransportType,
    create_transport,
    from_dict,
)


# ====================================================================
# Fixtures & Helpers
# ====================================================================


SAMPLE_TOOLS_RESPONSE = {
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "tools": [
            {
                "name": "echo",
                "description": "Echoes input back",
                "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
            },
            {
                "name": "add",
                "description": "Adds two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                },
            },
        ]
    },
}


class FakeHttpClient:
    """Fake HTTP client for testing HttpTransport without real network."""

    def __init__(self) -> None:
        self.responses: dict[str, Any] = {}
        self.posts: list[tuple[str, dict]] = []
        self._call_count = 0

    async def post(self, url: str, json: dict[str, Any] = None) -> dict[str, Any]:
        self.posts.append((url, json or {}))
        method = (json or {}).get("method", "")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": json.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "test-server", "version": "1.0.0"},
                    "sessionId": "sess-123",
                },
            }
        elif method == "tools/list":
            return SAMPLE_TOOLS_RESPONSE
        elif method == "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": json.get("id"),
                "result": {"content": [{"type": "text", "text": "ok"}]},
            }
        return {"jsonrpc": "2.0", "id": json.get("id"), "result": {}}


@pytest.fixture
def stdio_config() -> McpServerConfig:
    return McpServerConfig(
        name="test-stdio",
        transport=TransportType.STDIO,
        command="echo",
        args=["hello"],
    )


@pytest.fixture
def http_config() -> McpServerConfig:
    return McpServerConfig(
        name="test-http",
        transport=TransportType.HTTP,
        url="http://localhost:8080",
    )


@pytest.fixture
def sse_config() -> McpServerConfig:
    return McpServerConfig(
        name="test-sse",
        transport=TransportType.SSE,
        url="http://localhost:9090",
    )


@pytest.fixture
def fake_client() -> FakeHttpClient:
    return FakeHttpClient()


# ====================================================================
# Tests: TransportType
# ====================================================================


class TestTransportType:
    def test_values(self) -> None:
        assert TransportType.STDIO.value == "stdio"
        assert TransportType.SSE.value == "sse"
        assert TransportType.HTTP.value == "http"
        assert TransportType.WEBSOCKET.value == "websocket"

    def test_from_string(self) -> None:
        assert TransportType("stdio") is TransportType.STDIO
        assert TransportType("http") is TransportType.HTTP


# ====================================================================
# Tests: McpServerConfig
# ====================================================================


class TestMcpServerConfig:
    def test_basic_creation(self, stdio_config: McpServerConfig) -> None:
        assert stdio_config.name == "test-stdio"
        assert stdio_config.transport == TransportType.STDIO
        assert stdio_config.command == "echo"
        assert stdio_config.timeout == 30.0
        assert stdio_config.enabled is True

    def test_string_transport_coercion(self) -> None:
        cfg = McpServerConfig(name="s", transport="stdio", command="node")
        assert cfg.transport == TransportType.STDIO

    def test_stdio_requires_command(self) -> None:
        with pytest.raises(ValueError, match="requires a 'command'"):
            McpServerConfig(name="s", transport=TransportType.STDIO)

    def test_http_requires_url(self) -> None:
        with pytest.raises(ValueError, match="requires a 'url'"):
            McpServerConfig(name="s", transport=TransportType.HTTP)

    def test_sse_requires_url(self) -> None:
        with pytest.raises(ValueError, match="requires a 'url'"):
            McpServerConfig(name="s", transport=TransportType.SSE)

    def test_websocket_requires_url(self) -> None:
        with pytest.raises(ValueError, match="requires a 'url'"):
            McpServerConfig(name="s", transport=TransportType.WEBSOCKET)

    def test_defaults(self) -> None:
        cfg = McpServerConfig(name="x", transport="stdio", command="run")
        assert cfg.env == {}
        assert cfg.args == []
        assert cfg.timeout == 30.0
        assert cfg.enabled is True


# ====================================================================
# Tests: McpToolSchema
# ====================================================================


class TestMcpToolSchema:
    def test_creation(self) -> None:
        schema = McpToolSchema(
            name="echo",
            description="Echo tool",
            input_schema={"type": "object"},
            server_name="my-server",
        )
        assert schema.name == "echo"
        assert schema.server_name == "my-server"


# ====================================================================
# Tests: create_transport factory
# ====================================================================


class TestCreateTransport:
    def test_stdio(self, stdio_config: McpServerConfig) -> None:
        t = create_transport(stdio_config)
        assert isinstance(t, StdioTransport)

    def test_http(self, http_config: McpServerConfig) -> None:
        t = create_transport(http_config)
        assert isinstance(t, HttpTransport)

    def test_sse_maps_to_http(self, sse_config: McpServerConfig) -> None:
        t = create_transport(sse_config)
        assert isinstance(t, HttpTransport)

    def test_websocket_maps_to_http(self) -> None:
        cfg = McpServerConfig(name="ws", transport=TransportType.WEBSOCKET, url="ws://localhost")
        t = create_transport(cfg)
        assert isinstance(t, HttpTransport)


# ====================================================================
# Tests: HttpTransport
# ====================================================================


class TestHttpTransport:
    def test_connect_and_list_tools(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            transport = HttpTransport(http_config, http_client=fake_client)
            assert not transport.is_connected

            await transport.connect()
            assert transport.is_connected
            assert transport._session_id == "sess-123"

            tools = await transport.list_tools()
            assert len(tools) == 2
            assert tools[0].name == "echo"
            assert tools[0].server_name == "test-http"
            assert tools[1].name == "add"

        asyncio.run(_inner())

    def test_call_tool(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            transport = HttpTransport(http_config, http_client=fake_client)
            await transport.connect()
            result = await transport.call_tool("echo", {"text": "hello"})
            assert result == {"content": [{"type": "text", "text": "ok"}]}

        asyncio.run(_inner())

    def test_disconnect(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            transport = HttpTransport(http_config, http_client=fake_client)
            await transport.connect()
            await transport.disconnect()
            assert not transport.is_connected
            assert transport._session_id is None

        asyncio.run(_inner())

    def test_connect_without_client(self, http_config: McpServerConfig) -> None:
        async def _inner():
            transport = HttpTransport(http_config)
            with pytest.raises(ConnectionError, match="No HTTP client"):
                await transport.connect()

        asyncio.run(_inner())

    def test_post_sends_correct_url(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            transport = HttpTransport(http_config, http_client=fake_client)
            await transport.connect()
            assert any("/mcp" in url for url, _ in fake_client.posts)

        asyncio.run(_inner())

    def test_base_url_trailing_slash(
        self, fake_client: FakeHttpClient,
    ) -> None:
        cfg = McpServerConfig(
            name="s", transport=TransportType.HTTP, url="http://host:8080/"
        )
        transport = HttpTransport(cfg, http_client=fake_client)
        assert transport.base_url == "http://host:8080"


# ====================================================================
# Tests: McpManager
# ====================================================================


class TestMcpManager:
    def test_init(self, stdio_config: McpServerConfig, http_config: McpServerConfig) -> None:
        manager = McpManager([stdio_config, http_config])
        status = manager.get_server_status()
        assert status == {"test-stdio": "disconnected", "test-http": "disconnected"}

    def test_connect_all_http(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            manager = McpManager([http_config], http_client=fake_client)
            results = await manager.connect_all()
            assert results == {"test-http": True}
            assert manager.get_server_status() == {"test-http": "connected"}

        asyncio.run(_inner())

    def test_connect_all_skips_disabled(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            disabled = McpServerConfig(
                name="off", transport=TransportType.HTTP, url="http://x", enabled=False,
            )
            manager = McpManager([http_config, disabled], http_client=fake_client)
            results = await manager.connect_all()
            assert results == {"test-http": True, "off": False}
            status = manager.get_server_status()
            assert status["off"] == "disabled"

        asyncio.run(_inner())

    def test_call_tool(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            manager = McpManager([http_config], http_client=fake_client)
            await manager.connect_all()
            result = await manager.call_tool("test-http", "echo", {"text": "hi"})
            assert result == {"content": [{"type": "text", "text": "ok"}]}

        asyncio.run(_inner())

    def test_call_tool_unknown_server(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            manager = McpManager([http_config], http_client=fake_client)
            await manager.connect_all()
            with pytest.raises(KeyError, match="not connected"):
                await manager.call_tool("nonexistent", "echo", {})

        asyncio.run(_inner())

    def test_get_all_tools(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            manager = McpManager([http_config], http_client=fake_client)
            await manager.connect_all()
            tools = manager.get_all_tools()
            assert len(tools) == 2
            assert all(isinstance(t, McpToolSchema) for t in tools)

        asyncio.run(_inner())

    def test_disconnect_all(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            manager = McpManager([http_config], http_client=fake_client)
            await manager.connect_all()
            await manager.disconnect_all()
            assert manager.get_server_status() == {"test-http": "disconnected"}
            assert manager.get_all_tools() == []

        asyncio.run(_inner())

    def test_connect_failure(
        self, fake_client: FakeHttpClient,
    ) -> None:
        """Server that fails during connect should report False."""

        async def _inner():
            cfg = McpServerConfig(name="bad", transport=TransportType.HTTP, url="http://fail")

            class FailClient(FakeHttpClient):
                async def post(self, url: str, json: dict = None) -> dict:
                    raise ConnectionError("refused")

            manager = McpManager([cfg], http_client=FailClient())
            results = await manager.connect_all()
            assert results == {"bad": False}

        asyncio.run(_inner())

    def test_get_transport(
        self, http_config: McpServerConfig, fake_client: FakeHttpClient,
    ) -> None:
        async def _inner():
            manager = McpManager([http_config], http_client=fake_client)
            assert manager.get_transport("test-http") is None
            await manager.connect_all()
            assert manager.get_transport("test-http") is not None

        asyncio.run(_inner())


# ====================================================================
# Tests: from_dict config parsing
# ====================================================================


class TestFromDict:
    def test_claude_code_format(self) -> None:
        data = {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                    "env": {"NODE_ENV": "production"},
                },
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "timeout": 60.0,
                    "enabled": False,
                },
            }
        }
        configs = from_dict(data)
        assert len(configs) == 2
        fs = configs[0]
        assert fs.name == "filesystem"
        assert fs.transport == TransportType.STDIO
        assert fs.command == "npx"
        assert fs.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        assert fs.env == {"NODE_ENV": "production"}
        gh = configs[1]
        assert gh.name == "github"
        assert gh.timeout == 60.0
        assert gh.enabled is False

    def test_flat_list_format(self) -> None:
        data = {
            "servers": [
                {"name": "s1", "transport": "http", "url": "http://localhost:3000"},
                {"name": "s2", "transport": "websocket", "url": "ws://localhost:4000"},
            ]
        }
        configs = from_dict(data)
        assert len(configs) == 2
        assert configs[0].transport == TransportType.HTTP
        assert configs[1].transport == TransportType.WEBSOCKET

    def test_http_url_inference(self) -> None:
        """When url is present but transport is omitted, should default to http."""
        data = {
            "mcpServers": {
                "remote": {"url": "http://example.com/mcp"},
            }
        }
        configs = from_dict(data)
        assert configs[0].transport == TransportType.HTTP

    def test_empty_dict(self) -> None:
        assert from_dict({}) == []

    def test_sse_transport(self) -> None:
        data = {
            "mcpServers": {
                "sse-server": {
                    "transport": "sse",
                    "url": "http://localhost:7070",
                },
            }
        }
        configs = from_dict(data)
        assert configs[0].transport == TransportType.SSE
