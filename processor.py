import time
import subprocess
from pathlib import Path

# Set these to match your setup
VAULT_PATH = Path("/Users/dhouchin/Obsidian/SecondBrain")
AUDIO_PATH = VAULT_PATH / "audio"
WHISPER_CPP_PATH = Path("/Users/dhouchin/second_brain/whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL = Path("/Users/dhouchin/second_brain/whisper.cpp/models/ggml-base.en.bin")

def convert_to_wav(input_path: Path) -> Path:
    if input_path.suffix.lower() == ".wav":
        return input_path
    wav_path = input_path.with_suffix('.converted.wav')
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)]
    for attempt in range(3):
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and wav_path.exists():
            return wav_path
        time.sleep(0.2)
    print("ffmpeg failed to convert audio:", res.stderr if 'res' in locals() else "(no stderr)")
    return input_path  # fallback

def transcribe_with_whisper(audio_path: Path) -> str:
    out_txt_path = audio_path.with_suffix(audio_path.suffix + '.txt')
    cmd = [
        str(WHISPER_CPP_PATH),
        "-m", str(WHISPER_MODEL),
        "-f", str(audio_path),
        "-otxt"
    ]
    last_err = ""
    for attempt in range(3):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            # wait briefly for writer flush
            for _ in range(20):
                if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
                    return out_txt_path.read_text()
                time.sleep(0.1)
        last_err = result.stderr
    print("Whisper failed:", last_err)
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
    md_file = VAULT_PATH / f"{note_id}.md"
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
