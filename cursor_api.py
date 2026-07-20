"""Thin async client for the Cursor Cloud Agents API.

Endpoint reference: https://cursor.com/docs/cloud-agent/api/endpoints
All requests are authenticated with `Authorization: Bearer <CURSOR_API_KEY>`.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

BASE_URL = os.environ.get("CURSOR_API_URL", "https://api.cursor.com")


class CursorAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Cursor API error {status_code}: {message}")


class CursorClient:
    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", resp.text)
            except Exception:
                detail = resp.text
            raise CursorAPIError(resp.status_code, str(detail))
        if not resp.content:
            return {}
        return resp.json()

    # --- Agents -----------------------------------------------------------

    async def create_agent(
        self,
        prompt_text: str,
        repository: str,
        ref: str | None = None,
        model: str | None = None,
        branch_name: str | None = None,
        auto_create_pr: bool = False,
        webhook_url: str | None = None,
    ) -> dict:
        """POST /v0/agents — launch a new cloud agent."""
        source: dict[str, Any] = {"repository": repository}
        if ref:
            source["ref"] = ref
        body: dict[str, Any] = {
            "prompt": {"text": prompt_text},
            "source": source,
        }
        if model:
            body["model"] = model
        target: dict[str, Any] = {}
        if branch_name:
            target["branchName"] = branch_name
        if auto_create_pr:
            target["autoCreatePr"] = True
        if target:
            body["target"] = target
        if webhook_url:
            body["webhook"] = {"url": webhook_url}
        return await self._request("POST", "/v0/agents", json=body)

    async def list_agents(self, limit: int = 20, cursor: str | None = None) -> dict:
        """GET /v0/agents — paginated list of agents."""
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/v0/agents", params=params)

    async def get_agent(self, agent_id: str) -> dict:
        """GET /v0/agents/{id} — agent status and metadata."""
        return await self._request("GET", f"/v0/agents/{agent_id}")

    async def get_conversation(self, agent_id: str) -> dict:
        """GET /v0/agents/{id}/conversation — full message history."""
        return await self._request("GET", f"/v0/agents/{agent_id}/conversation")

    async def add_followup(self, agent_id: str, prompt_text: str) -> dict:
        """POST /v0/agents/{id}/followup — send follow-up instructions."""
        body = {"prompt": {"text": prompt_text}}
        return await self._request("POST", f"/v0/agents/{agent_id}/followup", json=body)

    async def stop_agent(self, agent_id: str) -> dict:
        """POST /v0/agents/{id}/stop — stop a running agent."""
        return await self._request("POST", f"/v0/agents/{agent_id}/stop")

    async def delete_agent(self, agent_id: str) -> dict:
        """DELETE /v0/agents/{id} — permanently delete an agent."""
        return await self._request("DELETE", f"/v0/agents/{agent_id}")

    # --- Metadata ---------------------------------------------------------

    async def me(self) -> dict:
        """GET /v0/me — API key info."""
        return await self._request("GET", "/v0/me")

    async def list_models(self) -> dict:
        """GET /v0/models — models available for cloud agents."""
        return await self._request("GET", "/v0/models")

    async def list_repositories(self) -> dict:
        """GET /v0/repositories — GitHub repositories accessible to agents."""
        return await self._request("GET", "/v0/repositories")
