from pathlib import Path
import subprocess
import time
from config import settings


def transcribe_audio(audio_path: Path):
    """Convert audio to WAV and run whisper.cpp transcription.

    Returns the transcript text and the converted WAV filename.
    """
    wav_path = audio_path.with_suffix('.converted.wav')
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)
    ]
    result = subprocess.run(ffmpeg_cmd, capture_output=True)
    if result.returncode != 0:
        print("ffmpeg failed to convert audio:", result.stderr)
        return "", None

    out_txt_path = wav_path.with_suffix(wav_path.suffix + '.txt')
    whisper_cmd = [
        str(settings.whisper_cpp_path),
        "-m", str(settings.whisper_model_path),
        "-f", str(wav_path),
        "-otxt",
    ]
    subprocess.run(whisper_cmd, capture_output=True, text=True)
    for _ in range(20):
        if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
            break
        time.sleep(0.1)
    if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
        content = out_txt_path.read_text().strip()
        return content, wav_path.name
    return "", wav_path.name
