import requests
import json

OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

def ollama_summarize(text, prompt=None):
    if not text or not text.strip():
        return ""
    system_prompt = prompt or "Summarize the following text as a helpful meeting note with main points and action items:"
    data = {
        "model": OLLAMA_MODEL,
        "prompt": f"{system_prompt}\n\n{text}\n\nSummary:"
    }
    try:
        resp = requests.post(OLLAMA_API_URL, json=data, stream=True, timeout=120)
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
        return summary.strip()
    except Exception as e:
        print("Ollama exception:", e)
    return ""
