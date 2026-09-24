# VenueMatch Setlist.fm Historical Coverage Probe

Generated: 2026-09-24T04:46:41.591476+00:00<br>
As-of date: 2026-09-24<br>
Mode: transient read-only probe; no Setlist.fm event records persisted

## Decision

**SETLIST_PERMISSION_REQUIRED_FOR_TRAINING**

Explicit Setlist.fm permission required before permanent storage or ML training: **True**

## Coverage Summary

- Artists sampled / queried: **193 / 193**
- Artists with history: **182**
- Unique historical performances: **7,400**
- Performances in / outside / unresolved for current markets: **1,607 / 5,793 / 0**
- Additional historical relationships: **586**
- Venue-resolution rate in current markets: **46.2%**
- Oldest / newest: **1966-08-13 / 2026-09-23**
- September 2025 through June 2026 additions: **259**

## Request Metrics

```json
{
  "requests": 424,
  "retries": 6,
  "throttles": 6,
  "not_found": 11,
  "status_counts": {
    "200": 407,
    "404": 11,
    "429": 6
  },
  "rate_limit_headers": {},
  "average_records_per_request": 17.646,
  "average_pages_per_artist": 2.14,
  "maximum_pages_for_one_artist": 8,
  "artists_at_page_cap": 52,
  "unaggregated_successful_requests": 5,
  "hard_request_cap": 500,
  "request_cap_respected": true
}
```

## Historical Windows

| historical_window | unique_performances | performances_in_current_markets | additional_relationships | exact_high_venue_resolutions |
| --- | --- | --- | --- | --- |
| 0-3 months | 1684 | 464 | 88 | 244 |
| 3-6 months | 1118 | 224 | 103 | 103 |
| 6-12 months | 1464 | 297 | 137 | 137 |
| 12-24 months | 2144 | 386 | 172 | 172 |
| 24+ months | 990 | 236 | 86 | 86 |

## Market Coverage

| market | historical_performances | additional_relationships | unique_artists | unique_resolved_venues | oldest_event_date | newest_event_date | exact_high_venue_resolutions | candidate_venues | months_of_temporal_depth | exact_high_venue_resolution_rate | dense_6_month_coverage | dense_12_month_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Atlanta, GA | 116 | 32 | 26 | 3 | 2024-02-08 | 2026-09-16 | 40 | 34 | 31.5 | 0.3448 | True | True |
| Austin, TX | 96 | 16 | 14 | 2 | 2025-06-07 | 2026-08-29 | 17 | 26 | 15.6 | 0.1771 | False | False |
| Baltimore, MD | 59 | 22 | 18 | 2 | 2023-11-14 | 2026-07-18 | 42 | 12 | 34.3 | 0.7119 | False | False |
| Boston, MA | 70 | 22 | 19 | 2 | 2024-06-04 | 2026-08-02 | 30 | 18 | 27.7 | 0.4286 | False | False |
| Buffalo, NY | 33 | 26 | 23 | 2 | 2023-06-26 | 2026-09-17 | 28 | 12 | 39.0 | 0.8485 | False | False |
| Chicago, IL | 169 | 69 | 43 | 6 | 2004-12-17 | 2026-09-21 | 73 | 53 | 261.2 | 0.432 | True | True |
| Cleveland, OH | 35 | 3 | 3 | 2 | 2025-10-28 | 2026-07-18 | 5 | 15 | 10.9 | 0.1429 | False | False |
| Dallas, TX | 80 | 38 | 29 | 3 | 2017-12-17 | 2026-09-04 | 41 | 21 | 105.2 | 0.5125 | True | True |
| Detroit, MI | 72 | 30 | 25 | 3 | 2008-09-07 | 2026-08-10 | 39 | 26 | 216.5 | 0.5417 | True | True |
| Los Angeles, CA | 166 | 62 | 48 | 3 | 2018-06-24 | 2026-09-18 | 65 | 41 | 99.0 | 0.3916 | True | True |
| Nashville, TN | 107 | 51 | 35 | 3 | 2023-11-14 | 2026-09-17 | 58 | 24 | 34.3 | 0.5421 | True | True |
| New York, NY | 140 | 38 | 22 | 3 | 2017-04-21 | 2026-07-25 | 58 | 51 | 113.1 | 0.4143 | True | True |
| Newark, NJ | 8 | 7 | 7 | 1 | 2024-09-09 | 2026-07-21 | 8 | 3 | 24.5 | 1.0 | False | False |
| Philadelphia, PA | 98 | 24 | 20 | 3 | 2024-02-16 | 2026-07-30 | 44 | 28 | 31.2 | 0.449 | True | True |
| Pittsburgh, PA | 35 | 7 | 7 | 1 | 2024-06-02 | 2026-06-05 | 14 | 15 | 27.7 | 0.4 | False | False |
| Richmond, VA | 42 | 14 | 12 | 3 | 2024-06-22 | 2026-09-15 | 21 | 13 | 27.1 | 0.5 | False | False |
| San Francisco, CA | 97 | 50 | 39 | 3 | 2019-12-18 | 2026-09-10 | 64 | 30 | 81.2 | 0.6598 | True | True |
| Seattle, WA | 91 | 35 | 30 | 2 | 2024-03-07 | 2026-09-10 | 41 | 25 | 30.6 | 0.4505 | False | False |
| Washington, DC | 93 | 40 | 32 | 3 | 2022-07-23 | 2026-09-20 | 54 | 21 | 50.1 | 0.5806 | True | True |

## Provider Overlap

| category | performance_count |
| --- | --- |
| already_known | 159 |
| already_known_jambase | 70 |
| already_known_musicbrainz | 0 |
| already_known_ticketmaster | 150 |
| ambiguous | 6570 |
| likely_duplicate | 85 |
| setlist_only | 586 |

## Projected Full Coverage

```json
{
  "eligible_musicbrainz_mapped_artists": 193,
  "projected_additional_usable_relationships": 586,
  "projected_pre_july_2026_training_relationships": 510,
  "combined_usable_historical_relationships": 9629,
  "projected_held_out_relationships": 8531,
  "projected_markets_with_dense_6_month_coverage": 10,
  "projected_markets_with_dense_12_month_coverage": 10,
  "average_historical_events_per_represented_market": 30.84,
  "average_candidate_venues_per_represented_market": 24.63,
  "candidate_set_viable": true,
  "estimated_requests_for_all_current_mbid_artists": 424,
  "theoretical_requests_if_all_artists_had_mbids": 12127,
  "estimated_runtime_minutes_current_mbid_artists": 7.1,
  "current_allowance_appears_sufficient": true,
  "allowance_note": "Probe used 424 of the 500-request safety cap; 6 HTTP 429 responses were handled conservatively."
}
```

## Decision Checks

```json
{
  "usable_historical_examples": true,
  "held_out_examples": true,
  "markets_with_6_months": true,
  "markets_with_12_months_preferred": true,
  "candidate_venues": true
}
```

## Data Handling

No API key, raw response, setlist, song, per-artist response, event-level performance row, or Setlist.fm venue list is retained in these artifacts. Event-level objects existed only in process memory and were cleared after aggregate calculation. Setlist.fm permission is required before any durable storage or training use.
