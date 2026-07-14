"use client";

import { useState } from "react";
import { Building2, CircleDollarSign, LoaderCircle, Radio, UsersRound } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { CityDashboardResponse, CityOption } from "@/lib/types";

export function CityPanel({ cities }: { cities: CityOption[] }) {
  const [selectedLabel, setSelectedLabel] = useState("");
  const [dashboard, setDashboard] = useState<CityDashboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const selected = cities.find((city) => city.label === selectedLabel) ?? cities[0];

  async function loadDashboard() {
    if (!selected) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiRequest<CityDashboardResponse>(
        `/cities/${encodeURIComponent(selected.city)}/dashboard?state=${encodeURIComponent(selected.state)}`,
      );
      setDashboard(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "City data is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="panel-body">
      <div className="search-intro">
        <p className="eyebrow">Market intelligence</p>
        <h2>Read the room before you book it.</h2>
        <p>Compare audience shape, buying power, local genre momentum, and available stages.</p>
      </div>

      <div className="search-form two-up">
        <label>
          <span>Market</span>
          <select value={selected?.label ?? ""} onChange={(event) => setSelectedLabel(event.target.value)}>
            {cities.map((city) => <option key={city.label}>{city.label}</option>)}
          </select>
        </label>
        <button className="primary-button" type="button" onClick={loadDashboard} disabled={loading}>
          {loading ? <LoaderCircle className="spin" size={18} /> : <Radio size={18} />}
          Build market brief
        </button>
      </div>

      {error && <p className="error-banner" role="alert">{error}</p>}
      {dashboard && (
        <section className="city-dashboard" aria-live="polite">
          <div className="city-title">
            <p className="eyebrow">Market brief</p>
            <h2>{dashboard.city}, {dashboard.state}</h2>
          </div>
          <div className="metric-grid">
            <div><UsersRound /><span>Population</span><strong>{dashboard.demographics.population.toLocaleString()}</strong></div>
            <div><Radio /><span>Median age</span><strong>{dashboard.demographics.median_age.toFixed(1)}</strong></div>
            <div><CircleDollarSign /><span>Median income</span><strong>${dashboard.demographics.median_income.toLocaleString()}</strong></div>
            <div><Building2 /><span>Tracked venues</span><strong>{dashboard.venues.length}</strong></div>
          </div>
          <div className="signal-panel">
            <div className="section-heading compact">
              <div><p className="eyebrow">Demand index</p><h3>Genres moving locally</h3></div>
              <span>0—100</span>
            </div>
            {dashboard.genre_signals.map((signal, index) => (
              <div className="signal-row" key={signal.genre}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{signal.genre}</strong>
                <div><i style={{ width: `${signal.signal_strength * 100}%` }} /></div>
                <b>{Math.round(signal.signal_strength * 100)}</b>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
