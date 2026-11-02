import importlib.util
import math
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.route_patterns import fit_route_patterns

SERVICES_PATH = PROJECT_ROOT / "app" / "services" / "gps_analyzer.py"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

spec = importlib.util.spec_from_file_location("gps_analyzer_module", SERVICES_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load GPS analyzer module from {SERVICES_PATH}.")
gps_analyzer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gps_analyzer
spec.loader.exec_module(gps_analyzer)

app = FastAPI(title="GPS Track Analyzer API")

app.include_router(router, prefix="/api/v1")

# Define allowed origins
# Fetch from environment variables for production flexibility, default to local React Vite port
ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")

# Split comma-separated string into a clean Python list
origins = [origin.strip() for origin in ALLOWED_ORIGINS_ENV.split(",")]

# Apply the CORS security middleware layer
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # Whitelisted URLs allowed to talk to this API
    allow_credentials=True,           # Allows browser cookies/auth headers if needed
    allow_methods=["*"],              # Allows all standard HTTP methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],              # Allows all browser headers
)

class Coordinate(BaseModel):
    latitude: float
    longitude: float


class Lap(BaseModel):
    number: int
    distance_miles: float
    total_distance_miles: float
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


def _parse_start_time(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Start time must be a valid ISO 8601 datetime.",
        ) from exc


# @app.get("/api/health")
# async def health() -> dict[str, str]:
#     return {"status": "ok"}

def _process_track_content(
    content: bytes,
    suffix: str,
    radius_meters: float,
    start_time: datetime | None,
    start_latitude: float | None,
    start_longitude: float | None,
) -> ProcessingResult:
    with tempfile.TemporaryDirectory() as temporary_directory:
        track_path = Path(temporary_directory) / f"track{suffix}"
        track_path.write_bytes(content)
        try:
            points = gps_analyzer.load_track(track_path, start_time=start_time)
            start_location = None
            if start_latitude is not None and start_longitude is not None:
                start_location = (start_latitude, start_longitude)
            laps_with_routes = gps_analyzer.measure_laps_with_routes(
                points,
                radius_meters=radius_meters,
                start_location=start_location,
            )
            geographic_routes = [
                [
                    (point.latitude, point.longitude)
                    for point in route
                ]
                for _, route in laps_with_routes
            ]
            patterns = fit_route_patterns(geographic_routes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    first_point = points[0]
    response_start = (
        start_latitude
        if start_latitude is not None
        else first_point.latitude,
        start_longitude
        if start_longitude is not None
        else first_point.longitude,
    )
    return ProcessingResult(
        track_point_count=len(points),
        start_location=Coordinate(
            latitude=response_start[0],
            longitude=response_start[1],
        ),
        first_point_time=first_point.timestamp,
        laps=[Lap(**lap.__dict__) for lap, _ in laps_with_routes],
        statistical_patterns=[
            StatisticalPattern(
                algorithm=pattern.algorithm,
                best_fit_lap=pattern.best_fit_lap,
                length_miles=pattern.length_miles,
                coordinates=[
                    Coordinate(latitude=latitude, longitude=longitude)
                    for latitude, longitude in pattern.coordinates
                ],
                fit_rmse_meters=pattern.fit_rmse_meters,
            )
            for pattern in patterns
        ],
        routes=[
            LapRoute(
                lap_number=lap.number,
                coordinates=[
                    Coordinate(
                        latitude=point.latitude,
                        longitude=point.longitude,
                    )
                    for point in route
                ],
            )
            for lap, route in laps_with_routes
        ],
    )


@app.post("/api/process-gps", response_model=ProcessingResult)
async def process_gps(
    file: Annotated[UploadFile, File()],
    radius_meters: Annotated[float, Form(gt=0)] = gps_analyzer.DEFAULT_RADIUS_METERS,
    start_time: Annotated[str | None, Form()] = None,
    start_latitude: Annotated[float | None, Form()] = None,
    start_longitude: Annotated[float | None, Form()] = None,
) -> ProcessingResult:
    filename = file.filename or ""
    suffix = Path(filename.replace("\\", "/")).suffix.lower()
    if suffix not in {".gpx", ".tcx"}:
        raise HTTPException(status_code=400, detail="Upload a .gpx or .tcx track.")
    if not math.isfinite(radius_meters):
        raise HTTPException(status_code=400, detail="Radius must be a finite number.")
    if (start_latitude is None) != (start_longitude is None):
        raise HTTPException(
            status_code=400,
            detail="Provide both start latitude and longitude, or neither.",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Track files must be 25 MB or smaller.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    parsed_start_time = _parse_start_time(start_time)
    return await run_in_threadpool(
        _process_track_content,
        content,
        suffix,
        radius_meters,
        parsed_start_time,
        start_latitude,
        start_longitude,
    )


if FRONTEND_DIST.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=FRONTEND_DIST, html=True),
        name="frontend",
    )
