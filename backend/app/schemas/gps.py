from datetime import datetime
from typing import Annotated
from fastapi import Form
from pydantic import BaseModel, Field, field_validator
from app.core.constants import DEFAULT_RADIUS_METERS

class Coordinate(BaseModel):
    latitude: float
    longitude: float


class Lap(BaseModel):
    number: int
    distance_miles: float
    total_distance_miles: float
    elevation_gain: float | None
    total_elevation_gain: float | None
    elapsed_seconds: float
    total_seconds: float
    pace_minutes_per_mile: float | None


class LapRoute(BaseModel):
    lap_number: int
    coordinates: list[Coordinate]


class StatisticalPattern(BaseModel):
    algorithm: str
    best_fit_lap: int
    length_miles: float
    coordinates: list[Coordinate]
    fit_rmse_meters: float


class ProcessingResult(BaseModel):
    track_point_count: int
    start_location: Coordinate
    first_point_time: datetime
    laps: list[Lap]
    routes: list[LapRoute]
    statistical_patterns: list[StatisticalPattern]

class GPSJobForm(BaseModel):
    """Container model to validate and parse input Form data."""
    radius_meters: Annotated[float, Form(gt=0)] = DEFAULT_RADIUS_METERS
    start_time: Annotated[str | None, Form()] = None
    start_latitude: Annotated[float | None, Form()] = None
    start_longitude: Annotated[float | None, Form()] = None

    @field_validator("start_time", mode="before")
    @classmethod
    def _parse_start_time(cls, value: str | None) -> datetime | None:
        if value is None or not str(value).strip():
            return None

        cleaned_value = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(cleaned_value)
        except ValueError as exc:
            # Pydantic natively translates a ValueError inside a validator
            # into a clean HTTP 422 Unprocessable Entity request error.
            raise ValueError("Start time must be a valid ISO 8601 datetime.") from exc
