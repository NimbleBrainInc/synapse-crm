"""The bundled skills over MCP (SEP-2640) on both protocol eras, and the older resource URIs."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.skills import SkillsClientExtension
from fastmcp.skills.extension import SkillsExtension
from fastmcp.skills.models import (
    GetSkillParams,
    GetSkillRequest,
    GetSkillResult,
    ListSkillsParams,
    ListSkillsRequest,
    ListSkillsResult,
)

from tests.conftest import _run

PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_EXTENSION = "io.modelcontextprotocol/skills"
SKILLS = ["follow-up-coach", "pipeline-reviewer"]
# NimbleBrain negotiates 2025-11-25 through the initialize handshake today; a modern client
# discovers the sessionless 2026-07-28 era. Skills must answer on both.
ERAS = [("legacy", "2025-11-25"), ("auto", "2026-07-28")]


@pytest.mark.parametrize(("mode", "protocol"), ERAS)
def test_the_skills_are_listed_and_fetched_on_both_protocol_eras(mcp, mode, protocol):
    async def check():
        async with Client(
            mcp, mode=mode, extensions=[SkillsClientExtension()]
        ) as client:
            assert client.protocol_version == protocol
            if mode == "auto":
                assert SKILLS_EXTENSION in client.server_capabilities.extensions
                listing = await client.list_skills()
                fetch = client.get_skill
            else:
                # The SDK strips capabilities.extensions from a handshake-era initialize
                # result and FastMCP's client helpers refuse that era, so a 2025-11-25 host
                # sends the methods itself.
                listed = await client.session.send_request(
                    ListSkillsRequest(params=ListSkillsParams()), ListSkillsResult
                )
                assert listed.result_type == "complete"
                listing = listed.skills

                async def fetch(uri):
                    request = GetSkillRequest(params=GetSkillParams(uri=uri))
                    return (
                        await client.session.send_request(request, GetSkillResult)
                    ).skill

            assert [skill.uri for skill in listing] == [
                f"skill://{name}/SKILL.md" for name in SKILLS
            ]
            for skill in listing:
                folder = skill.uri.split("/")[-2]
                assert skill.frontmatter.name == folder
                assert skill.frontmatter.description
                assert await fetch(skill.uri) == skill
                contents = (await client.read_resource_mcp(skill.uri)).contents[0]
                assert contents.mime_type == "text/markdown"
                served = contents.text.encode()
                assert (
                    served
                    == (PROJECT_ROOT / "skills" / folder / "SKILL.md").read_bytes()
                )
                assert [resource.model_dump() for resource in skill.resources] == [
                    {
                        "uri": skill.uri,
                        "digest": f"sha256:{hashlib.sha256(served).hexdigest()}",
                        "size": len(served),
                    }
                ]

    _run(check())


def test_skills_come_from_fastmcps_extension_with_the_era_limit_lifted(mcp):
    extension = mcp._extensions[SKILLS_EXTENSION]
    assert isinstance(extension, SkillsExtension)
    assert {
        binding.method: binding.protocol_versions for binding in extension.methods()
    } == {
        "skills/list": None,
        "skills/get": None,
    }


def test_the_upjack_skill_resources_still_return_the_same_files(mcp):
    async def check():
        async with Client(mcp) as client:
            for name in SKILLS:
                contents = await client.read_resource(f"upjack://skills/{name}")
                path = PROJECT_ROOT / "skills" / name / "SKILL.md"
                assert contents[0].text == path.read_text()

    _run(check())
