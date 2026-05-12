import os
import json
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

import muganizer_backend as backend


backend.setup_storage()


# -----------------------------
# Optional .env loading
# -----------------------------

def load_env_file():
    possible_env_files = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
    ]

    for env_path in possible_env_files:
        if not env_path.exists():
            continue

        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and value and key not in os.environ:
                os.environ[key] = value


load_env_file()


# -----------------------------
# Chat command parsing
# -----------------------------

def extract_json_object(text):
    text = str(text or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else text


def parse_command_with_ai(user_message):
    """
    Uses OpenAI to convert a normal chat message into a structured Muganizer command.
    Falls back to rule-based parsing if OpenAI is unavailable.
    """
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return parse_command_fallback(user_message)

    try:
        client = OpenAI()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        prompt = f"""
You are the command parser for Muganizer, an AI-powered local music organizer.

Convert the user's message into one JSON command.

Supported actions:
1. help
2. upload_files
3. search_library
4. generate_playlist
5. open_muganizer_folder
6. show_recent_tracks
7. show_storage_locations
8. unknown

Return only valid JSON with these keys:
action, query, count, response_hint

Rules:
- action must be exactly one of the supported actions.
- query should contain the search or playlist prompt when relevant.
- count should be an integer. Default to 10 for search and 15 for playlists.
- response_hint should be a short friendly phrase explaining what you understood.
- If the user says "upload", "add songs", "import files", or "organize music", use upload_files.
- If the user says "find", "search", "show songs like", or asks for a vibe/mood, use search_library unless they clearly ask for a playlist.
- If the user says "playlist", "make me a mix", or "create a playlist", use generate_playlist.
- If the user says "open folder" or "open Muganizer", use open_muganizer_folder.
- If the user says "recent", "latest", or "what did I add", use show_recent_tracks.
- If the user asks where files are saved, use show_storage_locations.

User message:
{user_message}
"""
        response = client.responses.create(model=model, input=prompt)
        data = json.loads(extract_json_object(response.output_text))

        action = str(data.get("action", "unknown")).strip()
        query = str(data.get("query", "")).strip()

        try:
            count = int(data.get("count", 10))
        except Exception:
            count = 10

        return {
            "action": action,
            "query": query,
            "count": count,
            "response_hint": str(data.get("response_hint", "")).strip(),
        }

    except Exception:
        return parse_command_fallback(user_message)


def parse_command_fallback(user_message):
    """
    Simple keyword fallback. This keeps the chat app usable even if the API key fails.
    """
    text = user_message.lower().strip()

    if any(word in text for word in ["help", "what can you do", "commands"]):
        return {"action": "help", "query": "", "count": 10, "response_hint": "Showing help."}

    if any(word in text for word in ["upload", "add song", "add songs", "import", "organize", "mp3"]):
        return {"action": "upload_files", "query": "", "count": 10, "response_hint": "Starting upload."}

    if "playlist" in text or "mix" in text:
        count = extract_count(text, default=15)
        query = clean_prompt(text, ["make", "create", "generate", "playlist", "mix", "me", "a", "an", "with"])
        return {"action": "generate_playlist", "query": query or user_message, "count": count, "response_hint": "Creating playlist."}

    if any(word in text for word in ["find", "search", "show", "songs for", "songs like"]):
        count = extract_count(text, default=10)
        query = clean_prompt(text, ["find", "search", "show", "me", "songs", "for", "like"])
        return {"action": "search_library", "query": query or user_message, "count": count, "response_hint": "Searching library."}

    if "open" in text and "folder" in text:
        return {"action": "open_muganizer_folder", "query": "", "count": 10, "response_hint": "Opening folder."}

    if any(word in text for word in ["recent", "latest", "last added"]):
        count = extract_count(text, default=10)
        return {"action": "show_recent_tracks", "query": "", "count": count, "response_hint": "Showing recent tracks."}

    if any(phrase in text for phrase in ["where", "saved", "storage", "located"]):
        return {"action": "show_storage_locations", "query": "", "count": 10, "response_hint": "Showing storage locations."}

    return {"action": "unknown", "query": user_message, "count": 10, "response_hint": "I am not sure what command that is."}


def extract_count(text, default=10):
    match = re.search(r"\b(\d{1,2})\b", text)
    if not match:
        return default
    return max(1, min(50, int(match.group(1))))


def clean_prompt(text, remove_words):
    words = text.split()
    cleaned = [w for w in words if w not in set(remove_words) and not w.isdigit()]
    return " ".join(cleaned).strip()


# -----------------------------
# GUI
# -----------------------------

class MuganizerChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Muganizer Chat")
        self.root.geometry("900x680")

        self.pending_upload_files = []
        self.pending_upload_index = 0
        self.pending_album_var = None
        self.pending_metadata = None
        self.pending_cover_path = None

        self.build_layout()
        self.bot_intro()

    def build_layout(self):
        title = tk.Label(
            self.root,
            text="Muganizer Chat",
            font=("Arial", 24, "bold")
        )
        title.pack(pady=(14, 4))

        subtitle = tk.Label(
            self.root,
            text="Talk to your music organizer: search, make playlists, upload MP3s, and open storage.",
            font=("Arial", 10),
            fg="gray"
        )
        subtitle.pack(pady=(0, 8))

        self.chat = scrolledtext.ScrolledText(
            self.root,
            width=105,
            height=28,
            wrap=tk.WORD,
            state="disabled",
            font=("Consolas", 10)
        )
        self.chat.pack(padx=18, pady=8, fill="both", expand=True)

        input_frame = tk.Frame(self.root)
        input_frame.pack(fill="x", padx=18, pady=8)

        self.entry = tk.Entry(input_frame, font=("Arial", 12))
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda event: self.handle_user_message())

        send_button = tk.Button(input_frame, text="Send", width=12, command=self.handle_user_message)
        send_button.pack(side="right")

        quick_frame = tk.Frame(self.root)
        quick_frame.pack(fill="x", padx=18, pady=(0, 12))

        tk.Button(quick_frame, text="Upload MP3s", command=self.start_upload_files).pack(side="left", padx=4)
        tk.Button(quick_frame, text="Recent Tracks", command=lambda: self.run_command({"action": "show_recent_tracks", "query": "", "count": 10})).pack(side="left", padx=4)
        tk.Button(quick_frame, text="Open Folder", command=lambda: self.run_command({"action": "open_muganizer_folder", "query": "", "count": 10})).pack(side="left", padx=4)
        tk.Button(quick_frame, text="Help", command=lambda: self.run_command({"action": "help", "query": "", "count": 10})).pack(side="left", padx=4)

    def bot_intro(self):
        self.add_bot_message(
            "Hey, I’m Muganizer Chat. Try:\n"
            "• Upload some MP3s\n"
            "• Find late night driving songs\n"
            "• Make a 15 song gym playlist\n"
            "• Show recent tracks\n"
            "• Open the Muganizer folder"
        )

    def add_user_message(self, message):
        self.append_chat(f"You: {message}\n\n")

    def add_bot_message(self, message):
        self.append_chat(f"Muganizer: {message}\n\n")

    def append_chat(self, text):
        self.chat.configure(state="normal")
        self.chat.insert(tk.END, text)
        self.chat.configure(state="disabled")
        self.chat.see(tk.END)

    def handle_user_message(self):
        message = self.entry.get().strip()
        if not message:
            return

        self.entry.delete(0, tk.END)
        self.add_user_message(message)

        self.add_bot_message("Thinking...")
        self.root.after(50, lambda: self.process_message_threaded(message))

    def process_message_threaded(self, message):
        thread = threading.Thread(target=self.process_message, args=(message,), daemon=True)
        thread.start()

    def process_message(self, message):
        command = parse_command_with_ai(message)
        self.root.after(0, lambda: self.run_command(command))

    def run_command(self, command):
        action = command.get("action", "unknown")
        query = command.get("query", "")
        count = int(command.get("count", 10) or 10)

        if action == "help":
            self.show_help()
        elif action == "upload_files":
            self.start_upload_files()
        elif action == "search_library":
            self.search_library(query, count)
        elif action == "generate_playlist":
            self.generate_playlist(query, count)
        elif action == "open_muganizer_folder":
            self.open_muganizer_folder()
        elif action == "show_recent_tracks":
            self.show_recent_tracks(count)
        elif action == "show_storage_locations":
            self.show_storage_locations()
        else:
            self.add_bot_message(
                "I’m not sure how to do that yet. Try asking me to upload MP3s, search your library, make a playlist, show recent tracks, or open the folder."
            )

    # -----------------------------
    # Command actions
    # -----------------------------

    def show_help(self):
        self.add_bot_message(
            "Here are the commands I understand:\n"
            "• “Upload MP3s” — choose songs and organize them\n"
            "• “Find sad melodic rap” — semantic search your library\n"
            "• “Make a 12 song gym playlist” — export an .m3u playlist\n"
            "• “Show recent tracks” — list recently processed songs\n"
            "• “Open the Muganizer folder” — open your storage folder\n"
            "• “Where are my files saved?” — show storage locations"
        )

    def search_library(self, query, count):
        if not query:
            query = "music"

        try:
            results = backend.semantic_search_tracks(query, limit=count)
        except Exception as e:
            self.add_bot_message(f"Search failed: {type(e).__name__}: {e}")
            return

        if not results:
            self.add_bot_message("I couldn’t find any processed tracks yet. Upload and process some MP3s first.")
            return

        lines = [f"I found {len(results)} result(s) for: “{query}”\n"]
        for i, track in enumerate(results, start=1):
            title = track.get("title", "Unknown Title")
            artist = track.get("artist", "Unknown Artist")
            genre = track.get("genre", "Unknown")
            score = float(track.get("score", 0))
            description = track.get("description", "")
            lines.append(f"{i}. {title} — {artist} ({score:.0%} match)")
            lines.append(f"   Genre: {genre}")
            if description:
                lines.append(f"   {description}")

        self.add_bot_message("\n".join(lines))

    def generate_playlist(self, query, count):
        if not query:
            query = "AI playlist"

        try:
            playlist_path, matches = backend.generate_playlist(query, limit=count)
        except Exception as e:
            self.add_bot_message(f"Playlist generation failed: {type(e).__name__}: {e}")
            return

        if not matches:
            self.add_bot_message("I created the playlist file, but there were no matching songs yet. Upload/process some MP3s first.")
            return

        lines = [
            f"Created playlist:\n{playlist_path}\n",
            f"Prompt: “{query}”",
            f"Songs included: {len(matches)}\n"
        ]

        for i, track in enumerate(matches, start=1):
            lines.append(f"{i}. {track.get('title', 'Unknown Title')} — {track.get('artist', 'Unknown Artist')}")

        self.add_bot_message("\n".join(lines))

    def open_muganizer_folder(self):
        try:
            backend.MUGANIZER_ROOT.mkdir(parents=True, exist_ok=True)
            backend.open_file(backend.MUGANIZER_ROOT)
            self.add_bot_message("Opened the Muganizer folder.")
        except Exception as e:
            self.add_bot_message(f"I couldn’t open the folder: {type(e).__name__}: {e}")

    def show_recent_tracks(self, count=10):
        try:
            tracks = backend.get_all_tracks()[:count]
        except Exception as e:
            self.add_bot_message(f"Could not read recent tracks: {type(e).__name__}: {e}")
            return

        if not tracks:
            self.add_bot_message("No tracks are in the Muganizer database yet.")
            return

        lines = [f"Here are your {len(tracks)} most recent track(s):\n"]
        for i, track in enumerate(tracks, start=1):
            lines.append(f"{i}. {track.get('title', 'Unknown Title')} — {track.get('artist', 'Unknown Artist')}")
            lines.append(f"   Album: {track.get('album', 'Unknown')}")
            lines.append(f"   Genre: {track.get('genre', 'Unknown')}")

        self.add_bot_message("\n".join(lines))

    def show_storage_locations(self):
        self.add_bot_message(
            "Muganizer storage locations:\n"
            f"Main folder: {backend.MUGANIZER_ROOT}\n"
            f"Local files: {backend.LOCAL_FILES_ROOT}\n"
            f"Album covers: {backend.ALBUM_COVERS_ROOT}\n"
            f"Artist covers: {backend.ARTIST_COVERS_ROOT}\n"
            f"Playlists: {backend.PLAYLISTS_ROOT}"
        )

    # -----------------------------
    # Upload flow
    # -----------------------------

    def start_upload_files(self):
        files = filedialog.askopenfilenames(
            title="Select MP3 file(s)",
            filetypes=[("MP3 Files", "*.mp3")]
        )

        if not files:
            self.add_bot_message("No files selected.")
            return

        self.pending_upload_files = [Path(f) for f in files]
        self.pending_upload_index = 0

        self.add_bot_message(f"Selected {len(self.pending_upload_files)} MP3 file(s). I’ll process them one at a time.")
        self.process_next_upload()

    def process_next_upload(self):
        if self.pending_upload_index >= len(self.pending_upload_files):
            self.add_bot_message("Upload processing complete.")
            return

        file_path = self.pending_upload_files[self.pending_upload_index]

        self.add_bot_message(f"Analyzing: {file_path.name}")

        try:
            guessed = backend.guess_metadata_with_ai(file_path.name)
        except Exception as e:
            self.add_bot_message(f"Metadata analysis failed for {file_path.name}: {type(e).__name__}: {e}")
            self.pending_upload_index += 1
            self.process_next_upload()
            return

        self.pending_metadata = {
            "title": guessed.get("title", file_path.stem),
            "artist": guessed.get("artist", ""),
            "features": guessed.get("features", []),
            "genre": guessed.get("genre", "Unknown"),
            "mood_tags": guessed.get("mood_tags", []),
            "description": guessed.get("description", ""),
            "confidence": guessed.get("confidence", 0.5),
            "reasoning_summary": guessed.get("reasoning_summary", ""),
            "spotify_album": guessed.get("spotify_album", ""),
            "spotify_release_date": guessed.get("spotify_release_date", ""),
            "spotify_cover_url": guessed.get("spotify_cover_url", ""),
            "spotify_url": guessed.get("spotify_url", ""),
            "spotify_match_title": guessed.get("spotify_match_title", ""),
            "spotify_match_artist": guessed.get("spotify_match_artist", "")
        }

        suggested_album = guessed.get("spotify_album", "") or ""
        if not suggested_album:
            suggested_album = "Unreleased"

        self.ask_album_for_pending_file(file_path, suggested_album)

    def ask_album_for_pending_file(self, file_path, suggested_album):
        popup = tk.Toplevel(self.root)
        popup.title("Confirm Upload Metadata")
        popup.geometry("620x430")
        popup.grab_set()

        metadata = self.pending_metadata

        tk.Label(popup, text="Confirm Upload", font=("Arial", 18, "bold")).pack(pady=12)
        tk.Label(popup, text=f"File: {file_path.name}", wraplength=560).pack(pady=4)

        info = tk.Frame(popup, relief="groove", bd=2, padx=12, pady=8)
        info.pack(fill="x", padx=18, pady=8)

        tk.Label(info, text=f"Title: {metadata.get('title', '')}", anchor="w").pack(anchor="w")
        tk.Label(info, text=f"Artist: {metadata.get('artist', '')}", anchor="w").pack(anchor="w")
        tk.Label(info, text=f"Features: {', '.join(metadata.get('features', [])) if metadata.get('features') else 'None'}", anchor="w").pack(anchor="w")
        tk.Label(info, text=f"Genre: {metadata.get('genre', 'Unknown')}", anchor="w").pack(anchor="w")
        tk.Label(info, text=f"Mood: {', '.join(metadata.get('mood_tags', [])) if metadata.get('mood_tags') else 'Unknown'}", anchor="w").pack(anchor="w")
        tk.Label(info, text=f"Description: {metadata.get('description', '')}", anchor="w", wraplength=550).pack(anchor="w")

        album_frame = tk.Frame(popup)
        album_frame.pack(pady=12)

        tk.Label(album_frame, text="Album:").pack(side="left", padx=5)
        album_entry = tk.Entry(album_frame, width=45)
        album_entry.insert(0, suggested_album)
        album_entry.pack(side="left", padx=5)

        button_frame = tk.Frame(popup)
        button_frame.pack(pady=14)

        def process_file():
            album = album_entry.get().strip()
            if not album:
                messagebox.showwarning("Missing Album", "Album is required.")
                return

            popup.destroy()
            self.finalize_pending_upload(album)

        def skip_file():
            popup.destroy()
            self.add_bot_message(f"Skipped {file_path.name}.")
            self.pending_upload_index += 1
            self.process_next_upload()

        tk.Button(button_frame, text="Process File", width=18, command=process_file).pack(side="left", padx=8)
        tk.Button(button_frame, text="Skip", width=18, command=skip_file).pack(side="left", padx=8)

    def finalize_pending_upload(self, album):
        file_path = self.pending_upload_files[self.pending_upload_index]
        metadata = dict(self.pending_metadata or {})
        metadata["album"] = album

        try:
            # Apply feature formatting using the existing backend helper.
            # If features is empty, this does nothing.
            title, artist = backend.format_features(
                metadata.get("title", ""),
                metadata.get("artist", ""),
                metadata.get("features", [])
            )
            metadata["title"] = title
            metadata["artist"] = artist

            if backend.normalize_text(album) != "unreleased":
                backend.create_local_album_folder(metadata["artist"], album)
            else:
                backend.create_local_artist_folder(metadata["artist"])

            # Cover selection is simplified in chat mode.
            cover_path = backend.select_cover_final(metadata["artist"], album)

            ai_duplicates = backend.find_ai_duplicates(metadata)
            normal_duplicates = backend.find_duplicates(metadata)

            if ai_duplicates or normal_duplicates:
                self.add_bot_message(
                    f"Possible duplicate detected for {metadata.get('title')} — {metadata.get('artist')}. "
                    "For now, chat mode will keep both by adding a numbered filename if needed."
                )

            backend.tag_mp3(file_path, metadata, cover_path)
            final_path = backend.organize_file(file_path, metadata)
            backend.save_track_to_database(metadata, final_path)
            backend.log_action(
                metadata.get("title", ""),
                metadata.get("artist", ""),
                metadata.get("album", ""),
                final_path,
                "Tagged and organized via chat"
            )

            self.add_bot_message(
                f"Processed:\n"
                f"{metadata.get('title')} — {metadata.get('artist')}\n"
                f"Album: {metadata.get('album')}\n"
                f"Genre: {metadata.get('genre', 'Unknown')}\n"
                f"Saved to:\n{final_path}"
            )

        except Exception as e:
            self.add_bot_message(f"Failed to process {file_path.name}: {type(e).__name__}: {e}")

        self.pending_upload_index += 1
        self.process_next_upload()


def main():
    root = tk.Tk()
    app = MuganizerChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
