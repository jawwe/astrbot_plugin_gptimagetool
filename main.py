"""AstrBot GPT Image Tool plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .openai_compatible import OpenAICompatibleClient, OpenAICompatibleError

try:
    from astrbot.api.web import error_response, json_response, request

    async def get_request_json() -> Any:
        """Read JSON through the current AstrBot Web API request proxy.

        Returns:
            Parsed JSON payload or an empty object.
        """
        return await request.json(default={})

except ModuleNotFoundError:
    from quart import jsonify, request

    def json_response(data: Any, *, status_code: int = 200):
        """Build a JSON response for AstrBot versions without astrbot.api.web.

        Args:
            data: JSON-serializable response body.
            status_code: HTTP status code.

        Returns:
            Quart JSON response.
        """
        return jsonify(data), status_code

    def error_response(message: str, *, status_code: int = 400):
        """Build an error envelope compatible with the Page bridge.

        Args:
            message: Safe error message for the Page.
            status_code: HTTP status code.

        Returns:
            Quart JSON error response.
        """
        return jsonify({"status": "error", "message": message}), status_code

    async def get_request_json() -> Any:
        """Read JSON through the legacy Quart request context.

        Returns:
            Parsed JSON payload or an empty object.
        """
        return await request.get_json(silent=True) or {}


PLUGIN_NAME = "astrbot_plugin_gptimagetool"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_AUXILIARY_SYSTEM_PROMPT = (
    "Rewrite the user's request as a concise, detailed image-generation prompt. "
    "Preserve the user's intent and language. Return only the prompt."
)


@register(
    PLUGIN_NAME,
    "jawwe",
    "Generate images through an OpenAI-compatible GPT Image API.",
    "1.0.0",
)
class GPTImageToolPlugin(Star):
    """Generate images and expose a Page for API configuration."""

    def __init__(self, context: Context) -> None:
        """Register Page APIs and initialize the local settings location.

        Args:
            context: AstrBot plugin context.
        """
        super().__init__(context)
        self._settings_path = (
            Path(get_astrbot_plugin_data_path()) / PLUGIN_NAME / "settings.json"
        )
        self._settings = self._default_settings()
        self._client = OpenAICompatibleClient()
        context.register_web_api(
            f"/{PLUGIN_NAME}/settings",
            self.get_settings,
            ["GET"],
            "Get GPT Image Tool settings",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/settings",
            self.save_settings,
            ["POST"],
            "Save GPT Image Tool settings",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/models",
            self.get_models,
            ["POST"],
            "List OpenAI-compatible models",
        )

    async def initialize(self) -> None:
        """Load persisted settings after the plugin has been created."""
        if not self._settings_path.exists():
            return
        try:
            raw_settings = json.loads(self._settings_path.read_text(encoding="utf-8"))
            if not isinstance(raw_settings, dict):
                raise ValueError("settings root must be an object")
            for section_name in ("primary", "auxiliary"):
                section = raw_settings.get(section_name)
                if isinstance(section, dict):
                    self._settings[section_name].update(section)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load GPT Image Tool settings: %s", exc)

    @filter.command("画图")
    async def draw(self, event: AstrMessageEvent, prompt: GreedyStr) -> None:
        """Generate an image from the prompt following the 画图 command.

        Args:
            event: The triggering message event.
            prompt: User supplied image description.
        """
        prompt = prompt.strip()
        if not prompt:
            yield event.plain_result("请在“画图”后提供图片描述。")
            return

        primary = self._settings["primary"]
        if not primary["base_url"] or not primary["api_key"] or not primary["model"]:
            yield event.plain_result("请先在 GPT Image Tool 配置页完成主图像接口设置。")
            return

        try:
            auxiliary = self._resolved_auxiliary_settings()
            if auxiliary is not None:
                prompt = await self._client.optimize_prompt(
                    base_url=auxiliary["base_url"],
                    api_key=auxiliary["api_key"],
                    model=auxiliary["model"],
                    system_prompt=auxiliary["system_prompt"],
                    prompt=prompt,
                )
            image = await self._client.generate_image(
                base_url=primary["base_url"],
                api_key=primary["api_key"],
                model=primary["model"],
                prompt=prompt,
            )
        except OpenAICompatibleError as exc:
            logger.warning("GPT Image Tool request failed: %s", exc)
            yield event.plain_result(f"画图失败：{exc}")
            return

        if "url" in image:
            yield event.image_result(image["url"])
            return
        yield event.chain_result([Image.fromBase64(image["b64_json"])])

    async def get_settings(self):
        """Return settings without exposing configured API keys."""
        return json_response(self._public_settings())

    async def save_settings(self):
        """Validate and persist Page-submitted settings.

        Returns:
            A sanitized settings object or a Page-compatible error response.
        """
        payload = await get_request_json()
        if not isinstance(payload, dict):
            return error_response("配置数据必须是 JSON 对象。")

        for section_name in ("primary", "auxiliary"):
            section = payload.get(section_name, {})
            if not isinstance(section, dict):
                return error_response(f"{section_name} 配置必须是对象。")
            target = self._settings[section_name]
            for key in ("base_url", "model", "system_prompt"):
                if key not in section:
                    continue
                value = section[key]
                if not isinstance(value, str):
                    return error_response(f"{key} 必须是字符串。")
                target[key] = value.strip()
            if "api_key" in section:
                api_key = section["api_key"]
                if not isinstance(api_key, str):
                    return error_response("API Key 必须是字符串。")
                if api_key.strip():
                    target["api_key"] = api_key.strip()
            if section_name == "auxiliary" and "enabled" in section:
                if not isinstance(section["enabled"], bool):
                    return error_response("辅助模型启用状态必须是布尔值。")
                target["enabled"] = section["enabled"]

        try:
            for section_name in ("primary", "auxiliary"):
                base_url = self._settings[section_name]["base_url"]
                if base_url:
                    self._client.validate_base_url(base_url)
        except OpenAICompatibleError as exc:
            return error_response(str(exc))

        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._settings_path.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                json.dumps(self._settings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(self._settings_path)
        except OSError as exc:
            logger.exception("Failed to save GPT Image Tool settings")
            return error_response(f"保存配置失败：{exc}", status_code=500)
        return json_response(self._public_settings())

    async def get_models(self):
        """Fetch models for a Page form without persisting form credentials.

        Returns:
            A model-id list or a Page-compatible error response.
        """
        payload = await get_request_json()
        if not isinstance(payload, dict):
            return error_response("模型请求必须是 JSON 对象。")
        target = payload.get("target")
        if target not in {"primary", "auxiliary"}:
            return error_response("未知的模型配置目标。")

        primary = self._settings["primary"]
        source = payload.get(target, {})
        if not isinstance(source, dict):
            return error_response("模型接口配置必须是对象。")
        base_url = str(source.get("base_url", "")).strip()
        api_key = str(source.get("api_key", "")).strip()
        if target == "auxiliary":
            base_url = base_url or primary["base_url"]
            api_key = api_key or primary["api_key"]
        if not base_url or not api_key:
            return error_response("请先输入 API 地址和 Key。")
        try:
            models = await self._client.list_models(base_url, api_key)
        except OpenAICompatibleError as exc:
            return error_response(str(exc), status_code=502)
        return json_response({"models": models})

    @staticmethod
    def _default_settings() -> dict[str, dict[str, Any]]:
        """Create the complete default settings document.

        Returns:
            Default primary and auxiliary model settings.
        """
        return {
            "primary": {"base_url": "", "api_key": "", "model": DEFAULT_IMAGE_MODEL},
            "auxiliary": {
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "model": "",
                "system_prompt": DEFAULT_AUXILIARY_SYSTEM_PROMPT,
            },
        }

    def _public_settings(self) -> dict[str, dict[str, Any]]:
        """Return settings safe for delivery to the Page iframe.

        Returns:
            Settings with API keys replaced by presence flags.
        """
        primary = self._settings["primary"]
        auxiliary = self._settings["auxiliary"]
        return {
            "primary": {
                "base_url": primary["base_url"],
                "model": primary["model"],
                "api_key_set": bool(primary["api_key"]),
            },
            "auxiliary": {
                "enabled": auxiliary["enabled"],
                "base_url": auxiliary["base_url"],
                "model": auxiliary["model"],
                "system_prompt": auxiliary["system_prompt"],
                "api_key_set": bool(auxiliary["api_key"]),
                "inherits_primary": not auxiliary["base_url"]
                and not auxiliary["api_key"],
            },
        }

    def _resolved_auxiliary_settings(self) -> dict[str, str] | None:
        """Resolve inherited auxiliary credentials before prompt optimization.

        Returns:
            Active auxiliary configuration, or None when it is disabled.

        Raises:
            OpenAICompatibleError: If enabled auxiliary settings are incomplete.
        """
        auxiliary = self._settings["auxiliary"]
        if not auxiliary["enabled"]:
            return None
        primary = self._settings["primary"]
        resolved = {
            "base_url": auxiliary["base_url"] or primary["base_url"],
            "api_key": auxiliary["api_key"] or primary["api_key"],
            "model": auxiliary["model"],
            "system_prompt": auxiliary["system_prompt"],
        }
        if not all(resolved.values()):
            raise OpenAICompatibleError("请完成辅助模型配置，或关闭提示词优化。")
        return resolved
