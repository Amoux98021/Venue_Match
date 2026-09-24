# VenueMatch Historical Data Audit

Generated: 2026-09-24T00:25:15.426069+00:00  
As-of date: 2026-09-23  
Unit: artist-event-venue relationship  
Mode: read-only

## Executive Summary

- Total relationships: **14,568**
- Historical relationships: **8,715**
- Current/future relationships: **5,853**
- Missing-date relationships: **0**
- Historical range: **2026-07-14** through **2026-09-22**
- Benchmark-eligible historical bookings: **8,671**
- Eligible with at least five candidates: **8,531**
- Useful markets: **0**
- Median candidate count: **22.0**
- Setlist.fm decision: **SETLIST_ENRICHMENT_RECOMMENDED**
- Failed readiness thresholds: **useful_markets, historical_depth_days**

## Temporal Coverage

- Historical depth: 70 days
- Distinct months: 3
- Distinct years: 1

## Provider Coverage

| Provider | Relationships | Historical | Earliest | Latest | Artists | Venues | Markets |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ticketmaster | 8405 | 6237 | 2026-07-14 | 2027-03-19 | 4154 | 469 | 20 |
| jambase | 6163 | 2478 | 2026-07-27 | 2027-02-06 | 3127 | 140 | 10 |

MusicBrainz enriches artist identity but is not stored as an event relationship source. The audit does not infer provider provenance that is absent from `events.source`.

## Market Coverage

| Market | Target | Historical | Future | Artists | Venues | Eligible | Mean candidates | Useful |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| New York, NY | True | 1972 | 849 | 939 | 50 | 1972 | 36.19 | False |
| Philadelphia, PA | True | 909 | 647 | 582 | 27 | 908 | 20.72 | False |
| Atlanta, GA | True | 903 | 912 | 590 | 33 | 903 | 27.62 | False |
| Washington, DC | True | 668 | 464 | 401 | 14 | 666 | 11.36 | False |
| Boston, MA | True | 621 | 645 | 365 | 18 | 621 | 14.38 | False |
| Los Angeles, CA | True | 568 | 125 | 480 | 37 | 568 | 30.69 | False |
| Chicago, IL | True | 535 | 87 | 449 | 52 | 534 | 36.89 | False |
| Nashville, TN | True | 432 | 72 | 325 | 23 | 432 | 16.0 | False |
| Dallas, TX | True | 298 | 117 | 266 | 20 | 297 | 17.49 | False |
| Richmond, VA | True | 292 | 290 | 168 | 11 | 290 | 7.72 | False |
| Baltimore, MD | True | 251 | 292 | 178 | 8 | 249 | 7.52 | False |
| Detroit, MI | True | 227 | 114 | 220 | 23 | 225 | 16.98 | False |
| San Francisco, CA | True | 221 | 110 | 196 | 29 | 221 | 20.53 | False |
| Seattle, WA | True | 192 | 105 | 174 | 24 | 192 | 18.99 | False |
| Austin, TX | True | 183 | 202 | 170 | 22 | 181 | 16.5 | False |
| Cleveland, OH | True | 152 | 82 | 142 | 14 | 152 | 11.72 | False |
| Buffalo, NY | True | 147 | 266 | 107 | 11 | 147 | 7.53 | False |
| Pittsburgh, PA | True | 114 | 337 | 75 | 11 | 113 | 8.75 | False |
| Newark, NJ | True | 30 | 135 | 18 | 1 | 0 | 0.0 | False |
| College Park, MD | True | 0 | 0 | 0 | 0 | 0 | 0.0 | False |
| Hollywood, CA | False | 0 | 2 | 0 | 0 | 0 | 0.0 | False |

A useful market has at least 50 eligible relationships, six historical months, and a mean candidate set of at least five venues.

## Artist Coverage

```json
{
  "total_artists": 5520,
  "artists_with_1_plus": 3724,
  "artists_with_2_plus": 1676,
  "artists_with_3_plus": 908,
  "artists_with_5_plus": 429,
  "artists_with_10_plus": 103,
  "median_historical_bookings_per_artist_with_history": 1.0,
  "mean_historical_bookings_per_artist_with_history": 2.34,
  "percent_with_musicbrainz_id": 3.5,
  "percent_with_genre_data": 87.03,
  "percent_with_lastfm_audience_data": 8.95,
  "percent_with_artist_popularity": 8.95,
  "top_25_artists": [
    {
      "id": "artist_e5be3232ee55514db9d6b448285ecc0c",
      "name": "Vince Giordano and the Nighthawks",
      "historical_booking_count": 72
    },
    {
      "id": "artist_5ea2984c7a9c5b5883a0a9a3d5015125",
      "name": "Grand Ole Opry",
      "historical_booking_count": 29
    },
    {
      "id": "artist_f5d0bf8b198d565395fd55d24e6f250e",
      "name": "Harry Styles",
      "historical_booking_count": 24
    },
    {
      "id": "artist_fcad151fe6b65cddb5749388c526cad5",
      "name": "Jamie xx",
      "historical_booking_count": 24
    },
    {
      "id": "artist_49b76d6198745fff97c09bf6f97f3229",
      "name": "Lonnie Plaxico",
      "historical_booking_count": 24
    },
    {
      "id": "artist_6e2dce698200511c98ba2d977b1d8965",
      "name": "RUSH",
      "historical_booking_count": 22
    },
    {
      "id": "artist_5ec8913fbd0f5770b536ecd5a75b78e1",
      "name": "J. Cole",
      "historical_booking_count": 21
    },
    {
      "id": "artist_d4ba0964408a513ba78cd9b76e828eb7",
      "name": "Eliane Elias",
      "historical_booking_count": 20
    },
    {
      "id": "artist_9708995083dc5bdda95e3af58b0c61d8",
      "name": "Eric Harland",
      "historical_booking_count": 20
    },
    {
      "id": "artist_3811588eab8059d58aac0fe85ef78d89",
      "name": "Ethan Iverson",
      "historical_booking_count": 20
    },
    {
      "id": "artist_f7f82a189c0c52c1bb2c1bffd5a3ea9d",
      "name": "Greg Osby",
      "historical_booking_count": 20
    },
    {
      "id": "artist_71127abe019d5ed7b71d3a1a2b87ecab",
      "name": "John Pizzarelli",
      "historical_booking_count": 20
    },
    {
      "id": "artist_81873c1b04f05f61ab0771ec633a8158",
      "name": "Monty Alexander",
      "historical_booking_count": 20
    },
    {
      "id": "artist_bddc2affb9c55a449b7a48f62fdde796",
      "name": "Bill Charlap",
      "historical_booking_count": 19
    },
    {
      "id": "artist_13a1092bde0154b5a5c325917cb7196b",
      "name": "Renee Rosnes",
      "historical_booking_count": 19
    },
    {
      "id": "artist_0503809a39095a7fb8f9be37570d1939",
      "name": "Noname",
      "historical_booking_count": 18
    },
    {
      "id": "artist_c5792fa300035e0aa66f18f1a82051fc",
      "name": "Arturo Sandoval",
      "historical_booking_count": 17
    },
    {
      "id": "artist_18465a9b03685719a91f29642767000f",
      "name": "Frank Vignola",
      "historical_booking_count": 17
    },
    {
      "id": "artist_55a2839e731451df8e0a6053fa5cb397",
      "name": "Sam Barber",
      "historical_booking_count": 17
    },
    {
      "id": "artist_05ef684375d651919208b5b8235beb1e",
      "name": "Chance The Rapper",
      "historical_booking_count": 16
    },
    {
      "id": "artist_5c60ba32bd6f5e879801e9d1dd75ac1a",
      "name": "Dogstar",
      "historical_booking_count": 16
    },
    {
      "id": "artist_d279a673f0eb5287aa20057dfea9aa3e",
      "name": "Kacey Musgraves",
      "historical_booking_count": 16
    },
    {
      "id": "artist_b7827cbf26885ee0aa2c5529a79931ef",
      "name": "Koe Wetzel",
      "historical_booking_count": 16
    },
    {
      "id": "artist_00539aa7e2d65a39bb086c3cd36d51cb",
      "name": "Sara Bareilles",
      "historical_booking_count": 16
    },
    {
      "id": "artist_deafa6dbad67514c811b2e62fdf85333",
      "name": "Citizen",
      "historical_booking_count": 15
    }
  ],
  "lastfm_limitation": "The schema stores Last.fm listener counts but does not currently store Last.fm playcount."
}
```

## Venue Coverage

```json
{
  "total_venues": 469,
  "venues_with_1_plus": 428,
  "venues_with_5_plus": 277,
  "venues_with_10_plus": 200,
  "venues_with_25_plus": 110,
  "venues_with_50_plus": 51,
  "median_historical_bookings_per_venue_with_history": 8.0,
  "mean_historical_bookings_per_venue_with_history": 20.36,
  "percent_with_capacity": 57.14,
  "percent_with_genre_history": 91.47,
  "percent_with_coordinates": 0.64,
  "percent_with_resolved_market": 100.0,
  "top_25_venues": [
    {
      "id": "venue_31eefdec70fc5096bf6113b193bd1f9a",
      "name": "Mercury Lounge",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 324
    },
    {
      "id": "venue_8ccb4766d80751ef9e810fe4a03c79b2",
      "name": "Birdland Jazz Club",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 243
    },
    {
      "id": "venue_7cba0912c7ce538ebf207c546f35b561",
      "name": "Birdland Theater",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 167
    },
    {
      "id": "venue_892509c4c54a52e9ac5c3131a0748ffa",
      "name": "Blue Note Jazz Club",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 154
    },
    {
      "id": "venue_de84c46f201355799edd42a90bc1acac",
      "name": "Madison Square Garden",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 148
    },
    {
      "id": "venue_2cf82a5316c953a8abca86b10f4f6e4c",
      "name": "The Foundry",
      "city": "Philadelphia",
      "state": "PA",
      "historical_booking_count": 126
    },
    {
      "id": "venue_c8a6caa2b0ee5726bcd957ed4815772f",
      "name": "Union Stage",
      "city": "Washington",
      "state": "DC",
      "historical_booking_count": 119
    },
    {
      "id": "venue_21650d69c8795480957b40ac202cde80",
      "name": "9:30 CLUB",
      "city": "Washington",
      "state": "DC",
      "historical_booking_count": 116
    },
    {
      "id": "venue_f38cdcf8f66c5dd68f1d6be083a42bf4",
      "name": "The Anthem",
      "city": "Washington",
      "state": "DC",
      "historical_booking_count": 116
    },
    {
      "id": "venue_569025f1990d55da9953692bc97b64be",
      "name": "The Rooftop at Pier 17",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 109
    },
    {
      "id": "venue_742bad6fda7f583b86ae7832a10d3b5e",
      "name": "The Atlantis",
      "city": "Washington",
      "state": "DC",
      "historical_booking_count": 102
    },
    {
      "id": "venue_57588640f8c354b4b1c98865eeb77664",
      "name": "Bowery Ballroom",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 95
    },
    {
      "id": "venue_a92520ce0b0e50e3b23f2863312bb193",
      "name": "MGM Music Hall at Fenway",
      "city": "Boston",
      "state": "MA",
      "historical_booking_count": 89
    },
    {
      "id": "venue_ef90d9e3cdac5c6ea4803e847879604e",
      "name": "Brighton Music Hall presented by Citizens",
      "city": "Boston",
      "state": "MA",
      "historical_booking_count": 88
    },
    {
      "id": "venue_ad767fe4d06159a2903aa2fedb21c9f9",
      "name": "The Moroccan Lounge",
      "city": "Los Angeles",
      "state": "CA",
      "historical_booking_count": 88
    },
    {
      "id": "venue_41403626a1e05c0ea0a12a99284d4d29",
      "name": "Echostage",
      "city": "Washington",
      "state": "DC",
      "historical_booking_count": 84
    },
    {
      "id": "venue_0950497125f05c899e92886c7854f8f0",
      "name": "MilkBoy Philadelphia",
      "city": "Philadelphia",
      "state": "PA",
      "historical_booking_count": 83
    },
    {
      "id": "venue_a5a6bd021b485f348e3db5455052f9b7",
      "name": "The Fillmore Philadelphia",
      "city": "Philadelphia",
      "state": "PA",
      "historical_booking_count": 83
    },
    {
      "id": "venue_ca615294ac9c50e4b64ace1e8ef8f37a",
      "name": "The Masquerade - Purgatory",
      "city": "Atlanta",
      "state": "GA",
      "historical_booking_count": 81
    },
    {
      "id": "venue_ea65775386fc592b90704bac950d1ecc",
      "name": "Gramercy Theatre",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 78
    },
    {
      "id": "venue_c1364959355c59f087807bf5a4962904",
      "name": "Citizens House of Blues Boston",
      "city": "Boston",
      "state": "MA",
      "historical_booking_count": 73
    },
    {
      "id": "venue_df8f6616124f595cacf8816ee2a46918",
      "name": "Big Night Live",
      "city": "Boston",
      "state": "MA",
      "historical_booking_count": 71
    },
    {
      "id": "venue_87281a5b99705e919ea287429e455826",
      "name": "TD Pavilion at Highmark Mann",
      "city": "Philadelphia",
      "state": "PA",
      "historical_booking_count": 71
    },
    {
      "id": "venue_0121aad7e422589a894cfc4b1b09230f",
      "name": "Irving Plaza Powered By Verizon 5G",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 69
    },
    {
      "id": "venue_ba8e8c5e8a67508383f3bc4a0f5b16bc",
      "name": "Sony Hall",
      "city": "New York",
      "state": "NY",
      "historical_booking_count": 68
    }
  ]
}
```

## Entity Quality

```json
{
  "duplicate_artist_candidate_groups": 30,
  "duplicate_artist_candidates": [
    {
      "normalized_key": "altin gun",
      "record_count": 2,
      "ids": [
        "artist_2229eb51795e5c77942e2f5f5b476f31",
        "artist_90692d5b50e0583f83dffbffa9e3a541"
      ],
      "names": [
        "Altin Gun",
        "Altin G\u00fcn"
      ]
    },
    {
      "normalized_key": "christone kingfish ingram",
      "record_count": 2,
      "ids": [
        "artist_2fdf4d6e5be15ca09b67781135cef469",
        "artist_b02af4a9bf9757ca86289920c7d8e676"
      ],
      "names": [
        "Christone \"Kingfish\" Ingram",
        "Christone \u201cKingfish\u201d Ingram"
      ]
    },
    {
      "normalized_key": "clipping",
      "record_count": 2,
      "ids": [
        "artist_dbf591e5ccce51fdb828822251cd2506",
        "artist_ec57d5031a3a578fb53da7110aa43ffc"
      ],
      "names": [
        "Clipping",
        "clipping."
      ]
    },
    {
      "normalized_key": "david lohlein",
      "record_count": 2,
      "ids": [
        "artist_175ef60db7fc50a8906a8784fca68e4d",
        "artist_1a516e02fd6556b5829c69f00c8a9737"
      ],
      "names": [
        "David Lohlein",
        "David L\u00f6hlein"
      ]
    },
    {
      "normalized_key": "domi jd beck",
      "record_count": 2,
      "ids": [
        "artist_a0022acbc7995deab7d2516bad594211",
        "artist_f8df3105ed2c5d2698a1291f15b077e6"
      ],
      "names": [
        "DOMi & JD BECK",
        "DOMi + JD Beck"
      ]
    },
    {
      "normalized_key": "eva ayllon",
      "record_count": 2,
      "ids": [
        "artist_219a41e292855c6bbda023b5d74d4cc6",
        "artist_c3849e4d39395b469662e01ffc6c80d9"
      ],
      "names": [
        "Eva Ayllon",
        "Eva Ayll\u00f3n"
      ]
    },
    {
      "normalized_key": "evelyn champagne king",
      "record_count": 2,
      "ids": [
        "artist_9216b21019915559a427842f2b61df9c",
        "artist_96a2fa9b48165035abd25413a993c7e1"
      ],
      "names": [
        "Evelyn Champagne King",
        "Evelyn \u201cChampagne\u201d King"
      ]
    },
    {
      "normalized_key": "fox n vead",
      "record_count": 2,
      "ids": [
        "artist_4292d83f1d975323b1765f0cbff5fed3",
        "artist_536e40d02c0c5857b678adfb706f3586"
      ],
      "names": [
        "Fox N' Vead",
        "Fox N\u2019 Vead"
      ]
    },
    {
      "normalized_key": "haruomi hosono",
      "record_count": 2,
      "ids": [
        "artist_68a635db3c2358288b8190931b390bfb",
        "artist_fdb663b63fef5b7ca35600f36e5557a7"
      ],
      "names": [
        "Haruomi Hosono",
        "Haruomi Hosono (\u7d30\u91ce\u6674\u81e3)"
      ]
    },
    {
      "normalized_key": "hernan cattaneo",
      "record_count": 2,
      "ids": [
        "artist_411d369e19525f279a2ebeac11621c19",
        "artist_57f1f739a75d58f69490570da1c9167d"
      ],
      "names": [
        "Hernan Cattaneo",
        "Hern\u00e1n Catt\u00e1neo"
      ]
    },
    {
      "normalized_key": "jon b",
      "record_count": 2,
      "ids": [
        "artist_65b6a0b25ea354f58f4ff5917699320f",
        "artist_e57a9927da2354eeb09b3e2930bd06ff"
      ],
      "names": [
        "Jon B",
        "Jon B."
      ]
    },
    {
      "normalized_key": "jonathan hulten",
      "record_count": 2,
      "ids": [
        "artist_2f6c5c2af8b352cbb35ba9c8d62e8b14",
        "artist_a384f3d435d652b6a2f4b304414a50c2"
      ],
      "names": [
        "Jonathan Hulten",
        "Jonathan Hult\u00e9n"
      ]
    },
    {
      "normalized_key": "kany garcia",
      "record_count": 2,
      "ids": [
        "artist_4a254389a2c95f8e8069363c6efd6181",
        "artist_bb4676e1d2a853f0b3e98a7ba97a8fa9"
      ],
      "names": [
        "Kany Garcia",
        "Kany Garc\u00eda"
      ]
    },
    {
      "normalized_key": "letlive",
      "record_count": 2,
      "ids": [
        "artist_161f80a3118c5c278fb21febc7d22343",
        "artist_20d1e1c1180850e78e7425f4663aa99b"
      ],
      "names": [
        "letlive",
        "letlive."
      ]
    },
    {
      "normalized_key": "lngshot",
      "record_count": 2,
      "ids": [
        "artist_36c474a7e19f5b8f8ceb3cdce768f852",
        "artist_7654d33a0bd154f9ab03230337874c76"
      ],
      "names": [
        "LNGSHOT",
        "LNGSHOT(\ub871\uc0f7)"
      ]
    },
    {
      "normalized_key": "matamoska",
      "record_count": 2,
      "ids": [
        "artist_226f7e94ebe057a7a9620f6822ff23fb",
        "artist_7feaac82d9e45c5d9de4eeb434414960"
      ],
      "names": [
        "Matamoska",
        "Matamoska!"
      ]
    },
    {
      "normalized_key": "minyo crusaders",
      "record_count": 2,
      "ids": [
        "artist_d1b862ba01745e51a3023a4c6c67a2fd",
        "artist_fdf645510e585f86a275cfa1b9193ee5"
      ],
      "names": [
        "Minyo Crusaders",
        "Minyo Crusaders (\u6c11\u8b21\u30af\u30eb\u30bb\u30a4\u30c0\u30fc\u30ba)"
      ]
    },
    {
      "normalized_key": "mon rovia",
      "record_count": 2,
      "ids": [
        "artist_b7fffc48a70059fdaeede2d1692e7ea0",
        "artist_bd4d33ffc2f552e293c539df9e07aa5e"
      ],
      "names": [
        "Mon Rovia",
        "Mon Rov\u00eea"
      ]
    },
    {
      "normalized_key": "monsieur perine",
      "record_count": 2,
      "ids": [
        "artist_438a97f61555564e9ba10715424517dd",
        "artist_670085aefad05d38b7daa94cd482cf47"
      ],
      "names": [
        "Monsieur Perine",
        "Monsieur Perin\u00e9"
      ]
    },
    {
      "normalized_key": "mya",
      "record_count": 2,
      "ids": [
        "artist_9c430423626c5fccaca04fd67260fcf9",
        "artist_ca3a84f3d011553abfbc8edace2d7b19"
      ],
      "names": [
        "Mya",
        "M\u00fda"
      ]
    },
    {
      "normalized_key": "pedro alterio",
      "record_count": 2,
      "ids": [
        "artist_6a5645a6f4965f38bc4cbf7a229212b4",
        "artist_716807128abc5367bafaf3243d1fbf40"
      ],
      "names": [
        "Pedro Alterio",
        "Pedro Alt\u00e9rio"
      ]
    },
    {
      "normalized_key": "poison ruin",
      "record_count": 2,
      "ids": [
        "artist_2dbc0857b9fa55af9c3921362d74bd4b",
        "artist_df48645d28cb594cb143e67726a199df"
      ],
      "names": [
        "Poison Ruin",
        "Poison Ru\u00efn"
      ]
    },
    {
      "normalized_key": "rolling quartz",
      "record_count": 2,
      "ids": [
        "artist_4a38a9aaa43f594c9ce74d28c6669832",
        "artist_dac7eb3d14545d7a85807a751a869f6e"
      ],
      "names": [
        "Rolling Quartz",
        "Rolling Quartz (\ub864\ub9c1\ucffc\uce20)"
      ]
    },
    {
      "normalized_key": "screamin cheetah wheelies",
      "record_count": 2,
      "ids": [
        "artist_1f7aeafd3d0c52e0a5a24560e48bec89",
        "artist_aa2661a0c7445afb8e10a08a0371ac6b"
      ],
      "names": [
        "Screamin' Cheetah Wheelies",
        "Screamin\u2019 Cheetah Wheelies"
      ]
    },
    {
      "normalized_key": "shotguns n roses a powerful blast of gnr",
      "record_count": 2,
      "ids": [
        "artist_68e52d5cb69a5f34803c1ceb8a438bf5",
        "artist_ce50c46ee60e5cadb613d2b06ddbb9ac"
      ],
      "names": [
        "Shotguns N Roses (A Powerful Blast of GNR)",
        "Shotguns N Roses - A Powerful Blast Of GNR"
      ]
    },
    {
      "normalized_key": "sunn o",
      "record_count": 2,
      "ids": [
        "artist_136a2f410f9f5473a88a0acd179ab888",
        "artist_72f18e3d66a3590695e93313070edf01"
      ],
      "names": [
        "Sunn O )))",
        "Sunn O)))"
      ]
    },
    {
      "normalized_key": "sunset rollercoaster",
      "record_count": 2,
      "ids": [
        "artist_39ac77728fd85c6ba32c93bdf762c26a",
        "artist_8d4cb1ac0f2a5f72ad9d5e4646dc27b1"
      ],
      "names": [
        "Sunset Rollercoaster",
        "Sunset Rollercoaster (\u843d\u65e5\u98db\u8eca)"
      ]
    },
    {
      "normalized_key": "the point",
      "record_count": 2,
      "ids": [
        "artist_245ea54fb48b53b8a1462a4e7eb221fd",
        "artist_3eabf270ec155f3791ed5eb02d30a6e3"
      ],
      "names": [
        "The Point",
        "The Point."
      ]
    },
    {
      "normalized_key": "um jennifer",
      "record_count": 2,
      "ids": [
        "artist_7b2bb8a44f4e554a9b90e0b741421cff",
        "artist_8dacb1b915f85c7589e4993479b50a87"
      ],
      "names": [
        "Um Jennifer?",
        "Um, Jennifer?"
      ]
    },
    {
      "normalized_key": "wave to earth",
      "record_count": 2,
      "ids": [
        "artist_20e1ec90e4a95c56a14ec0517ed1d91d",
        "artist_a31e5db46ee650379a4c8489b17c9f43"
      ],
      "names": [
        "Wave To Earth",
        "wave to earth (\uc6e8\uc774\ube0c \ud22c \uc5b4\uc2a4)"
      ]
    }
  ],
  "duplicate_venue_candidate_groups": 2,
  "duplicate_venue_candidates": [
    {
      "normalized_key": "exit in|nashville|tn",
      "record_count": 2,
      "ids": [
        "venue_215658cfc8c05f609f66fb1cfb5de504",
        "venue_a5595176fa01560ea4939862ad7b9cb7"
      ],
      "names": [
        "Exit In",
        "Exit/In"
      ]
    },
    {
      "normalized_key": "fox theatre atlanta|atlanta|ga",
      "record_count": 2,
      "ids": [
        "venue_2ec2be7eb3375580b45922dbfd4657e8",
        "venue_db9bd14bba38554fb30ffb17b2bf2f3d"
      ],
      "names": [
        "Fox Theatre - Atlanta",
        "Fox Theatre Atlanta"
      ]
    }
  ],
  "relationships_missing_artist_id": 0,
  "relationships_missing_venue_id": 0,
  "unresolved_artist_relationships": 0,
  "unresolved_venue_relationships": 0,
  "relationships_missing_market": 0,
  "relationships_missing_event_genre": 2872,
  "relationships_whose_artist_has_no_genre": 965,
  "venues_missing_capacity": 201,
  "relationships_with_missing_venue_capacity": 2125,
  "relationships_missing_provider_provenance": 0,
  "provider_provenance_limitation": "Event-level source is stored. MusicBrainz is used for artist identity enrichment, not as an event relationship source, so MusicBrainz-derived bookings cannot be reported."
}
```

## Benchmark Eligibility

```json
{
  "total_historical_bookings": 8715,
  "eligible_historical_bookings": 8671,
  "eligible_with_5_plus_candidates": 8531,
  "eligible_unique_artists": 3713,
  "eligible_unique_venues": 427,
  "eligible_markets": 18,
  "useful_markets": 0,
  "basic_eligibility_definition": "Resolved historical relationship with a known market and at least one alternative venue in the same market that had been observed by the event date.",
  "strict_eligibility_definition": "Basic entity/date requirements with at least five total candidate venues, including the booked venue."
}
```

Candidate counts include the booked venue. Basic eligibility requires at least one additional same-market venue with observed activity on or before the booking date. Genre, capacity, and artist history are deliberately excluded from candidate generation.

## Candidate-Set Distribution

```json
{
  "minimum": 2,
  "p25": 14.0,
  "median": 22.0,
  "mean": 23.51,
  "p75": 32.0,
  "p90": 41.0,
  "maximum": 52
}
```

## Recommended Temporal Folds

| Fold | Train start | Train end | Test start | Test end | Train events | Test events | Markets |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-07-14 | 2026-08-26 | 2026-08-27 | 2026-09-07 | 3314 | 1878 | 18 |
| 2 | 2026-07-14 | 2026-09-07 | 2026-09-08 | 2026-09-15 | 5192 | 1656 | 18 |
| 3 | 2026-07-14 | 2026-09-15 | 2026-09-16 | 2026-09-22 | 6848 | 1823 | 18 |

## Setlist.fm Recommendation

**SETLIST_ENRICHMENT_RECOMMENDED**

Historical enrichment is recommended because these thresholds failed: useful_markets, historical_depth_days.

```json
{
  "eligible_historical_bookings": {
    "actual": 8671,
    "threshold": 5000,
    "passed": true
  },
  "held_out_test_bookings": {
    "actual": 5357,
    "threshold": 1000,
    "passed": true
  },
  "useful_markets": {
    "actual": 0,
    "threshold": 4,
    "passed": false
  },
  "mean_candidate_count": {
    "actual": 23.51,
    "threshold": 5.0,
    "passed": true
  },
  "historical_depth_days": {
    "actual": 70,
    "threshold": 365,
    "passed": false
  }
}
```
