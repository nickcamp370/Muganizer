import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    TkinterDnD = None

import muganizer_backend as backend


backend.setup_storage()

root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
root.title("Muganizer V6 AI")
root.geometry("900x680")

state = {}


def clear_window():
    for widget in root.winfo_children():
        widget.destroy()


def cancel_to_main_menu():
    state.clear()
    main_menu()


def add_navigation_buttons(back_command=None):
    if back_command is not None:
        tk.Button(root, text="Back", width=14, command=back_command).place(x=20, y=575)
    tk.Button(root, text="Cancel", width=14, command=cancel_to_main_menu).place(x=150, y=575)


def labeled_entry(parent, label, default="", width=45):
    frame = tk.Frame(parent)
    frame.pack(pady=5)
    tk.Label(frame, text=label, width=14, anchor="e").pack(side="left", padx=5)
    entry = tk.Entry(frame, width=width)
    entry.insert(0, default or "")
    entry.pack(side="left")
    return entry




def create_image_preview(parent, image_path, size=(180, 180)):
    try:
        image = Image.open(image_path).convert("RGB")
        image.thumbnail(size)
        photo = ImageTk.PhotoImage(image)
        label = tk.Label(parent, image=photo)
        label.image = photo
        label.pack(pady=8)
        return label
    except Exception:
        tk.Label(parent, text="Preview unavailable").pack(pady=8)
        return None


def parse_drop_files(raw):
    files = []
    current = ""
    inside = False
    for char in raw:
        if char == "{":
            inside = True
            current = ""
        elif char == "}":
            inside = False
            files.append(current)
            current = ""
        elif char == " " and not inside:
            if current:
                files.append(current)
                current = ""
        else:
            current += char
    if current:
        files.append(current)

    paths = []
    for f in files:
        p = Path(f)
        if p.is_dir():
            paths.extend(list(p.rglob("*.mp3")))
        elif p.suffix.lower() == ".mp3":
            paths.append(p)
    return paths


def handle_drop(event):
    files = parse_drop_files(event.data)
    if not files:
        messagebox.showwarning("No MP3s Found", "No MP3 files were found in what you dropped.")
        return
    state["files"] = files
    state["index"] = 0
    state["processed"] = 0
    if len(files) > 1:
        batch_mode_page()
    else:
        process_current_file(auto_mode=False)

def main_menu():
    clear_window()
    state.clear()

    tk.Label(root, text="Muganizer V6 AI + Spotify", font=("Arial", 24, "bold")).pack(pady=22)
    tk.Label(root, text="Spotify lookup, AI metadata, semantic search, playlists, cover embedding, and duplicate checking", font=("Arial", 10)).pack(pady=4)

    tk.Button(root, text="Upload 1 or more MP3s", width=38, height=2, command=upload_mp3_choice_page).pack(pady=8)
    tk.Button(root, text="Upload Cover Image", width=38, height=2, command=upload_cover_page).pack(pady=8)
    tk.Button(root, text="AI Semantic Search", width=38, height=2, command=semantic_search_page).pack(pady=8)
    tk.Button(root, text="AI Playlist Generator", width=38, height=2, command=playlist_generator_page).pack(pady=8)
    tk.Button(root, text="Manage Storage", width=38, height=2, command=manage_storage_menu).pack(pady=8)

    if DND_AVAILABLE:
        drop = tk.Label(root, text="Drag and drop MP3 files or folders here", relief="groove", width=55, height=5)
        drop.pack(pady=18)
        drop.drop_target_register(DND_FILES)
        drop.dnd_bind("<<Drop>>", handle_drop)
    else:
        tk.Label(root, text="Drag-and-drop disabled. Run: pip install tkinterdnd2", fg="gray").pack(pady=18)


def upload_mp3_choice_page():
    clear_window()
    tk.Label(root, text="Upload MP3s", font=("Arial", 20, "bold")).pack(pady=20)
    tk.Label(root, text="Choose files, choose a folder, or drag files onto the main menu.").pack(pady=5)

    tk.Button(root, text="Choose MP3 file(s)", width=34, height=2, command=lambda: choose_mp3_files("files")).pack(pady=8)
    tk.Button(root, text="Choose folder of MP3s", width=34, height=2, command=lambda: choose_mp3_files("folder")).pack(pady=8)
    add_navigation_buttons(back_command=main_menu)


def choose_mp3_files(mode):
    files = []
    if mode == "files":
        selected = filedialog.askopenfilenames(title="Select MP3 file(s)", filetypes=[("MP3 Files", "*.mp3")])
        files = [Path(f) for f in selected]
    else:
        folder = filedialog.askdirectory(title="Select folder containing MP3s")
        if folder:
            files = list(Path(folder).rglob("*.mp3"))

    if not files:
        return

    state["files"] = files
    state["index"] = 0
    state["processed"] = 0

    if len(files) > 1:
        batch_mode_page()
    else:
        process_current_file(auto_mode=False)


def batch_mode_page():
    clear_window()
    tk.Label(root, text="Batch Processing Mode", font=("Arial", 20, "bold")).pack(pady=20)
    tk.Label(root, text=f"{len(state['files'])} MP3 files selected.").pack(pady=5)

    tk.Button(root, text="Manual Mode - review each file", width=36, height=2, command=lambda: process_current_file(auto_mode=False)).pack(pady=8)
    tk.Button(root, text="Auto Mode - fewer prompts", width=36, height=2, command=lambda: process_current_file(auto_mode=True)).pack(pady=8)
    add_navigation_buttons(back_command=main_menu)


def process_current_file(auto_mode=False):
    files = state.get("files", [])
    idx = state.get("index", 0)

    if idx >= len(files):
        clear_window()
        tk.Label(root, text="Processing Complete", font=("Arial", 22, "bold")).pack(pady=30)
        tk.Label(root, text=f"Processed {state.get('processed', 0)} of {len(files)} files.").pack(pady=10)
        tk.Button(root, text="Return to Main Menu", width=30, command=main_menu).pack(pady=20)
        return

    file_path = files[idx]
    state["current_file"] = file_path
    state["auto_mode"] = auto_mode

    guessed = backend.guess_metadata_with_ai(file_path.name)

    guessed_title = guessed.get("title", file_path.stem)
    guessed_artist = guessed.get("artist", "")

    title = guessed_title
    artist = guessed_artist

    state["guess"] = {
        "title": title,
        "artist": artist,
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

    metadata_guess_page()


def metadata_guess_page():
    clear_window()
    file_path = state["current_file"]
    guess = state["guess"]

    tk.Label(root, text="Metadata Guess", font=("Arial", 20, "bold")).pack(pady=18)
    tk.Label(root, text=f"File: {file_path.name}", wraplength=620).pack(pady=4)

    box = tk.Frame(root, relief="groove", bd=2, padx=20, pady=15)
    box.pack(pady=18)

    tk.Label(box, text=f"Title: {guess['title']}", anchor="w", width=65).pack(anchor="w")
    tk.Label(box, text=f"Artist: {guess['artist']}", anchor="w", width=65).pack(anchor="w")
    tk.Label(box, text=f"Features: {', '.join(guess['features']) if guess['features'] else 'None'}", anchor="w", width=65).pack(anchor="w")
    tk.Label(box, text=f"Genre: {guess.get('genre', 'Unknown')}", anchor="w", width=65).pack(anchor="w")
    tk.Label(box, text=f"Mood: {', '.join(guess.get('mood_tags', [])) if guess.get('mood_tags') else 'Unknown'}", anchor="w", width=65).pack(anchor="w")
    tk.Label(box, text=f"Confidence: {float(guess.get('confidence', 0.5)):.0%}", anchor="w", width=65).pack(anchor="w")
    tk.Label(box, text=f"AI Description: {guess.get('description', '')}", anchor="w", width=65, wraplength=620).pack(anchor="w")
    if guess.get("spotify_album") or guess.get("spotify_url"):
        tk.Label(box, text=f"Spotify Album Suggestion: {guess.get('spotify_album', '') or 'None'}", anchor="w", width=65).pack(anchor="w")
        tk.Label(box, text=f"Spotify Match: {guess.get('spotify_match_title', '')} — {guess.get('spotify_match_artist', '')}", anchor="w", width=65).pack(anchor="w")

    tk.Label(root, text="Does this metadata look correct?").pack(pady=8)

    tk.Button(root, text="Yes, only ask me for the album", width=36, height=2, command=album_only_page).pack(pady=5)
    tk.Button(root, text="No, let me edit all metadata", width=36, height=2, command=edit_metadata_page).pack(pady=5)
    add_navigation_buttons(back_command=metadata_guess_page)


def edit_metadata_page():
    clear_window()
    guess = state["guess"]

    tk.Label(root, text="Edit Metadata", font=("Arial", 20, "bold")).pack(pady=15)

    form = tk.Frame(root)
    form.pack(pady=10)

    title_entry = labeled_entry(form, "Song Title:", guess["title"])
    artist_entry = labeled_entry(form, "Artist:", guess["artist"])
    features_entry = labeled_entry(form, "Features:", ", ".join(guess["features"]))

    tk.Label(root, text="Enter features separated by commas. Leave blank if there are none.").pack(pady=3)

    def save():
        title = title_entry.get().strip()
        artist = artist_entry.get().strip()
        features = [f.strip() for f in features_entry.get().split(",") if f.strip()]

        if not title or not artist:
            messagebox.showwarning("Missing Info", "Title and artist are required.")
            return

        state["metadata_base"] = {
            "title": title, "artist": artist, "features": features,
            "genre": guess.get("genre", "Unknown"),
            "mood_tags": guess.get("mood_tags", []),
            "description": guess.get("description", ""),
            "confidence": guess.get("confidence", 0.5),
            "reasoning_summary": guess.get("reasoning_summary", ""),
            "spotify_album": guess.get("spotify_album", ""),
            "spotify_release_date": guess.get("spotify_release_date", ""),
            "spotify_cover_url": guess.get("spotify_cover_url", ""),
            "spotify_url": guess.get("spotify_url", ""),
            "spotify_match_title": guess.get("spotify_match_title", ""),
            "spotify_match_artist": guess.get("spotify_match_artist", "")
        }
        album_entry_page()

    tk.Button(root, text="Continue to Album", width=28, height=2, command=save).pack(pady=18)
    add_navigation_buttons(back_command=metadata_guess_page)


def album_only_page():
    guess = state["guess"]
    if not guess.get("title") or not guess.get("artist"):
        edit_metadata_page()
        return

    state["metadata_base"] = {
        "title": guess["title"],
        "artist": guess["artist"],
        "features": guess["features"],
        "genre": guess.get("genre", "Unknown"),
        "mood_tags": guess.get("mood_tags", []),
        "description": guess.get("description", ""),
        "confidence": guess.get("confidence", 0.5),
        "reasoning_summary": guess.get("reasoning_summary", "")
    }
    album_entry_page()


def album_entry_page():
    clear_window()
    base = state["metadata_base"]
    existing = backend.list_existing_albums_for_artist(base["artist"])

    tk.Label(root, text="Album Selection", font=("Arial", 20, "bold")).pack(pady=15)
    tk.Label(root, text=f"Artist: {base['artist']}").pack(pady=3)
    if base.get("spotify_album"):
        tk.Label(root, text=f"Spotify suggested album: {base.get('spotify_album')}", fg="gray").pack(pady=2)

    form = tk.Frame(root)
    form.pack(pady=8)

    suggested_album = base.get("spotify_album", "")
    album_var = tk.StringVar(value=existing[0] if existing else suggested_album)
    if existing:
        tk.Label(form, text="Choose existing album or type a new one:").pack(pady=4)
        dropdown = tk.OptionMenu(form, album_var, *existing)
        dropdown.pack(pady=5)
    else:
        tk.Label(form, text="No existing albums found for this artist.").pack(pady=4)

    album_entry = labeled_entry(form, "Album:", album_var.get())
    if existing:
        def update_entry(*args):
            album_entry.delete(0, tk.END)
            album_entry.insert(0, album_var.get())
        album_var.trace_add("write", update_entry)

    def continue_cover():
        album = album_entry.get().strip()
        if not album:
            messagebox.showwarning("Missing Album", "Album is required.")
            return

        state["album"] = album
        title, artist = backend.format_features(base["title"], base["artist"], base["features"])
        state["metadata"] = {
            "title": title, "artist": artist, "album": album,
            "features": base.get("features", []),
            "genre": base.get("genre", "Unknown"),
            "mood_tags": base.get("mood_tags", []),
            "description": base.get("description", ""),
            "confidence": base.get("confidence", 0.5),
            "reasoning_summary": base.get("reasoning_summary", ""),
            "spotify_album": base.get("spotify_album", ""),
            "spotify_release_date": base.get("spotify_release_date", ""),
            "spotify_cover_url": base.get("spotify_cover_url", ""),
            "spotify_url": base.get("spotify_url", ""),
            "spotify_match_title": base.get("spotify_match_title", ""),
            "spotify_match_artist": base.get("spotify_match_artist", "")
        }

        if backend.normalize_text(album) != "unreleased":
            backend.create_local_album_folder(base["artist"], album)
        else:
            backend.create_local_artist_folder(base["artist"])

        cover_selection_page()

    tk.Button(root, text="Continue to Cover", width=28, height=2, command=continue_cover).pack(pady=18)
    add_navigation_buttons(back_command=metadata_guess_page)


def cover_selection_page():
    clear_window()
    metadata = state["metadata"]
    base_artist = state["metadata_base"]["artist"]
    album = state["album"]

    tk.Label(root, text="Cover Selection", font=("Arial", 20, "bold")).pack(pady=15)

    album_cover = backend.select_existing_album_cover(album)

    if backend.normalize_text(album) == "unreleased":
        artist_cover = backend.select_artist_cover(base_artist)
        if artist_cover:
            state["cover_path"] = artist_cover
            cover_confirm_page(f'Album is "Unreleased", so Muganizer selected an artist cover.', artist_cover)
            return

        tk.Label(root, text='Album is "Unreleased". Muganizer will not create or use an album cover folder.', wraplength=620).pack(pady=8)
        tk.Label(root, text="No artist cover was found. Please upload an artist cover or continue without one.", wraplength=620).pack(pady=8)

        tk.Button(root, text="Upload Artist Cover", width=30, height=2, command=lambda: upload_cover_for_current("artist", base_artist)).pack(pady=6)
        tk.Button(root, text="Continue Without Cover", width=30, height=2, command=lambda: set_cover_and_continue(None)).pack(pady=6)
        add_navigation_buttons(back_command=album_entry_page)
        return

    if album_cover:
        state["cover_path"] = album_cover
        cover_confirm_page("Album cover found and selected first.", album_cover)
        return

    tk.Label(root, text=f'No album cover was found for "{album}".', wraplength=620).pack(pady=8)
    tk.Label(root, text="Would you like to add an album cover now?", wraplength=620).pack(pady=8)

    tk.Button(root, text="Add Album Cover", width=30, height=2, command=lambda: upload_cover_for_current("album", album)).pack(pady=6)
    tk.Button(root, text="Use Artist Cover Instead", width=30, height=2, command=use_artist_cover_instead).pack(pady=6)
    tk.Button(root, text="Continue Without Cover", width=30, height=2, command=lambda: set_cover_and_continue(None)).pack(pady=6)
    add_navigation_buttons(back_command=album_entry_page)


def cover_confirm_page(message, cover_path):
    clear_window()
    tk.Label(root, text="Cover Selected", font=("Arial", 20, "bold")).pack(pady=15)
    tk.Label(root, text=message, wraplength=650).pack(pady=5)
    tk.Label(root, text=str(cover_path), wraplength=650).pack(pady=4)
    create_image_preview(root, cover_path, size=(210, 210))

    tk.Button(root, text="Continue", width=28, height=2, command=confirm_file_page).pack(pady=12)
    add_navigation_buttons(back_command=cover_selection_page)


def upload_cover_for_current(category, folder_name):
    uploaded = filedialog.askopenfilename(title="Select cover image", filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
    if not uploaded:
        return
    state["pending_cover_upload"] = {"path": uploaded, "category": category, "folder_name": folder_name, "return_to": "mp3"}
    preview_new_cover_page()


def preview_new_cover_page():
    clear_window()
    info = state["pending_cover_upload"]
    tk.Label(root, text="Cover Preview", font=("Arial", 20, "bold")).pack(pady=15)
    tk.Label(root, text=f"Save as {info['category']} cover for: {info['folder_name']}", wraplength=650).pack(pady=5)
    create_image_preview(root, info["path"], size=(240, 240))

    def save_cover():
        saved = backend.save_cover_image(info["path"], category=info["category"], folder_name=info["folder_name"])
        state.pop("pending_cover_upload", None)
        if info.get("return_to") == "mp3":
            set_cover_and_continue(saved)
        else:
            messagebox.showinfo("Saved", f"Cover saved:\n{saved}")
            main_menu()

    tk.Button(root, text="Save This Cover", width=28, height=2, command=save_cover).pack(pady=10)
    add_navigation_buttons(back_command=cover_selection_page if info.get("return_to") == "mp3" else upload_cover_page)


def use_artist_cover_instead():
    artist = state["metadata_base"]["artist"]
    artist_cover = backend.select_artist_cover(artist)

    if artist_cover:
        set_cover_and_continue(artist_cover)
    else:
        clear_window()
        tk.Label(root, text="No Artist Cover Found", font=("Arial", 20, "bold")).pack(pady=15)
        tk.Label(root, text="There is no artist cover available. Upload one or continue without a cover.", wraplength=620).pack(pady=8)
        tk.Button(root, text="Upload Artist Cover", width=30, height=2, command=lambda: upload_cover_for_current("artist", artist)).pack(pady=6)
        tk.Button(root, text="Continue Without Cover", width=30, height=2, command=lambda: set_cover_and_continue(None)).pack(pady=6)
        add_navigation_buttons(back_command=album_entry_page)


def set_cover_and_continue(cover_path):
    state["cover_path"] = cover_path
    confirm_file_page()


def confirm_file_page():
    clear_window()
    metadata = state["metadata"]
    cover_path = state.get("cover_path")
    preview_path = backend.get_destination_path(metadata)

    tk.Label(root, text="Confirm File", font=("Arial", 20, "bold")).pack(pady=15)

    box = tk.Frame(root, relief="groove", bd=2, padx=18, pady=12)
    box.pack(pady=10)

    tk.Label(box, text=f"Title: {metadata['title']}", anchor="w", width=70).pack(anchor="w")
    tk.Label(box, text=f"Artist: {metadata['artist']}", anchor="w", width=70).pack(anchor="w")
    tk.Label(box, text=f"Album: {metadata['album']}", anchor="w", width=70).pack(anchor="w")
    tk.Label(box, text=f"Genre: {metadata.get('genre', 'Unknown')}", anchor="w", width=70).pack(anchor="w")
    tk.Label(box, text=f"Mood: {', '.join(metadata.get('mood_tags', [])) if metadata.get('mood_tags') else 'Unknown'}", anchor="w", width=70).pack(anchor="w")
    tk.Label(box, text=f"Cover: {cover_path.name if cover_path else 'None'}", anchor="w", width=70).pack(anchor="w")
    tk.Label(box, text=f"Destination: {preview_path}", anchor="w", width=70, wraplength=620).pack(anchor="w")

    if cover_path:
        create_image_preview(root, cover_path, size=(130, 130))

    tk.Button(root, text="Process This File", width=28, height=2, command=duplicate_check_page).pack(pady=10)
    add_navigation_buttons(back_command=cover_selection_page)


def duplicate_check_page():
    metadata = state["metadata"]
    ai_duplicates = backend.find_ai_duplicates(metadata)
    if ai_duplicates:
        state["duplicate_ai"] = ai_duplicates[0]
        state["duplicate"] = Path(ai_duplicates[0]["file_path"])
        duplicate_page()
        return

    duplicates = backend.find_duplicates(metadata)
    if duplicates:
        state["duplicate"] = duplicates[0]
        duplicate_page()
    else:
        finalize_current_file()


def duplicate_page():
    clear_window()
    existing = state["duplicate"]

    tk.Label(root, text="Duplicate Found", font=("Arial", 20, "bold")).pack(pady=15)
    tk.Label(root, text=str(existing), wraplength=620).pack(pady=8)
    if state.get("duplicate_ai"):
        d = state["duplicate_ai"]
        tk.Label(root, text=f"AI Similarity: {float(d.get('duplicate_score', 0)):.0%}", wraplength=620).pack(pady=3)
        tk.Label(root, text=f"Reason: {d.get('duplicate_reason', 'Similar metadata and description')}", wraplength=620).pack(pady=3)

    tk.Button(root, text="Open Existing File to Listen", width=34, height=2, command=lambda: backend.open_file(existing)).pack(pady=5)
    tk.Button(root, text="Replace Existing File", width=34, height=2, command=replace_duplicate).pack(pady=5)
    tk.Button(root, text="Keep Both", width=34, height=2, command=keep_both_page).pack(pady=5)
    tk.Button(root, text="Skip This File", width=34, height=2, command=cancel_current_file).pack(pady=5)
    add_navigation_buttons(back_command=confirm_file_page)


def replace_duplicate():
    final_path = backend.replace_existing_file(state["current_file"], state["duplicate"])
    backend.tag_mp3(final_path, state["metadata"], state.get("cover_path"))
    backend.save_track_to_database(state["metadata"], final_path)
    backend.log_action(state["metadata"]["title"], state["metadata"]["artist"], state["metadata"]["album"], final_path, "Replaced duplicate")
    advance_to_next_file(True)


def keep_both_page():
    clear_window()
    tk.Label(root, text="Keep Both", font=("Arial", 20, "bold")).pack(pady=15)
    tk.Label(root, text="Which file should be renamed?").pack(pady=5)

    tk.Button(root, text="Rename New File", width=30, height=2, command=rename_new_file_page).pack(pady=6)
    tk.Button(root, text="Rename Existing File", width=30, height=2, command=rename_existing_file_page).pack(pady=6)
    add_navigation_buttons(back_command=duplicate_page)


def rename_new_file_page():
    clear_window()
    tk.Label(root, text="Rename New File", font=("Arial", 20, "bold")).pack(pady=15)
    entry = labeled_entry(root, "New Title:", state["metadata"]["title"])

    def save():
        new_title = entry.get().strip()
        if not new_title:
            messagebox.showwarning("Missing Title", "New title is required.")
            return
        state["metadata"]["title"] = new_title
        finalize_current_file()

    tk.Button(root, text="Save and Process", width=28, height=2, command=save).pack(pady=18)
    add_navigation_buttons(back_command=duplicate_page)


def rename_existing_file_page():
    clear_window()
    tk.Label(root, text="Rename Existing File", font=("Arial", 20, "bold")).pack(pady=15)
    entry = labeled_entry(root, "New Name:", state["duplicate"].stem)

    def save():
        new_name = entry.get().strip()
        if not new_name:
            messagebox.showwarning("Missing Name", "New name is required.")
            return
        backend.rename_existing_file(state["duplicate"], new_name)
        finalize_current_file()

    tk.Button(root, text="Save and Process New File", width=30, height=2, command=save).pack(pady=18)
    add_navigation_buttons(back_command=duplicate_page)


def finalize_current_file():
    metadata = state["metadata"]
    backend.tag_mp3(state["current_file"], metadata, state.get("cover_path"))
    final_path = backend.organize_file(state["current_file"], metadata)
    backend.save_track_to_database(metadata, final_path)
    backend.log_action(metadata["title"], metadata["artist"], metadata["album"], final_path, "Tagged and organized")
    advance_to_next_file(True)


def cancel_current_file():
    metadata = state.get("metadata", {"title": "", "artist": "", "album": ""})
    backend.log_action(metadata.get("title", ""), metadata.get("artist", ""), metadata.get("album", ""), "", "Cancelled file")
    advance_to_next_file(False)


def advance_to_next_file(processed):
    if processed:
        state["processed"] = state.get("processed", 0) + 1

    state["index"] = state.get("index", 0) + 1
    auto_mode = state.get("auto_mode", False)

    for key in ["current_file", "guess", "metadata_base", "metadata", "album", "cover_path", "duplicate", "pending_cover_upload", "general_cover_path", "duplicate_ai"]:
        state.pop(key, None)

    process_current_file(auto_mode=auto_mode)


def upload_cover_page():
    clear_window()
    tk.Label(root, text="Upload Cover Image", font=("Arial", 20, "bold")).pack(pady=20)
    tk.Label(root, text="Choose image first, then assign it to an artist or album.").pack(pady=5)

    tk.Button(root, text="Choose Image", width=30, height=2, command=choose_cover_image_general).pack(pady=8)
    add_navigation_buttons(back_command=main_menu)


def choose_cover_image_general():
    image_path = filedialog.askopenfilename(title="Select cover image", filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
    if not image_path:
        return
    state["general_cover_path"] = image_path
    choose_cover_type_page()


def choose_cover_type_page():
    clear_window()
    tk.Label(root, text="Cover Type", font=("Arial", 20, "bold")).pack(pady=20)
    create_image_preview(root, state["general_cover_path"], size=(180, 180))

    tk.Button(root, text="Album Cover", width=30, height=2, command=lambda: assign_cover_artist_page("album")).pack(pady=6)
    tk.Button(root, text="Artist Cover", width=30, height=2, command=lambda: assign_cover_artist_page("artist")).pack(pady=6)
    add_navigation_buttons(back_command=upload_cover_page)


def assign_cover_artist_page(category):
    clear_window()
    artists = backend.list_existing_artists()

    tk.Label(root, text="Choose Artist", font=("Arial", 20, "bold")).pack(pady=15)
    create_image_preview(root, state["general_cover_path"], size=(150, 150))

    artist_var = tk.StringVar(value=artists[0] if artists else "")

    if artists:
        tk.Label(root, text="Choose a pre-existing artist:").pack(pady=3)
        tk.OptionMenu(root, artist_var, *artists).pack(pady=4)

    tk.Label(root, text="Or type a new artist:").pack(pady=3)
    artist_entry = tk.Entry(root, width=40)
    artist_entry.pack(pady=4)

    def continue_next():
        artist = artist_entry.get().strip() or artist_var.get().strip()
        if not artist:
            messagebox.showwarning("Missing Artist", "Artist is required.")
            return
        backend.create_artist(artist)
        if category == "artist":
            saved = backend.save_cover_image(state["general_cover_path"], category="artist", folder_name=artist)
            messagebox.showinfo("Saved", f"Artist cover saved:\n{saved}")
            main_menu()
        else:
            assign_cover_album_page(artist)

    tk.Button(root, text="Continue", width=26, height=2, command=continue_next).pack(pady=12)
    add_navigation_buttons(back_command=choose_cover_type_page)


def assign_cover_album_page(artist):
    clear_window()
    existing_albums = backend.list_existing_albums_for_artist(artist)

    tk.Label(root, text="Choose Album", font=("Arial", 20, "bold")).pack(pady=15)
    tk.Label(root, text=f"Artist: {artist}").pack(pady=3)
    create_image_preview(root, state["general_cover_path"], size=(140, 140))

    album_var = tk.StringVar(value=existing_albums[0] if existing_albums else "")

    if existing_albums:
        tk.Label(root, text="Choose a pre-existing album:").pack(pady=3)
        tk.OptionMenu(root, album_var, *existing_albums).pack(pady=4)

    tk.Label(root, text="Or type a new album:").pack(pady=3)
    album_entry = tk.Entry(root, width=40)
    album_entry.pack(pady=4)

    def save_album_cover():
        album = album_entry.get().strip() or album_var.get().strip()
        if not album:
            messagebox.showwarning("Missing Album", "Album is required.")
            return
        backend.create_album(album, associated_artist=artist)
        saved = backend.save_cover_image(state["general_cover_path"], category="album", folder_name=album)
        messagebox.showinfo("Saved", f"Album cover saved:\n{saved}")
        main_menu()

    tk.Button(root, text="Save Album Cover", width=26, height=2, command=save_album_cover).pack(pady=12)
    add_navigation_buttons(back_command=lambda: assign_cover_artist_page("album"))


def semantic_search_page():
    clear_window()
    tk.Label(root, text="AI Semantic Search", font=("Arial", 20, "bold")).pack(pady=15)
    tk.Label(root, text="Search by meaning, not just exact words. Try: late night driving songs, aggressive gym music, sad melodic rap.", wraplength=720).pack(pady=5)
    entry = tk.Entry(root, width=70)
    entry.pack(pady=8)
    results_frame = tk.Frame(root)
    results_frame.pack(fill="both", expand=True, padx=30, pady=10)

    def run_search():
        for widget in results_frame.winfo_children():
            widget.destroy()
        query = entry.get().strip()
        if not query:
            messagebox.showwarning("Missing Search", "Type a search prompt first.")
            return
        results = backend.semantic_search_tracks(query, limit=8)
        if not results:
            tk.Label(results_frame, text="No songs found in the Muganizer database yet. Upload/process MP3s first.").pack(pady=8)
            return
        for track in results:
            row = tk.Frame(results_frame, relief="groove", bd=1, padx=8, pady=5)
            row.pack(fill="x", pady=3)
            title = f"{track.get('title')} — {track.get('artist')}  ({float(track.get('score', 0)):.0%} match)"
            tk.Label(row, text=title, font=("Arial", 10, "bold"), anchor="w").pack(anchor="w")
            tk.Label(row, text=f"Mood/genre: {track.get('genre', 'Unknown')} | {track.get('mood_tags', '')}", anchor="w", wraplength=720).pack(anchor="w")
            tk.Label(row, text=track.get("description", ""), anchor="w", wraplength=720).pack(anchor="w")
            tk.Button(row, text="Open", command=lambda p=track.get('file_path'): backend.open_file(p)).pack(anchor="e")

    tk.Button(root, text="Search", width=24, height=2, command=run_search).pack(pady=5)
    add_navigation_buttons(back_command=main_menu)


def playlist_generator_page():
    clear_window()
    tk.Label(root, text="AI Playlist Generator", font=("Arial", 20, "bold")).pack(pady=15)
    tk.Label(root, text="Describe the playlist you want. Muganizer uses semantic search to export a .m3u playlist.", wraplength=720).pack(pady=5)
    prompt_entry = tk.Entry(root, width=70)
    prompt_entry.pack(pady=8)
    prompt_entry.insert(0, "hype gym songs")
    count_entry = labeled_entry(root, "Song Count:", "15", width=10)
    results_frame = tk.Frame(root)
    results_frame.pack(fill="both", expand=True, padx=30, pady=10)

    def generate():
        for widget in results_frame.winfo_children():
            widget.destroy()
        prompt = prompt_entry.get().strip()
        try:
            limit = int(count_entry.get().strip())
        except Exception:
            limit = 15
        if not prompt:
            messagebox.showwarning("Missing Prompt", "Describe the playlist first.")
            return
        playlist_path, matches = backend.generate_playlist(prompt, limit=limit)
        tk.Label(results_frame, text=f"Playlist created: {playlist_path}", font=("Arial", 10, "bold"), wraplength=720).pack(anchor="w", pady=5)
        for track in matches:
            tk.Label(results_frame, text=f"• {track.get('title')} — {track.get('artist')} ({float(track.get('score', 0)):.0%})", anchor="w", wraplength=720).pack(anchor="w")
        tk.Button(results_frame, text="Open Playlist Folder", command=lambda: backend.open_file(backend.PLAYLISTS_ROOT)).pack(pady=8)

    tk.Button(root, text="Generate Playlist", width=26, height=2, command=generate).pack(pady=5)
    add_navigation_buttons(back_command=main_menu)

def manage_storage_menu():
    clear_window()
    tk.Label(root, text="Manage Storage", font=("Arial", 20, "bold")).pack(pady=25)

    tk.Button(root, text="Add New Album", width=34, height=2, command=add_new_album_page).pack(pady=8)
    tk.Button(root, text="Add New Artist", width=34, height=2, command=add_new_artist_page).pack(pady=8)
    tk.Button(root, text="Open Muganizer in File Explorer", width=34, height=2, command=open_muganizer_folder).pack(pady=8)
    add_navigation_buttons(back_command=main_menu)


def add_new_album_page():
    clear_window()
    tk.Label(root, text="Add New Album", font=("Arial", 20, "bold")).pack(pady=15)

    album_entry = labeled_entry(root, "Album:")
    artist_entry = labeled_entry(root, "Artist:")

    def save_album():
        album = album_entry.get().strip()
        artist = artist_entry.get().strip()
        if not album or not artist:
            messagebox.showwarning("Missing Info", "Album and artist are required.")
            return

        album_folder = backend.create_album(album, associated_artist=artist)

        if backend.normalize_text(album) == "unreleased":
            messagebox.showinfo("Unreleased", "Unreleased does not get an album cover folder.\nArtist storage was created instead.")
            manage_storage_menu()
            return

        state["new_album_name"] = album
        upload = messagebox.askyesno("Album Cover", "Would you like to upload an album cover now?")
        if upload:
            image_path = filedialog.askopenfilename(title="Select album cover", filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
            if image_path:
                backend.save_cover_image(image_path, category="album", folder_name=album)

        messagebox.showinfo("Success", f"Album folder created:\n{album_folder}")
        manage_storage_menu()

    tk.Button(root, text="Create Album", width=28, height=2, command=save_album).pack(pady=18)
    add_navigation_buttons(back_command=manage_storage_menu)


def add_new_artist_page():
    clear_window()
    tk.Label(root, text="Add New Artist", font=("Arial", 20, "bold")).pack(pady=15)
    artist_entry = labeled_entry(root, "Artist:")

    def save_artist():
        artist = artist_entry.get().strip()
        if not artist:
            messagebox.showwarning("Missing Artist", "Artist is required.")
            return

        artist_folder = backend.create_artist(artist)

        upload = messagebox.askyesno("Artist Cover", "Would you like to upload an artist cover now?")
        if upload:
            image_path = filedialog.askopenfilename(title="Select artist cover", filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
            if image_path:
                backend.save_cover_image(image_path, category="artist", folder_name=artist)

        messagebox.showinfo("Success", f"Artist folder created:\n{artist_folder}")
        manage_storage_menu()

    tk.Button(root, text="Create Artist", width=28, height=2, command=save_artist).pack(pady=18)
    add_navigation_buttons(back_command=manage_storage_menu)


def open_muganizer_folder():
    backend.MUGANIZER_ROOT.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(backend.MUGANIZER_ROOT)
    else:
        os.system(f'open "{backend.MUGANIZER_ROOT}"')


main_menu()
root.mainloop()
