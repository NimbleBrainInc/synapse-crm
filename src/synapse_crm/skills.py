"""Serve the bundled skills over MCP (SEP-2640, `io.modelcontextprotocol/skills`) on every era.

FastMCP's `SkillsExtension` answers `skills/list` and `skills/get` from a `SkillsDirectoryProvider`
and binds both methods to the 2026-07-28 protocol era only. NimbleBrain still negotiates
2025-11-25 through the initialize handshake, so this subclass keeps FastMCP's handlers, models and
listing and lifts the era limit from its two method bindings.
"""

from collections.abc import Sequence
from dataclasses import replace

from fastmcp.server.extensions import MethodBinding
from fastmcp.skills.extension import SkillsExtension


class SkillsOnEveryEra(SkillsExtension):
    def methods(self) -> Sequence[MethodBinding]:
        return tuple(
            replace(binding, protocol_versions=None) for binding in super().methods()
        )
