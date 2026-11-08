import { FormEvent, useEffect, useRef, useState } from "react";
import { latLngBounds, Map as LeafletMap } from "leaflet";
import {
  Activity,
  Download,
  Gauge,
  LoaderCircle,
  MapPin,
  Route as RouteIcon,
  SlidersHorizontal,
  Timer,
  Upload,
} from "lucide-react";
import {
  Circle,
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";

type Coordinate = {
  latitude: number;
  longitude: number;
};

type Lap = {
  number: number;
  distance_miles: number;
  total_distance_miles: number;
  elevation_gain: number;
  total_elevation_gain: number;
  elapsed_seconds: number;
  total_seconds: number;
  pace_minutes_per_mile: number | null;
};

type LapRoute = {
  lap_number: number;
  coordinates: Coordinate[];
};

type StatisticalPattern = {
  algorithm: string;
  best_fit_lap: number;
  length_miles: number;
  coordinates: Coordinate[];
  fit_rmse_meters: number;
};

type ProcessingResult = {
  track_point_count: number;
  start_location: Coordinate;
  first_point_time: string;
  laps: Lap[];
  routes: LapRoute[];
  statistical_patterns: StatisticalPattern[];
};

type StartLocation = {
  latitude: number;
  longitude: number;
};

const PATTERN_COLORS: Record<string, string> = {
  "Extended Kalman Filtering (EKF)": "#d94f4f",
  // "Smoothing Splines": "#e58b2f",
  "Bézier Curves": "#d4ae22",
};

function zoomToExtent(map: LeafletMap, routes: LapRoute[]) {
  const coordinates = routes.flatMap((route) =>
    route.coordinates
      .filter(
        (point) =>
          Number.isFinite(point.latitude) &&
          point.latitude >= -90 &&
          point.latitude <= 90 &&
          Number.isFinite(point.longitude) &&
          point.longitude >= -180 &&
          point.longitude <= 180,
      )
      .map((point) => [point.latitude, point.longitude] as [number, number]),
  );
  const bounds = latLngBounds(coordinates);

  if (bounds.isValid()) {
    map.fitBounds(bounds, { padding: [24, 24] });
  }
}

function InitialRouteExtent({ routes }: { routes: LapRoute[] }) {
  const map = useMap();

  useEffect(() => {
    zoomToExtent(map, routes);
  }, [map]);

  return null;
}

function localDateTimeValue(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function MapClickHandler({
  onPick,
}: {
  onPick: (location: StartLocation) => void;
}) {
  useMapEvents({
    click(event) {
      onPick({
        latitude: event.latlng.lat,
        longitude: event.latlng.lng,
      });
    },
  });
  return null;
}

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ProcessingResult | null>(null);
  const [radius, setRadius] = useState("20");
  const [startTime, setStartTime] = useState(() =>
    localDateTimeValue(new Date()),
  );
  const [startLatitude, setStartLatitude] = useState("");
  const [startLongitude, setStartLongitude] = useState("");
  const [visibleLaps, setVisibleLaps] = useState<Record<number, boolean>>({});
  const [visiblePatterns, setVisiblePatterns] = useState<
    Record<string, boolean>
  >({});
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState("");
  const [mapKey, setMapKey] = useState(0);
  const requestId = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);

  const processTrack = async (
    trackFile: File,
    startLocation?: StartLocation,
  ) => {
    const radiusValue = Number(radius);
    if (!Number.isFinite(radiusValue) || radiusValue <= 0) {
      setError("Return radius must be a positive number.");
      return;
    }

    const request = ++requestId.current;
    setIsProcessing(true);
    setError("");

    const formData = new FormData();
    formData.append("file", trackFile);
    formData.append("radius_meters", radius);
    if (startTime) {
      formData.append("start_time", new Date(startTime).toISOString());
    }
    if (startLocation) {
      formData.append("start_latitude", String(startLocation.latitude));
      formData.append("start_longitude", String(startLocation.longitude));
    }

    try {
      const response = await fetch("/api/process-gps", {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail ?? "Could not process this track.");
      }

      const data = (await response.json()) as ProcessingResult;
      if (request !== requestId.current) return;
      setResult(data);
      setStartTime(localDateTimeValue(new Date(data.first_point_time)));
      setStartLatitude(data.start_location.latitude.toFixed(6));
      setStartLongitude(data.start_location.longitude.toFixed(6));
      setVisibleLaps((previous) =>
        Object.fromEntries(
          data.routes.map((route) => [
            route.lap_number,
            previous[route.lap_number] ?? true,
          ]),
        ),
      );
      setVisiblePatterns((previous) =>
        Object.fromEntries(
          data.statistical_patterns.map((pattern) => [
            pattern.algorithm,
            previous[pattern.algorithm] ?? true,
          ]),
        ),
      );
    } catch (caught) {
      if (request === requestId.current) {
        setError(
          caught instanceof Error
            ? caught.message
            : "An unexpected error occurred while processing the track.",
        );
      }
    } finally {
      if (request === requestId.current) {
        setIsProcessing(false);
      }
    }
  };

  const handleFile = (selected: File | undefined) => {
    if (!selected) return;
    setFile(selected);
    setResult(null);
    setVisibleLaps({});
    setVisiblePatterns({});
    setStartLatitude("");
    setStartLongitude("");
    setMapKey((current) => current + 1);
    void processTrack(selected);
  };

  const handleAnalyze = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) return;

    let location: StartLocation | undefined;
    if (startLatitude.trim() || startLongitude.trim()) {
      const latitude = Number(startLatitude);
      const longitude = Number(startLongitude);
      if (
        !Number.isFinite(latitude) ||
        latitude < -90 ||
        latitude > 90 ||
        !Number.isFinite(longitude) ||
        longitude < -180 ||
        longitude > 180
      ) {
        setError("Enter a valid latitude and longitude.");
        return;
      }
      location = { latitude, longitude };
    }
    void processTrack(file, location);
  };

  const handleMapPick = (location: StartLocation) => {
    setStartLatitude(location.latitude.toFixed(6));
    setStartLongitude(location.longitude.toFixed(6));
    if (file) void processTrack(file, location);
  };

  const allLapsVisible =
    !!result?.routes.length &&
    result.routes.every((route) => visibleLaps[route.lap_number] !== false);

  const setAllRoutesVisible = (checked: boolean) => {
    if (!result) return;
    setVisibleLaps(
      Object.fromEntries(
        result.routes.map((route) => [route.lap_number, checked]),
      ),
    );
  };

  const downloadCsv = () => {
    if (!result?.laps.length) return;
    const headers = [
      "lap",
      "lap_distance_miles",
      "total_distance_miles",
      "lap_elevation_gain",
      "total_elevation_gain",
      "lap_time",
      "total_time",
      "lap_pace_minutes_per_mile",
    ];
    const rows = result.laps.map((lap) => [
      lap.number,
      lap.distance_miles.toFixed(3),
      lap.total_distance_miles.toFixed(3),
      lap.elevation_gain.toFixed(0),
      lap.total_elevation_gain.toFixed(0),
      formatDuration(lap.elapsed_seconds),
      formatDuration(lap.total_seconds),
      lap.pace_minutes_per_mile?.toFixed(2) ?? "",
    ]);
    const csv = [headers, ...rows]
      .map((row) =>
        row.map((value) => `"${String(value).replace(/"/g, '""')}"`).join(","),
      )
      .join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "lap_metrics.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Activity size={21} strokeWidth={2.3} />
          </div>
          <div>
            <div className="brand-name">Trail Trace</div>
            <div className="brand-caption">GPS track analyzer</div>
          </div>
        </div>

        <div className="sidebar-content">
          <section className="side-section">
            <div className="section-title">
              <Upload size={15} />
              <span>Track file</span>
            </div>
            <button
              className="upload-target"
              type="button"
              onClick={() => fileInput.current?.click()}
            >
              <span className="upload-icon">
                <Upload size={19} />
              </span>
              <span className="upload-title">
                {file ? "Choose another track" : "Upload a GPX or TCX file"}
              </span>
              <span className="upload-hint">Up to 25 MB</span>
            </button>
            <input
              ref={fileInput}
              className="visually-hidden"
              type="file"
              accept=".gpx,.tcx"
              onChange={(event) => {
                handleFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
            {file && (
              <div className="selected-file" title={file.name}>
                <RouteIcon size={15} />
                <span>{file.name}</span>
              </div>
            )}
          </section>

          {result && (
            <section className="side-section pattern-controls">
              <div className="section-title">
                <Activity size={15} />
                <span>Route Analysis</span>
              </div>
              {result.statistical_patterns.length ? (
                <div
                  className="pattern-table"
                  role="table"
                  aria-label="Statistical route patterns"
                >
                  <div className="pattern-table-header" role="row">
                    <span role="columnheader" aria-label="Show pattern" />
                    <span role="columnheader">Algorithm</span>
                    <span role="columnheader">Key</span>
                    <span role="columnheader">Dist</span>
                  </div>
                  {result.statistical_patterns.map((pattern) => (
                    <label
                      className="pattern-row"
                      key={pattern.algorithm}
                      role="row"
                    >
                      <span className="pattern-checkbox" role="cell">
                        <input
                          type="checkbox"
                          checked={visiblePatterns[pattern.algorithm] ?? true}
                          onChange={(event) =>
                            setVisiblePatterns((previous) => ({
                              ...previous,
                              [pattern.algorithm]: event.target.checked,
                            }))
                          }
                          aria-label={`Show ${pattern.algorithm} pattern route`}
                        />
                        <span className="custom-check" />
                      </span>
                      <span
                        className="pattern-algorithm"
                        role="cell"
                        title={`Best fit: lap ${pattern.best_fit_lap}; RMSE ${pattern.fit_rmse_meters.toFixed(1)} m`}
                      >
                        {pattern.algorithm}
                      </span>
                      <span
                        className="pattern-key"
                        role="cell"
                        aria-hidden="true"
                      >
                        <span
                          className="pattern-key-line"
                          style={{
                            backgroundColor:
                              PATTERN_COLORS[pattern.algorithm] ?? "#66736f",
                          }}
                        />
                      </span>
                      <span className="pattern-length" role="cell">
                        {pattern.length_miles.toFixed(2)} mi
                      </span>
                    </label>
                  ))}
                </div>
              ) : (
                <p className="pattern-empty">
                  No completed laps are available for route pattern fitting.
                </p>
              )}
            </section>
          )}

          {/* {result && result.routes.length > 0 && (
            <section className="side-section route-controls">
              <div className="section-title">
                <RouteIcon size={15} />
                <span>Map routes</span>
              </div>
              <label className="route-toggle route-toggle-all">
                <span className="route-toggle-check">
                  <input
                    type="checkbox"
                    checked={allLapsVisible}
                    onChange={(event) =>
                      setAllRoutesVisible(event.target.checked)
                    }
                    aria-label="Show all lap routes"
                  />
                  <span className="custom-check" />
                </span>
                <strong>Show all routes</strong>
              </label>
              <div className="route-toggle-list">
                {result.routes.map((route) => (
                  <label className="route-toggle" key={route.lap_number}>
                    <span className="route-toggle-check">
                      <input
                        type="checkbox"
                        checked={visibleLaps[route.lap_number] !== false}
                        onChange={(event) =>
                          setVisibleLaps((previous) => ({
                            ...previous,
                            [route.lap_number]: event.target.checked,
                          }))
                        }
                        aria-label={`Show lap ${route.lap_number} route`}
                      />
                      <span className="custom-check" />
                    </span>
                    <span className="route-toggle-name">
                      Lap {String(route.lap_number).padStart(2, "0")}
                    </span>
                    <small>
                      {result.laps
                        .find((lap) => lap.number === route.lap_number)
                        ?.distance_miles.toFixed(2)}{" "}
                      mi
                    </small>
                  </label>
                ))}
              </div>
            </section>
          )} */}

          <form className="side-section settings-form" onSubmit={handleAnalyze}>
            <div className="section-title">
              <SlidersHorizontal size={15} />
              <span>Analysis parameters</span>
            </div>
            <label className="field-label" htmlFor="radius">
              Return radius
            </label>
            <div className="input-with-unit">
              <input
                id="radius"
                type="number"
                min="0.1"
                step="any"
                value={radius}
                onChange={(event) => setRadius(event.target.value)}
              />
              <span>meters</span>
            </div>

            <label className="field-label" htmlFor="start-time">
              Start time
            </label>
            <input
              id="start-time"
              className="text-input"
              type="datetime-local"
              value={startTime}
              onChange={(event) => setStartTime(event.target.value)}
            />
            <span className="field-hint">
              Used when the track has no timestamps.
            </span>

            <div className="field-label start-location-label">
              Lap start location
            </div>
            <div className="coordinate-inputs">
              <label>
                <span>Latitude</span>
                <input
                  type="number"
                  min="-90"
                  max="90"
                  step="any"
                  value={startLatitude}
                  placeholder="—"
                  onChange={(event) => setStartLatitude(event.target.value)}
                />
              </label>
              <label>
                <span>Longitude</span>
                <input
                  type="number"
                  min="-180"
                  max="180"
                  step="any"
                  value={startLongitude}
                  placeholder="—"
                  onChange={(event) => setStartLongitude(event.target.value)}
                />
              </label>
            </div>

            <button
              className="primary-button"
              type="submit"
              disabled={!file || isProcessing}
            >
              {isProcessing ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Activity size={16} />
              )}
              <span>{isProcessing ? "Analyzing…" : "Analyze track"}</span>
            </button>
          </form>

          {error && (
            <div className="error-message" role="alert">
              {error}
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <span className="status-dot" />
          <span>GPX and TCX supported</span>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">TRACK OVERVIEW</p>
            <h1>{file ? file.name : "Analyze your route"}</h1>
          </div>
          {result && (
            <div className="topbar-stats">
              <div className="topbar-stat">
                <RouteIcon size={16} />
                <span>{result.laps.length} laps</span>
              </div>
              <div className="topbar-stat">
                <MapPin size={16} />
                <span>{result.track_point_count.toLocaleString()} points</span>
              </div>
              <div className="topbar-stat">
                  <Timer size={16} />
                  <span>
                  {formatDuration(
                    result.laps[result.laps.length - 1].total_seconds,
                  )} (
                  {formatDuration(
                    result.laps[result.laps.length - 1].total_seconds /
                    result.laps.length,
                  )}/lap)
                  </span>
              </div>
              <div className="topbar-stat">
                <Gauge size={16} />
                <span>
                {result.laps[
                  result.laps.length - 1
                ].total_distance_miles.toFixed(2)}{" "}
                mi (
                  {(
                  result.laps[result.laps.length - 1].total_distance_miles /
                  result.laps.length
                ).toFixed(2)}{" "}
                mi/lap)
                </span>
              </div>
              <div className="topbar-stat">
                <Gauge size={16} />
                <span>
                {(result.laps[
                  result.laps.length - 1
                ].total_elevation_gain ?? 0).toFixed(0)}{" "}
                ft (
                  {(
                  (result.laps[result.laps.length - 1].total_elevation_gain ?? 0) /
                  result.laps.length
                ).toFixed(0)}{" "}
                ft/lap)
                </span>
              </div>
              <div className="topbar-stat">
                <Timer size={16} />
                <span>
                  {formatDuration(
                    result.laps[result.laps.length - 1].total_seconds /
                    (result.laps[result.laps.length - 1].total_distance_miles),
                  )}/mi
                </span>
              </div>
            </div>
          )}
        </header>

        {result ? (
          <div className="content-grid">
            <section className="map-panel">
              <div className="panel-heading">
                <div>
                  <h2>Route map</h2>
                  <p>Click anywhere on the map to set the lap start point.</p>
                </div>
                <div className="map-legend">
                  <span className="legend-line" />
                  <span>Lap route</span>
                  <span className="legend-dot" />
                  <span>Start point</span>
                </div>
              </div>
              <div className="map-frame">
                <MapContainer
                  key={mapKey}
                  center={[
                    result.start_location.latitude,
                    result.start_location.longitude,
                  ]}
                  zoom={14}
                  scrollWheelZoom
                  className="route-map"
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  <InitialRouteExtent routes={result.routes} />
                  <MapClickHandler onPick={handleMapPick} />
                  {result.routes.map(
                    (route) =>
                      visibleLaps[route.lap_number] !== false && (
                        <Polyline
                          key={route.lap_number}
                          positions={route.coordinates.map((point) => [
                            point.latitude,
                            point.longitude,
                          ] as [number, number])}
                          pathOptions={{
                            color: "#337c72",
                            weight: 4,
                            opacity: 0.88,
                          }}
                        >
                          <Popup>Lap {route.lap_number}</Popup>
                        </Polyline>
                      ),
                  )}
                  {result.statistical_patterns.map(
                    (pattern) =>
                      (visiblePatterns[pattern.algorithm] ?? true) && (
                        <Polyline
                          key={`pattern-${pattern.algorithm}`}
                          positions={pattern.coordinates.map(
                            (point) =>
                              [point.latitude, point.longitude] as [
                                number,
                                number,
                              ],
                          )}
                          pathOptions={{
                            color:
                              PATTERN_COLORS[pattern.algorithm] ?? "#66736f",
                            weight: 5,
                            opacity: 0.95,
                            dashArray: "8 6",
                          }}
                        >
                          <Popup>
                            {pattern.algorithm} · best fit lap{" "}
                            {pattern.best_fit_lap} ·{" "}
                            {pattern.length_miles.toFixed(2)} mi
                          </Popup>
                        </Polyline>
                      ),
                  )}
                  <Circle
                    center={[
                      result.start_location.latitude,
                      result.start_location.longitude,
                    ]}
                    radius={Number(radius) || 20}
                    pathOptions={{
                      color: "#d29453",
                      fillColor: "#e5aa6f",
                      fillOpacity: 0.12,
                    }}
                  />
                  <CircleMarker
                    center={[
                      result.start_location.latitude,
                      result.start_location.longitude,
                    ]}
                    radius={7}
                    pathOptions={{
                      color: "#fff",
                      weight: 2,
                      fillColor: "#d29453",
                      fillOpacity: 1,
                    }}
                  >
                    <Popup>Lap start location</Popup>
                  </CircleMarker>
                </MapContainer>
                {isProcessing && (
                  <div className="map-loading">
                    <LoaderCircle className="spin" size={17} />
                    Updating analysis…
                  </div>
                )}
              </div>
            </section>

            <section className="laps-panel">
              <div className="panel-heading laps-heading">
                <div>
                  <h2>Lap statistics</h2>
                  <p>Choose which laps to show on the map.</p>
                </div>
                <button
                  className="icon-button"
                  type="button"
                  onClick={downloadCsv}
                  disabled={!result.laps.length}
                  title="Export metrics to CSV"
                  aria-label="Export metrics to CSV"
                >
                  <Download size={17} />
                </button>
              </div>

              {result.laps.length ? (
                <>
                  <div className="lap-list">
                    <div className="lap-list-header">
                      <label className="check-cell all-check">
                        <input
                          type="checkbox"
                          checked={allLapsVisible}
                          onChange={(event) =>
                            setAllRoutesVisible(event.target.checked)
                          }
                          aria-label="Show all lap routes"
                        />
                        <span className="custom-check" />
                        <span>ALL</span>
                      </label>
                      <span>LAP</span>
                      <span>DIST</span>
                      <span>ELEV</span>
                      <span>TIME</span>
                      <span>PACE</span>
                    </div>
                    <div className="lap-scroll">
                      {result.laps.map((lap) => (
                        <label className="lap-row" key={lap.number}>
                          <span className="check-cell">
                            <input
                              type="checkbox"
                              checked={visibleLaps[lap.number] !== false}
                              onChange={(event) =>
                                setVisibleLaps((previous) => ({
                                  ...previous,
                                  [lap.number]: event.target.checked,
                                }))
                              }
                              aria-label={`Show lap ${lap.number} route`}
                            />
                            <span className="custom-check" />
                          </span>
                          <span className="lap-number">
                            {String(lap.number).padStart(2, "0")}
                          </span>
                          <span className="lap-data">
                            <strong>{lap.distance_miles.toFixed(2)}</strong>
                            <small>mi</small>
                          </span>
                          <span className="lap-data">
                            <strong>{(lap.elevation_gain ?? 0).toFixed(0)}</strong>
                            <small>ft</small>
                          </span>
                          <span className="lap-data">
                            <strong>{formatDuration(lap.elapsed_seconds)}</strong>
                          </span>
                          <span className="lap-data">
                            <strong>
                              {lap.pace_minutes_per_mile === null
                                ? "—"
                                : `${lap.pace_minutes_per_mile.toFixed(2)}`}
                            </strong>
                            {lap.pace_minutes_per_mile !== null && (
                              <small>min/mi</small>
                            )}
                          </span>
                        </label>
                      ))}
                    </div>
                    {/* <div className="lap-summary">
                      <div>
                        <Timer size={16} />
                        <span>Total time</span>
                        <strong>
                          {formatDuration(
                            result.laps[result.laps.length - 1].total_seconds,
                          )} (
                          {formatDuration(
                            result.laps[result.laps.length - 1].total_seconds /
                            result.laps.length,
                          )}/lap)
                        </strong>
                      </div>
                      <div>
                        <Gauge size={16} />
                        <span>Total distance</span>
                        <strong>
                          {result.laps[
                            result.laps.length - 1
                          ].total_distance_miles.toFixed(2)}{" "}
                          mi (
                            {(
                            result.laps[result.laps.length - 1].total_distance_miles /
                            result.laps.length
                          ).toFixed(2)}{" "}
                          mi/lap)
                        </strong>
                      </div>
                    </div> */}
                  </div>
                </>
              ) : (
                <div className="empty-laps">
                  <RouteIcon size={22} />
                  <strong>No completed laps</strong>
                  <span>
                    No returns were found within the selected start radius.
                  </span>
                </div>
              )}
            </section>
          </div>
        ) : (
          <div className="welcome-panel">
            <div className="welcome-icon">
              <MapPin size={29} />
            </div>
            <p className="eyebrow">YOUR ROUTE, IN FOCUS</p>
            <h2>Make every lap count.</h2>
            <p className="welcome-copy">
              Upload a GPS track to map your route, measure completed laps, and
              compare your pace.
            </p>
            <button
              className="primary-button welcome-button"
              type="button"
              onClick={() => fileInput.current?.click()}
            >
              <Upload size={16} />
              <span>Upload a track</span>
            </button>
          </div>
        )}
      </section>
    </main>
  );
}

export default App;
