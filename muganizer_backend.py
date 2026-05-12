import os
import re
import csv
import json
import random
import shutil
import sqlite3
import math
import hashlib
from difflib import SequenceMatcher
import subprocess
import sys
from io import BytesIO
from datetime import datetime
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TPE2, TCON, APIC
from PIL import Image

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import spotify_lookup
except ImportError:
    spotify_lookup = None


def load_env_file():
    """Load OPENAI_API_KEY and OPENAI_MODEL from a local .env file without extra dependencies."""
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


def log_debug(message):
    try:
        MUGANIZER_ROOT.mkdir(parents=True, exist_ok=True)
        with open(MUGANIZER_ROOT / "muganizer_debug.log", "a", encoding="utf-8") as f:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{now}] {message}\n")
    except Exception:
        pass


MUGANIZER_ROOT = Path.home() / "Music" / "Muganizer"
LOCAL_FILES_ROOT = MUGANIZER_ROOT / "Local Files"
COVERS_ROOT = MUGANIZER_ROOT / "Covers"
ALBUM_COVERS_ROOT = COVERS_ROOT / "Albums"
ARTIST_COVERS_ROOT = COVERS_ROOT / "Artists"
LOG_FILE = MUGANIZER_ROOT / "muganizer_log.csv"
DATABASE_FILE = MUGANIZER_ROOT / "muganizer_library.sqlite3"
PLAYLISTS_ROOT = MUGANIZER_ROOT / "Playlists"


def setup_storage():
    LOCAL_FILES_ROOT.mkdir(parents=True, exist_ok=True)
    ALBUM_COVERS_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIST_COVERS_ROOT.mkdir(parents=True, exist_ok=True)
    PLAYLISTS_ROOT.mkdir(parents=True, exist_ok=True)
    init_database()


def clean_filename(text):
    text = str(text or "").strip()
    text = re.sub(r'[<>:"/\\|?*]', "", text)
    return text.strip()


def normalize_text(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def format_features(title, artist, features):
    features = [f.strip() for f in features if f and f.strip()]
    title = title.strip()
    artist = artist.strip()

    if not features:
        return title, artist

    artist_with_features = artist + ", " + ", ".join(features)

    if len(features) == 1:
        feature_text = features[0]
    elif len(features) == 2:
        feature_text = f"{features[0]} & {features[1]}"
    else:
        feature_text = ", ".join(features[:-1]) + f", & {features[-1]}"

    title_with_features = f"{title} (feat. {feature_text})"
    return title_with_features, artist_with_features


def split_features_from_title(title):
    title = str(title or "").strip()
    feature_match = re.search(
        r"(?:\(|\[)?(?:feat\.?|ft\.?|featuring)\s+(.+?)(?:\)|\])?$",
        title,
        re.IGNORECASE
    )

    if not feature_match:
        return title, []

    feature_text = feature_match.group(1).strip(" ()[]")
    clean_title = re.sub(
        r"\s*(?:\(|\[)?(?:feat\.?|ft\.?|featuring)\s+.+?(?:\)|\])?$",
        "",
        title,
        flags=re.IGNORECASE
    ).strip()

    features = re.split(r",|&| and ", feature_text)
    features = [f.strip(" ()[]") for f in features if f.strip()]
    return clean_title, features


def guess_metadata_from_filename(filename):
    name = Path(filename).stem
    name = re.sub(r"[_]+", " ", name).strip()
    metadata = {"title": name, "artist": "", "features": []}

    patterns = [
        r"^(?P<artist>.+?)\s*-\s*(?P<title>.+)$",
        r"^(?P<title>.+?)\s+by\s+(?P<artist>.+)$"
    ]

    for pattern in patterns:
        match = re.match(pattern, name, re.IGNORECASE)
        if match:
            metadata["title"] = match.group("title").strip()
            metadata["artist"] = match.group("artist").strip()
            break

    clean_title, features = split_features_from_title(metadata["title"])
    metadata["title"] = clean_title
    metadata["features"] = features
    return metadata


def extract_json_object(text):
    text = str(text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else text


def _metadata_defaults(base=None):
    base = dict(base or {})
    base.setdefault("title", "")
    base.setdefault("artist", "")
    base.setdefault("features", [])
    base.setdefault("genre", "Unknown")
    base.setdefault("mood_tags", [])
    base.setdefault("description", "")
    base.setdefault("confidence", 0.50)
    base.setdefault("reasoning_summary", "Generated from filename and available tags.")
    return base


def _coerce_ai_metadata(data, filename):
    features = data.get("features", [])
    if isinstance(features, str):
        features = [features] if features.strip() else []
    mood_tags = data.get("mood_tags", [])
    if isinstance(mood_tags, str):
        mood_tags = [mood_tags] if mood_tags.strip() else []

    try:
        confidence = float(data.get("confidence", 0.7))
    except Exception:
        confidence = 0.7

    cleaned = _metadata_defaults({
        "title": str(data.get("title", Path(filename).stem)).strip(),
        "artist": str(data.get("artist", "")).strip(),
        "features": [str(f).strip() for f in features if str(f).strip()],
        "genre": str(data.get("genre", "Unknown")).strip() or "Unknown",
        "mood_tags": [str(m).strip() for m in mood_tags if str(m).strip()],
        "description": str(data.get("description", "")).strip(),
        "confidence": max(0.0, min(1.0, confidence)),
        "reasoning_summary": str(data.get("reasoning_summary", "Generated from filename.")).strip(),
    })

    # Extra fields used by the UI when Spotify finds a likely match.
    cleaned["spotify_album"] = str(data.get("spotify_album", "")).strip()
    cleaned["spotify_release_date"] = str(data.get("spotify_release_date", "")).strip()
    cleaned["spotify_cover_url"] = str(data.get("spotify_cover_url", "")).strip()
    cleaned["spotify_url"] = str(data.get("spotify_url", "")).strip()
    cleaned["spotify_match_title"] = str(data.get("spotify_match_title", "")).strip()
    cleaned["spotify_match_artist"] = str(data.get("spotify_match_artist", "")).strip()
    return cleaned


def guess_metadata_with_ai(filename):
    """
    Main metadata pipeline:
    1. Build a simple filename fallback.
    2. Ask OpenAI for an initial title/artist/features/genre/mood guess.
    3. Use that guess to retrieve Spotify catalog matches when credentials exist.
    4. Ask OpenAI to make a final metadata decision using both filename + Spotify context.
    """
    fallback = _metadata_defaults(guess_metadata_from_filename(filename))

    if OpenAI is None:
        fallback["description"] = "OpenAI package is not installed, so this was inferred from filename only."
        fallback["mood_tags"] = ["unknown"]
        log_debug("OpenAI package is not installed. Install with: python -m pip install openai")
        return fallback

    if not os.getenv("OPENAI_API_KEY"):
        fallback["description"] = "OPENAI_API_KEY was not found, so this was inferred from filename only."
        fallback["mood_tags"] = ["unknown"]
        log_debug("OPENAI_API_KEY not found. Check that .env is in the same folder as muganizer_gui.py and contains OPENAI_API_KEY=...")
        return fallback

    try:
        client = OpenAI()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        initial_prompt = f"""
You are the first-pass metadata parser for Muganizer, an AI-powered local music organizer.
Analyze this MP3 filename and infer likely music metadata.

Filename: {filename}

Return only valid JSON with exactly these keys:
title, artist, features, genre, mood_tags, description, confidence, reasoning_summary

Rules:
- Do not guess album in this first pass.
- features must be a list of strings.
- mood_tags must be a list of 3 to 6 short strings.
- description must be one concise sentence useful for semantic search.
- confidence must be a number from 0 to 1.
- reasoning_summary must be short and user-facing.
- For names like "Artist - Title", artist should be the part before the dash and title after the dash.
"""
        response = client.responses.create(model=model, input=initial_prompt)
        initial_data = json.loads(extract_json_object(response.output_text))
        initial_guess = _coerce_ai_metadata(initial_data, filename)

        spotify_results_text = "Spotify lookup unavailable."
        spotify_results = []
        if spotify_lookup is not None:
            try:
                spotify_info = spotify_lookup.spotify_enrich_metadata(initial_guess, filename)
                spotify_results = spotify_info.get("results", [])
                spotify_results_text = spotify_lookup.format_spotify_results_for_prompt(spotify_results)
                if not spotify_results:
                    log_debug(f"Spotify returned no results for {filename}. Query: {spotify_info.get('query', '')}")
            except Exception as spotify_error:
                spotify_results_text = f"Spotify lookup failed: {type(spotify_error).__name__}"
                log_debug(f"Spotify lookup failed for {filename}: {type(spotify_error).__name__}: {spotify_error}")

        final_prompt = f"""
You are the final metadata engine for Muganizer.
Use the uploaded filename, the first AI guess, and Spotify catalog results to choose the best metadata.

Filename: {filename}

First AI guess JSON:
{json.dumps(initial_guess, ensure_ascii=False)}

Spotify search results:
{spotify_results_text}

Return only valid JSON with exactly these keys:
title, artist, features, genre, mood_tags, description, confidence, reasoning_summary,
spotify_album, spotify_release_date, spotify_cover_url, spotify_url, spotify_match_title, spotify_match_artist

Rules:
- Prefer Spotify title/artist when a result clearly matches the filename.
- Do NOT flip artist/title unless Spotify evidence or filename format strongly supports it.
- Use spotify_album only as a suggested album; the user can still edit/choose album later.
- Spotify often gives artist genres, not track genres. Use Spotify context plus your reasoning to infer a practical genre label.
- features must be a list of strings.
- mood_tags must be a list of 3 to 6 short strings.
- description must be one concise sentence useful for semantic search and playlists.
- confidence must be a number from 0 to 1.
- reasoning_summary must be a short user-facing explanation.
- If there is no good Spotify match, keep the first AI guess and explain that Spotify did not confirm it.
"""
        final_response = client.responses.create(model=model, input=final_prompt)
        final_data = json.loads(extract_json_object(final_response.output_text))
        return _coerce_ai_metadata(final_data, filename)

    except Exception as e:
        fallback["description"] = f"AI/Spotify metadata failed: {type(e).__name__}. Check muganizer_debug.log."
        fallback["mood_tags"] = ["ai-error"]
        log_debug(f"AI/Spotify metadata failed for {filename}: {type(e).__name__}: {e}")
        return fallback


def list_existing_artists():
    artists = set()
    if LOCAL_FILES_ROOT.exists():
        for p in LOCAL_FILES_ROOT.iterdir():
            if p.is_dir():
                artists.add(p.name)
    if ARTIST_COVERS_ROOT.exists():
        for p in ARTIST_COVERS_ROOT.iterdir():
            if p.is_dir():
                artists.add(p.name)
    return sorted(artists)


def list_existing_albums_for_artist(artist):
    artist_folder = LOCAL_FILES_ROOT / clean_filename(artist)
    if not artist_folder.exists():
        return []
    return sorted([p.name for p in artist_folder.iterdir() if p.is_dir()])


def create_local_artist_folder(artist):
    folder = LOCAL_FILES_ROOT / clean_filename(artist)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def create_local_album_folder(artist, album):
    folder = LOCAL_FILES_ROOT / clean_filename(artist) / clean_filename(album)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def find_random_cover(folder):
    folder = Path(folder)
    if not folder.exists():
        return None

    valid_extensions = {".jpg", ".jpeg", ".png"}
    covers = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions]
    return random.choice(covers) if covers else None


def select_existing_album_cover(album):
    if normalize_text(album) == "unreleased":
        return None

    album_folder = ALBUM_COVERS_ROOT / clean_filename(album)
    if album_folder.exists():
        return find_random_cover(album_folder)
    return None


def select_artist_cover(artist):
    artist_folder = ARTIST_COVERS_ROOT / clean_filename(artist)
    if artist_folder.exists():
        return find_random_cover(artist_folder)
    return None


def select_cover_final(artist, album):
    cover = select_existing_album_cover(album)
    if cover:
        return cover
    return select_artist_cover(artist)


def ensure_id3(file_path):
    try:
        return ID3(file_path)
    except ID3NoHeaderError:
        tags = ID3()
        tags.save(file_path)
        return ID3(file_path)


def image_to_jpeg_bytes(image_path):
    image = Image.open(image_path).convert("RGB")
    image = image.resize((500, 500))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def tag_mp3(file_path, metadata, cover_path=None):
    file_path = Path(file_path)

    try:
        audio = EasyID3(file_path)
    except Exception:
        audio = EasyID3()
        audio.save(file_path)
        audio = EasyID3(file_path)

    audio["title"] = metadata["title"]
    audio["artist"] = metadata["artist"]
    audio["album"] = metadata["album"]
    if metadata.get("genre"):
        audio["genre"] = metadata.get("genre", "")
    audio.save()

    id3 = ensure_id3(file_path)
    id3["TIT2"] = TIT2(encoding=3, text=metadata["title"])
    id3["TPE1"] = TPE1(encoding=3, text=metadata["artist"])
    id3["TALB"] = TALB(encoding=3, text=metadata["album"])
    id3["TPE2"] = TPE2(encoding=3, text=metadata["artist"])
    if metadata.get("genre"):
        id3["TCON"] = TCON(encoding=3, text=metadata.get("genre", ""))

    if cover_path:
        image_data = image_to_jpeg_bytes(cover_path)
        id3.delall("APIC")
        id3.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=image_data))

    id3.save(file_path, v2_version=3)


def read_existing_tags(file_path):
    try:
        audio = EasyID3(file_path)
        return {
            "title": audio.get("title", [""])[0],
            "artist": audio.get("artist", [""])[0],
            "album": audio.get("album", [""])[0],
        }
    except Exception:
        return {"title": "", "artist": "", "album": ""}


def find_duplicates(metadata):
    duplicates = []
    if not LOCAL_FILES_ROOT.exists():
        return duplicates

    target_title = normalize_text(metadata["title"])
    target_artist = normalize_text(metadata["artist"].split(",")[0])

    for file in LOCAL_FILES_ROOT.rglob("*.mp3"):
        existing_tags = read_existing_tags(file)
        existing_title = normalize_text(existing_tags.get("title")) or normalize_text(file.stem)
        existing_artist = normalize_text(existing_tags.get("artist"))

        title_match = target_title and (target_title == existing_title or target_title in normalize_text(file.stem))
        artist_match = not target_artist or not existing_artist or target_artist in existing_artist

        if title_match and artist_match:
            duplicates.append(file)

    return duplicates


def open_file(file_path):
    file_path = Path(file_path)
    if os.name == "nt":
        os.startfile(file_path)
    elif sys.platform == "darwin":
        subprocess.call(["open", str(file_path)])
    else:
        subprocess.call(["xdg-open", str(file_path)])


def get_artist_folder_names(metadata):
    """
    Return separate artist folder names for a track.

    Important: the tagged MP3 artist field may be "Main Artist, Feature Artist".
    Folder organization should NOT create one combined folder with that full string.
    Instead, Muganizer stores a copy under each involved artist.
    """
    artists = []

    raw_artist = str(metadata.get("artist", "")).strip()
    features = metadata.get("features", [])

    # If the artist tag already contains comma-separated artists, split them.
    # This handles: "Travis Scott, Playboi Carti".
    if raw_artist:
        artists.extend([a.strip() for a in raw_artist.split(",") if a.strip()])

    # Also include the explicit features list when available.
    if isinstance(features, str):
        features = [f.strip() for f in features.split(",") if f.strip()]

    if isinstance(features, list):
        artists.extend([str(f).strip() for f in features if str(f).strip()])

    # Remove duplicates while preserving order.
    cleaned = []
    seen = set()
    for artist in artists:
        key = normalize_text(artist)
        if key and key not in seen:
            cleaned.append(artist)
            seen.add(key)

    return cleaned or ["Unknown Artist"]


def get_primary_artist_folder(metadata):
    return get_artist_folder_names(metadata)[0]


def get_destination_path(metadata, artist_folder_name=None):
    if artist_folder_name is None:
        artist_folder_name = get_primary_artist_folder(metadata)

    destination_folder = LOCAL_FILES_ROOT / clean_filename(artist_folder_name) / clean_filename(metadata["album"])
    return destination_folder / f"{clean_filename(metadata['title'])}.mp3"


def get_available_destination_path(destination_file):
    destination_file = Path(destination_file)
    destination_file.parent.mkdir(parents=True, exist_ok=True)

    counter = 1
    base = destination_file.stem
    suffix = destination_file.suffix

    while destination_file.exists():
        destination_file = destination_file.parent / f"{base} ({counter}){suffix}"
        counter += 1

    return destination_file


def organize_file(file_path, metadata):
    """
    Organize a tagged MP3 into the library.

    If the track has featured artists, Muganizer creates a separate copy under
    each artist's folder instead of creating one combined folder name.

    Example:
        Artist tag: Travis Scott, Playboi Carti
        Album: UTOPIA

    Creates:
        Local Files/Travis Scott/UTOPIA/<title>.mp3
        Local Files/Playboi Carti/UTOPIA/<title>.mp3

    Returns the primary artist copy path.
    """
    file_path = Path(file_path)
    artist_folders = get_artist_folder_names(metadata)

    # Move the original file into the primary artist folder first.
    primary_destination = get_available_destination_path(get_destination_path(metadata, artist_folders[0]))
    shutil.move(str(file_path), str(primary_destination))

    # Copy the already-tagged primary file into the remaining artist folders.
    for artist_name in artist_folders[1:]:
        copy_destination = get_available_destination_path(get_destination_path(metadata, artist_name))
        shutil.copy2(str(primary_destination), str(copy_destination))

    return primary_destination


def replace_existing_file(new_file, existing_file):
    new_file = Path(new_file)
    existing_file = Path(existing_file)
    existing_file.unlink()
    shutil.move(str(new_file), str(existing_file))
    return existing_file


def rename_existing_file(existing_file, new_name):
    existing_file = Path(existing_file)
    new_file = existing_file.with_name(clean_filename(new_name) + existing_file.suffix)

    counter = 1
    base = new_file.stem
    while new_file.exists():
        new_file = existing_file.with_name(f"{base} ({counter}){existing_file.suffix}")
        counter += 1

    existing_file.rename(new_file)
    return new_file


def save_cover_image(image_path, category, folder_name):
    image_path = Path(image_path)

    if category == "album":
        destination_folder = ALBUM_COVERS_ROOT / clean_filename(folder_name)
    else:
        destination_folder = ARTIST_COVERS_ROOT / clean_filename(folder_name)

    destination_folder.mkdir(parents=True, exist_ok=True)

    base_name = clean_filename(folder_name)
    output_path = destination_folder / f"{base_name}.jpg"

    counter = 1
    while output_path.exists():
        output_path = destination_folder / f"{base_name} ({counter}).jpg"
        counter += 1

    image = Image.open(image_path).convert("RGB")
    image = image.resize((500, 500))
    image.save(output_path, "JPEG", quality=92)

    return output_path


def create_album(album_name, associated_artist=None):
    folder = None
    if normalize_text(album_name) != "unreleased":
        folder = ALBUM_COVERS_ROOT / clean_filename(album_name)
        folder.mkdir(parents=True, exist_ok=True)

    if associated_artist:
        create_artist(associated_artist)
        create_local_artist_folder(associated_artist)
        if normalize_text(album_name) != "unreleased":
            create_local_album_folder(associated_artist, album_name)

    return folder


def create_artist(artist_name):
    cover_folder = ARTIST_COVERS_ROOT / clean_filename(artist_name)
    cover_folder.mkdir(parents=True, exist_ok=True)
    create_local_artist_folder(artist_name)
    return cover_folder


def log_action(title, artist, album, final_path, action):
    setup_storage()
    file_exists = LOG_FILE.exists()

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        if not file_exists:
            writer.writerow(["Date", "Time", "Title", "Artist", "Album", "Final File Path", "Action Taken"])

        now = datetime.now()
        writer.writerow([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            title,
            artist,
            album,
            str(final_path),
            action
        ])


# -----------------------------
# AI library database + search
# -----------------------------

def get_db_connection():
    setup_dirs_only()
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def setup_dirs_only():
    LOCAL_FILES_ROOT.mkdir(parents=True, exist_ok=True)
    ALBUM_COVERS_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIST_COVERS_ROOT.mkdir(parents=True, exist_ok=True)
    PLAYLISTS_ROOT.mkdir(parents=True, exist_ok=True)


def init_database():
    setup_dirs_only()
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            album TEXT,
            features TEXT,
            genre TEXT,
            mood_tags TEXT,
            description TEXT,
            confidence REAL,
            reasoning_summary TEXT,
            file_path TEXT UNIQUE,
            search_text TEXT,
            embedding TEXT,
            date_added TEXT
        )
    """)
    conn.commit()
    conn.close()


def metadata_search_text(metadata):
    parts = [
        metadata.get("title", ""),
        metadata.get("artist", ""),
        metadata.get("album", ""),
        metadata.get("genre", ""),
        ", ".join(metadata.get("mood_tags", []) if isinstance(metadata.get("mood_tags"), list) else [str(metadata.get("mood_tags", ""))]),
        metadata.get("description", ""),
    ]
    return " | ".join([str(p) for p in parts if str(p).strip()])


def create_embedding(text):
    text = str(text or "")
    if OpenAI is not None and os.getenv("OPENAI_API_KEY"):
        try:
            client = OpenAI()
            response = client.embeddings.create(model="text-embedding-3-small", input=text)
            return response.data[0].embedding
        except Exception:
            pass

    # Offline fallback: deterministic hashed bag-of-words vector.
    dims = 192
    vec = [0.0] * dims
    words = re.findall(r"[a-z0-9']+", text.lower())
    for word in words:
        idx = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16) % dims
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_similarity(a, b):
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    nb = math.sqrt(sum(x * x for x in b[:n])) or 1.0
    return dot / (na * nb)


def save_track_to_database(metadata, final_path):
    init_database()
    full_metadata = _metadata_defaults(metadata)
    search_text = metadata_search_text(full_metadata)
    embedding = create_embedding(search_text)

    conn = get_db_connection()
    conn.execute("""
        INSERT OR REPLACE INTO tracks
        (title, artist, album, features, genre, mood_tags, description, confidence, reasoning_summary, file_path, search_text, embedding, date_added)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        full_metadata.get("title", ""),
        full_metadata.get("artist", ""),
        full_metadata.get("album", ""),
        json.dumps(full_metadata.get("features", [])),
        full_metadata.get("genre", "Unknown"),
        json.dumps(full_metadata.get("mood_tags", [])),
        full_metadata.get("description", ""),
        float(full_metadata.get("confidence", 0.5)),
        full_metadata.get("reasoning_summary", ""),
        str(final_path),
        search_text,
        json.dumps(embedding),
        datetime.now().isoformat(timespec="seconds"),
    ))
    conn.commit()
    conn.close()


def get_all_tracks():
    init_database()
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM tracks ORDER BY date_added DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def semantic_search_tracks(query, limit=10):
    init_database()
    q_embedding = create_embedding(query)
    scored = []
    for track in get_all_tracks():
        try:
            emb = json.loads(track.get("embedding") or "[]")
        except Exception:
            emb = []
        semantic = cosine_similarity(q_embedding, emb)
        keyword = SequenceMatcher(None, normalize_text(query), normalize_text(track.get("search_text", ""))).ratio()
        score = (0.80 * semantic) + (0.20 * keyword)
        track["score"] = round(score, 3)
        scored.append(track)
    scored.sort(key=lambda row: row["score"], reverse=True)
    return scored[:limit]


def find_ai_duplicates(metadata, limit=5):
    target_text = metadata_search_text(_metadata_defaults(metadata))
    target_embedding = create_embedding(target_text)
    results = []
    for track in get_all_tracks():
        try:
            emb = json.loads(track.get("embedding") or "[]")
        except Exception:
            emb = []
        emb_score = cosine_similarity(target_embedding, emb)
        title_score = SequenceMatcher(None, normalize_text(metadata.get("title", "")), normalize_text(track.get("title", ""))).ratio()
        artist_score = SequenceMatcher(None, normalize_text(metadata.get("artist", "")), normalize_text(track.get("artist", ""))).ratio()
        score = (0.50 * emb_score) + (0.30 * title_score) + (0.20 * artist_score)
        if score >= 0.78:
            track["duplicate_score"] = round(score, 3)
            track["duplicate_reason"] = f"Title {title_score:.0%}, artist {artist_score:.0%}, semantic {emb_score:.0%}"
            results.append(track)
    results.sort(key=lambda row: row["duplicate_score"], reverse=True)
    return results[:limit]


def generate_playlist(prompt, limit=15):
    matches = semantic_search_tracks(prompt, limit=limit)
    safe_name = clean_filename(prompt)[:50] or "AI Playlist"
    playlist_path = PLAYLISTS_ROOT / f"{safe_name}.m3u"
    with open(playlist_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.write(f"# Generated by Muganizer from prompt: {prompt}\n")
        for track in matches:
            path = track.get("file_path", "")
            if path:
                f.write(path + "\n")
    return playlist_path, matches
