import requests
import json
from config import settings

def _ollama_options_dict():
    """Build an options dict for Ollama from settings, skipping Nones.

    Common useful keys: num_ctx, num_predict, temperature, top_p, num_gpu
    """
    opts = {}
    if getattr(settings, 'ollama_num_ctx', None) is not None:
        opts['num_ctx'] = int(settings.ollama_num_ctx)
    if getattr(settings, 'ollama_num_predict', None) is not None:
        opts['num_predict'] = int(settings.ollama_num_predict)
    if getattr(settings, 'ollama_temperature', None) is not None:
        opts['temperature'] = float(settings.ollama_temperature)
    if getattr(settings, 'ollama_top_p', None) is not None:
        opts['top_p'] = float(settings.ollama_top_p)
    if getattr(settings, 'ollama_num_gpu', None) is not None:
        opts['num_gpu'] = int(settings.ollama_num_gpu)
    return opts


def ollama_summarize(text, prompt=None):
    """Return summary, tags and actions extracted from *text* using Ollama."""
    print(f"[ollama_summarize] Called with text: {repr(text[:200])}")
    if not text or not text.strip():
        return {"summary": "", "tags": [], "actions": []}

    system_prompt = (
        prompt
        or "Summarize and extract tags and action items from this transcript of conversation snippet or note."
    )
    data = {
        "model": settings.ollama_model,
        "prompt": (
            f"{system_prompt}\n\n{text}\n\n"
            "Respond in JSON with keys 'summary', 'tags', and 'actions'."
        ),
        "options": _ollama_options_dict() or None,
    }
    try:
        resp = requests.post(settings.ollama_api_url, json=data, stream=True, timeout=60)
        output = ""
        for line in resp.iter_lines():
            if line:
                try:
                    obj = json.loads(line.decode("utf-8"))
                    if "response" in obj:
                        output += obj["response"]
                except Exception as e:
                    print("Ollama stream parse error:", e, line)
        output = output.strip()
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            print("Ollama JSON decode failed, returning raw text")
            return {"summary": output, "tags": [], "actions": []}

        summary = parsed.get("summary", "").strip()
        tags = parsed.get("tags", []) or []
        actions = parsed.get("actions", []) or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        if isinstance(actions, str):
            actions = [a.strip() for a in actions.splitlines() if a.strip()]
        result = {"summary": summary, "tags": tags, "actions": actions}
        print(f"[ollama_summarize] Returning: {result}")
        return result
    except Exception as e:
        print("Ollama exception:", e)
    return {"summary": "", "tags": [], "actions": []}


def ollama_generate_title(text):
    if not text or not text.strip():
        return "Untitled Note"
    prompt = (
        "Generate a concise, descriptive title (max 10 words) for the following note or meeting transcript. "
        "Avoid generic phrases like 'Meeting Transcript' or 'Recording.' "
        "Only respond with the title, no extra commentary.\n\n"
        f"{text}\n\nTitle:"
    )
    try:
        resp = requests.post(
            settings.ollama_api_url,
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": True,
                "options": _ollama_options_dict() or None,
            },
            timeout=30,
        )
        title = ""
        for line in resp.iter_lines():
            if line:
                obj = json.loads(line.decode("utf-8"))
                if "response" in obj:
                    title += obj["response"]
        return title.strip().strip('"') or "Untitled Note"
    except Exception as e:
        print("Ollama title exception:", e)
        return "Untitled Note"
