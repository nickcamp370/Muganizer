# Muganizer

AI-powered conversational music management platform.

Muganizer combines GPT Actions, FastAPI, OpenAI, Spotify metadata enrichment, semantic search, and automated MP3 organization into a conversational AI music management system.

## Features

- AI metadata generation
- Spotify metadata enrichment
- Conversational GPT interface
- Semantic search
- AI playlist generation
- Automatic MP3 tagging
- Cover art embedding
- Multi-artist organization
- GPT Actions + FastAPI integration

## Architecture

Custom GPT -> GPT Actions -> FastAPI -> Muganizer Backend -> Spotify/OpenAI APIs -> Local MP3 Library

## Tech Stack

- Python
- FastAPI
- OpenAI API
- Spotify API
- Mutagen
- SQLite
- Tkinter
- ngrok

## Installation

```powershell
python -m pip install -r requirements.txt
python -m uvicorn muganizer_api:app --host 127.0.0.1 --port 8000 --reload
ngrok http 8000
```

## License

MIT License
