from dataclasses import dataclass
import json
import os
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


SKILL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills", "bruce-drawio")


def _read_skill_file(filename: str) -> str:
    path = os.path.join(SKILL_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def generate_diagram_plan(req: AIRequest) -> dict:
    provider = (req.provider or "").lower().strip()
    if not provider:
        raise ValueError("未配置模型厂商")
    if not req.model.strip():
        raise ValueError("未配置模型名称")
    if not req.api_key.strip() and provider not in ("ollama", "custom"):
        raise ValueError("API Key 为空")

    prompt = _build_prompt(req.prompt)
    raw_text = _call_provider(req, prompt)

    xml = _extract_drawio_xml(raw_text)
    if xml:
        return {"xml": xml, "provider": provider, "model": req.model, "direction": "TB"}

    plan = _parse_plan(raw_text)
    plan.setdefault("provider", provider)
    plan.setdefault("model", req.model)
    plan.setdefault("direction", "TB")
    if not isinstance(plan.get("items"), list) or not plan["items"]:
        plan["items"] = _fallback_items(req.prompt)
    return plan


def _build_prompt(user_prompt: str) -> str:
    skill_md = _read_skill_file("SKILL.md")
    best_practices = _read_skill_file(os.path.join("references", "best-practices.md"))

    skill_section = ""
    if skill_md:
        skill_section = f"\n\n## Skill 规则\n{skill_md}"
    if best_practices:
        skill_section += f"\n\n## XML 模板与布局规则\n{best_practices}"

    return (
        "你是一个专业的图表生成器。用户会描述想要的图表，你需要直接生成完整的 drawio XML。\n\n"
        "你必须让 AI 控制整张图的绘制：根据用户需求决定节点、关系、布局、分组、颜色和图表类型，而不是只输出简单列表。\n\n"
        "## 工作流程\n"
        "1. 理解用户需求，判断图表类型。支持类型包括：flowchart、architecture、uml-sequence、uml-class、er、mindmap、network\n"
        "2. 直接生成完整的 drawio XML\n"
        "3. 自检：确保所有 ID 唯一、坐标是 10 的倍数、节点不重叠、XML 格式正确\n"
        "4. 只输出 XML，不要解释\n\n"
        "## 类型要求\n"
        "- flowchart：使用开始/结束、处理、判断、输入输出，必须有清晰箭头流向\n"
        "- architecture：使用前端、网关、服务、缓存、数据库、部署分层\n"
        "- uml-sequence：使用参与者生命线和消息箭头表达调用顺序\n"
        "- uml-class：使用类/接口框，包含属性、方法、继承/依赖关系\n"
        "- er：使用实体、属性、主外键、1:N/N:M 关系\n"
        "- mindmap：中心主题在中间，分支向四周展开\n"
        "- network：客户端、交换/路由/网关、防火墙、服务器、数据库、监控等拓扑节点\n\n"
        "## 输出格式\n"
        "只输出完整的 drawio XML，以 <?xml 开头，以 </mxfile> 结尾。不要用代码块包裹，不要加任何解释文字。\n"
        f"{skill_section}\n\n"
        f"## 用户需求\n{user_prompt}"
    )


def _extract_drawio_xml(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"(<\?xml[\s\S]*?</mxfile>)", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"(<mxfile[\s\S]*?</mxfile>)", text)
    if match:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + match.group(1).strip()
    return ""


def _call_provider(req: AIRequest, prompt: str) -> str:
    provider = (req.provider or "").lower().strip()
    if provider == "gemini":
        return _call_gemini(req, prompt)
    if provider == "anthropic":
        return _call_anthropic(req, prompt)
    return _call_openai_compatible(req, prompt)


def _call_openai_compatible(req: AIRequest, prompt: str) -> str:
    provider_local = (req.provider or "").lower().strip()
    base_url = (req.base_url or "").rstrip("/")
    if not base_url and provider_local != "custom":
        base_url = "https://api.openai.com/v1"
    if not base_url and provider_local == "custom":
        raise ValueError("自定义厂商必须填写 API 地址")
    url = base_url + "/chat/completions"
    payload = {
        "model": req.model,
        "messages": [
            {"role": "system", "content": "你只输出 drawio XML，不要解释。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 8000,
    }
    data = _http_json(url, payload, req.api_key, req.auth_type)
    return _extract_text_from_openai(data)


def _call_anthropic(req: AIRequest, prompt: str) -> str:
    base_url = (req.base_url or "").rstrip("/") or "https://api.anthropic.com/v1"
    url = base_url + "/messages"
    payload = {
        "model": req.model,
        "max_tokens": 8000,
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
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8000},
    }
    data = _http_json(url, payload, req.api_key, req.auth_type, gemini=True)
    return _extract_text_from_gemini(data)


def _http_json(url: str, payload: dict, api_key: str, auth_type: str, anthropic: bool = False, gemini: bool = False) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if anthropic:
        if auth_type == "oauth":
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif not gemini:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        if auth_type == "oauth" and exc.code in (400, 401, 403):
            raise ValueError("账号凭据错误或已失效，请重新授权后粘贴新的授权结果")
        if exc.code in (401, 403):
            raise ValueError("API Key 或账号凭据错误，请检查配置")
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
