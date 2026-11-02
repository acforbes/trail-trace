#!/usr/bin/env python3
"""Measure laps whenever a GPS track returns to its starting location."""

# python C:\forbesoft\micro-apps\trail-trace\core\gps_analyzer.py activity.gpx
# python C:\forbesoft\micro-apps\trail-trace\core\gps_analyzer.py activity.tcx --radius-meters 30 --output laps.csv
# python C:\forbesoft\micro-apps\trail-trace\core\gps_analyzer.py activity.gpx --start-time 2024-01-01T08:00:00Z

import argparse
import csv
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


EARTH_RADIUS_METERS = 6_371_000
METERS_PER_MILE = 1609.344
DEFAULT_RADIUS_METERS = 20.0


@dataclass(frozen=True)
class TrackPoint:
    latitude: float
    longitude: float
    timestamp: datetime


@dataclass(frozen=True)
class Lap:
    number: int
    distance_miles: float
    total_distance_miles: float
    elapsed_seconds: float
    total_seconds: float
    pace_minutes_per_mile: float | None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child.text
    return None


def _parse_point(latitude: str, longitude: str, timestamp: str | None) -> TrackPoint:
    if timestamp is None:
        raise ValueError("Every track point must have a timestamp.")
    try:
        lat = float(latitude)
        lon = float(longitude)
        time = datetime.fromisoformat(timestamp.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid track point: {exc}") from exc
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError(f"Latitude out of range: {latitude}")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError(f"Longitude out of range: {longitude}")
    return TrackPoint(lat, lon, time)


def _parse_gpx_point(element: ET.Element, timestamp: str) -> TrackPoint:
    latitude = element.get("lat")
    longitude = element.get("lon")
    if latitude is None or longitude is None:
        print(f"GPX: Missing Latitude/Longitude {element}")
        raise ValueError("A GPX track point is missing latitude or longitude.")
    return _parse_point(latitude, longitude, timestamp)


def _parse_tcx_point(element: ET.Element, timestamp: str) -> TrackPoint | None:
    position = next(
        (child for child in element if _local_name(child.tag) == "Position"),
        None,
    )
    if position is None:
        print(f"TCX: Missing Position {element}")
        return None
    latitude = _child_text(position, "LatitudeDegrees")
    longitude = _child_text(position, "LongitudeDegrees")
    if latitude is None or longitude is None:
        print(f"TCX: Missing Latitude/Longitude {element}")
        raise ValueError("A TCX track point is missing latitude or longitude.")
    return _parse_point(latitude, longitude, timestamp)


def load_track(path: Path, start_time: datetime | None = None) -> list[TrackPoint]:
    """Load ordered track points from a GPX or TCX file."""
    suffix = path.suffix.lower()
    if suffix not in {".gpx", ".tcx"}:
        raise ValueError("Input file must have a .gpx or .tcx extension.")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse XML in {path}: {exc}") from exc

    if suffix == ".gpx":
        elements = [
            element
            for element in root.iter()
            if _local_name(element.tag) == "trkpt"
        ]
        timestamps = [_child_text(element, "time") for element in elements]
        if all(timestamp is None for timestamp in timestamps):
            base_time = start_time or datetime.now().astimezone()
            timestamps = [
                (base_time + timedelta(seconds=index)).isoformat()
                for index in range(len(elements))
            ]
        elif any(timestamp is None for timestamp in timestamps):
            raise ValueError(
                "Track points must either all have timestamps or all be missing them."
            )
        timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
        points = [
            _parse_gpx_point(element, timestamp)
            for element, timestamp in zip(elements, timestamps)
        ]
    else:
        elements = [
            element
            for element in root.iter()
            if _local_name(element.tag) == "Trackpoint"
            and any(_local_name(child.tag) == "Position" for child in element)
        ]
        timestamps = [_child_text(element, "Time") for element in elements]
        if all(timestamp is None for timestamp in timestamps):
            base_time = start_time or datetime.now().astimezone()
            timestamps = [
                (base_time + timedelta(seconds=index)).isoformat()
                for index in range(len(elements))
            ]
        elif any(timestamp is None for timestamp in timestamps):
            raise ValueError(
                "Track points must either all have timestamps or all be missing them."
            )
        timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
        points = []
        for element, timestamp in zip(elements, timestamps):
            point = _parse_tcx_point(element, timestamp)
            if point is not None:
                points.append(point)
    if not points:
        raise ValueError(f"No track points found in {path}.")
    return points


def distance_meters(first: TrackPoint, second: TrackPoint) -> float:
    """Return the great-circle distance between two GPS points."""
    lat1, lat2 = math.radians(first.latitude), math.radians(second.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(second.longitude - first.longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(min(1.0, haversine)))


def measure_laps(
    points: Iterable[TrackPoint],
    radius_meters: float = DEFAULT_RADIUS_METERS,
    start_location: tuple[float, float] | None = None,
) -> list[Lap]:
    """Measure completed laps on each return within the start-point radius."""
    return [
        lap
        for lap, _ in measure_laps_with_routes(
            points,
            radius_meters=radius_meters,
            start_location=start_location,
        )
    ]


def measure_laps_with_routes(
    points: Iterable[TrackPoint],
    radius_meters: float = DEFAULT_RADIUS_METERS,
    start_location: tuple[float, float] | None = None,
) -> list[tuple[Lap, list[TrackPoint]]]:
    """Measure completed laps on each return within the start-point radius."""
    if not math.isfinite(radius_meters) or radius_meters <= 0:
        raise ValueError("The start-point radius must be a positive number.")

    iterator = iter(points)
    try:
        first_point = next(iterator)
    except StopIteration as exc:
        raise ValueError("No track points to analyze.") from exc

    if start_location is None:
        start = first_point
    else:
        latitude, longitude = start_location
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError(f"Latitude out of range: {latitude}")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError(f"Longitude out of range: {longitude}")
        start = TrackPoint(latitude, longitude, first_point.timestamp)

    previous = first_point
    cumulative_meters = 0.0
    last_lap_meters = 0.0
    last_lap_time = first_point.timestamp
    last_timestamp = first_point.timestamp
    lap_number = 0
    has_left_start = distance_meters(start, first_point) > radius_meters
    laps_with_routes: list[tuple[Lap, list[TrackPoint]]] = []
    lap_route = [first_point]

    for point in iterator:
        if (point.timestamp.utcoffset() is None) != (last_timestamp.utcoffset() is None):
            raise ValueError("Track timestamps must consistently include a timezone.")
        if point.timestamp < last_timestamp:
            raise ValueError("Track point timestamps must be in chronological order.")
        lap_route.append(point)
        cumulative_meters += distance_meters(previous, point)
        distance_from_start = distance_meters(start, point)

        if distance_from_start > radius_meters:
            has_left_start = True
        elif has_left_start:
            lap_number += 1
            lap_meters = cumulative_meters - last_lap_meters
            elapsed_seconds = (point.timestamp - last_lap_time).total_seconds()
            total_seconds = (point.timestamp - start.timestamp).total_seconds()
            lap_miles = lap_meters / METERS_PER_MILE
            pace = elapsed_seconds / 60 / lap_miles if lap_miles else None
            laps_with_routes.append(
                (
                    Lap(
                        number=lap_number,
                        distance_miles=lap_miles,
                        total_distance_miles=cumulative_meters / METERS_PER_MILE,
                        elapsed_seconds=elapsed_seconds,
                        total_seconds=total_seconds,
                        pace_minutes_per_mile=pace,
                    ),
                    lap_route,
                )
            )
            lap_route = [point]
            last_lap_meters = cumulative_meters
            last_lap_time = point.timestamp
            has_left_start = False

        previous = point
        last_timestamp = point.timestamp

    return laps_with_routes


def _format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def write_laps_csv(path: Path, laps: Iterable[Lap]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "lap",
                "lap_distance_miles",
                "total_distance_miles",
                "lap_time",
                "total_time",
                "lap_pace_minutes_per_mile",
            )
        )
        for lap in laps:
            writer.writerow(
                (
                    lap.number,
                    f"{lap.distance_miles:.3f}",
                    f"{lap.total_distance_miles:.3f}",
                    _format_duration(lap.elapsed_seconds),
                    _format_duration(lap.total_seconds),
                    ""
                    if lap.pace_minutes_per_mile is None
                    else f"{lap.pace_minutes_per_mile:.2f}",
                )
            )


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Start time must be an ISO 8601 datetime (for example, 2024-01-01T12:00:00Z)."
        ) from exc


def main(start_time: datetime | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Create a lap-by-lap CSV from a GPX or TCX GPS track."
    )
    parser.add_argument("input_file", type=Path, help="Input .gpx or .tcx file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="CSV output path (default: <input>_laps.csv)",
    )
    parser.add_argument(
        "--radius-meters",
        type=float,
        default=DEFAULT_RADIUS_METERS,
        help=f"Distance from the first point that counts as a pass (default: {DEFAULT_RADIUS_METERS:g})",
    )
    parser.add_argument(
        "--start-time",
        type=_parse_datetime,
        default=start_time or datetime.now().astimezone(),
        help="Base ISO 8601 datetime for tracks with no timestamps "
        "(default: current local time)",
    )
    args = parser.parse_args()
    output_path = args.output or args.input_file.with_name(
        f"{args.input_file.stem}_laps.csv"
    )

    try:
        laps = measure_laps(
            load_track(args.input_file, args.start_time), args.radius_meters
        )
        write_laps_csv(output_path, laps)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Wrote {len(laps)} laps to {output_path}")


if __name__ == "__main__":
    main()