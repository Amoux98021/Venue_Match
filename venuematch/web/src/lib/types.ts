export type TabId = "artist" | "venue" | "city" | "raw";

export type ApiSources = Record<string, boolean>;

export interface CityOption {
  city: string;
  state: string;
  label: string;
}

export interface VenueOption {
  id: string;
  name: string;
  city: string;
  state: string;
  capacity: number | null;
}

export interface OptionsResponse {
  artists: string[];
  cities: CityOption[];
  venues: VenueOption[];
  venue_queries: string[];
  data_mode: string;
  api_sources: ApiSources;
}

export interface ScoreRecord {
  genre_fit_score: number;
  venue_history_score: number;
  city_demand_score: number;
  capacity_fit_score: number;
  artist_popularity_score: number;
  final_score: number;
  explanation: string;
}

export interface ArtistVenueResult extends ScoreRecord {
  artist_name: string;
  venue_id: string;
  venue_name: string;
  city: string;
  state: string;
  capacity: number | null;
}

export interface VenueArtistResult extends ScoreRecord {
  artist_id: string;
  artist_name: string;
  home_city: string;
  home_state: string;
  venue_name: string;
  city: string;
  state: string;
  genres: string;
}

export interface RecommendationResponse<T extends ScoreRecord> {
  explanation: string;
  results: T[];
  weights: Record<string, number>;
}

export interface CityDashboardResponse {
  city: string;
  state: string;
  demographics: {
    population: number;
    median_age: number;
    median_income: number;
  };
  genre_signals: Array<{ genre: string; signal_strength: number }>;
  venues: VenueOption[];
}

export interface RawResponse {
  dataset: string;
  count: number;
  rows: Array<Record<string, unknown>>;
}
