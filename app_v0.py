from fastapi import FastAPI, UploadFile, File, Query
from pydantic import BaseModel
from markdown_writer import save_markdown, log_project_note
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import re

app = FastAPI() # FastAPI app instance must be declared before any @app decorators!

# Point path to your Obsidian vault directory
VAULT_PATH = Path("/Users/dhouchin/Obsidian/SecondBrain")
AUDIO_PATH = VAULT_PATH / "audio"
AUDIO_PATH.mkdir(exist_ok=True, parents=True)

WHISPER_CPP_PATH = "/Users/dhouchin/second_brain/whisper.cpp/build/bin"  # Update this path if your whisper.cpp folder is elsewhere
WHISPER_MODEL = "/Users/dhouchin/second_brain/whisper.cpp/models/ggml-base.en.bin"

def safe_filename(filename: str) -> str:
    # Lowercase, replace spaces with underscores, keep only safe chars
    name = filename.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_\-\.]", "", name)

class NoteIn(BaseModel):
    title: str
    content: str

@app.post("/note")
async def create_note(note: NoteIn):
    dt = datetime.now().strftime("%Y-%m-%d-%H%M")
    filename = f"{dt}-{note.title.replace(' ', '_')}.md"
    save_markdown(note.title, note.content, filename)
    return {"status": "ok", "filename": filename}


@app.post("/audio")
async def upload_audio(file: UploadFile = File(...)):
    dt = datetime.now().strftime("%Y-%m-%d-%H%M")
    # Replace spaces and special chars for Obsidian compatibility
    safe_filename = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", file.filename)
    audio_filename = f"{dt}-{safe_filename}"
    audio_filepath = AUDIO_PATH / audio_filename
    with audio_filepath.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    note_title = audio_filename
    note_content = (
        f"**Audio file saved.**\n\n![[audio/{audio_filename}]]\n\n#needs-transcription"
    )
    filename = f"{dt}-{note_title}.md"
    save_markdown(note_title, note_content, filename)
    log_project_note(f"Audio file uploaded: {audio_filename} and note created: {filename}")
    return {
        "status": "ok",
        "filename": filename,
        "audio_file": str(audio_filepath),
    }

@app.post("/transcribe")
async def transcribe_audio(filename: str = Query(...)):
    audio_filepath = AUDIO_PATH / filename
    transcript = transcribe_with_whisper(audio_filepath)
    md_name = f"{audio_filepath.stem}.md"
    md_path = VAULT_PATH / md_name
    if md_path.exists():
        content = md_path.read_text()
        content = content.replace("#needs-transcription", "")
        updated = content + f"\n\n**Transcription:**\n{transcript}\n#transcribed"
        md_path.write_text(updated)
        log_project_note(f"Transcribed audio file: {filename}, updated note: {md_name}")
        return {"status": "ok", "filename": md_name, "transcript": transcript}
    else:
        save_markdown(audio_filepath.stem, f"**Transcription:**\n{transcript}\n#transcribed", md_name)
        log_project_note(f"Transcribed audio file: {filename}, created new note: {md_name}")
        return {"status": "ok", "filename": md_name, "transcript": transcript}

def convert_to_wav(audio_path: Path) -> Path:
    wav_path = audio_path.with_suffix('.wav')
    if wav_path.exists():
        print(f"WAV version already exists: {wav_path}")
        return wav_path
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(audio_path), str(wav_path)
    ], capture_output=True, text=True)
    print("ffmpeg stdout:", result.stdout)
    print("ffmpeg stderr:", result.stderr)
    if wav_path.exists():
        return wav_path
    else:
        raise RuntimeError(f"Failed to convert {audio_path} to WAV. ffmpeg output:\n{result.stderr}")

def transcribe_with_whisper(audio_path: Path) -> str:
    # Convert if needed
    if audio_path.suffix.lower() not in {'.wav', '.mp3', '.flac', '.ogg'}:
        print(f"Converting {audio_path} to wav for Whisper.cpp...")
        audio_path = convert_to_wav(audio_path)
    out_txt_path = audio_path.with_suffix('.txt')
    cmd = [
        f"{WHISPER_CPP_PATH}/whisper-cli",
        "-m", WHISPER_MODEL,
        "-f", str(audio_path),
        "-otxt"
    ]
    print("Running Whisper.cpp command:", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )
    print("Whisper.cpp stdout:", result.stdout)
    print("Whisper.cpp stderr:", result.stderr)
    if result.returncode == 0 and out_txt_path.exists():
        return out_txt_path.read_text()
    else:
        return f"Transcription failed\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"