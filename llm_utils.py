import requests
import json
from config import settings

def ollama_summarize(text, prompt=None):
    print(f"[ollama_summarize] Called with text: {repr(text[:200])}")  # Print the first 200 chars
    if not text or not text.strip():
        return ""
    #system_prompt = prompt or "Summarize the following text as a helpful meeting note with main points and action items:"
    system_prompt = prompt or "Summarize and extract action items from this transcript of conversation snippet or note."
    data = {
        "model": settings.ollama_model,
        "prompt": f"{system_prompt}\n\n{text}\n\nSummary:"
    }
    try:
        resp = requests.post(settings.ollama_api_url, json=data, stream=True, timeout=120)
        summary = ""
        # Ollama streams JSON lines, so iterate each line and build up the response
        for line in resp.iter_lines():
            if line:
                try:
                    obj = json.loads(line.decode("utf-8"))
                    # Ollama returns incremental responses with 'response' key
                    if "response" in obj:
                        summary += obj["response"]
                except Exception as e:
                    print("Ollama stream parse error:", e, line)
                    print(f"[ollama_summarize] Returning summary: {repr(summary[:200])}")
        return summary.strip()
    except Exception as e:
        print("Ollama exception:", e)
    return ""

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
            settings.ollama_api_url, json={"model": settings.ollama_model, "prompt": prompt, "stream": True}, timeout=60
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
