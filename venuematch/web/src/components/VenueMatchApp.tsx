"use client";

import { FormEvent, startTransition, useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  Building2,
  Database,
  Gauge,
  LoaderCircle,
  Map,
  Music2,
  RadioTower,
  Search,
  Sparkles,
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import type {
  ArtistVenueResult,
  OptionsResponse,
  RecommendationResponse,
  TabId,
  VenueArtistResult,
} from "@/lib/types";
import { CityPanel } from "./CityPanel";
import { RawPanel } from "./RawPanel";
import { RecommendationList } from "./RecommendationList";

const TABS: Array<{ id: TabId; label: string; icon: typeof Music2 }> = [
  { id: "artist", label: "Artist → venue", icon: Music2 },
  { id: "venue", label: "Venue → artist", icon: Building2 },
  { id: "city", label: "City pulse", icon: Map },
  { id: "raw", label: "Raw data", icon: Database },
];

export function VenueMatchApp() {
  const [activeTab, setActiveTab] = useState<TabId>("artist");
  const [options, setOptions] = useState<OptionsResponse | null>(null);
  const [bootError, setBootError] = useState("");
  const [selectedArtist, setSelectedArtist] = useState("");
  const [selectedCity, setSelectedCity] = useState("");
  const [selectedVenue, setSelectedVenue] = useState("");
  const [artistResults, setArtistResults] = useState<ArtistVenueResult[]>([]);
  const [venueResults, setVenueResults] = useState<VenueArtistResult[]>([]);
  const [searchError, setSearchError] = useState("");
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    let active = true;
    apiRequest<OptionsResponse>("/meta/options")
      .then((payload) => {
        if (active) setOptions(payload);
      })
      .catch((reason: unknown) => {
        if (active) setBootError(reason instanceof Error ? reason.message : "VenueMatch could not start.");
      });
    return () => { active = false; };
  }, []);

  const artist = selectedArtist || options?.artists[0] || "";
  const city = selectedCity || options?.cities[0]?.city || "";
  const venue = selectedVenue || options?.venue_queries[0] || "";
  const connectedSources = options ? Object.values(options.api_sources).filter(Boolean).length : 0;

  function changeTab(tab: TabId) {
    startTransition(() => setActiveTab(tab));
    setSearchError("");
  }

  async function searchArtist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearching(true);
    setSearchError("");
    try {
      const response = await apiRequest<RecommendationResponse<ArtistVenueResult>>(
        "/recommendations/artist-to-venue",
        { method: "POST", body: JSON.stringify({ artist_name: artist, target_city: city, top_n: 10 }) },
      );
      setArtistResults(response.results);
    } catch (reason) {
      setSearchError(reason instanceof Error ? reason.message : "No venue matches were found.");
    } finally {
      setSearching(false);
    }
  }

  async function searchVenue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearching(true);
    setSearchError("");
    try {
      const response = await apiRequest<RecommendationResponse<VenueArtistResult>>(
        "/recommendations/venue-to-artist",
        { method: "POST", body: JSON.stringify({ venue_name_or_city: venue, top_n: 10 }) },
      );
      setVenueResults(response.results);
    } catch (reason) {
      setSearchError(reason instanceof Error ? reason.message : "No artist matches were found.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="VenueMatch home">
          <span><RadioTower size={20} /></span>
          VenueMatch
        </a>
        <div className="header-status">
          <span className="live-dot" />
          {options?.data_mode === "sample" ? "Seed data online" : `${connectedSources} sources connected`}
        </div>
        <a className="header-link" href="#workspace">Open matcher <ArrowRight size={16} /></a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span>01</span> Booking intelligence for independent music</p>
          <h1>Put the right artist<br />on the <em>right stage.</em></h1>
          <p className="hero-subtitle">
            VenueMatch turns genre alignment, market demand, booking history, capacity, and artist pull into one explainable recommendation.
          </p>
          <a className="hero-cta" href="#workspace"><Search size={19} /> Run a match</a>
        </div>
        <aside className="formula-card">
          <div className="formula-topline"><span>Scoring model / v1.0</span><Gauge size={18} /></div>
          <p>Final recommendation</p>
          <div className="formula-score">0<span>—</span>100</div>
          <div className="formula-lines">
            <span><i style={{ width: "35%" }} />Genre fit <b>35%</b></span>
            <span><i style={{ width: "25%" }} />Venue history <b>25%</b></span>
            <span><i style={{ width: "20%" }} />City demand <b>20%</b></span>
            <span><i style={{ width: "10%" }} />Capacity fit <b>10%</b></span>
            <span><i style={{ width: "10%" }} />Artist pull <b>10%</b></span>
          </div>
          <div className="formula-note"><Sparkles size={15} /> Transparent by design. Every point has a reason.</div>
        </aside>
      </section>

      <section className="workspace" id="workspace">
        <div className="workspace-topbar">
          <div><span className="window-dot" /><span className="window-dot" /><span className="window-dot" /></div>
          <span>VENUE_MATCH / RECOMMENDATION_DESK</span>
          <Activity size={16} />
        </div>
        <nav className="tabs" aria-label="VenueMatch tools">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                className={activeTab === tab.id ? "active" : ""}
                key={tab.id}
                type="button"
                onClick={() => changeTab(tab.id)}
                aria-pressed={activeTab === tab.id}
              >
                <Icon size={17} /> {tab.label}
              </button>
            );
          })}
        </nav>

        {bootError ? (
          <div className="boot-state error-state">
            <RadioTower size={32} />
            <h2>Backend connection needed</h2>
            <p>{bootError}</p>
            <code>python3 -m uvicorn app:app --reload</code>
          </div>
        ) : !options ? (
          <div className="boot-state"><LoaderCircle className="spin" size={30} /><p>Loading markets and booking history…</p></div>
        ) : (
          <>
            {activeTab === "artist" && (
              <div className="panel-body">
                <div className="search-intro">
                  <p className="eyebrow">Artist routing</p>
                  <h2>Find the room that already wants the sound.</h2>
                  <p>Start with an artist and a target market. We rank the viable stages and show exactly why each one fits.</p>
                </div>
                <form className="search-form" onSubmit={searchArtist}>
                  <label><span>Artist</span><select value={artist} onChange={(event) => setSelectedArtist(event.target.value)}>{options.artists.map((name) => <option key={name}>{name}</option>)}</select></label>
                  <label><span>Target market</span><select value={city} onChange={(event) => setSelectedCity(event.target.value)}>{options.cities.map((item) => <option value={item.city} key={item.label}>{item.label}</option>)}</select></label>
                  <button className="primary-button" disabled={searching} type="submit">{searching ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />} Match venues</button>
                </form>
                {searchError && <p className="error-banner" role="alert">{searchError}</p>}
                <RecommendationList results={artistResults} />
              </div>
            )}

            {activeTab === "venue" && (
              <div className="panel-body">
                <div className="search-intro">
                  <p className="eyebrow">Talent discovery</p>
                  <h2>Book toward the audience you have.</h2>
                  <p>Choose a venue or scan an entire city to find artists whose sound, scale, and momentum align.</p>
                </div>
                <form className="search-form two-up" onSubmit={searchVenue}>
                  <label><span>Venue or city</span><select value={venue} onChange={(event) => setSelectedVenue(event.target.value)}>{options.venue_queries.map((name) => <option key={name}>{name}</option>)}</select></label>
                  <button className="primary-button" disabled={searching} type="submit">{searching ? <LoaderCircle className="spin" size={18} /> : <Music2 size={18} />} Match artists</button>
                </form>
                {searchError && <p className="error-banner" role="alert">{searchError}</p>}
                <RecommendationList results={venueResults} />
              </div>
            )}

            {activeTab === "city" && <CityPanel cities={options.cities} />}
            {activeTab === "raw" && <RawPanel />}
          </>
        )}
      </section>

      <section className="trust-strip">
        <p className="eyebrow">Built for useful skepticism</p>
        <div>
          <span><b>01</b> Official and public sources only</span>
          <span><b>02</b> Missing capacity lowers confidence</span>
          <span><b>03</b> No private sales data scraped</span>
          <span><b>04</b> Rule weights stay visible</span>
        </div>
      </section>

      <footer><span>VenueMatch / MVP 1.0</span><p>Better routing starts with better context.</p><span>Washington → New York</span></footer>
    </main>
  );
}
