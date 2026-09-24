# VenueMatch MusicBrainz Historical Coverage Probe

Generated: 2026-09-24T03:02:33.007505+00:00  
As-of date: 2026-09-24  
Mode: read-only; no production event writes

## Decision

**MUSICBRAINZ_PARTIAL_ENRICHMENT_ONLY**

Setlist.fm still needed before the final historical benchmark: **True**

## Coverage Summary

- API requests used: **170**
- Request breakdown: **101 artist-event / 49 place-search / 20 place-event**
- Artists sampled / successfully queried: **100 / 100**
- Artists with historical events: **59**
- MusicBrainz places mapped: **20**
- Unique historical events: **988**
- Events in current markets: **379**
- Events resolving to existing artists / venues: **774 / 320**
- Already-known / MusicBrainz-only events: **9 / 144**
- Additional historical relationships: **193**
- Oldest / newest: **1957-07-04 / 2026-09-23**
- Venue-resolution success rate: **13.5%**
- Current-market venue-resolution success rate: **61.5%**
- Markets with at least 6 months: **16**
- Markets with at least 12 months: **16**
- Events older than 6 months / 12 months: **861 / 796**

## Sample Profile

```json
{
  "history_bands": {
    "high": 21,
    "low": 14,
    "medium": 65
  },
  "mapped_place_markets": 12,
  "provider_bias": {
    "jambase-heavy": 21,
    "ticketmaster-heavy": 79
  },
  "represented_artist_markets": 17,
  "represented_primary_genres": 57
}
```

## Entity Resolution

```json
{
  "artist": {
    "exact": 708,
    "medium": 714,
    "unresolved": 2953
  },
  "venue": {
    "exact": 434,
    "high": 157,
    "medium": 3,
    "unresolved": 3781
  }
}
```

## Lookback Counts

```json
{
  "0-3 months": 42,
  "12-24 months": 196,
  "24+ months": 600,
  "3-6 months": 38,
  "6-12 months": 65
}
```

## Market Results

| market | additional_events | additional_relationships | unique_artists | unique_resolved_venues | oldest_event_date | months_of_temporal_depth | exact_high_venue_resolution_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Atlanta, GA | 10 | 14 | 11 | 4 | 2011-10-02 | 179.7 | 0.8636 |
| Austin, TX | 8 | 10 | 10 | 3 | 2012-04-29 | 172.8 | 0.1649 |
| Baltimore, MD | 2 | 2 | 2 | 2 | 2024-11-09 | 22.5 | 1.0 |
| Buffalo, NY | 7 | 14 | 13 | 3 | 2015-10-31 | 130.8 | 0.9545 |
| Chicago, IL | 11 | 18 | 15 | 4 | 2007-10-21 | 227.1 | 0.5714 |
| Cleveland, OH | 5 | 11 | 11 | 2 | 2001-08-07 | 301.5 | 1.0 |
| Dallas, TX | 23 | 28 | 19 | 2 | 1993-08-06 | 397.6 | 0.7901 |
| Detroit, MI | 3 | 4 | 4 | 2 | 2018-06-26 | 98.9 | 0.625 |
| Los Angeles, CA | 0 | 0 | 0 | 0 | None | 0.0 | 0.0 |
| Nashville, TN | 5 | 6 | 3 | 2 | 2018-06-12 | 99.4 | 0.4118 |
| New York, NY | 2 | 2 | 2 | 1 | 2018-07-01 | 98.8 | 0.9231 |
| Newark, NJ | 18 | 21 | 14 | 1 | 2012-07-02 | 170.7 | 1.0 |
| Philadelphia, PA | 11 | 13 | 12 | 5 | 2017-11-16 | 106.2 | 0.76 |
| Pittsburgh, PA | 9 | 12 | 6 | 2 | 2011-08-12 | 181.4 | 0.8947 |
| Richmond, VA | 0 | 0 | 0 | 0 | None | 0.0 | 1.0 |
| San Francisco, CA | 7 | 8 | 5 | 4 | 2016-09-17 | 120.2 | 0.12 |
| Seattle, WA | 8 | 12 | 8 | 5 | 2018-07-07 | 98.6 | 0.2609 |
| Washington, DC | 15 | 18 | 16 | 5 | 1998-04-21 | 341.1 | 0.9577 |

## Provider Overlap

| category | event_count | relationship_count |
| --- | --- | --- |
| already_known | 9 | 16 |
| musicbrainz_only | 144 | 193 |
| likely_duplicate | 0 | 0 |
| ambiguous | 826 | 4166 |
| already_known_jambase | 8 | 14 |
| already_known_ticketmaster | 9 | 15 |

## Projected Full Backfill

```json
{
  "artist_backfill_api_call_estimate": 195,
  "artist_plus_mapping_and_venue_event_call_estimate": 1133,
  "artist_plus_place_mapping_call_estimate": 664,
  "artist_plus_place_mapping_runtime_minutes": 11.6,
  "average_artist_api_requests": 1.01,
  "eligible_musicbrainz_mapped_artists": 193,
  "expanded_runtime_minutes": 19.8,
  "expected_markets_with_12_months": 16,
  "expected_markets_with_6_months": 16,
  "expected_oldest_event_date": "1957-07-04",
  "optional_venue_event_calls": 469,
  "projected_0_3_month_relationships": 19,
  "projected_additional_historical_relationships": 372,
  "projection_note": "Market projections are conservative lower bounds from observed sample markets.",
  "runtime_hours_at_rate_limit": 0.06,
  "runtime_seconds_at_rate_limit": 205,
  "sample_successful_artists": 100,
  "venue_place_mapping_search_calls": 469
}
```

## Decision Checks

```json
{
  "future_held_out_examples": false,
  "markets_with_12_months_preferred": true,
  "markets_with_6_months": true,
  "usable_relationships_after_enrichment": true,
  "venue_resolution_quality": true
}
```

## Recommended Next Action

Use MusicBrainz as a partial historical enrichment source after expanding place mappings, but do not rely on it as the sole benchmark source. The all-artist projection adds approximately **372** usable relationships and only **19** recent held-out relationships, which is below the benchmark target. Proceed with Setlist.fm enrichment before the final historical recommendation benchmark.
