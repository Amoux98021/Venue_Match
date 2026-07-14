# VenueMatch

VenueMatch is a Python-first MVP that recommends concert venues for artists and artists for venues using a transparent rule-based scoring engine backed by SQLite and a Streamlit demo.

## MVP capabilities

- Artist-to-venue ranking by city
- Venue-to-artist and city-to-artist discovery
- Transparent scoring across genre fit, venue history, city demand, capacity fit, and artist popularity
- Local SQLite database with seed data for Washington DC, Baltimore, Philadelphia, New York, and College Park
- Modular API client stubs and ingestion scripts for official/public data sources
- Baseline ML training placeholder for future supervised ranking

## Project structure

```text
venuematch/
  app.py
  README.md
  .env.template
  requirements.txt
  data/
    raw/
    processed/
    sample/
  scripts/
  src/
    clients/
    db/
    features/
    models/
    scoring/
    utils/
```

## Setup

```bash
cd venuematch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
streamlit run app.py
```

The app runs without API keys by automatically creating and using the bundled mock dataset.

## Environment variables

- `TICKETMASTER_API_KEY`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `LASTFM_API_KEY`
- `MUSICBRAINZ_USER_AGENT`
- `CENSUS_API_KEY`
- `JAMBASE_API_KEY` optional
- `DATABASE_URL` optional, defaults to local SQLite

## Data sources and safety

VenueMatch is designed to use official APIs or public datasets only. No private ticket sales data is scraped or required for this MVP.

- Ticketmaster Discovery API
- Spotify Web API
- Last.fm API
- MusicBrainz API
- U.S. Census API

## Seed data

If API credentials are unavailable, VenueMatch loads sample records for:

- Washington, DC
- Baltimore, MD
- Philadelphia, PA
- New York, NY
- College Park, MD

The sample data lives in `data/sample/mock_data.json`.

## Database schema

The SQLite schema includes:

- `artists`
- `venues`
- `events`
- `artist_genres`
- `city_demographics`
- `city_genre_signals`
- `venue_genre_history`
- `recommendations`

## Ingestion scripts

Scripts live in `scripts/` and can write normalized data into SQLite:

- `ingest_ticketmaster.py`
- `ingest_spotify.py`
- `ingest_lastfm.py`
- `ingest_musicbrainz.py`
- `ingest_census.py`

Each script supports a safe fallback path when keys are missing so local development is not blocked.

## Rule-based scoring

The recommender uses this weighted formula:

```text
final_score =
  0.35 * genre_fit_score +
  0.25 * venue_history_score +
  0.20 * city_demand_score +
  0.10 * capacity_fit_score +
  0.10 * artist_popularity_score
```

Genre fit is based on normalized overlap between artist genres, venue history, and city genre signals.

## ML placeholder

`src/models/train_baseline.py` prepares features from historical events and only trains a simple baseline classifier if enough labeled rows exist.

## Demo notes

The Streamlit app includes:

- Artist-to-venue tab
- Venue-to-artist tab
- City dashboard tab
- Explanation panel
- Raw data preview

## Common commands

Initialize the local database and seed sample data:

```bash
python scripts/seed_sample_data.py
```

Run the baseline trainer:

```bash
python src/models/train_baseline.py
```
