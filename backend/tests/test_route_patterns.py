import math
import unittest

from core.route_patterns import fit_route_patterns


def _circle_route(
    radius_meters: float,
    phase: float,
    point_count: int = 65,
) -> list[tuple[float, float]]:
    earth_radius_meters = 6_371_000
    route = []
    for index in range(point_count):
        angle = 2 * math.pi * index / (point_count - 1) + phase
        x = radius_meters * math.cos(angle)
        y = radius_meters * math.sin(angle)
        latitude = math.degrees(y / earth_radius_meters)
        longitude = math.degrees(
            x / (earth_radius_meters * math.cos(math.radians(42)))
        )
        route.append((42 + latitude, -83 + longitude))
    return route


class RoutePatternTests(unittest.TestCase):
    def test_fits_three_patterns_against_all_laps(self) -> None:
        routes = [
            _circle_route(100, 0),
            _circle_route(103, 0.01),
            _circle_route(120, -0.02),
        ]

        patterns = fit_route_patterns(routes)

        self.assertEqual(
            [pattern.algorithm for pattern in patterns],
            [
                "Extended Kalman Filtering (EKF)",
                "Smoothing Splines",
                "Bézier Curves",
            ],
        )
        for pattern in patterns:
            with self.subTest(algorithm=pattern.algorithm):
                self.assertIn(pattern.best_fit_lap, range(1, len(routes) + 1))
                self.assertGreater(pattern.length_miles, 0)
                self.assertGreater(len(pattern.coordinates), 2)
                self.assertTrue(math.isfinite(pattern.fit_rmse_meters))
                for latitude, longitude in pattern.coordinates:
                    self.assertTrue(-90 <= latitude <= 90)
                    self.assertTrue(-180 <= longitude <= 180)

    def test_empty_lap_set_has_no_patterns(self) -> None:
        self.assertEqual(fit_route_patterns([]), [])


if __name__ == "__main__":
    unittest.main()
