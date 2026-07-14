# VenueMatch

VenueMatch is an explainable artist-and-venue matching product built with Next.js, FastAPI, and SQL. It ranks booking opportunities using genre fit, venue history, city demand, capacity fit, and artist popularity.

The app runs immediately with bundled seed data and is ready for Ticketmaster, Last.fm, MusicBrainz, Census, Neon Postgres, and Vercel configuration.

See the [application README](venuematch/README.md) for architecture, local setup, API documentation, and deployment instructions.

```bash
cd venuematch
python -m uvicorn app:app --reload --port 8000

# In a second terminal
cd venuematch/web
npm run dev
```
