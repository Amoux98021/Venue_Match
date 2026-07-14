import type { ScoreRecord } from "@/lib/types";

const SCORE_LABELS: Array<[keyof ScoreRecord, string]> = [
  ["genre_fit_score", "Genre fit"],
  ["venue_history_score", "Venue history"],
  ["city_demand_score", "Local demand"],
  ["capacity_fit_score", "Capacity fit"],
  ["artist_popularity_score", "Artist pull"],
];

export function ScoreBreakdown({ record }: { record: ScoreRecord }) {
  return (
    <div className="score-breakdown" aria-label="Recommendation score breakdown">
      {SCORE_LABELS.map(([key, label]) => {
        const score = Number(record[key]);
        return (
          <div className="score-row" key={key}>
            <span>{label}</span>
            <div className="score-track" aria-hidden="true">
              <span style={{ width: `${Math.max(0, Math.min(score * 100, 100))}%` }} />
            </div>
            <strong>{Math.round(score * 100)}</strong>
          </div>
        );
      })}
    </div>
  );
}
