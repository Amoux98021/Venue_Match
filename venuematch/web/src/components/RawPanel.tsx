"use client";

import { useDeferredValue, useState } from "react";
import { Database, LoaderCircle, Search } from "lucide-react";
import { apiRequest } from "@/lib/api";
import type { RawResponse } from "@/lib/types";

const DATASETS = [
  "artists",
  "venues",
  "events",
  "artist_genres",
  "city_demographics",
  "city_genre_signals",
  "venue_genre_history",
  "recommendations",
];

function displayValue(value: unknown) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(3);
  return String(value);
}

export function RawPanel() {
  const [dataset, setDataset] = useState("events");
  const [data, setData] = useState<RawResponse | null>(null);
  const [filter, setFilter] = useState("");
  const deferredFilter = useDeferredValue(filter);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      setData(await apiRequest<RawResponse>(`/raw/${dataset}?limit=100`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Raw data is unavailable.");
    } finally {
      setLoading(false);
    }
  }

  const rows = data?.rows.filter((row) =>
    JSON.stringify(row).toLowerCase().includes(deferredFilter.toLowerCase()),
  ) ?? [];
  const columns = rows.length ? Object.keys(rows[0]) : data?.rows[0] ? Object.keys(data.rows[0]) : [];

  return (
    <div className="panel-body">
      <div className="search-intro">
        <p className="eyebrow">Evidence desk</p>
        <h2>Inspect the records behind every match.</h2>
        <p>Preview normalized source tables without exposing credentials or unrestricted database access.</p>
      </div>
      <div className="search-form raw-controls">
        <label>
          <span>Dataset</span>
          <select value={dataset} onChange={(event) => setDataset(event.target.value)}>
            {DATASETS.map((name) => <option key={name}>{name}</option>)}
          </select>
        </label>
        <button className="primary-button" type="button" onClick={loadData} disabled={loading}>
          {loading ? <LoaderCircle className="spin" size={18} /> : <Database size={18} />}
          Load preview
        </button>
        <label className="filter-field">
          <span>Filter rows</span>
          <div><Search size={17} /><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Type to filter" /></div>
        </label>
      </div>
      {error && <p className="error-banner" role="alert">{error}</p>}
      {data && (
        <div className="raw-table-wrap" aria-live="polite">
          <div className="table-meta"><strong>{data.dataset}</strong><span>{rows.length} of {data.count} rows</span></div>
          <div className="table-scroll">
            <table>
              <thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr></thead>
              <tbody>{rows.map((row, index) => {
                const rowKey = String(row.id ?? row.artist_id ?? row.venue_id ?? `${data.dataset}-${index}`);
                return <tr key={rowKey}>{columns.map((column) => <td key={column}>{displayValue(row[column])}</td>)}</tr>;
              })}</tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
