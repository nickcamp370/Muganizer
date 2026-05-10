# Muganizer

AI-powered conversational music management platform.

Muganizer combines GPT Actions, FastAPI, OpenAI, Spotify metadata enrichment, semantic search, and automated MP3 organization into a conversational AI music management system.

## Overview

Muganizer is a local-first AI-powered music organization platform designed to automate and modernize MP3 management.

The system allows users to:

- Organize local MP3 libraries automatically
- Generate AI-powered metadata
- Enrich metadata using Spotify
- Embed album artwork into MP3 files
- Perform semantic music searches
- Generate natural-language playlists
- Control the system conversationally using a Custom GPT
- Organize tracks across multiple artist folders automatically

The platform uses a FastAPI backend connected to a Custom GPT through GPT Actions.

## Features
AI Metadata Generation

Uses the OpenAI API to infer:

- Song title
- Artist
- Features
- Genre
- Mood tags
- Semantic descriptions

from unstructured MP3 filenames.

## Spotify Metadata Enrichment
Muganizer uses the Spotify API to:

- Confirm likely title/artist matches
- Retrieve album information
- Retrieve release dates
- Retrieve album artwork
- Improve metadata confidence

## Conversational GPT Interface
Users can interact with Muganizer through natural conversation.

Example prompts:
```
Show inbox files
Tag the first song using album UTOPIA
Find chill nighttime songs
Make me a 15 song gym playlist
Show recent tracks
```
## Inbox-Based AI Workflow
Users place untagged MP3 files into the Muganizer Inbox.

The GPT:

1. Detects inbox files
2. Generates metadata
3. Shows metadata to the user
4. Allows confirmation or edits
5. Tags and organizes MP3 files automatically

## Automatic MP3 Tagging
Muganizer embeds:

- Title
- Artist
- Album
- Genre
- Cover artwork

using Mutagen ID3 tagging.

## Automatic Cover Art Embedding
Spotify cover artwork is downloaded and embedded directly into MP3 metadata.

## Multi-Artist Organization
Tracks with featured artists are automatically copied into multiple artist folders.

Example:
```
Travis Scott/UTOPIA/FE!N (feat. Playboi Carti).mp3
Playboi Carti/UTOPIA/FE!N (feat. Playboi Carti).mp3
```

## Semantic Search
Muganizer generates semantic embeddings for tracks using OpenAI embeddings.

Users can search using natural-language prompts such as:
```
late night driving songs
melodic rage rap
sad gym music
```

## AI Playlist Generation
Generate playlists from natural-language prompts.

Example:
```
Make me a 20 song gym playlist
```

## Architecture
```
Custom GPT
↓
GPT Actions
↓
FastAPI
↓
Muganizer Backend
↓
Spotify API + OpenAI API
↓
Local MP3 Library
```

## Tech Stack
Frontend
- Tkinter
- Custom GPT Interface
Backend
- Python
- FastAPI
AI
- OpenAI API
- GPT Actions
- Semantic Embeddings
Music Metadata
- Spotify API
- Mutagen
Database
- SQLite
- Infrastructure
ngrok

## Project Structure
```
Muganizer/
│
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── .env.example
│
├── muganizer_gui.py
├── muganizer_backend.py
├── muganizer_api.py
├── spotify_lookup.py
│
├── muganizer_openapi_schema.yaml
│
├── assets/
│   ├── screenshots/
│   ├── demo.gif
│   └── architecture.png
│
└── docs/
    └── setup_guide.md
```

## Installation
Clone Repository
```
git clone <your-repository-url>
cd Muganizer
```
Install Dependencies
```
python -m pip install -r requirements.txt
```
Configure Environment Variables
- Create a .env file using .env.example.

Start API
```
python -m uvicorn muganizer_api:app --host 127.0.0.1 --port 8000 --reload
```
Start ngrok
```
ngrok http 8000
```
Connect Custom GPT
1. Create a Custom GPT
2. Add Actions
3. Paste the OpenAPI schema
4. Replace the schema URL with your ngrok URL
5. Save the GPT

## Example Workflow
```
1. User drops MP3 into Inbox
2. GPT detects inbox file
3. GPT generates metadata
4. User confirms metadata
5. GPT tags MP3
6. Muganizer embeds artwork
7. Muganizer organizes file
8. Track added to semantic database
```

## Future Improvements
- Direct waveform/audio analysis
- BPM and key detection
- Local LLM support
- Electron/web interface
- Streaming service synchronization
- AI recommendation engine
- Automated duplicate cleanup
- Audio fingerprinting

## License
This project is licensed under the MIT License.
