# VenueMatch

VenueMatch is an explainable booking-intelligence product that ranks concert venues for artists and artists for venues. It combines genre alignment, historical booking patterns, local demand, room capacity, and artist popularity without scraping private ticket-sales data.

The production MVP uses a Next.js frontend, a Python FastAPI backend, and either local SQLite or hosted Neon Postgres. Missing API keys automatically activate the bundled sample dataset.

## Architecture

```text
Next.js web app (Vercel)
  -> same-origin /api/backend proxy
FastAPI scoring API (Vercel Python)
  -> SQLAlchemy
SQLite locally / Neon Postgres in production
  -> Ticketmaster, Last.fm, MusicBrainz, Census, JamBase
  -> protected daily ingestion cron
```

## Features

- Artist-to-venue rankings by target city
- Venue-or-city-to-artist rankings
- City dashboard with demographics and genre-demand signals
- Visible score components and plain-language explanations
- Whitelisted raw-data previews
- Automatic sample mode for Washington, Baltimore, Philadelphia, New York, and College Park
- Postgres-ready relational schema and baseline ML training placeholder
- Idempotent live-data ingestion with bounded event retention

## Local setup

### 1. Backend

```bash
cd venuematch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
python scripts/init_database.py
python -m uvicorn app:app --reload --port 8000
```

FastAPI docs are available at `http://127.0.0.1:8000/docs`.

### 2. Frontend

In a second terminal:

```bash
cd venuematch/web
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

## Environment variables

Backend `.env`:

```dotenv
DATABASE_URL=sqlite:///data/processed/venuematch.db
TICKETMASTER_API_KEY=
LASTFM_API_KEY=
MUSICBRAINZ_USER_AGENT=VenueMatch/1.0 (your-email@example.com)
CENSUS_API_KEY=
CENSUS_ACS_YEAR=2024
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
JAMBASE_API_KEY=
ALLOWED_ORIGINS=http://localhost:3000
CRON_SECRET=
```

Frontend `web/.env.local`:

```dotenv
VENUE_MATCH_API_URL=http://127.0.0.1:8000
```

Spotify is optional enrichment. VenueMatch uses Last.fm listeners/play counts and event frequency as its primary popularity signals so Spotify restrictions do not block the product.

## Live data ingestion

Run a refresh locally after configuring API credentials and `DATABASE_URL`:

```bash
python scripts/ingest_live.py
```

Production exposes `GET /ingestion/sync`, protected by `CRON_SECRET`. Vercel calls it once daily at approximately 07:00 UTC. Each refresh:

- requests up to 75 upcoming music events for each launch city
- upserts artists, venues, events, tags, and Census demographics
- resolves Ticketmaster venue IDs through JamBase and stores maximum capacity with provenance
- rebuilds city-demand and venue-booking signals from normalized event rows
- retains one year of Ticketmaster event records and stores no raw API responses

JamBase capacity checks are cached for 30 days to protect the API quota. Capacity values use JamBase's `maximumAttendeeCapacity` field and keep the source record, URL, and retrieval timestamp in `venue_capacity_sources`. JamBase attribution is displayed beside sourced capacities in the recommendation interface.

`GET /ingestion/status` reports table counts, the latest run, and Postgres database size. The Neon Free plan currently allows 0.5 GB per project, so the bounded normalized dataset is intentionally much smaller than the available storage.

## Scoring model

```text
final_score =
  0.35 * genre_fit_score +
  0.25 * venue_history_score +
  0.20 * city_demand_score +
  0.10 * capacity_fit_score +
  0.10 * artist_popularity_score
```

Genre fit uses normalized overlap between artist tags, venue history, and city signals. Unknown venue capacity receives a neutral-low score and an explicit reduced-confidence explanation.

## API endpoints

- `GET /health`
- `GET /meta/options`
- `POST /recommendations/artist-to-venue`
- `POST /recommendations/venue-to-artist`
- `GET /cities/{city}/dashboard`
- `GET /raw/{dataset}`

## Neon and Vercel deployment

Create two Vercel projects from the same GitHub repository. This avoids relying on Vercel Services private beta.

### Backend project

1. Import the repository into Vercel.
2. Set the Root Directory to `venuematch`.
3. Vercel detects `api/index.py` as a FastAPI Python Function.
4. Install Neon from Vercel Marketplace and attach it to this project.
5. Set `DATABASE_URL` to Neon's pooled connection string.
6. Add the API variables from `.env.template`.
7. Set `ALLOWED_ORIGINS` to the frontend production URL.

The backend creates missing tables automatically and loads sample data only when the database is empty.

### Frontend project

1. Import the same repository as a second Vercel project.
2. Set the Root Directory to `venuematch/web`.
3. Set `VENUE_MATCH_API_URL` to the backend Vercel URL without a trailing slash.
4. Deploy using the detected Next.js settings.

All provider keys stay in the backend project. Browser requests pass through the server-side Next.js proxy.

Vercel Hobby is suitable for a personal, non-commercial demo. Review Vercel and provider commercial terms before launching a paid product.

## Data ingestion

The scripts under `scripts/` use official APIs and write raw snapshots under `data/raw/`:

- `ingest_ticketmaster.py`
- `ingest_lastfm.py`
- `ingest_musicbrainz.py`
- `ingest_census.py`
- `ingest_spotify.py` (optional)

Venue capacity should be curated from official venue sources with a source URL and verification date. Do not scrape private inventory or ticket-sales systems.

## Verification

```bash
python -m pytest
python src/models/train_baseline.py
cd web
npm run lint
npm run build
npm audit
```
