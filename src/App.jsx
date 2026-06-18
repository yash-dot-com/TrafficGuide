import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");
const BENGALURU_CENTER = [12.9716, 77.5946];
const TIMELINE_STATES = ["T-24h", "T-2h", "Live", "T+2h"];
const FIELD_STATION = "Cubbon Park";

function apiPath(path) {
  return `${API_BASE}${path}`;
}

async function apiRequest(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
  };
  if (options.body !== undefined && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(apiPath(path), {
    ...options,
    headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  return payload;
}

function formatClock(date) {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  }).format(date);
}

function formatTime(value) {
  if (!value) return "Unscheduled";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unscheduled";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  }).format(date);
}

function formatNumber(value) {
  if (value === null || value === undefined) return "0";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(1);
  return String(value);
}

function priorityClass(priority) {
  return String(priority || "").toLowerCase() === "high" ? "high" : "low";
}

function markerEventId(event) {
  return event.id || event.event_id;
}

function markerTitle(event) {
  return event.name || event.event_cause || event.address || markerEventId(event);
}

function eventScheduledStart(event) {
  return event.scheduled_start || event.scheduled_start_time || event.start_datetime;
}

function createPlannedIcon(isHighlighted) {
  return L.divIcon({
    className: `planned-event-icon${isHighlighted ? " planned-event-icon-highlight" : ""}`,
    html: `<span></span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function durationLabel(forecast) {
  if (!forecast) return "Pending";
  const low = Math.round(forecast.duration_low || 0);
  const median = Math.round(forecast.duration_median || 0);
  const high = Math.round(forecast.duration_high || 0);
  return `${low}-${high} min, median ${median}`;
}

function formatMeters(value) {
  const meters = Number(value || 0);
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

function MetricCard({ label, value, accent }) {
  return (
    <section className={`metric-card ${accent || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

function ExecutiveMetric({ label, value, detail }) {
  return (
    <section className="executive-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </section>
  );
}

function TimelineToggle({ value, onChange }) {
  return (
    <div className="timeline-toggle" aria-label="Timeline state">
      {TIMELINE_STATES.map((state) => (
        <button
          key={state}
          type="button"
          className={value === state ? "active" : ""}
          onClick={() => onChange(state)}
        >
          {state}
        </button>
      ))}
    </div>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  return <div className={`toast ${toast.type || "info"}`}>{toast.message}</div>;
}

const FIELD_OFFICER_KEY = "gridFieldOfficer";
const FIELD_QUEUE_KEY = "gridFieldOfflineQueue";

const FIELD_TRANSLATIONS = {
  en: {
    title: "Field Officer View",
    assignment: "Current assignment",
    save: "Save login",
    badge: "Badge ID",
    station: "Station",
    language: "Language",
    refresh: "Refresh",
    sync: "Sync queue",
    alerts: "Enable alerts",
    acknowledged: "Acknowledge",
    deployed: "GPS check-in",
    backup: "Need backup",
    barricades: "Need barricades",
    cleared: "Road cleared",
    note: "Status note",
    photo: "Photo update",
    noPlan: "No accepted plan yet",
    empty: "No control points assigned",
  },
  hi: {
    title: "फील्ड अधिकारी दृश्य",
    assignment: "वर्तमान असाइनमेंट",
    save: "लॉगिन सेव करें",
    badge: "बैज आईडी",
    station: "थाना",
    language: "भाषा",
    refresh: "रीफ्रेश",
    sync: "क्यू सिंक करें",
    alerts: "अलर्ट चालू करें",
    acknowledged: "स्वीकार करें",
    deployed: "GPS चेक-इन",
    backup: "बैकअप चाहिए",
    barricades: "बैरिकेड चाहिए",
    cleared: "सड़क साफ",
    note: "स्थिति नोट",
    photo: "फोटो अपडेट",
    noPlan: "अभी कोई स्वीकृत योजना नहीं",
    empty: "कोई नियंत्रण बिंदु असाइन नहीं",
  },
  kn: {
    title: "ಕ್ಷೇತ್ರ ಅಧಿಕಾರಿ ನೋಟ",
    assignment: "ಪ್ರಸ್ತುತ ನಿಯೋಜನೆ",
    save: "ಲಾಗಿನ್ ಉಳಿಸಿ",
    badge: "ಬ್ಯಾಡ್ಜ್ ಐಡಿ",
    station: "ಠಾಣೆ",
    language: "ಭಾಷೆ",
    refresh: "ರಿಫ್ರೆಶ್",
    sync: "ಕ್ಯೂ ಸಿಂಕ್",
    alerts: "ಎಚ್ಚರಿಕೆ ಆನ್",
    acknowledged: "ಸ್ವೀಕರಿಸಿ",
    deployed: "GPS ಚೆಕ್-ಇನ್",
    backup: "ಬ್ಯಾಕಪ್ ಬೇಕು",
    barricades: "ಬ್ಯಾರಿಕೇಡ್ ಬೇಕು",
    cleared: "ರಸ್ತೆ ತೆರವು",
    note: "ಸ್ಥಿತಿ ಟಿಪ್ಪಣಿ",
    photo: "ಫೋಟೋ ಅಪ್ಡೇಟ್",
    noPlan: "ಇನ್ನೂ ಅನುಮೋದಿತ ಯೋಜನೆ ಇಲ್ಲ",
    empty: "ನಿಯೋಜಿತ ನಿಯಂತ್ರಣ ಬಿಂದುಗಳಿಲ್ಲ",
  },
};

function readStoredJson(key, fallback) {
  try {
    const stored = window.localStorage.getItem(key);
    return stored ? JSON.parse(stored) : fallback;
  } catch {
    return fallback;
  }
}

function FieldPage() {
  const [officer, setOfficer] = useState(() =>
    readStoredJson(FIELD_OFFICER_KEY, {
      badge: "CBP-319",
      station: FIELD_STATION,
      language: "en",
    })
  );
  const [loginDraft, setLoginDraft] = useState(officer);
  const [assignments, setAssignments] = useState(null);
  const [statuses, setStatuses] = useState({});
  const [notes, setNotes] = useState({});
  const [photos, setPhotos] = useState({});
  const [queue, setQueue] = useState(() => readStoredJson(FIELD_QUEUE_KEY, []));
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const t = FIELD_TRANSLATIONS[officer.language] || FIELD_TRANSLATIONS.en;

  const showToast = useCallback((message, type = "info") => {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 2600);
  }, []);

  const loadAssignments = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await apiRequest(`/field/assignments?station=${encodeURIComponent(officer.station)}`);
      setAssignments(payload);
      const nextStatuses = {};
      (payload.assignments || []).forEach((assignment) => {
        nextStatuses[assignment.control_point_node_id] = "pending";
      });
      setStatuses(nextStatuses);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setLoading(false);
    }
  }, [officer.station, showToast]);

  useEffect(() => {
    loadAssignments();
  }, [loadAssignments]);

  useEffect(() => {
    window.localStorage.setItem(FIELD_QUEUE_KEY, JSON.stringify(queue));
  }, [queue]);

  function saveLogin(event) {
    event.preventDefault();
    const nextOfficer = {
      badge: loginDraft.badge || "field.officer",
      station: loginDraft.station || FIELD_STATION,
      language: loginDraft.language || "en",
    };
    setOfficer(nextOfficer);
    window.localStorage.setItem(FIELD_OFFICER_KEY, JSON.stringify(nextOfficer));
    showToast("Login saved", "success");
  }

  async function submitFieldStatus(payload) {
    try {
      await apiRequest("/field/status", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Status sent", "success");
      return true;
    } catch (error) {
      setQueue((current) => [...current, { ...payload, queued_at: new Date().toISOString() }]);
      showToast("Saved offline", "info");
      return false;
    }
  }

  async function flushQueue() {
    if (queue.length === 0) return;
    const remaining = [];
    for (const item of queue) {
      try {
        await apiRequest("/field/status", {
          method: "POST",
          body: JSON.stringify(item),
        });
      } catch {
        remaining.push(item);
      }
    }
    setQueue(remaining);
    showToast(remaining.length === 0 ? "Queue synced" : "Some updates remain offline", remaining.length === 0 ? "success" : "info");
  }

  function baseStatusPayload(assignment, status, extra = {}) {
    return {
      station: officer.station,
      event_id: assignments?.event_id,
      control_point_node_id: assignment.control_point_node_id,
      status,
      actor: officer.badge,
      tenant_id: "bengaluru-traffic",
      note: notes[assignment.control_point_node_id] || undefined,
      photo_url: photos[assignment.control_point_node_id] || undefined,
      ...extra,
    };
  }

  async function sendStatus(assignment, status, extra = {}) {
    setStatuses((current) => ({ ...current, [assignment.control_point_node_id]: status }));
    await submitFieldStatus(baseStatusPayload(assignment, status, extra));
  }

  function gpsCheckIn(assignment) {
    if (!navigator.geolocation) {
      sendStatus(assignment, "deployed");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        sendStatus(assignment, "deployed", {
          lat: position.coords.latitude,
          lon: position.coords.longitude,
        });
      },
      () => sendStatus(assignment, "deployed")
    );
  }

  async function enableAlerts() {
    if (!("Notification" in window)) {
      showToast("Notifications unavailable", "error");
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission === "granted") {
      new Notification("GRID field alerts enabled");
      showToast("Alerts enabled", "success");
    }
  }

  const rows = assignments?.assignments || [];

  return (
    <main className="field-shell">
      <header className="field-header">
        <div>
          <span>{t.title}</span>
          <h1>{officer.station}</h1>
        </div>
        <a href="/" aria-label="Open command console">Console</a>
      </header>

      <form className="field-login" onSubmit={saveLogin}>
        <label>
          <span>{t.badge}</span>
          <input
            value={loginDraft.badge}
            onChange={(event) => setLoginDraft((current) => ({ ...current, badge: event.target.value }))}
          />
        </label>
        <label>
          <span>{t.station}</span>
          <input
            value={loginDraft.station}
            onChange={(event) => setLoginDraft((current) => ({ ...current, station: event.target.value }))}
          />
        </label>
        <label>
          <span>{t.language}</span>
          <select
            value={loginDraft.language}
            onChange={(event) => setLoginDraft((current) => ({ ...current, language: event.target.value }))}
          >
            <option value="en">English</option>
            <option value="hi">हिन्दी</option>
            <option value="kn">ಕನ್ನಡ</option>
          </select>
        </label>
        <button type="submit">{t.save}</button>
      </form>

      <section className="field-context">
        <span>{t.assignment}</span>
        <strong>{assignments?.event_name || t.noPlan}</strong>
        {assignments?.created_at && <time>{formatTime(assignments.created_at)}</time>}
        <div className="field-context-actions">
          <button type="button" onClick={loadAssignments}>{t.refresh}</button>
          <button type="button" onClick={flushQueue}>{t.sync} ({queue.length})</button>
          <button type="button" onClick={enableAlerts}>{t.alerts}</button>
        </div>
      </section>

      {loading ? (
        <section className="field-empty">Loading assignments...</section>
      ) : rows.length === 0 ? (
        <section className="field-empty">
          <strong>{t.empty}</strong>
          <p>Accept a plan touching {officer.station} from the command console.</p>
          <button type="button" onClick={loadAssignments}>{t.refresh}</button>
        </section>
      ) : (
        <section className="field-list" aria-label="Assigned control points">
          {rows.map((assignment, index) => {
            const nodeId = assignment.control_point_node_id;
            const status = statuses[nodeId] || "pending";
            return (
              <article className="field-card" key={`${nodeId}-${index}`}>
                <div className="field-card-main">
                  <span>Control point {index + 1}</span>
                  <strong>Node {nodeId}</strong>
                  <p>
                    {assignment.personnel_assigned} officers · lane estimate {assignment.lane_estimate || "n/a"}
                  </p>
                  <small>
                    {assignment.lat?.toFixed ? assignment.lat.toFixed(5) : assignment.lat}, {" "}
                    {assignment.lon?.toFixed ? assignment.lon.toFixed(5) : assignment.lon}
                  </small>
                </div>
                <div className="field-update-box">
                  <label>
                    <span>{t.note}</span>
                    <textarea
                      value={notes[nodeId] || ""}
                      onChange={(event) => setNotes((current) => ({ ...current, [nodeId]: event.target.value }))}
                      rows="2"
                    />
                  </label>
                  <label className="field-file-input">
                    <span>{t.photo}</span>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(event) => {
                        const fileName = event.target.files?.[0]?.name || "";
                        setPhotos((current) => ({ ...current, [nodeId]: fileName }));
                      }}
                    />
                  </label>
                </div>
                <div className="field-action-grid">
                  <button type="button" onClick={() => sendStatus(assignment, "acknowledged")}>
                    {t.acknowledged}
                  </button>
                  <button type="button" onClick={() => gpsCheckIn(assignment)}>
                    {t.deployed}
                  </button>
                  <button type="button" className="warn" onClick={() => sendStatus(assignment, "need_backup")}>
                    {t.backup}
                  </button>
                  <button type="button" className="warn" onClick={() => sendStatus(assignment, "need_barricades")}>
                    {t.barricades}
                  </button>
                  <button type="button" className="clear" onClick={() => sendStatus(assignment, "road_cleared")}>
                    {t.cleared}
                  </button>
                </div>
                <div className={`field-current-status ${status}`}>{status.replaceAll("_", " ")}</div>
              </article>
            );
          })}
        </section>
      )}

      <Toast toast={toast} />
    </main>
  );
}

function DetailDrawer({
  selectedEvent,
  forecast,
  plan,
  loadingForecast,
  loadingPlan,
  onClose,
  onGetPlan,
  onAccept,
  onAdjust,
}) {
  const [adjusting, setAdjusting] = useState(false);
  const [adjustedPersonnel, setAdjustedPersonnel] = useState("");

  useEffect(() => {
    setAdjusting(false);
    setAdjustedPersonnel("");
  }, [selectedEvent?.id]);

  if (!selectedEvent) {
    return (
      <aside className="detail-drawer empty">
        <h2>Event Detail</h2>
        <p>Select a marker to inspect forecast and deployment options.</p>
      </aside>
    );
  }

  const title = markerTitle(selectedEvent);
  const cause = selectedEvent.event_cause || selectedEvent.cause || "Traffic event";
  const similarCount = forecast?.similar_events?.length ?? 0;
  const shortfall = plan?.shortfall || 0;
  const controlPoints = plan?.control_points || [];
  const allocations = plan?.allocations || [];

  return (
    <aside className="detail-drawer">
      <div className="drawer-head">
        <div>
          <h2>{title}</h2>
          <p>{cause}</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close detail drawer">
          x
        </button>
      </div>

      <div className="drawer-section">
        <span className="section-kicker">Forecast</span>
        {loadingForecast ? (
          <div className="skeleton-lines">
            <span></span>
            <span></span>
            <span></span>
          </div>
        ) : forecast ? (
          <div className="forecast-grid">
            <div>
              <span>Severity</span>
              <strong className={forecast.severity_label === "HIGH" ? "danger-text" : ""}>
                {forecast.severity_label}
              </strong>
            </div>
            <div>
              <span>Probability</span>
              <strong>{Math.round((forecast.severity_probability || 0) * 100)}%</strong>
            </div>
            <div>
              <span>Duration</span>
              <strong>{durationLabel(forecast)}</strong>
            </div>
            <div>
              <span>Risk</span>
              <strong>{Math.round((forecast.risk_score || 0) * 100)}%</strong>
            </div>
            <div>
              <span>Similar Events</span>
              <strong>{similarCount}</strong>
            </div>
          </div>
        ) : (
          <p className="muted">Forecast unavailable.</p>
        )}
      </div>

      <button
        type="button"
        className="primary-action"
        onClick={onGetPlan}
        disabled={loadingPlan || !forecast}
      >
        {loadingPlan ? "Building plan..." : "Get recommended plan"}
      </button>

      {plan && (
        <div className="drawer-section plan-section">
          {shortfall > 0 && (
            <div className="warning-banner">
              Shortfall: {shortfall} officers are still needed within the allocation radius.
            </div>
          )}
          <div className="plan-stats">
            <div>
              <span>Personnel</span>
              <strong>{plan.total_personnel}</strong>
            </div>
            <div>
              <span>Barricades</span>
              <strong>{plan.total_barricades}</strong>
            </div>
            <div>
              <span>Diversions</span>
              <strong>{plan.diversions?.length || 0}</strong>
            </div>
          </div>

          {(plan.plan_warnings || []).length > 0 && (
            <div className="plan-warning-list">
              {(plan.plan_warnings || []).map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}

          <div className="control-point-list">
            <span className="section-kicker">Control Spots</span>
            {controlPoints.length === 0 ? (
              <p className="muted">No control spot returned for this event.</p>
            ) : (
              controlPoints.map((point, index) => {
                const pointAllocations = allocations.filter(
                  (allocation) => String(allocation.control_point_node_id) === String(point.node_id),
                );
                return (
                  <article className="control-point-row" key={`${point.node_id}-${index}`}>
                    <div className="control-point-head">
                      <strong>Spot {index + 1}</strong>
                      <span>{formatMeters(point.distance_m)} away</span>
                    </div>
                    <div className="control-point-metrics">
                      <span>{point.personnel_needed || 0} officers</span>
                      <span>{point.barricades_needed || 0} barricades</span>
                      <span>{point.lane_estimate || 1} lane proxy</span>
                      {point.is_arterial && <span>arterial</span>}
                    </div>
                    <ul className="reasoning-list">
                      {(point.reasoning || []).slice(0, 4).map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                    {pointAllocations.length > 0 && (
                      <div className="allocation-list">
                        {pointAllocations.map((allocation) => (
                          <span key={`${allocation.station_id}-${allocation.distance_m}`}>
                            {allocation.station_name}: {allocation.personnel_assigned} officers
                          </span>
                        ))}
                      </div>
                    )}
                    <small>{point.selection_method || "junction"} · node {point.node_id}</small>
                  </article>
                );
              })
            )}
          </div>

          <div className="diversion-list">
            <span className="section-kicker">Diversion Routes</span>
            {(plan.diversions || []).length === 0 ? (
              <p className="muted">No alternate route returned.</p>
            ) : (
              plan.diversions.map((route) => (
                <div className="diversion-row" key={`${route.source_node_id}-${route.target_node_id}-${route.rank}`}>
                  <strong>Route {route.rank}</strong>
                  <span>+{formatMeters(route.added_length_m || 0)}</span>
                </div>
              ))
            )}
          </div>

          <div className="feedback-actions">
            <button type="button" className="accept-button" onClick={onAccept}>
              Accept plan
            </button>
            <button type="button" className="secondary-button" onClick={() => setAdjusting((open) => !open)}>
              Adjust
            </button>
          </div>

          {adjusting && (
            <form
              className="adjust-form"
              onSubmit={(event) => {
                event.preventDefault();
                onAdjust(Number(adjustedPersonnel));
              }}
            >
              <label htmlFor="adjusted-personnel">Personnel count</label>
              <div>
                <input
                  id="adjusted-personnel"
                  min="0"
                  type="number"
                  value={adjustedPersonnel}
                  onChange={(event) => setAdjustedPersonnel(event.target.value)}
                  placeholder={String(plan.total_personnel || 0)}
                  required
                />
                <button type="submit">Submit</button>
              </div>
            </form>
          )}
        </div>
      )}
    </aside>
  );
}

function App() {
  if (window.location.pathname === "/field") {
    return <FieldPage />;
  }

  const [clock, setClock] = useState(new Date());
  const [metrics, setMetrics] = useState({
    active_incident_count: 0,
    planned_events_today: 0,
    total_personnel_deployed: 0,
    forecast_accuracy_30d: null,
  });
  const [roiMetrics, setRoiMetrics] = useState({
    average_incident_duration_reduction_minutes: 0,
    deployment_time_saved_minutes: 0,
    personnel_utilization: 0,
    preventable_high_risk_corridors_detected: 0,
    plan_acceptance_rate: 0,
    citizen_delay_hours_avoided: 0,
  });
  const [activeEvents, setActiveEvents] = useState([]);
  const [plannedEvents, setPlannedEvents] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [plan, setPlan] = useState(null);
  const [loadingForecast, setLoadingForecast] = useState(false);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [timeline, setTimeline] = useState("T-24h");
  const [toast, setToast] = useState(null);
  const [apiStatus, setApiStatus] = useState("connecting");

  const mapRef = useRef(null);
  const layersRef = useRef({
    markers: L.layerGroup(),
    overlays: L.layerGroup(),
    routes: L.layerGroup(),
  });

  const highlightedPlannedId = useMemo(() => {
    if (!plannedEvents.length) return null;
    const stageMatch = plannedEvents.find((event) => event.demo_stage === timeline);
    if (stageMatch) return stageMatch.id;
    return plannedEvents[0]?.id || null;
  }, [plannedEvents, timeline]);

  const showToast = useCallback((message, type = "info") => {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 2800);
  }, []);

  const refreshMetrics = useCallback(async () => {
    const payload = await apiRequest("/metrics/summary");
    setMetrics(payload);
    return payload;
  }, []);

  const refreshRoi = useCallback(async () => {
    const payload = await apiRequest("/metrics/roi");
    setRoiMetrics(payload);
    return payload;
  }, []);

  const refreshEvents = useCallback(async () => {
    const [active, upcoming] = await Promise.all([
      apiRequest("/events/active"),
      apiRequest("/events/upcoming"),
    ]);
    setActiveEvents(active);
    setPlannedEvents(upcoming);
  }, []);

  const fetchForecast = useCallback(
    async (event) => {
      const id = markerEventId(event);
      if (!id) return;
      setSelectedEvent(event);
      setForecast(null);
      setPlan(null);
      setLoadingForecast(true);
      try {
        const payload = await apiRequest(`/events/${encodeURIComponent(id)}/forecast`, {
          method: "POST",
        });
        setForecast(payload);
      } catch (error) {
        showToast(error.message, "error");
      } finally {
        setLoadingForecast(false);
      }
    },
    [showToast]
  );

  const fetchPlan = useCallback(async () => {
    if (!selectedEvent) return;
    const id = markerEventId(selectedEvent);
    setLoadingPlan(true);
    try {
      const payload = await apiRequest(`/events/${encodeURIComponent(id)}/plan`, {
        method: "POST",
      });
      setPlan(payload);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setLoadingPlan(false);
    }
  }, [selectedEvent, showToast]);

  const postFeedback = useCallback(
    async (body, successMessage) => {
      if (!selectedEvent) return;
      const id = markerEventId(selectedEvent);
      try {
        await apiRequest(`/events/${encodeURIComponent(id)}/feedback`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        await refreshMetrics();
        await refreshRoi();
        showToast(successMessage, "success");
      } catch (error) {
        showToast(error.message, "error");
      }
    },
    [selectedEvent, refreshMetrics, refreshRoi, showToast]
  );

  useEffect(() => {
    const interval = window.setInterval(() => setClock(new Date()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    refreshMetrics().catch((error) => {
      setApiStatus("offline");
      showToast(error.message, "error");
    });
    refreshEvents().catch((error) => {
      setApiStatus("offline");
      showToast(error.message, "error");
    });
    refreshRoi().catch((error) => {
      setApiStatus("offline");
      showToast(error.message, "error");
    });
  }, [refreshEvents, refreshMetrics, refreshRoi, showToast]);

  useEffect(() => {
    let closedByEffect = false;
    let retryTimer = null;
    let socket = null;

    function connect() {
      socket = new WebSocket(`${WS_BASE}/ws/live`);
      socket.onopen = () => setApiStatus("live");
      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.metrics) setMetrics(payload.metrics);
        if (Array.isArray(payload.newly_active_events) && payload.newly_active_events.length > 0) {
          setActiveEvents((current) => {
            const ids = new Set(current.map((item) => markerEventId(item)));
            const additions = payload.newly_active_events.filter((item) => !ids.has(markerEventId(item)));
            return [...additions, ...current];
          });
          showToast(`${payload.newly_active_events.length} newly active event${payload.newly_active_events.length > 1 ? "s" : ""}`, "info");
        }
      };
      socket.onerror = () => setApiStatus("offline");
      socket.onclose = () => {
        if (!closedByEffect) {
          setApiStatus("reconnecting");
          retryTimer = window.setTimeout(connect, 3000);
        }
      };
    }

    connect();
    return () => {
      closedByEffect = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (socket) socket.close();
    };
  }, [showToast]);

  useEffect(() => {
    if (mapRef.current) return;
    const map = L.map("traffic-map", {
      zoomControl: false,
      preferCanvas: true,
    }).setView(BENGALURU_CENTER, 12);
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);
    layersRef.current.markers.addTo(map);
    layersRef.current.overlays.addTo(map);
    layersRef.current.routes.addTo(map);
    mapRef.current = map;
    window.setTimeout(() => {
      map.invalidateSize();
      map.setView(BENGALURU_CENTER, 13);
    }, 0);
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const markerLayer = layersRef.current.markers;
    markerLayer.clearLayers();

    activeEvents.forEach((event) => {
      if (event.latitude == null || event.longitude == null) return;
      const marker = L.circleMarker([event.latitude, event.longitude], {
        radius: 8,
        color: priorityClass(event.priority) === "high" ? "#ff4d4d" : "#818894",
        fillColor: priorityClass(event.priority) === "high" ? "#ff4d4d" : "#818894",
        fillOpacity: 0.86,
        weight: 2,
      });
      marker.bindTooltip(`${event.event_cause || "Active event"} · ${event.priority || "Priority pending"}`);
      marker.on("click", () => fetchForecast({ ...event, source: "active" }));
      marker.addTo(markerLayer);
    });

    plannedEvents.forEach((event) => {
      if (event.latitude == null || event.longitude == null) return;
      const isHighlighted = event.id === highlightedPlannedId;
      const marker = L.marker([event.latitude, event.longitude], {
        icon: createPlannedIcon(isHighlighted),
        zIndexOffset: isHighlighted ? 800 : 400,
      });
      marker.bindTooltip(`${event.name} · ${formatTime(eventScheduledStart(event))}`);
      marker.on("click", () => fetchForecast({ ...event, source: "planned" }));
      marker.addTo(markerLayer);
    });
  }, [activeEvents, plannedEvents, highlightedPlannedId, fetchForecast]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const overlays = layersRef.current.overlays;
    const routes = layersRef.current.routes;
    overlays.clearLayers();
    routes.clearLayers();

    if (selectedEvent?.latitude != null && selectedEvent?.longitude != null) {
      const risk = forecast?.risk_score ?? 0;
      const radius = 200 + Math.max(0, Math.min(1, risk)) * 600;
      L.circle([selectedEvent.latitude, selectedEvent.longitude], {
        radius,
        color: "#f3b23f",
        fillColor: "#f3b23f",
        fillOpacity: 0.12,
        weight: 2,
      }).addTo(overlays);
      map.flyTo([selectedEvent.latitude, selectedEvent.longitude], Math.max(map.getZoom(), 13), {
        duration: 0.6,
      });
    }

    (plan?.diversions || []).forEach((route, index) => {
      const coordinates = (route.path || []).map((point) => [point.lat, point.lon]);
      if (coordinates.length < 2) return;
      L.polyline(coordinates, {
        color: index === 0 ? "#35b6ff" : "#6adf99",
        weight: index === 0 ? 5 : 4,
        opacity: 0.82,
      }).addTo(routes);
    });
  }, [selectedEvent, forecast, plan]);

  const timelineEvent = plannedEvents.find((event) => event.id === highlightedPlannedId);
  const metricAccuracy = metrics.forecast_accuracy_30d == null ? "n/a" : `${formatNumber(metrics.forecast_accuracy_30d)}%`;
  const roiUtilization = `${Math.round((roiMetrics.personnel_utilization || 0) * 100)}%`;
  const roiAcceptance = `${Math.round((roiMetrics.plan_acceptance_rate || 0) * 100)}%`;

  return (
    <main className="console-shell">
      <header className="top-bar">
        <div>
          <h1>Bengaluru Traffic Command</h1>
          <span>Central Zone 1</span>
        </div>
        <div className="top-status">
          <a className="field-link" href="/field">Field view</a>
          <span className={`connection-pill ${apiStatus}`}>{apiStatus}</span>
          <time>{formatClock(clock)} IST</time>
        </div>
      </header>

      <section className="metric-strip">
        <MetricCard label="Active Incidents" value={formatNumber(metrics.active_incident_count)} accent="danger" />
        <MetricCard label="Planned Today" value={formatNumber(metrics.planned_events_today)} accent="planned" />
        <MetricCard label="Personnel Deployed" value={formatNumber(metrics.total_personnel_deployed)} accent="staff" />
        <MetricCard label="Forecast Error 30d" value={metricAccuracy} accent="accuracy" />
      </section>

      <section className="executive-strip" aria-label="Executive ROI metrics">
        <div className="executive-strip-head">
          <span>Executive ROI</span>
          <strong>{formatNumber(roiMetrics.sample_count || 0)} feedback rows</strong>
        </div>
        <ExecutiveMetric
          label="Delay-hours avoided"
          value={formatNumber(roiMetrics.citizen_delay_hours_avoided)}
          detail="pilot estimate"
        />
        <ExecutiveMetric
          label="Duration reduction"
          value={`${formatNumber(roiMetrics.average_incident_duration_reduction_minutes)} min`}
          detail="avg incident"
        />
        <ExecutiveMetric
          label="Plan acceptance"
          value={roiAcceptance}
          detail="30 day feedback"
        />
        <ExecutiveMetric
          label="Personnel utilization"
          value={roiUtilization}
          detail={`${formatNumber(roiMetrics.preventable_high_risk_corridors_detected)} high-risk corridors`}
        />
      </section>

      <section className="workspace">
        <div className="map-panel">
          <div className="map-toolbar">
            <TimelineToggle value={timeline} onChange={setTimeline} />
            <div className="timeline-focus">
              <span>Demo focus</span>
              <strong>{timelineEvent ? timelineEvent.name : "No planned event"}</strong>
            </div>
          </div>
          <div id="traffic-map" className="traffic-map" />
          <div className="map-legend">
            <span><i className="legend-dot high"></i>High active</span>
            <span><i className="legend-dot low"></i>Low active</span>
            <span><i className="legend-diamond"></i>Planned</span>
          </div>
        </div>

        <DetailDrawer
          selectedEvent={selectedEvent}
          forecast={forecast}
          plan={plan}
          loadingForecast={loadingForecast}
          loadingPlan={loadingPlan}
          onClose={() => {
            setSelectedEvent(null);
            setForecast(null);
            setPlan(null);
          }}
          onGetPlan={fetchPlan}
          onAccept={() => postFeedback({ accepted: true, plan }, "Plan accepted")}
          onAdjust={(adjusted) => postFeedback({ accepted: false, adjusted_personnel: adjusted, plan }, "Adjustment submitted")}
        />
      </section>

      <Toast toast={toast} />
    </main>
  );
}

export default App;
