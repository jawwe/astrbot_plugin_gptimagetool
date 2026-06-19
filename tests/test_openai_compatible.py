"""Tests for the OpenAI-compatible HTTP client."""

import asyncio
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai_compatible import OpenAICompatibleClient, OpenAICompatibleError


def test_lists_models_and_uses_bearer_auth() -> None:
    """The model request uses the configured API root and authentication."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.example.com/v1/models"
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, json={"data": [{"id": "z"}, {"id": "a"}, {"id": "a"}]})

    client = OpenAICompatibleClient(httpx.MockTransport(handler))
    assert asyncio.run(client.list_models("https://api.example.com/v1/", "secret")) == [
        "a",
        "z",
    ]


def test_generates_url_and_base64_images() -> None:
    """The image endpoint accepts both supported provider response forms."""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/v1/images/generations"
        if calls == 1:
            return httpx.Response(
                200,
                json={"data": [{"url": "https://image.example/a.png"}]},
            )
        return httpx.Response(200, json={"data": [{"b64_json": "aGVsbG8="}]})

    client = OpenAICompatibleClient(httpx.MockTransport(handler))
    assert asyncio.run(
        client.generate_image(
            base_url="https://api.example.com/v1",
            api_key="key",
            model="gpt-image-2",
            prompt="cat",
        )
    ) == {"url": "https://image.example/a.png"}
    assert asyncio.run(
        client.generate_image(
            base_url="https://api.example.com/v1",
            api_key="key",
            model="gpt-image-2",
            prompt="cat",
        )
    ) == {"b64_json": "aGVsbG8="}


def test_optimizes_prompt_and_reports_provider_errors() -> None:
    """Chat completions are parsed and provider errors are safe to show."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("chat/completions"):
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "detailed cat"}}]},
            )
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    client = OpenAICompatibleClient(httpx.MockTransport(handler))
    assert asyncio.run(
        client.optimize_prompt(
            base_url="https://api.example.com/v1",
            api_key="key",
            model="gpt-4.1-mini",
            system_prompt="Improve",
            prompt="cat",
        )
    ) == "detailed cat"
    with pytest.raises(OpenAICompatibleError, match="HTTP 401.*invalid key"):
        asyncio.run(client.list_models("https://api.example.com/v1", "key"))
