from pathlib import Path
import subprocess
import time
from config import settings
from typing import Callable, Optional

# Optional Vosk (lightweight, offline ASR)
try:
    import vosk  # type: ignore
    _VOSK_AVAILABLE = True
except Exception:
    _VOSK_AVAILABLE = False


def _convert_to_wav_16k_mono(audio_path: Path) -> Path | None:
    """Convert source audio to 16kHz mono PCM WAV using ffmpeg."""
    wav_path = audio_path.with_suffix('.converted.wav')
    # Add CPU throttling to ffmpeg too
    ffmpeg_cmd = [
        "nice", "-n", "19",  # Lower priority for ffmpeg too
        "ffmpeg", "-y", "-i", str(audio_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)
    ]
    try:
        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=60)  # 1 minute timeout
        if result.returncode != 0:
            print("ffmpeg failed to convert audio:", result.stderr)
            return None
        return wav_path
    except subprocess.TimeoutExpired:
        print("ffmpeg conversion timed out")
        return None


def _transcribe_with_whisper(wav_path: Path, timeout_seconds: int = 180) -> str:
    out_txt_path = wav_path.with_suffix(wav_path.suffix + '.txt')
    
    # Use the configured model
    model_to_use = settings.whisper_model_path
    
    print(f"Using model: {model_to_use} (size: {model_to_use.stat().st_size // 1024}KB)")
    
    # Multi-layer CPU throttling to prevent machine slowdown
    whisper_cmd = [
        "nice", "-n", "19",  # Lower CPU priority
        str(settings.whisper_cpp_path),
        "-m", str(model_to_use),
        "-f", str(wav_path),
        "-otxt",
        "-t", "1",      # Force single thread
        "-ng",          # Disable GPU
        "--no-prints",  # Reduce output overhead
    ]
    
    print(f"Running whisper (throttled): {' '.join(whisper_cmd)}")
    try:
        # Use lower-level process controls for better throttling
        import os
        process = subprocess.Popen(
            whisper_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid  # Create new process group
        )
        
        # Wait with timeout
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        
        if process.returncode != 0:
            print(f"Whisper failed with return code {process.returncode}: {stderr}")
            
    except subprocess.TimeoutExpired:
        print("Whisper transcription timed out - killing process")
        try:
            os.killpg(os.getpgid(process.pid), 9)  # Kill entire process group
        except:
            pass
    for _ in range(50):
        if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
            break
        time.sleep(0.1)
    if out_txt_path.exists() and out_txt_path.stat().st_size > 0:
        return out_txt_path.read_text().strip()
    return ""


def _get_wav_duration_seconds(wav_path: Path) -> float:
    try:
        import wave
        with wave.open(str(wav_path), 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 16000
            return frames / float(rate) if rate else 0.0
    except Exception:
        return 0.0


def _split_wav_by_duration(wav_path: Path, segment_seconds: int = 600) -> list[Path]:
    """Split a PCM WAV into segments by duration using Python wave I/O.

    Creates files alongside the original with suffix .partN.wav and returns their paths.
    """
    import wave
    parts: list[Path] = []
    try:
        with wave.open(str(wav_path), 'rb') as wf:
            params = wf.getparams()
            rate = wf.getframerate() or 16000
            chunk_frames = int(segment_seconds * rate)
            total_frames = wf.getnframes()
            idx = 0
            while wf.tell() < total_frames:
                frames = wf.readframes(chunk_frames)
                if not frames:
                    break
                out_path = wav_path.with_suffix(f".part{idx}.wav")
                with wave.open(str(out_path), 'wb') as out:
                    out.setparams(params)
                    out.writeframes(frames)
                parts.append(out_path)
                idx += 1
    except Exception as e:
        print(f"WAV split failed, processing as single file: {e}")
        return []
    return parts


def _transcribe_with_vosk(wav_path: Path) -> str:
    """Transcribe using Vosk if available. Requires a Vosk model directory.

    Vosk is CPU-only and lightweight; set settings.vosk_model_path via .env.
    """
    if not _VOSK_AVAILABLE:
        return ""
    model_path = settings.vosk_model_path
    try:
        if not model_path or not Path(model_path).exists():
            print("Vosk model not found. Set VOSK_MODEL_PATH in your environment.")
            return ""
        import wave
        import json as _json
        wf = wave.open(str(wav_path), "rb")
        if wf.getnchannels() != 1 or wf.getframerate() != 16000:
            # Should not happen; we convert above
            pass
        rec = vosk.KaldiRecognizer(vosk.Model(str(model_path)), 16000)
        rec.SetWords(False)
        transcript_chunks = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = _json.loads(rec.Result())
                if res.get("text"):
                    transcript_chunks.append(res["text"])
        final = _json.loads(rec.FinalResult()).get("text", "")
        if final:
            transcript_chunks.append(final)
        return " ".join([t.strip() for t in transcript_chunks if t.strip()]).strip()
    except Exception as e:
        print("Vosk transcription error:", e)
        return ""


def transcribe_audio(audio_path: Path, progress_cb: Optional[Callable[[int, int], None]] = None):
    """Convert audio to WAV and transcribe using configured backend.

    Returns (transcript_text, converted_wav_filename)
    """
    # Quick disable for testing - set DISABLE_TRANSCRIPTION=1 to skip
    import os
    if os.getenv('DISABLE_TRANSCRIPTION', '0') == '1':
        print("Transcription disabled via DISABLE_TRANSCRIPTION=1")
        wav_path = _convert_to_wav_16k_mono(audio_path) 
        return "[Transcription disabled for testing]", wav_path.name if wav_path else None
    
    wav_path = _convert_to_wav_16k_mono(audio_path)
    if not wav_path:
        return "", None

    backend = (getattr(settings, 'transcriber', 'whisper') or 'whisper').lower()
    text = ""
    if backend == 'vosk':
        text = _transcribe_with_vosk(wav_path)
        if not text:
            # Fallback to whisper if available
            backend = 'whisper'
    if backend == 'whisper':
        # For long files, split into segments to avoid timeouts and memory spikes
        max_seg = int(getattr(settings, 'transcription_segment_seconds', 600) or 600)
        duration = _get_wav_duration_seconds(wav_path)
        if duration > max_seg + 30:
            parts = _split_wav_by_duration(wav_path, max_seg)
            if parts:
                seg_texts = []
                for i, part in enumerate(parts):
                    # Allow longer timeout per segment if needed
                    timeout = 600 if max_seg >= 600 else 300
                    seg_txt = _transcribe_with_whisper(part, timeout_seconds=timeout)
                    seg_texts.append(seg_txt)
                    if progress_cb:
                        try:
                            progress_cb(i + 1, len(parts))
                        except Exception:
                            pass
                    try:
                        part.unlink(missing_ok=True)
                    except Exception:
                        pass
                text = "\n\n".join(t for t in seg_texts if t)
            else:
                # Fallback single-run with extended timeout
                text = _transcribe_with_whisper(wav_path, timeout_seconds=600)
        else:
            text = _transcribe_with_whisper(wav_path)

    return text, wav_path.name
