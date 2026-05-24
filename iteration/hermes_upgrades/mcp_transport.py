"""
MCP (Model Context Protocol) Transport Enhancement Module for Hermes Agent.

Provides multi-transport MCP server management with support for STDIO, SSE,
HTTP, and WebSocket transports. Compatible with Claude Code's mcpServers
configuration format.

Design inspired by Claude Code's MCP transport architecture.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Transport Types
# ---------------------------------------------------------------------------

class TransportType(str, Enum):
    """Supported MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"
    WEBSOCKET = "websocket"


# ---------------------------------------------------------------------------
# 2. Configuration & Schema Data Classes
# ---------------------------------------------------------------------------

@dataclass
class McpServerConfig:
    """Configuration for a single MCP server.

    Compatible with Claude Code's ``mcpServers`` JSON format::

        {
            "name": "my-server",
            "transport": "stdio",
            "command": "node",
            "args": ["server.js"],
            "env": {"NODE_ENV": "production"},
            "timeout": 30.0,
            "enabled": true
        }
    """

    name: str
    transport: TransportType
    command: Optional[str] = None
    url: Optional[str] = None
    env: dict[str, str] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)
    timeout: float = 30.0
    enabled: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.transport, str):
            self.transport = TransportType(self.transport)
        if self.transport == TransportType.STDIO and not self.command:
            raise ValueError("STDIO transport requires a 'command'")
        if self.transport in (TransportType.SSE, TransportType.HTTP, TransportType.WEBSOCKET) and not self.url:
            raise ValueError(f"{self.transport.value} transport requires a 'url'")


@dataclass
class McpToolSchema:
    """Schema describing a tool exposed by an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


# ---------------------------------------------------------------------------
# 3. Abstract Transport Base
# ---------------------------------------------------------------------------

class McpTransport(ABC):
    """Abstract base for all MCP transports."""

    def __init__(self, config: McpServerConfig) -> None:
        self._config = config
        self._connected = False

    @property
    def config(self) -> McpServerConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the MCP server."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection to the MCP server."""

    @abstractmethod
    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool on the MCP server.

        Args:
            name: Tool name.
            args: Tool arguments.

        Returns:
            Tool result as a dict.
        """

    @abstractmethod
    async def list_tools(self) -> list[McpToolSchema]:
        """Return schemas for all tools exposed by this server."""


# ---------------------------------------------------------------------------
# 4. STDIO Transport
# ---------------------------------------------------------------------------

class StdioTransport(McpTransport):
    """Transport that communicates with an MCP server over stdin/stdout
    using JSON-RPC 2.0 messages.

    Lifecycle:
        1. Spawn subprocess with ``command`` + ``args``.
        2. Send ``initialize`` request, await ``initialize`` response.
        3. Send ``initialized`` notification.
        4. Ready for ``tools/list`` and ``tools/call``.
    """

    def __init__(self, config: McpServerConfig) -> None:
        super().__init__(config)
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._tools: list[McpToolSchema] = []

    # -- Deny-list for suspicious commands -----------------------------------
    _BLOCKED_COMMANDS: frozenset[str] = frozenset({
        "rm", "dd", "mkfs", "fdisk", "format", "del", "rmdir",
        "sudo", "su", "chmod", "chown", "chgrp",
        "curl", "wget", "nc", "ncat", "netcat", "socat",
        "python", "python3", "ruby", "perl", "bash", "sh", "zsh", "fish",
        "eval", "exec",
    })

    @staticmethod
    def _validate_command(command: str, args: list[str]) -> None:
        """Validate the MCP server command before spawning.

        Raises ValueError if the command is empty or contains shell
        metacharacters that suggest injection.
        """
        if not command or not command.strip():
            raise ValueError("MCP command must not be empty")
        # Check for shell metacharacters in command or args
        dangerous_chars = set(";&|`$(){}!#~")
        for ch in dangerous_chars:
            if ch in command:
                raise ValueError(
                    f"MCP command contains dangerous character {ch!r}: {command!r}"
                )
        for arg in args:
            for ch in dangerous_chars:
                if ch in arg:
                    raise ValueError(
                        f"MCP arg contains dangerous character {ch!r}: {arg!r}"
                    )

    # -- JSON-RPC helpers ---------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send(self, message: dict[str, Any]) -> None:
        """Write a JSON-RPC message to the subprocess stdin."""
        if not self._process or not self._process.stdin:
            raise ConnectionError("Transport not connected")
        data = json.dumps(message) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

    async def _read_message(self) -> Optional[dict[str, Any]]:
        """Read a single JSON-RPC message from stdout."""
        if not self._process or not self._process.stdout:
            return None
        line = await asyncio.wait_for(
            self._process.stdout.readline(),
            timeout=self._config.timeout,
        )
        if not line:
            return None
        return json.loads(line.decode())

    async def _reader_loop(self) -> None:
        """Background task that reads responses and resolves pending futures."""
        try:
            while self._connected:
                msg = await self._read_message()
                if msg is None:
                    break
                req_id = msg.get("id")
                if req_id is not None and req_id in self._pending:
                    self._pending.pop(req_id).set_result(msg)
                # Notifications (no id) are logged but not correlated.
                elif "method" in msg:
                    logger.debug("Notification from %s: %s", self._config.name, msg.get("method"))
        except (ConnectionError, asyncio.CancelledError, asyncio.TimeoutError):
            pass
        finally:
            self._connected = False

    # -- Public API ---------------------------------------------------------

    async def connect(self) -> None:
        """Spawn subprocess and perform the MCP initialize handshake."""
        env = {**os.environ, **self._config.env}
        if self._config.command is None:
            raise ValueError("MCP server command is required but got None")
        self._validate_command(self._config.command, self._config.args)
        self._process = await asyncio.create_subprocess_exec(
            self._config.command,
            *self._config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._connected = True
        self._reader_task = asyncio.ensure_future(self._reader_loop())

        # MCP initialize handshake
        resp = await self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hermes-agent", "version": "1.0.0"},
        })
        if "error" in resp:
            raise ConnectionError(f"Initialize failed: {resp['error']}")

        # Send initialized notification (no id)
        await self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

        # Pre-fetch tools
        self._tools = await self.list_tools()

    async def disconnect(self) -> None:
        """Terminate the subprocess and clean up."""
        self._connected = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None
        for fut in self._pending.values():
            fut.cancel()
        self._pending.clear()
        self._tools.clear()

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the correlated response."""
        req_id = self._next_id()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = fut
        await self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        })
        return await asyncio.wait_for(fut, timeout=self._config.timeout)

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request("tools/call", {"name": name, "arguments": args})
        if "error" in resp:
            raise RuntimeError(f"Tool call failed: {resp['error']}")
        return resp.get("result", {})

    async def list_tools(self) -> list[McpToolSchema]:
        resp = await self._request("tools/list", {})
        if "error" in resp:
            logger.warning("tools/list error: %s", resp["error"])
            return []
        tools_raw = resp.get("result", {}).get("tools", [])
        return [
            McpToolSchema(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                server_name=self._config.name,
            )
            for t in tools_raw
        ]


# ---------------------------------------------------------------------------
# 5. HTTP Transport (SSE variant handled as HTTP + SSE stream)
# ---------------------------------------------------------------------------

class HttpTransport(McpTransport):
    """Transport that communicates with an MCP server over HTTP.

    Uses HTTP POST to ``/mcp`` for request/response and an optional SSE
    stream for server-initiated notifications.

    This implementation defines the interface; actual network I/O is
    delegated to an injectable ``_http_client`` for testability.
    """

    def __init__(
        self,
        config: McpServerConfig,
        http_client: Optional[Any] = None,
    ) -> None:
        super().__init__(config)
        self._http_client = http_client
        self._tools: list[McpToolSchema] = []
        self._session_id: Optional[str] = None

    @property
    def base_url(self) -> str:
        return self._config.url.rstrip("/") if self._config.url else ""

    async def connect(self) -> None:
        """Initialize session with the remote MCP server."""
        if self._http_client is None:
            raise ConnectionError("No HTTP client configured")
        resp = await self._post("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hermes-agent", "version": "1.0.0"},
        })
        self._session_id = resp.get("result", {}).get("sessionId")
        await self._notify("notifications/initialized", {})
        self._connected = True
        self._tools = await self.list_tools()

    async def disconnect(self) -> None:
        self._connected = False
        self._session_id = None
        self._tools.clear()

    async def _post(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request via HTTP POST."""
        if self._http_client is None:
            raise ConnectionError("Transport not connected")
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        return await self._http_client.post(f"{self.base_url}/mcp", json=payload)

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if self._http_client is None:
            return
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        await self._http_client.post(f"{self.base_url}/mcp", json=payload)

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        resp = await self._post("tools/call", {"name": name, "arguments": args})
        if "error" in resp:
            raise RuntimeError(f"Tool call failed: {resp['error']}")
        return resp.get("result", {})

    async def list_tools(self) -> list[McpToolSchema]:
        resp = await self._post("tools/list", {})
        if "error" in resp:
            return []
        tools_raw = resp.get("result", {}).get("tools", [])
        return [
            McpToolSchema(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                server_name=self._config.name,
            )
            for t in tools_raw
        ]


# ---------------------------------------------------------------------------
# 6. Transport Factory
# ---------------------------------------------------------------------------

_TRANSPORT_MAP: dict[TransportType, type[McpTransport]] = {
    TransportType.STDIO: StdioTransport,
    TransportType.HTTP: HttpTransport,
    TransportType.SSE: HttpTransport,   # SSE shares HTTP transport
    TransportType.WEBSOCKET: HttpTransport,  # Placeholder; same interface
}


def create_transport(config: McpServerConfig, **kwargs: Any) -> McpTransport:
    """Create the appropriate transport for the given config.

    Args:
        config: Server configuration.
        **kwargs: Extra arguments forwarded to the transport constructor.

    Returns:
        An ``McpTransport`` instance (not yet connected).
    """
    cls = _TRANSPORT_MAP.get(config.transport)
    if cls is None:
        raise ValueError(f"Unsupported transport type: {config.transport}")
    return cls(config, **kwargs)


# ---------------------------------------------------------------------------
# 7. McpManager
# ---------------------------------------------------------------------------

class McpManager:
    """Manages multiple MCP server connections.

    Args:
        configs: List of server configurations.
        **transport_kwargs: Extra kwargs forwarded to transport constructors.
    """

    def __init__(
        self,
        configs: list[McpServerConfig],
        **transport_kwargs: Any,
    ) -> None:
        self._configs = {c.name: c for c in configs}
        self._transports: dict[str, McpTransport] = {}
        self._transport_kwargs = transport_kwargs

    # -- Lifecycle ----------------------------------------------------------

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all enabled servers.

        Returns:
            Mapping of server name to connection success.
        """
        results: dict[str, bool] = {}
        for name, config in self._configs.items():
            if not config.enabled:
                results[name] = False
                continue
            try:
                transport = create_transport(config, **self._transport_kwargs)
                await transport.connect()
                self._transports[name] = transport
                results[name] = True
                logger.info("Connected to MCP server '%s'", name)
            except Exception:
                logger.exception("Failed to connect to MCP server '%s'", name)
                results[name] = False
        return results

    async def disconnect_all(self) -> None:
        """Disconnect from all connected servers."""
        for name, transport in list(self._transports.items()):
            try:
                await transport.disconnect()
                logger.info("Disconnected from MCP server '%s'", name)
            except Exception:
                logger.exception("Error disconnecting from '%s'", name)
        self._transports.clear()

    # -- Tool operations ----------------------------------------------------

    async def call_tool(
        self, server: str, tool: str, args: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool on a specific server.

        Args:
            server: Server name.
            tool: Tool name.
            args: Tool arguments.

        Returns:
            Tool result.

        Raises:
            KeyError: If the server is not connected.
        """
        transport = self._transports.get(server)
        if transport is None:
            raise KeyError(f"Server '{server}' is not connected")
        return await transport.call_tool(tool, args)

    def get_all_tools(self) -> list[McpToolSchema]:
        """Return tool schemas from all connected servers."""
        tools: list[McpToolSchema] = []
        for transport in self._transports.values():
            if isinstance(transport, (StdioTransport, HttpTransport)):
                tools.extend(transport._tools)
        return tools

    def get_server_status(self) -> dict[str, str]:
        """Return status of every configured server.

        Returns:
            Mapping of server name to status string:
            ``"connected"``, ``"disconnected"``, or ``"disabled"``.
        """
        status: dict[str, str] = {}
        for name, config in self._configs.items():
            if not config.enabled:
                status[name] = "disabled"
            elif name in self._transports and self._transports[name].is_connected:
                status[name] = "connected"
            else:
                status[name] = "disconnected"
        return status

    def get_transport(self, name: str) -> Optional[McpTransport]:
        """Get the transport for a connected server, or ``None``."""
        return self._transports.get(name)


# ---------------------------------------------------------------------------
# 8. Config Parsing
# ---------------------------------------------------------------------------

def from_dict(data: dict[str, Any]) -> list[McpServerConfig]:
    """Parse MCP server configurations from a dict.

    Compatible with Claude Code's ``mcpServers`` format::

        {
            "mcpServers": {
                "my-server": {
                    "command": "node",
                    "args": ["server.js"],
                    "env": {"KEY": "val"}
                }
            }
        }

    Or a flat list format::

        {
            "servers": [
                {"name": "s1", "transport": "stdio", "command": "node"}
            ]
        }

    Args:
        data: Configuration dict.

    Returns:
        List of ``McpServerConfig`` objects.
    """
    configs: list[McpServerConfig] = []

    # Claude Code format: {"mcpServers": {"name": { ... }}}
    mcp_servers = data.get("mcpServers")
    if isinstance(mcp_servers, dict):
        for name, server_cfg in mcp_servers.items():
            transport_str = server_cfg.get("transport", "stdio")
            # Default to stdio if command is present, else http if url present
            if "command" in server_cfg:
                transport_str = server_cfg.get("transport", "stdio")
            elif "url" in server_cfg:
                transport_str = server_cfg.get("transport", "http")
            configs.append(McpServerConfig(
                name=name,
                transport=TransportType(transport_str),
                command=server_cfg.get("command"),
                url=server_cfg.get("url"),
                env=server_cfg.get("env", {}),
                args=server_cfg.get("args", []),
                timeout=server_cfg.get("timeout", 30.0),
                enabled=server_cfg.get("enabled", True),
            ))

    # Flat list format: {"servers": [ { "name": ..., ... } ]}
    servers_list = data.get("servers")
    if isinstance(servers_list, list):
        for server_cfg in servers_list:
            transport_str = server_cfg.get("transport", "stdio")
            configs.append(McpServerConfig(
                name=server_cfg["name"],
                transport=TransportType(transport_str),
                command=server_cfg.get("command"),
                url=server_cfg.get("url"),
                env=server_cfg.get("env", {}),
                args=server_cfg.get("args", []),
                timeout=server_cfg.get("timeout", 30.0),
                enabled=server_cfg.get("enabled", True),
            ))

    return configs
