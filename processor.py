import subprocess
from pathlib import Path
import uuid
import shutil
import os
from config import settings

def convert_to_wav(input_path: Path) -> Path:
    if input_path.suffix.lower() == ".wav":
        return input_path
    wav_path = input_path.with_suffix('.wav')
    subprocess.run(["ffmpeg", "-y", "-i", str(input_path), str(wav_path)])
    return wav_path

def transcribe_with_whisper(audio_path: Path) -> str:
    out_txt_path = audio_path.with_suffix('.txt')
    cmd = [
        str(settings.whisper_cpp_path),
        "-m", str(settings.whisper_model_path),
        "-f", str(audio_path),
        "-otxt"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and out_txt_path.exists():
        return out_txt_path.read_text()
    else:
        print("Whisper failed:", result.stderr)
        return ""

def summarize_with_ollama(transcript: str, model="llama3") -> dict:
    import requests
    # Make sure your Ollama API is running locally
    url = "http://localhost:11434/api/generate"
    ###prompt = f"Summarize and extract action items from this meeting transcript:\n\n{transcript}\n\nRespond in JSON with 'summary', 'tags', 'actions'."
    prompt = (
    "You are an intelligent note-taking assistant. Analyze the following text, which could be a conversation, personal note, meeting, idea, or any other type of content."
    "\n\n"
    "Provide a concise summary of the main points or content. "
    "If there are clear action items (such as tasks, next steps, or follow-ups), list them. "
    "Also, suggest relevant tags for categorization. "
    "If any section (summary, action items, tags) is not applicable, leave it blank or an empty list."
    "\n\n"
    "Respond in JSON with keys: 'summary', 'tags', 'actions'."
    "\n\n"
    "Text:\n"
    f"{transcript}"
    "\n\n"
    "JSON:"
    )
    payload = {"model": model, "prompt": prompt, "stream": False}
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        try:
            import json
            return json.loads(response.json()["response"])
        except Exception as e:
            print("Ollama parse error:", e)
    return {"summary": "", "tags": [], "actions": []}

def create_note_from_audio(audio_path: Path, transcript: str, summary: str, tags=None, actions=None):
    tags = tags or []
    actions = actions or []
    note_id = audio_path.stem
    md_file = settings.vault_path / f"{note_id}.md"
    yaml_header = "---\n"
    yaml_header += f"audio: {audio_path.name}\n"
    yaml_header += f"tags: {tags}\n"
    yaml_header += f"actions: {actions}\n"
    yaml_header += f"summary: \"{summary}\"\n"
    yaml_header += "---\n\n"
    with open(md_file, "w") as f:
        f.write(yaml_header)
        f.write("# Transcript\n\n")
        f.write(transcript)
    print(f"Wrote note: {md_file}")

def process_audio_file(audio_file: Path):
    print(f"Processing {audio_file}")
    wav_file = convert_to_wav(audio_file)
    transcript = transcribe_with_whisper(wav_file)
    if not transcript:
        print("No transcript generated.")
        return
    ollama_result = summarize_with_ollama(transcript)
    create_note_from_audio(
        audio_file,
        transcript,
        ollama_result.get("summary", ""),
        ollama_result.get("tags", []),
        ollama_result.get("actions", []),
    )

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        process_audio_file(Path(sys.argv[1]))
    else:
        print("Usage: python processor.py <audio_file_path>")
