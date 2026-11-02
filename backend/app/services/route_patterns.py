"""Fit representative statistical routes across a set of GPS laps."""

import math
from dataclasses import dataclass
from typing import Callable

from scipy.interpolate import splprep, splev

EARTH_RADIUS_METERS = 6_371_000.0
METERS_PER_MILE = 1609.344
SAMPLE_COUNT = 96
EKF_POSITION_NOISE_METERS = 3.0
SPLINE_POSITION_NOISE_METERS = 4.0

Point = tuple[float, float]
GeographicPoint = tuple[float, float]


@dataclass(frozen=True)
class PatternFit:
    algorithm: str
    best_fit_lap: int
    length_miles: float
    coordinates: list[GeographicPoint]
    fit_rmse_meters: float


def _project_route(
    route: list[GeographicPoint],
    origin: GeographicPoint,
    reference_latitude: float,
) -> list[Point]:
    origin_latitude, origin_longitude = origin
    cosine_latitude = math.cos(math.radians(reference_latitude))
    return [
        (
            EARTH_RADIUS_METERS
            * math.radians(longitude - origin_longitude)
            * cosine_latitude,
            EARTH_RADIUS_METERS * math.radians(latitude - origin_latitude),
        )
        for latitude, longitude in route
    ]


def _resample_route(route: list[Point], sample_count: int) -> list[Point]:
    cumulative = [0.0]
    for first, second in zip(route, route[1:]):
        cumulative.append(
            cumulative[-1] + math.dist(first, second)
        )
    total_length = cumulative[-1]
    if not math.isfinite(total_length) or total_length <= 0:
        raise ValueError("A lap route must have positive length to fit a pattern.")

    resampled: list[Point] = []
    segment_index = 0
    for sample_index in range(sample_count):
        target = total_length * sample_index / (sample_count - 1)
        while (
            segment_index < len(cumulative) - 2
            and cumulative[segment_index + 1] < target
        ):
            segment_index += 1
        segment_length = cumulative[segment_index + 1] - cumulative[segment_index]
        fraction = (
            0.0
            if segment_length == 0
            else (target - cumulative[segment_index]) / segment_length
        )
        first = route[segment_index]
        second = route[segment_index + 1]
        resampled.append(
            (
                first[0] + (second[0] - first[0]) * fraction,
                first[1] + (second[1] - first[1]) * fraction,
            )
        )
    return resampled


def _fit_extended_kalman_filter(route: list[Point]) -> list[Point]:
    position_variance = EKF_POSITION_NOISE_METERS**2
    state = [
        route[0][0],
        route[0][1],
        math.dist(route[0], route[1]),
        math.atan2(route[1][1] - route[0][1], route[1][0] - route[0][0]),
    ]
    covariance = [
        [25.0, 0.0, 0.0, 0.0],
        [0.0, 25.0, 0.0, 0.0],
        [0.0, 0.0, 4.0, 0.0],
        [0.0, 0.0, 0.0, 0.25],
    ]
    filtered = [route[0]]

    for measurement in route[1:]:
        x, y, speed, heading = state
        cosine_heading = math.cos(heading)
        sine_heading = math.sin(heading)
        transition = [
            [1.0, 0.0, cosine_heading, -speed * sine_heading],
            [0.0, 1.0, sine_heading, speed * cosine_heading],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        predicted_state = [
            x + speed * cosine_heading,
            y + speed * sine_heading,
            speed,
            heading,
        ]
        predicted_covariance = _multiply(
            _multiply(transition, covariance),
            _transpose(transition),
        )
        for index, process_variance in enumerate((0.05, 0.05, 0.4, 0.03)):
            predicted_covariance[index][index] += process_variance

        innovation_covariance = [
            [
                predicted_covariance[0][0] + position_variance,
                predicted_covariance[0][1],
            ],
            [
                predicted_covariance[1][0],
                predicted_covariance[1][1] + position_variance,
            ],
        ]
        inverse_innovation = _inverse_2x2(innovation_covariance)
        gain = [
            [
                predicted_covariance[row][0] * inverse_innovation[0][column]
                + predicted_covariance[row][1] * inverse_innovation[1][column]
                for column in range(2)
            ]
            for row in range(4)
        ]
        residual = (
            measurement[0] - predicted_state[0],
            measurement[1] - predicted_state[1],
        )
        state = [
            predicted_state[row]
            + gain[row][0] * residual[0]
            + gain[row][1] * residual[1]
            for row in range(4)
        ]
        state[3] = (state[3] + math.pi) % (2 * math.pi) - math.pi

        correction = [
            [
                (1.0 if row == column else 0.0)
                - (gain[row][0] if column == 0 else 0.0)
                - (gain[row][1] if column == 1 else 0.0)
                for column in range(4)
            ]
            for row in range(4)
        ]
        measurement_noise = [
            [position_variance, 0.0],
            [0.0, position_variance],
        ]
        covariance = _add(
            _multiply(
                _multiply(correction, predicted_covariance),
                _transpose(correction),
            ),
            _multiply(_multiply(gain, measurement_noise), _transpose(gain)),
        )
        filtered.append((state[0], state[1]))
    return filtered


def _fit_smoothing_spline(route: list[Point]) -> list[Point]:
    x_values, y_values = zip(*route)
    spline, _ = splprep(
        [x_values, y_values],
        s=len(route) * SPLINE_POSITION_NOISE_METERS**2,
        k=3,
        per=True,
    )
    smoothed_x, smoothed_y = splev(
        [index / (SAMPLE_COUNT - 1) for index in range(SAMPLE_COUNT)],
        spline,
    )
    return list(zip(smoothed_x, smoothed_y))


def _fit_bezier_curve(route: list[Point]) -> list[Point]:
    unique_route = route[:-1]
    if len(unique_route) < 3:
        raise ValueError("A lap needs at least three points for a Bézier fit.")

    segment_steps = 8
    fitted: list[Point] = []
    point_count = len(unique_route)
    for index, start in enumerate(unique_route):
        previous = unique_route[(index - 1) % point_count]
        end = unique_route[(index + 1) % point_count]
        following = unique_route[(index + 2) % point_count]
        control_one = (
            start[0] + (end[0] - previous[0]) / 6,
            start[1] + (end[1] - previous[1]) / 6,
        )
        control_two = (
            end[0] - (following[0] - start[0]) / 6,
            end[1] - (following[1] - start[1]) / 6,
        )
        for step in range(segment_steps):
            t = step / segment_steps
            inverse_t = 1 - t
            fitted.append(
                (
                    inverse_t**3 * start[0]
                    + 3 * inverse_t**2 * t * control_one[0]
                    + 3 * inverse_t * t**2 * control_two[0]
                    + t**3 * end[0],
                    inverse_t**3 * start[1]
                    + 3 * inverse_t**2 * t * control_one[1]
                    + 3 * inverse_t * t**2 * control_two[1]
                    + t**3 * end[1],
                )
            )
    fitted.append(fitted[0])
    return _resample_route(fitted, SAMPLE_COUNT)


def _multiply(first: list[list[float]], second: list[list[float]]) -> list[list[float]]:
    return [
        [
            sum(first[row][index] * second[index][column] for index in range(len(second)))
            for column in range(len(second[0]))
        ]
        for row in range(len(first))
    ]


def _transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [list(column) for column in zip(*matrix)]


def _add(first: list[list[float]], second: list[list[float]]) -> list[list[float]]:
    return [
        [left + right for left, right in zip(first_row, second_row)]
        for first_row, second_row in zip(first, second)
    ]


def _inverse_2x2(matrix: list[list[float]]) -> list[list[float]]:
    determinant = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    if not math.isfinite(determinant) or determinant <= 0:
        raise ValueError("Could not calculate the EKF innovation covariance.")
    return [
        [matrix[1][1] / determinant, -matrix[0][1] / determinant],
        [-matrix[1][0] / determinant, matrix[0][0] / determinant],
    ]


def _route_length(route: list[Point]) -> float:
    return sum(math.dist(first, second) for first, second in zip(route, route[1:]))


def _to_geographic(
    route: list[Point],
    origin: GeographicPoint,
    reference_latitude: float,
) -> list[GeographicPoint]:
    origin_latitude, origin_longitude = origin
    cosine_latitude = math.cos(math.radians(reference_latitude))
    if abs(cosine_latitude) < 1e-12:
        raise ValueError("Cannot fit route patterns at the geographic poles.")
    return [
        (
            origin_latitude + math.degrees(y / EARTH_RADIUS_METERS),
            origin_longitude
            + math.degrees(x / (EARTH_RADIUS_METERS * cosine_latitude)),
        )
        for x, y in route
    ]


def _build_fit(
    algorithm: str,
    routes: list[list[GeographicPoint]],
    origin: GeographicPoint,
    reference_latitude: float,
    fit_route: Callable[[list[Point]], list[Point]],
) -> PatternFit:
    projected = [
        _project_route(route, origin, reference_latitude) for route in routes
    ]
    sampled_routes = [
        _resample_route(route, SAMPLE_COUNT) for route in projected
    ]
    fitted_candidates = [fit_route(route) for route in sampled_routes]
    sampled_fits = [
        _resample_route(route, SAMPLE_COUNT) for route in fitted_candidates
    ]
    consensus = [
        (
            sum(route[index][0] for route in sampled_routes)
            / len(sampled_routes),
            sum(route[index][1] for route in sampled_routes)
            / len(sampled_routes),
        )
        for index in range(SAMPLE_COUNT)
    ]
    errors = [
        sum(
            math.dist(fitted_point, average_point) ** 2
            for fitted_point, average_point in zip(candidate, consensus)
        )
        / SAMPLE_COUNT
        for candidate in sampled_fits
    ]
    best_index = min(range(len(errors)), key=errors.__getitem__)
    geographic_fit = _to_geographic(
        fitted_candidates[best_index],
        origin,
        reference_latitude,
    )
    return PatternFit(
        algorithm=algorithm,
        best_fit_lap=best_index + 1,
        length_miles=_route_length(fitted_candidates[best_index]) / METERS_PER_MILE,
        coordinates=geographic_fit,
        fit_rmse_meters=math.sqrt(errors[best_index]),
    )


def fit_route_patterns(
    routes: list[list[GeographicPoint]],
) -> list[PatternFit]:
    """Fit each algorithm per lap, then select its closest match to all laps."""
    valid_routes = [
        [
            (latitude, longitude)
            for latitude, longitude in route
            if math.isfinite(latitude)
            and -90 <= latitude <= 90
            and math.isfinite(longitude)
            and -180 <= longitude <= 180
        ]
        for route in routes
    ]
    valid_routes = [route for route in valid_routes if len(route) >= 2]
    if not valid_routes:
        return []

    reference_latitude = sum(
        latitude for latitude, _ in valid_routes[0]
    ) / len(valid_routes[0])
    origin = valid_routes[0][0]
    return [
        _build_fit(
            "Extended Kalman Filtering (EKF)",
            valid_routes,
            origin,
            reference_latitude,
            _fit_extended_kalman_filter,
        ),
        _build_fit(
            "Smoothing Splines",
            valid_routes,
            origin,
            reference_latitude,
            _fit_smoothing_spline,
        ),
        _build_fit(
            "Bézier Curves",
            valid_routes,
            origin,
            reference_latitude,
            _fit_bezier_curve,
        ),
    ]
