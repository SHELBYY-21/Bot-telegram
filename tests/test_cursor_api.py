import json

import httpx
import pytest

from cursor_api import CursorAPIError, CursorClient


def make_client(handler):
    return CursorClient("test-key", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_create_agent_body_and_auth():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers["Authorization"]
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "bc_1", "status": "CREATING"})

    client = make_client(handler)
    agent = await client.create_agent(
        prompt_text="fix the bug",
        repository="https://github.com/o/r",
        ref="main",
        model="claude",
        branch_name="feat/x",
        auto_create_pr=True,
        webhook_url="https://example.com/hook",
    )
    await client.close()

    assert agent["id"] == "bc_1"
    assert captured["auth"] == "Bearer test-key"
    assert captured["method"] == "POST"
    assert captured["path"] == "/v0/agents"
    assert captured["body"] == {
        "prompt": {"text": "fix the bug"},
        "source": {"repository": "https://github.com/o/r", "ref": "main"},
        "model": "claude",
        "target": {"branchName": "feat/x", "autoCreatePr": True},
        "webhook": {"url": "https://example.com/hook"},
    }


@pytest.mark.asyncio
async def test_create_agent_minimal_body_omits_optionals():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "bc_2"})

    client = make_client(handler)
    await client.create_agent(prompt_text="hi", repository="https://github.com/o/r")
    await client.close()

    assert captured["body"] == {
        "prompt": {"text": "hi"},
        "source": {"repository": "https://github.com/o/r"},
    }


@pytest.mark.asyncio
async def test_error_raises_with_status_and_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key"})

    client = make_client(handler)
    with pytest.raises(CursorAPIError) as exc:
        await client.me()
    await client.close()

    assert exc.value.status_code == 401
    assert "invalid api key" in str(exc.value)


@pytest.mark.asyncio
async def test_agent_action_paths():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={})

    client = make_client(handler)
    await client.get_agent("bc_9")
    await client.get_conversation("bc_9")
    await client.add_followup("bc_9", "more")
    await client.stop_agent("bc_9")
    await client.delete_agent("bc_9")
    await client.list_agents(limit=5, cursor="abc")
    await client.list_models()
    await client.list_repositories()
    await client.close()

    assert seen == [
        ("GET", "/v0/agents/bc_9"),
        ("GET", "/v0/agents/bc_9/conversation"),
        ("POST", "/v0/agents/bc_9/followup"),
        ("POST", "/v0/agents/bc_9/stop"),
        ("DELETE", "/v0/agents/bc_9"),
        ("GET", "/v0/agents"),
        ("GET", "/v0/models"),
        ("GET", "/v0/repositories"),
    ]


@pytest.mark.asyncio
async def test_empty_response_body_returns_empty_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = make_client(handler)
    assert await client.delete_agent("bc_9") == {}
    await client.close()
