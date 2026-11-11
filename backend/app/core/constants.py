from typing import Final

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
EARTH_RADIUS_METERS: Final[int] = 6_371_000
METERS_PER_MILE: Final[float] = 1609.344
FEET_PER_METER: Final[float] = 3.28084
DEFAULT_RADIUS_METERS: Final[float] = 20.0
ELEVATION_TOLERANCE_METERS: Final[float] = 3.0
NUMBER_OF_POINTS_ERROR_THRESHOLD: Final[int] = 5 # percentage of total points beyond tolerance
