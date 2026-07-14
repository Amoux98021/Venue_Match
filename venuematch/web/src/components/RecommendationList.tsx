import { MapPin, Sparkles, UsersRound } from "lucide-react";
import type { ArtistVenueResult, VenueArtistResult } from "@/lib/types";
import { ScoreBreakdown } from "./ScoreBreakdown";

type Result = ArtistVenueResult | VenueArtistResult;

function isVenueResult(result: Result): result is ArtistVenueResult {
  return "venue_id" in result;
}

export function RecommendationList({ results }: { results: Result[] }) {
  if (!results.length) {
    return null;
  }

  return (
    <section className="recommendation-list" aria-live="polite">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Ranked output</p>
          <h2>{results.length} strongest matches</h2>
        </div>
        <p>Every score is inspectable. No black box.</p>
      </div>

      {results.map((result, index) => {
        const venueResult = isVenueResult(result);
        const title = venueResult ? result.venue_name : result.artist_name;
        const subtitle = venueResult
          ? `${result.city}, ${result.state}`
          : `Best at ${result.venue_name} · ${result.city}, ${result.state}`;
        const key = venueResult ? result.venue_id : result.artist_id;

        return (
          <article className="recommendation-card" key={key}>
            <div className="rank-stamp" aria-label={`Rank ${index + 1}`}>
              {String(index + 1).padStart(2, "0")}
            </div>
            <div className="recommendation-main">
              <div className="recommendation-title-row">
                <div>
                  <p className="result-kicker">{venueResult ? "Recommended room" : "Recommended artist"}</p>
                  <h3>{title}</h3>
                  <p className="location-line"><MapPin size={15} /> {subtitle}</p>
                </div>
                <div className="final-score">
                  <strong>{Math.round(result.final_score * 100)}</strong>
                  <span>match</span>
                </div>
              </div>

              <div className="result-facts">
                {venueResult ? (
                  <span>
                    <UsersRound size={15} />
                    {result.capacity ? `${result.capacity.toLocaleString()} cap` : "Capacity unverified"}
                    {result.capacity_source === "jambase" && result.capacity_source_url ? (
                      <a href={result.capacity_source_url} target="_blank" rel="noreferrer">Data: JamBase</a>
                    ) : null}
                  </span>
                ) : (
                  <span><Sparkles size={15} /> {result.genres || "Genre data pending"}</span>
                )}
              </div>

              <ScoreBreakdown record={result} />
              <div className="explanation-callout">
                <Sparkles size={16} />
                <p>{result.explanation}</p>
              </div>
            </div>
          </article>
        );
      })}
    </section>
  );
}
