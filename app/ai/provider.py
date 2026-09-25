"""One call to a model, in either of the two wire formats Zen speaks.

Claude goes through Anthropic's /messages, GPT through OpenAI's /responses.
Both are reduced here to the same shape: a list of turns in, text or tool
calls out, with token counts. Nothing above this module knows which one ran.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

import httpx

from ..config import Settings


class AINotConfigured(Exception):
    pass


class AIError(Exception):
    pass


@dataclass
class Image:
    png: bytes


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    raw_assistant: object = None   # the provider's own assistant turn, to echo back


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict


class Provider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        if not settings.opencode_api_key:
            raise AINotConfigured("尚未設定 AI（伺服器沒有 OpenCode API key）")
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.ai_timeout_seconds)

    # ── public ──────────────────────────────────────────────────────────────

    def complete(self, system: str, turns: list[dict], tools: list[Tool] | None = None,
                 max_tokens: int = 1200) -> Reply:
        style = self.settings.ai_api_style
        if style == "anthropic":
            return self._anthropic(system, turns, tools or [], max_tokens)
        if style == "openai":
            return self._openai(system, turns, tools or [], max_tokens)
        raise AIError(f"未知的 AI_API_STYLE：{style}")

    # Turns are provider-neutral: {"role": "user", "text": ..., "images": [...]},
    # {"role": "assistant_raw", "raw": ...}, {"role": "tool", "id": ..., "result": ...}.

    def _post(self, path: str, body: dict) -> dict:
        try:
            res = self.client.post(
                self.settings.opencode_base_url.rstrip("/") + path,
                headers={"Authorization": f"Bearer {self.settings.opencode_api_key}",
                         "Content-Type": "application/json",
                         "anthropic-version": "2023-06-01"},
                json=body,
            )
        except httpx.HTTPError as exc:
            raise AIError(f"連不到 AI 服務：{type(exc).__name__}") from exc
        if res.status_code >= 400:
            # The body can echo the request; keep only the start, never the key.
            raise AIError(f"AI 服務回應 {res.status_code}：{res.text[:200]}")
        return res.json()

    # ── Anthropic /messages ─────────────────────────────────────────────────

    def _anthropic(self, system, turns, tools, max_tokens) -> Reply:
        messages: list[dict] = []
        for t in turns:
            if t["role"] == "user":
                content = [{"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": base64.b64encode(img.png).decode()}} for img in t.get("images", [])]
                content.append({"type": "text", "text": t["text"]})
                messages.append({"role": "user", "content": content})
            elif t["role"] == "assistant_raw":
                messages.append({"role": "assistant", "content": t["raw"]})
            elif t["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": t["id"],
                         "content": json.dumps(t["result"], ensure_ascii=False)}
                if messages and messages[-1]["role"] == "user" and isinstance(
                        messages[-1]["content"], list) and messages[-1]["content"] and \
                        messages[-1]["content"][0].get("type") == "tool_result":
                    messages[-1]["content"].append(block)
                else:
                    messages.append({"role": "user", "content": [block]})
        # Anthropic wants turns to alternate; fold any run of same-role turns
        # (tool results followed by an image, say) into one.
        merged: list[dict] = []
        for m in messages:
            if merged and merged[-1]["role"] == m["role"]:
                prev = merged[-1]["content"]
                prev = prev if isinstance(prev, list) else [{"type": "text", "text": prev}]
                cur = m["content"] if isinstance(m["content"], list) else [
                    {"type": "text", "text": m["content"]}]
                merged[-1]["content"] = prev + cur
            else:
                merged.append(m)
        body = {"model": self.settings.ai_model, "max_tokens": max_tokens,
                "system": system, "messages": merged}
        if tools:
            body["tools"] = [{"name": x.name, "description": x.description,
                              "input_schema": x.parameters} for x in tools]
        out = self._post("/messages", body)
        text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {})
                 for b in out.get("content", []) if b.get("type") == "tool_use"]
        usage = out.get("usage", {})
        return Reply(text, calls, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                     raw_assistant=out.get("content", []))

    # ── OpenAI /responses ───────────────────────────────────────────────────

    def _openai(self, system, turns, tools, max_tokens) -> Reply:
        items: list[dict] = []
        for t in turns:
            if t["role"] == "user":
                content = [{"type": "input_image",
                            "image_url": "data:image/png;base64,"
                            + base64.b64encode(img.png).decode()} for img in t.get("images", [])]
                content.append({"type": "input_text", "text": t["text"]})
                items.append({"role": "user", "content": content})
            elif t["role"] == "assistant_raw":
                items.extend(t["raw"])
            elif t["role"] == "tool":
                items.append({"type": "function_call_output", "call_id": t["id"],
                              "output": json.dumps(t["result"], ensure_ascii=False)})
        body = {"model": self.settings.ai_model, "instructions": system, "input": items,
                "max_output_tokens": max_tokens}
        if tools:
            body["tools"] = [{"type": "function", "name": x.name, "description": x.description,
                              "parameters": x.parameters} for x in tools]
        out = self._post("/responses", body)
        output = out.get("output", [])
        text = "".join(c.get("text", "") for o in output if o.get("type") == "message"
                       for c in o.get("content", []) if c.get("type") == "output_text")
        calls = [ToolCall(o["call_id"], o["name"], json.loads(o.get("arguments") or "{}"))
                 for o in output if o.get("type") == "function_call"]
        usage = out.get("usage", {})
        return Reply(text, calls, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
                     raw_assistant=[o for o in output
                                    if o.get("type") in ("message", "function_call")])
