
# Muganizer API with Inbox Tagging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
import muganizer_backend as backend

backend.setup_storage()
APP_NAME = "Muganizer API"
API_KEY = os.getenv("MUGANIZER_API_KEY", "")
INBOX_ROOT = backend.MUGANIZER_ROOT / "Inbox"
INBOX_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=APP_NAME,
    description="Local API for Muganizer with inbox-based MP3 tagging, search, playlists, recent tracks, and storage info.",
    version="1.1.0",
)

def check_api_key(x_api_key: Optional[str] = Header(default=None)):
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key.")

class SearchRequest(BaseModel):
    query: str
    limit: int = Field(10, ge=1, le=50)

class PlaylistRequest(BaseModel):
    prompt: str
    limit: int = Field(15, ge=1, le=50)

class TagInboxFileRequest(BaseModel):
    filename: str
    album: str = "Unreleased"
    title_override: Optional[str] = None
    artist_override: Optional[str] = None
    genre_override: Optional[str] = None
    keep_features: bool = True

class TagAllInboxRequest(BaseModel):
    album: str = "Unreleased"
    limit: int = Field(25, ge=1, le=100)

class InboxFile(BaseModel):
    filename: str
    path: str
    size_bytes: int

class TrackSummary(BaseModel):
    title: str
    artist: str
    album: Optional[str] = ""
    genre: Optional[str] = ""
    mood_tags: Optional[str] = ""
    description: Optional[str] = ""
    file_path: Optional[str] = ""
    score: Optional[float] = None

class TagResult(BaseModel):
    success: bool
    message: str
    original_filename: str
    final_path: Optional[str] = ""
    metadata: Optional[TrackSummary] = None

class PlaylistResponse(BaseModel):
    playlist_path: str
    tracks: List[TrackSummary]

class StorageLocations(BaseModel):
    muganizer_root: str
    inbox_root: str
    local_files_root: str
    album_covers_root: str
    artist_covers_root: str
    playlists_root: str
    database_file: str
    log_file: str

class RecentTracksResponse(BaseModel):
    tracks: List[TrackSummary]

class OpenFolderResponse(BaseModel):
    opened: bool
    path: str
    message: str

class HealthResponse(BaseModel):
    status: str
    muganizer_root: str
    inbox_root: str

def row_to_track_summary(row: Dict[str, Any]) -> TrackSummary:
    return TrackSummary(
        title=str(row.get("title", "")),
        artist=str(row.get("artist", "")),
        album=str(row.get("album", "")),
        genre=str(row.get("genre", "")),
        mood_tags=str(row.get("mood_tags", "")),
        description=str(row.get("description", "")),
        file_path=str(row.get("file_path", "")),
        score=row.get("score", None),
    )

def metadata_to_track_summary(metadata: Dict[str, Any], final_path: str = "") -> TrackSummary:
    mood_tags = metadata.get("mood_tags", "")
    if isinstance(mood_tags, list):
        mood_tags = ", ".join(mood_tags)
    return TrackSummary(
        title=str(metadata.get("title", "")),
        artist=str(metadata.get("artist", "")),
        album=str(metadata.get("album", "")),
        genre=str(metadata.get("genre", "")),
        mood_tags=str(mood_tags),
        description=str(metadata.get("description", "")),
        file_path=str(final_path),
        score=None,
    )

def list_inbox_mp3_paths() -> List[Path]:
    INBOX_ROOT.mkdir(parents=True, exist_ok=True)
    return sorted([p for p in INBOX_ROOT.iterdir() if p.is_file() and p.suffix.lower() == ".mp3"])

def safe_inbox_path(filename: str) -> Path:
    candidate = INBOX_ROOT / Path(filename).name
    if not candidate.exists() or candidate.suffix.lower() != ".mp3":
        raise HTTPException(status_code=404, detail=f"MP3 not found in inbox: {filename}")
    return candidate

def finalize_inbox_file(file_path: Path, request: TagInboxFileRequest) -> TagResult:
    original_filename = file_path.name
    try:
        guessed = backend.guess_metadata_with_ai(file_path.name)
        metadata = {
            "title": request.title_override or guessed.get("title", file_path.stem),
            "artist": request.artist_override or guessed.get("artist", ""),
            "features": guessed.get("features", []) if request.keep_features else [],
            "album": request.album or "Unreleased",
            "genre": request.genre_override or guessed.get("genre", "Unknown"),
            "mood_tags": guessed.get("mood_tags", []),
            "description": guessed.get("description", ""),
            "confidence": guessed.get("confidence", 0.5),
            "reasoning_summary": guessed.get("reasoning_summary", ""),
            "spotify_album": guessed.get("spotify_album", ""),
            "spotify_release_date": guessed.get("spotify_release_date", ""),
            "spotify_cover_url": guessed.get("spotify_cover_url", ""),
            "spotify_url": guessed.get("spotify_url", ""),
            "spotify_match_title": guessed.get("spotify_match_title", ""),
            "spotify_match_artist": guessed.get("spotify_match_artist", ""),
        }
        if metadata.get("features"):
            formatted_title, formatted_artist = backend.format_features(metadata.get("title", ""), metadata.get("artist", ""), metadata.get("features", []))
            metadata["title"] = formatted_title
            metadata["artist"] = formatted_artist
        if not metadata.get("title"):
            metadata["title"] = file_path.stem
        if not metadata.get("artist"):
            metadata["artist"] = "Unknown Artist"
        if backend.normalize_text(metadata["album"]) != "unreleased":
            backend.create_local_album_folder(metadata["artist"], metadata["album"])
        else:
            backend.create_local_artist_folder(metadata["artist"])
        cover_path = backend.select_cover_final(metadata["artist"], metadata["album"])
        backend.tag_mp3(file_path, metadata, cover_path)
        final_path = backend.organize_file(file_path, metadata)
        backend.save_track_to_database(metadata, final_path)
        backend.log_action(metadata.get("title", ""), metadata.get("artist", ""), metadata.get("album", ""), final_path, "Tagged and organized via GPT inbox action")
        return TagResult(success=True, message="MP3 tagged, organized, logged, and saved to database.", original_filename=original_filename, final_path=str(final_path), metadata=metadata_to_track_summary(metadata, str(final_path)))
    except Exception as e:
        return TagResult(success=False, message=f"Failed to tag MP3: {type(e).__name__}: {e}", original_filename=original_filename, final_path="", metadata=None)

@app.get("/")
def root():
    return {"name": APP_NAME, "status": "running", "message": "Muganizer API is running."}

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", muganizer_root=str(backend.MUGANIZER_ROOT), inbox_root=str(INBOX_ROOT))

@app.get("/inbox", response_model=List[InboxFile])
def list_inbox(x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    return [InboxFile(filename=p.name, path=str(p), size_bytes=p.stat().st_size) for p in list_inbox_mp3_paths()]

@app.post("/tag-inbox-file", response_model=TagResult)
def tag_inbox_file(request: TagInboxFileRequest, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    return finalize_inbox_file(safe_inbox_path(request.filename), request)

@app.post("/tag-all-inbox", response_model=List[TagResult])
def tag_all_inbox(request: TagAllInboxRequest, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    return [finalize_inbox_file(p, TagInboxFileRequest(filename=p.name, album=request.album)) for p in list_inbox_mp3_paths()[:request.limit]]

@app.post("/search", response_model=List[TrackSummary])
def search_library(request: SearchRequest, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    return [row_to_track_summary(row) for row in backend.semantic_search_tracks(request.query, limit=request.limit)]

@app.post("/playlist", response_model=PlaylistResponse)
def generate_playlist(request: PlaylistRequest, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    playlist_path, matches = backend.generate_playlist(request.prompt, limit=request.limit)
    return PlaylistResponse(playlist_path=str(playlist_path), tracks=[row_to_track_summary(row) for row in matches])

@app.get("/recent", response_model=RecentTracksResponse)
def recent_tracks(limit: int = 10, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    tracks = backend.get_all_tracks()[:max(1, min(50, int(limit)))]
    return RecentTracksResponse(tracks=[row_to_track_summary(row) for row in tracks])

@app.get("/storage", response_model=StorageLocations)
def storage_locations(x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    return StorageLocations(muganizer_root=str(backend.MUGANIZER_ROOT), inbox_root=str(INBOX_ROOT), local_files_root=str(backend.LOCAL_FILES_ROOT), album_covers_root=str(backend.ALBUM_COVERS_ROOT), artist_covers_root=str(backend.ARTIST_COVERS_ROOT), playlists_root=str(backend.PLAYLISTS_ROOT), database_file=str(backend.DATABASE_FILE), log_file=str(backend.LOG_FILE))

@app.post("/open-folder", response_model=OpenFolderResponse)
def open_muganizer_folder(x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    try:
        backend.MUGANIZER_ROOT.mkdir(parents=True, exist_ok=True)
        backend.open_file(backend.MUGANIZER_ROOT)
        return OpenFolderResponse(opened=True, path=str(backend.MUGANIZER_ROOT), message="Opened Muganizer folder.")
    except Exception as e:
        return OpenFolderResponse(opened=False, path=str(backend.MUGANIZER_ROOT), message=f"Could not open folder: {type(e).__name__}: {e}")

@app.get("/tracks", response_model=List[TrackSummary])
def all_tracks(limit: int = 50, x_api_key: Optional[str] = Header(default=None)):
    check_api_key(x_api_key)
    tracks = backend.get_all_tracks()[:max(1, min(200, int(limit)))]
    return [row_to_track_summary(row) for row in tracks]
