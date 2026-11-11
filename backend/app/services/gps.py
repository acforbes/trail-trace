import tempfile
from datetime import datetime
from pathlib import Path
from app.schemas.gps import ProcessingResult, Coordinate, Lap, StatisticalPattern, LapRoute
from app.services import gps_analyzer
from app.services.route_patterns import fit_route_patterns

def process_gps_file(
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
            raise ValueError(f"Error processing GPS file: {exc}") from exc

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
