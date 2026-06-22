from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

from src.features.prepare import load_feature_frames


MIN_TRAINING_ROWS = 6


def build_training_frame(db_path: Path | None = None) -> pd.DataFrame:
    frames = load_feature_frames(db_path)
    events = frames["events"].copy()
    artists = frames["artists"][["id", "popularity", "monthly_listeners"]].rename(columns={"id": "artist_id"})
    venues = frames["venues"][["id", "capacity"]].rename(columns={"id": "venue_id"})

    data = events.merge(artists, on="artist_id", how="left").merge(venues, on="venue_id", how="left")
    data["attendance_estimate"] = data["attendance_estimate"].fillna(0)
    data["capacity"] = data["capacity"].fillna(data["capacity"].median() if not data["capacity"].dropna().empty else 0)
    data["popularity"] = data["popularity"].fillna(data["popularity"].median() if not data["popularity"].dropna().empty else 50)
    data["monthly_listeners"] = data["monthly_listeners"].fillna(0)
    data["capacity_utilization_proxy"] = data["attendance_estimate"] / data["capacity"].replace(0, 1)
    return data


def train_model(db_path: Path | None = None) -> str:
    training_frame = build_training_frame(db_path)
    label_counts = training_frame["outcome_label"].value_counts()
    if (
        len(training_frame) < MIN_TRAINING_ROWS
        or training_frame["outcome_label"].nunique() < 2
        or label_counts.min() < 2
    ):
        return (
            "Not enough labeled historical event data yet. "
            "Seed more positive and negative event examples before training."
        )

    features = training_frame[
        ["popularity", "monthly_listeners", "capacity", "attendance_estimate", "capacity_utilization_proxy"]
    ]
    labels = training_frame["outcome_label"]
    x_train, x_test, y_train, y_test = train_test_split(
        features,
        labels,
        test_size=0.33,
        random_state=42,
        stratify=labels,
    )

    candidates = {
        "logistic_regression": LogisticRegression(max_iter=1000),
        "random_forest": RandomForestClassifier(n_estimators=100, random_state=42),
    }

    reports: list[str] = []
    for name, model in candidates.items():
        model.fit(x_train, y_train)
        predictions = model.predict(x_test)
        reports.append(f"Model: {name}\n{classification_report(y_test, predictions, zero_division=0)}")
    return "\n".join(reports)


if __name__ == "__main__":
    print(train_model())
