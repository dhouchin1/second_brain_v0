import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from processor import process_audio_file

VAULT_PATH = Path("/Users/dhouchin/Obsidian/SecondBrain")
AUDIO_PATH = VAULT_PATH / "audio"

class VaultHandler(FileSystemEventHandler):
    def on_created(self, event):
        path = Path(event.src_path)
        # Skip hidden/temp files (e.g., ._ or ~)
        name = path.name
        if name.startswith('.') or name.startswith('._') or name.endswith('~'):
            return
        if path.suffix.lower() in {".m4a", ".wav", ".mp3"}:
            print(f"New audio: {path.name} -- Triggering transcription...")
            process_audio_file(path)
        elif path.suffix == ".md":
            print(f"New note: {path.name} -- Index or process as needed.")

def watch_vault():
    event_handler = VaultHandler()
    observer = Observer()
    observer.schedule(event_handler, str(AUDIO_PATH), recursive=False)
    observer.schedule(event_handler, str(VAULT_PATH), recursive=False)
    observer.start()
    print("Watching vault for changes...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    watch_vault()
