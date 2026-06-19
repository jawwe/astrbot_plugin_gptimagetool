"""Minimal OpenAI-compatible API client used by GPT Image Tool."""

from __future__ import annotations

from typing import Any

import httpx


class OpenAICompatibleError(RuntimeError):
    """A safe error message suitable for display to an AstrBot user."""


class OpenAICompatibleClient:
    """Call the OpenAI-compatible endpoints required by this plugin."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Create the client.

        Args:
            transport: Optional test transport. Production requests use httpx defaults.
        """
        self._transport = transport

    @staticmethod
    def validate_base_url(base_url: str) -> str:
        """Validate an OpenAI-compatible API root URL.

        Args:
            base_url: API root, normally ending in `/v1`.

        Returns:
            The URL without a trailing slash.

        Raises:
            OpenAICompatibleError: If the URL is not an absolute HTTP(S) URL.
        """
        try:
            url = httpx.URL(base_url.strip())
        except httpx.InvalidURL as exc:
            raise OpenAICompatibleError(
                "API 地址必须是完整的 HTTP 或 HTTPS 地址。"
            ) from exc
        if url.scheme not in {"http", "https"} or not url.host:
            raise OpenAICompatibleError("API 地址必须是完整的 HTTP 或 HTTPS 地址。")
        return str(url).rstrip("/")

    async def list_models(self, base_url: str, api_key: str) -> list[str]:
        """Fetch model identifiers from the OpenAI-compatible models endpoint.

        Args:
            base_url: OpenAI-compatible API root.
            api_key: Bearer API key.

        Returns:
            Sorted unique model identifiers.

        Raises:
            OpenAICompatibleError: If the provider response is invalid or unsuccessful.
        """
        payload = await self._request("GET", base_url, api_key, "models")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise OpenAICompatibleError("模型接口未返回 data 列表。")
        models = sorted(
            {
                item["id"].strip()
                for item in data
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and item["id"].strip()
            },
            key=str.lower,
        )
        if not models:
            raise OpenAICompatibleError("模型接口未返回可用模型。")
        return models

    async def optimize_prompt(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        prompt: str,
    ) -> str:
        """Use a chat model to rewrite an image-generation prompt.

        Args:
            base_url: OpenAI-compatible API root.
            api_key: Bearer API key.
            model: Auxiliary chat model name.
            system_prompt: User configured optimization instruction.
            prompt: Original image request.

        Returns:
            Optimized prompt text.

        Raises:
            OpenAICompatibleError: If the response lacks a text completion.
        """
        payload = await self._request(
            "POST",
            base_url,
            api_key,
            "chat/completions",
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenAICompatibleError("辅助模型未返回有效的提示词。") from exc
        if not isinstance(content, str) or not content.strip():
            raise OpenAICompatibleError("辅助模型未返回有效的提示词。")
        return content.strip()

    async def generate_image(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> dict[str, str]:
        """Generate one image with an OpenAI-compatible image endpoint.

        Args:
            base_url: OpenAI-compatible API root.
            api_key: Bearer API key.
            model: Image model name.
            prompt: Image-generation prompt.

        Returns:
            A response containing either `url` or `b64_json`.

        Raises:
            OpenAICompatibleError: If the response has no supported image payload.
        """
        payload = await self._request(
            "POST",
            base_url,
            api_key,
            "images/generations",
            {"model": model, "prompt": prompt},
        )
        try:
            image = payload["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenAICompatibleError("图像接口未返回图片数据。") from exc
        if not isinstance(image, dict):
            raise OpenAICompatibleError("图像接口返回格式不正确。")
        for key in ("url", "b64_json"):
            value = image.get(key)
            if isinstance(value, str) and value.strip():
                return {key: value.strip()}
        raise OpenAICompatibleError("图像接口未返回 URL 或 Base64 图片。")

    async def _request(
        self,
        method: str,
        base_url: str,
        api_key: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an authenticated API request and normalize provider failures.

        Args:
            method: HTTP method.
            base_url: OpenAI-compatible API root.
            api_key: Bearer API key.
            endpoint: Relative endpoint path.
            payload: Optional JSON request body.

        Returns:
            Provider JSON response.

        Raises:
            OpenAICompatibleError: If the request or provider response fails.
        """
        api_root = self.validate_base_url(base_url)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(90.0, connect=15.0),
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    f"{api_root}/{endpoint}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise OpenAICompatibleError("无法连接到 API 服务。") from exc

        if response.is_error:
            detail = ""
            try:
                error = response.json().get("error", {})
                if isinstance(error, dict) and isinstance(error.get("message"), str):
                    detail = error["message"].strip()
            except ValueError:
                pass
            suffix = f"：{detail}" if detail else ""
            raise OpenAICompatibleError(
                f"API 请求失败（HTTP {response.status_code}）{suffix}"
            )
        try:
            response_data = response.json()
        except ValueError as exc:
            raise OpenAICompatibleError("API 未返回 JSON 数据。") from exc
        if not isinstance(response_data, dict):
            raise OpenAICompatibleError("API 返回格式不正确。")
        return response_data
