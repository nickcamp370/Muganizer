import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()


SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"


def get_spotify_token():
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    auth_string = f"{client_id}:{client_secret}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Basic {auth_base64}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "client_credentials"
    }

    try:
        response = requests.post(
            SPOTIFY_TOKEN_URL,
            headers=headers,
            data=data,
            timeout=10
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception:
        return None


def search_spotify_tracks(query, limit=5):
    token = get_spotify_token()

    if not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}"
    }

    params = {
        "q": query,
        "type": "track",
        "limit": limit
    }

    try:
        response = requests.get(
            SPOTIFY_SEARCH_URL,
            headers=headers,
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    tracks = []

    for item in data.get("tracks", {}).get("items", []):
        album = item.get("album", {})
        artists = item.get("artists", [])

        artist_names = [artist.get("name", "") for artist in artists if artist.get("name")]
        main_artist = artist_names[0] if artist_names else ""

        images = album.get("images", [])
        cover_url = images[0]["url"] if images else ""

        tracks.append({
            "spotify_id": item.get("id", ""),
            "title": item.get("name", ""),
            "artist": main_artist,
            "artists": artist_names,
            "album": album.get("name", ""),
            "release_date": album.get("release_date", ""),
            "cover_url": cover_url,
            "popularity": item.get("popularity", 0),
            "spotify_url": item.get("external_urls", {}).get("spotify", "")
        })

    return tracks


def build_spotify_query(ai_guess, filename=""):
    title = ai_guess.get("title", "")
    artist = ai_guess.get("artist", "")

    if title and artist:
        return f'track:{title} artist:{artist}'

    if title:
        return title

    return filename


def spotify_enrich_metadata(ai_guess, filename=""):
    query = build_spotify_query(ai_guess, filename)
    results = search_spotify_tracks(query, limit=5)

    return {
        "query": query,
        "results": results,
        "best_match": results[0] if results else None
    }


def format_spotify_results_for_prompt(results):
    if not results:
        return "No Spotify results found."

    lines = []

    for i, track in enumerate(results, start=1):
        lines.append(
            f"{i}. Title: {track.get('title', '')}\n"
            f"   Artist: {track.get('artist', '')}\n"
            f"   All Artists: {', '.join(track.get('artists', []))}\n"
            f"   Album: {track.get('album', '')}\n"
            f"   Release Date: {track.get('release_date', '')}\n"
            f"   Popularity: {track.get('popularity', 0)}\n"
            f"   Spotify URL: {track.get('spotify_url', '')}"
        )

    return "\n\n".join(lines)