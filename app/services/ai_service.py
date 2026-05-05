from dataclasses import dataclass
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


@dataclass
class AIRequest:
    provider: str
    model: str
    prompt: str
    base_url: str = ""
    api_key: str = ""
    auth_type: str = "api_key"


def generate_diagram_plan(req: AIRequest) -> dict:
    provider = (req.provider or "").lower().strip()
    if not provider:
        raise ValueError("未配置模型厂商")
    if not req.model.strip():
        raise ValueError("未配置模型名称")
    if not req.api_key.strip() and provider != "ollama":
        raise ValueError("API Key 为空")

    prompt = _build_prompt(req.prompt)
    raw_text = _call_provider(req, prompt)
    plan = _parse_plan(raw_text)
    plan.setdefault("provider", provider)
    plan.setdefault("model", req.model)
    plan.setdefault("direction", "TB")
    if not isinstance(plan.get("items"), list) or not plan["items"]:
        plan["items"] = _fallback_items(req.prompt)
    return plan


def _build_prompt(user_prompt: str) -> str:
    return (
        "你是流程图生成器。请只返回 JSON，不要解释，不要代码块。\n"
        "JSON 格式必须是：{\"direction\":\"TB\"|\"LR\",\"items\":[[\"type\",\"label\"],...]}\n"
        "type 仅使用以下值之一：terminator,process,decision,data,document,database,model,service,server,web,mobile,api,cache,queue,training,evaluation,experiment,paper,person,note,callout,cloud,code,deployment,augment,embedding,attention,loss,optimizer,metric,display,offpage,subroutine,preparation,manualInput,delay,connector\n"
        "items 至少 3 个，最多 12 个，按流程顺序排列。\n"
        f"用户描述：{user_prompt}"
    )


def _call_provider(req: AIRequest, prompt: str) -> str:
    provider = (req.provider or "").lower().strip()
    if provider == "gemini":
        return _call_gemini(req, prompt)
    if provider == "anthropic":
        return _call_anthropic(req, prompt)
    return _call_openai_compatible(req, prompt)


def _call_openai_compatible(req: AIRequest, prompt: str) -> str:
    base_url = (req.base_url or "").rstrip("/") or "https://api.openai.com/v1"
    url = base_url + "/chat/completions"
    payload = {
        "model": req.model,
        "messages": [
            {"role": "system", "content": "你只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    data = _http_json(url, payload, req.api_key, req.auth_type)
    return _extract_text_from_openai(data)


def _call_anthropic(req: AIRequest, prompt: str) -> str:
    base_url = (req.base_url or "").rstrip("/") or "https://api.anthropic.com/v1"
    url = base_url + "/messages"
    payload = {
        "model": req.model,
        "max_tokens": 1200,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = _http_json(url, payload, req.api_key, req.auth_type, anthropic=True)
    return _extract_text_from_anthropic(data)


def _call_gemini(req: AIRequest, prompt: str) -> str:
    base_url = (req.base_url or "").rstrip("/") or "https://generativelanguage.googleapis.com/v1beta"
    model = urllib.parse.quote(req.model, safe="")
    if "key=" in base_url:
        url = f"{base_url}/models/{model}:generateContent"
    else:
        url = f"{base_url}/models/{model}:generateContent?key={urllib.parse.quote(req.api_key)}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    data = _http_json(url, payload, req.api_key, req.auth_type, gemini=True)
    return _extract_text_from_gemini(data)


def _http_json(url: str, payload: dict, api_key: str, auth_type: str, anthropic: bool = False, gemini: bool = False) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if anthropic:
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif not gemini:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise ValueError(f"AI 请求失败: {detail}")
    except Exception as exc:
        raise ValueError(f"AI 请求失败: {exc}")


def _extract_text_from_openai(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def _extract_text_from_anthropic(data: dict[str, Any]) -> str:
    parts = []
    for item in data.get("content") or []:
        if item.get("type") == "text":
            parts.append(item.get("text") or "")
    return "\n".join(parts)


def _extract_text_from_gemini(data: dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    content = (candidates[0].get("content") or {}).get("parts") or []
    return "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict))


def _parse_plan(text: str) -> dict:
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, re.S)
    payload = match.group(0) if match else text.strip()
    try:
        data = json.loads(payload)
    except Exception:
        return {"items": _fallback_items(text)}
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            data["items"] = _normalize_items(data["items"])
        return data
    return {"items": _fallback_items(text)}


def _normalize_items(items: list) -> list[list[str]]:
    result: list[list[str]] = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            type_name = str(item[0]).strip() or "process"
            label = str(item[1]).strip()
            if label:
                result.append([type_name, label])
    return result[:12]


def _fallback_items(text: str) -> list[list[str]]:
    parts = [part.strip() for part in re.split(r"[，,。；;\n]+", text or "") if part.strip()]
    if len(parts) < 2:
        parts = ["开始", "理解需求", "处理", "结束"]
    items: list[list[str]] = []
    for index, label in enumerate(parts[:12]):
        if index == 0:
            shape = "terminator"
        elif "?" in label or "是否" in label or "判断" in label:
            shape = "decision"
        else:
            shape = "process"
        items.append([shape, label])
    return items
