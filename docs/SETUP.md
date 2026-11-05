# Setup and reference

Everything you need to run Innerbloom on your own computer, choose a model, and talk to its API.

- [Install](#install)
- [Try it with sample data](#try-it-with-sample-data)
- [Picking a model](#picking-a-model)
- [Settings](#settings)
- [Using Google Gemini instead](#using-google-gemini-instead)
- [Spotify (optional)](#spotify-optional)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Tests](#tests)
- [API reference](#api-reference)
- [The public demo](#the-public-demo)

## Install

You need **Python 3.10+** and **[Ollama](https://ollama.ai)**.

```bash
git clone https://github.com/GhanshyamPaunikar/innerbloom.git
cd innerbloom
pip install -r requirements.txt
```

Start Ollama and pull a chat model and an embedding model:

```bash
ollama serve
# in another terminal
ollama pull qwen2.5:7b
ollama pull mxbai-embed-large
```

Start Innerbloom:

```bash
python run_local.py
# open http://127.0.0.1:5000/app
```

One small server runs the page and the API, bound to this computer only. It serves `index.html` and `assets/`, never the repository or `./data/`, where your journal lives. On macOS, if AirPlay Receiver already uses port 5000, add `--port 5500`.

## Try it with sample data

```bash
python run_local.py --demo --port 8766
# open http://127.0.0.1:8766/app
```

The preview uses temporary fictional entries and clearly labelled simulated AI. It never reads `./data/`, needs no Ollama, and forgets everything when it stops.

## Picking a model

The default is **`qwen2.5:7b`**, the best quality that fits in 8 GB of RAM. A different model only changes quality; every feature works at any size.

| Model | RAM | Speed (M1) | What gets better |
| --- | --- | --- | --- |
| `llama3.2:3b` | 8 GB | about 30 tok/s | Fast, but robotic, and invents intentions. Fine for trying it out. |
| `qwen2.5:7b` (default) | 8 GB, tight | about 15 tok/s | The right starting point. Chat feels human; contradictions are grounded in real text. |
| `mistral:7b-instruct` | 8 GB, tight | about 18 tok/s | Drier voice, strong at triggers. |
| `llama3.1:8b` | 16 GB ideal | about 10 tok/s | Sharper long-range story. Background use only on 8 GB. |
| `qwen2.5:14b` | 16 GB or more | about 4 tok/s | Therapist-grade nuance. Chat is slow. |
| `gpt-oss:20b`, `mixtral:8x7b` | 24 to 48 GB | 2 to 6 tok/s | The story and wellbeing summaries become worth rereading. |

```bash
ollama pull llama3.1:8b
INNERBLOOM_MODEL=llama3.1:8b python run_local.py
```

**The embedding model matters most.** Without `mxbai-embed-large` (or `nomic-embed-text`), search falls back to keywords. With it, "when did I feel unappreciated?" finds entries about being overlooked, even when neither word appears.

## Settings

All optional, as environment variables:

```bash
INNERBLOOM_MODEL=qwen2.5:7b                                       # chat model
INNERBLOOM_EMBED_MODEL=mxbai-embed-large                          # embedding model
INNERBLOOM_OLLAMA_URL=http://localhost:11434/api/generate         # generation
INNERBLOOM_OLLAMA_EMBED_URL=http://localhost:11434/api/embeddings # embeddings
INNERBLOOM_OLLAMA_TAGS_URL=http://localhost:11434/api/tags        # model list and health
INNERBLOOM_DATA_DIR=./data                                        # where your journal is stored
```

## Using Google Gemini instead

```bash
INNERBLOOM_PROVIDER=gemini                     # default: ollama
GEMINI_API_KEY=...                             # from aistudio.google.com
INNERBLOOM_MODEL=gemini-flash-lite-latest      # default with Gemini
INNERBLOOM_EMBED_MODEL=gemini-embedding-001    # default with Gemini
```

Your entries and questions are then sent to Google for analysis. Keep Ollama for a fully private journal.

## Spotify (optional)

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard), create an app and copy its **Client ID**.
2. In Innerbloom's **Settings**, paste the Client ID and note the redirect address shown, for example `http://127.0.0.1:5500/index.html` when started with `--port 5500`.
3. Add that exact redirect address to your Spotify app.
4. Click **Connect Spotify**.

Innerbloom uses PKCE with a checked `state` value, so no client secret is needed. Your token stays in `./data/` and refreshes itself. Once connected, Music shows your recent and top tracks with album art, genre-based estimates on request, and a reflection on your listening beside your writing.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Cmd/Ctrl + K` | Command palette, jump to any view |
| `Cmd/Ctrl + S` | Save the entry you are writing |
| `Esc` | Close a dialog or the palette |

## Tests

```bash
pip install pytest
python -m pytest -q
```

`python tests/test_app.py` also runs the backend suite on its own and prints each check.

The backend suite runs end to end against FastAPI's `TestClient`, with Ollama and Spotify mocked: entries, chat, the agent loop, insight engines, search, crisis detection, stats, Spotify and People, plus concurrent saves, failed analyses, deleted-entry cleanup and the local-only request rules. The workspace tests check that only the page and its assets are ever served. The demo tests cover private sandboxes, time zones and AI limits.

## API reference

### Entries

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/save` | Create and analyse an entry |
| `GET` | `/journal` | List entries (filters: `q`, `tag`, `emotion`) |
| `GET` | `/journal/{id}` | One entry |
| `PUT` | `/journal/{id}` | Edit |
| `DELETE` | `/journal/{id}` | Delete |
| `POST` | `/journal/reanalyze` | Read again entries whose analysis failed |
| `GET` | `/search?q=` | Keyword and meaning search |
| `GET` | `/export` | Markdown export |

### Chat and agent

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/chat/agent` | Agent loop streamed as JSONL: classify, plan, tools, draft |
| `POST` | `/chat` | One reply with citations |
| `POST` | `/chat/stream` | Token-streamed reply |
| `GET` | `/chat` | History |
| `DELETE` | `/chat` | Clear history |

### Insights and analysis

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/insights/contradictions`, `/triggers`, `/wellbeing`, `/narrative` | Read a cached insight |
| `POST` | `/insights/{engine}/refresh` | Recompute one engine in the background |
| `POST` | `/insights/refresh-all` | Recompute all four |
| `GET` | `/insights/status` | Background progress |
| `GET` | `/analyze` | Long-term synthesis |
| `GET` | `/stats` | Streaks, word counts, mood distribution, daily intensity |
| `GET` | `/graph` | Memory graph: nodes, edges, named clusters |
| `GET` | `/anniversary?days=30` | Then and now reflection |
| `GET` | `/weekly-review`, `/monthly-review` | Period reflections |
| `GET` | `/connections/{id}` | Related past entries |
| `GET` | `/reflect/{id}` | Reflection questions for an entry |
| `POST` | `/reflect/{id}/answers` | Save reflection answers |
| `GET` | `/prompt` | Adaptive writing prompt |

### People

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/people` | Everyone, with stats, CRM fields and signals (`include_hidden` optional) |
| `GET` | `/people/{key}` | One person, with a longer timeline |
| `PUT` | `/people/{key}` | Relationship, birthday, check-in cadence, name, pin or hide |
| `POST` | `/people/{key}/notes` | Add a dated note |
| `DELETE` | `/people/{key}/notes/{note_id}` | Delete a note |
| `POST` | `/people/{key}/checkin` | "I reached out" |

### Spotify (optional)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/spotify/status` | Connection state |
| `POST` | `/spotify/config`, `/exchange`, `/disconnect` | PKCE setup and removal |
| `GET` | `/spotify/recent`, `/top` | Recent plays, top tracks |
| `GET` | `/spotify/genre-mood`, `/insight` | Listening snapshot and AI reflection |

### Health

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | App status and model |
| `GET` | `/health` | Model connection |

## The public demo

The live demo at [ghanshyampaunikar.com/innerbloom](https://ghanshyampaunikar.com/innerbloom) runs this backend with Gemini and `INNERBLOOM_SANDBOX=1`. Each visitor gets a private copy of a fictional 40-day journal (`demo_seed/`), dated so it ends on their today and deleted after six idle hours. Spotify is off, and AI calls are capped per visitor, per IP and per day (`INNERBLOOM_AI_PER_VISITOR`, `INNERBLOOM_AI_PER_IP`, `INNERBLOOM_AI_PER_DAY`).

- `scripts/build_demo_seed.py` rebuilds the sample journal's embeddings and insights.
- `scripts/export_website_demo.py <website folder>` copies the page, backend and sample into the website.
- `scripts/build_readme_media.py` renders the README animations from `docs/media/src`.
