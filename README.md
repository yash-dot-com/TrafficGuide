# Bengaluru Traffic Congestion Forecasting System - MVP

## 📋 Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Solution Architecture](#solution-architecture)
- [Quick Start](#quick-start)
- [Technology Stack](#technology-stack)
- [Data Schema](#data-schema)
- [Core Modules](#core-modules)
- [API Documentation](#api-documentation)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Data Flow](#data-flow)
- [Performance](#performance)
- [Deployment](#deployment)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Future Enhancements](#future-enhancements)
- [Contributing](#contributing)
- [References](#references)

---

## Overview

This is an **event-driven traffic congestion forecasting and resource optimization system** designed for Bengaluru's traffic management. The MVP focuses on the **data layer and prediction/planning pipeline**, enabling rapid incident response with data-driven resource deployment.

### Key Capabilities

1. **Real-time Impact Prediction**: ML models predict incident severity and duration within seconds
2. **Intelligent Deployment Planning**: Automatically identifies optimal control points and allocates personnel/barricades
3. **Multi-Incident Coordination**: Manages multiple concurrent incidents holistically
4. **Feedback Loop**: Officers report outcomes → system learns and improves
5. **Multi-tenancy Ready**: Same codebase can serve multiple cities
6. **Graceful Degradation**: System remains operational even if components fail (no DB, no road graph, etc.)

### MVP Scope (Data Layer Only)

✅ **Included**:
- PostgreSQL backend with PostGIS spatial queries
- ML prediction pipeline (severity, duration, risk scoring)
- Geographic optimization (control points, routing, allocation)
- RESTful API with caching and real-time WebSocket updates
- Feedback collection and audit logging
- Field officer status tracking

❌ **Out of Scope**:
- Mobile/web UI (separate repos)
- Real-time incident feed integration (stub adapters provided)
- Model retraining pipeline (assumes pre-trained artifacts)
- Deployment infrastructure (Docker/K8s configurations)

---

## Problem Statement

### The Challenge

Bengaluru experiences severe traffic congestion exacerbated by unpredictable incidents (accidents, vehicle breakdowns, events) that cascade into city-wide delays lasting hours. The current incident response system suffers from:

| Challenge | Impact | Current State |
|-----------|--------|---|
| **Delayed Response** | Every minute lost = 10,000+ vehicles affected | Officers rely on experience-based estimates |
| **Poor Resource Allocation** | Over/under-deployment of personnel | Manual station-by-station coordination |
| **Suboptimal Positioning** | Wrong locations = limited congestion mitigation | No systematic control point analysis |
| **No Predictability** | Public transport reliability suffers | No data-driven duration forecasts |
| **Limited Learning** | Mistakes repeat; no feedback loop | No systematic data capture from field |

### The Business Case

- **Bengaluru Metro**: ~9 million residents, 2000+ incidents/week
- **Economic Loss**: 8 hours/year per commuter lost to congestion (₹30K+ annual cost)
- **Response Time**: Reducing clearance time by 20% = ₹2B+ annual economic benefit
- **Resource Efficiency**: Optimal allocation saves 15–25% personnel deployments

---

## Solution Architecture

### System Architecture Diagram

```mermaid
graph TB
    subgraph DataSources["📥 DATA SOURCES"]
        CSV["CSV Files<br/>(Astram Exports)"]
        LiveFeeds["Live Feeds<br/>(Google Maps, CCTV)"]
        PlannedEvents["Planned Events<br/>(Permits, VIP)"]
        Weather["Weather API<br/>(Rainfall, Temp)"]
    end

    subgraph DataLayer["💾 DATA LAYER"]
        PostgreSQL["PostgreSQL 15<br/>+ PostGIS"]
        JSONL["JSONL Files<br/>(Offline Fallback)"]
        Cache["In-Memory Cache<br/>(Forecast, Plans)"]
    end

    subgraph MLLayer["🤖 ML FORECASTING"]
        PredictPy["predict.py<br/>━━━━━<br/>Severity + Duration<br/>Risk Score"]
        SeverityModel["XGBoost<br/>Classifier"]
        DurationModels["LightGBM<br/>Quantiles"]
    end

    subgraph PlanningLayer["🗺️ PLANNING"]
        GenPlan["generate_plan.py<br/>━━━━━<br/>Control Points<br/>Resource Sizing"]
        RoadGraph["OSM Road Graph<br/>(Cached)"]
    end

    subgraph AllocationLayer["⚙️ OPTIMIZATION"]
        AllocPy["allocation.py<br/>━━━━━<br/>OR-Tools Solver<br/>+ Greedy Fallback"]
    end

    subgraph WorkflowLayer["📋 WORKFLOW"]
        Workflow["workflow.py<br/>━━━━━<br/>Approval Chain<br/>Audit Log"]
    end

    subgraph FeedbackLoop["📊 FEEDBACK"]
        FeedbackCapture["Officer Feedback<br/>━━━━━<br/>Duration, Rating<br/>Adjustments"]
        ModelRetraining["Model Retraining<br/>━━━━━<br/>train_models.py"]
    end

    subgraph Execution["🚀 EXECUTION"]
        FieldOfficers["Field Officers<br/>(Mobile)"]
        Dashboard["Command Center<br/>(Web)"]
        WebSocket["WebSocket Live<br/>Updates"]
    end

    %% Connections
    CSV --> DataLayer
    LiveFeeds --> DataLayer
    PlannedEvents --> DataLayer
    Weather --> DataLayer

    DataLayer --> MLLayer
    MLLayer --> PlanningLayer
    PlanningLayer --> AllocationLayer
    AllocationLayer --> WorkflowLayer
    WorkflowLayer --> Execution

    FieldOfficers --> FeedbackCapture
    Dashboard --> FeedbackCapture
    FeedbackCapture --> ModelRetraining
    ModelRetraining -.->|Updates Models| MLLayer

    Execution --> WebSocket

    classDef source fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef layer fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef ml fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef exec fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    classDef feedback fill:#f1f8e9,stroke:#33691e,stroke-width:2px

    class DataSources source
    class DataLayer layer
    class MLLayer,PlanningLayer,AllocationLayer ml
    class WorkflowLayer layer
    class Execution exec
    class FeedbackLoop feedback
```

**View Full Architecture Diagram**: See [ARCHITECTURE.mmd](./ARCHITECTURE.mmd) for a comprehensive component-level diagram with all modules, data flows, and integrations.

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         INCIDENT EVENT                           │
│                                                                   │
│  ├─ Live feed (Google Maps, Astram API, CCTV)                   │
│  ├─ Planned events (permits, VIP movements)                     │
│  └─ Historical data (CSV load)                                  │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│               FORECASTING LAYER (predict.py)                     │
│                                                                   │
│  1. Feature Engineering                                          │
│     └─ Normalize event cause, corridor, zone, time features     │
│                                                                   │
│  2. ML Prediction                                                │
│     ├─ Severity Classification (XGBoost)                        │
│     │  └─ P(HIGH severity) from event + contextual features    │
│     ├─ Duration Quantile Regression (LightGBM)                 │
│     │  └─ Q25, Q50, Q75 with survival analysis adjustment      │
│     └─ Risk Scoring (Historical Density Heatmap)               │
│        └─ Corridor × Hour × Day_of_Week → Risk [0,1]          │
│                                                                   │
│  3. Operational Metrics                                         │
│     ├─ Expected delay minutes                                   │
│     ├─ Queue length (m)                                         │
│     ├─ Personnel demand (count)                                 │
│     └─ Confidence level [0.35-0.92]                             │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│            PLANNING LAYER (generate_plan.py)                     │
│                                                                   │
│  1. Geographic Analysis                                         │
│     ├─ Load OSM road graph (cached)                            │
│     ├─ Find control points (intersections/segments)            │
│     └─ Compute diversions (alternative routes)                 │
│                                                                   │
│  2. Resource Sizing                                             │
│     ├─ Personnel per control point (based on severity)         │
│     ├─ Barricades per control point                            │
│     └─ Total demand calculation                                │
│                                                                   │
│  3. Allocation Optimization (allocation.py)                     │
│     ├─ Distance matrix (control points ↔ stations)             │
│     ├─ OR-Tools LP solver (if available)                       │
│     └─ Greedy fallback (if solver unavailable)                 │
│                                                                   │
│  Result: Deployment Plan with allocations + warnings            │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                 WORKFLOW LAYER (workflow.py)                     │
│                                                                   │
│  1. Plan Lifecycle                                              │
│     draft → submitted → approved → activated → closed          │
│                                                                   │
│  2. Multi-level Approval                                        │
│     ├─ Traffic Commander (validates plan)                      │
│     ├─ Zone Superintendent (authorizes deployment)             │
│     └─ Audit trail at each step                                │
│                                                                   │
│  3. Immutable Audit Log                                         │
│     └─ Every action logged with actor, timestamp, reason       │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              EXECUTION & FEEDBACK LAYER                          │
│                                                                   │
│  1. Field Officer Updates                                       │
│     ├─ Real-time status (control_points.node_id + status)     │
│     ├─ Photo/note capture (photo_url, note fields)            │
│     └─ Location updates (lat, lon from mobile GPS)            │
│                                                                   │
│  2. Outcome Recording                                           │
│     ├─ Actual incident duration                                │
│     ├─ Personnel adjustments made                              │
│     ├─ Officer rating (1-5 stars)                             │
│     └─ Plan acceptance/rejection                               │
│                                                                   │
│  3. Loop Closure                                                │
│     Actual outcomes → Feedback table → Model retraining         │
│                       (offline, via train_models.py)            │
└─────────────────────────────────────────────────────────────────┘
```

### Data Architecture

```
┌──────────────────────────────────┐
│       PostgreSQL 15 + PostGIS    │
│                                  │
│  ├─ tenants (multi-tenancy)     │
│  ├─ app_users (RBAC)            │
│  ├─ events (incidents w/ geom)  │
│  ├─ police_stations (inventory) │
│  ├─ feedback (outcomes)         │
│  ├─ plan_workflows (lifecycle)  │
│  ├─ field_status_updates (live) │
│  └─ audit_log (compliance)      │
│                                  │
└──────────────────────────────────┘
         ↑          ↓
    SQLAlchemy
       ORM
         ↑          ↓
    ┌──────────────────────────────────┐
    │      Python FastAPI Server       │
    │  :8000 (REST + WebSocket)        │
    └──────────────────────────────────┘
         ↑          ↓
    ┌──────────────────────────────────────────┐
    │   Clients (Mobile, Web, Command Center)  │
    └──────────────────────────────────────────┘
```

### ML Pipeline Architecture

```
┌─────────────────────────────────────┐
│   Model Training (train_models.py)  │
│   Runs offline on historical data   │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│          Trained Artifacts (models/ dir)            │
│                                                      │
│  ├─ severity_model.pkl                             │
│  │  └─ XGBoost classifier pipeline                │
│  ├─ duration_q25_model.pkl                        │
│  ├─ duration_q50_model.pkl                        │
│  └─ duration_q75_model.pkl                        │
│     └─ LightGBM quantile regressors              │
│  ├─ risk_density.parquet                         │
│  │  └─ Corridor × Hour × Day_of_Week heatmap    │
│  └─ duration_survival_table.parquet              │
│     └─ Censoring adjustments per corridor        │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────┐
│   predict.py (predict_impact)        │
│                                      │
│  1. Load artifacts (cached, LRU)     │
│  2. Build feature frame              │
│  3. Predict severity + duration      │
│  4. Lookup risk score                │
│  5. Compute operational metrics      │
│                                      │
│  → Deterministic, <2s latency        │
└──────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15 (optional; system works offline with JSONL)
- PostGIS extension (if using PostgreSQL)

### 1. Install Dependencies

```bash
cd TrafficGuide
pip install -r requirements.txt
```

### 2. Set Up Environment

```bash
# Create .env file
cat > .env <<EOF
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/gridlock
MODEL_DIR=./models
APP_ENV=local
FORECAST_CACHE_TTL_SECONDS=300
PLAN_CACHE_TTL_SECONDS=600
EOF
```

### 3. Initialize Database (Optional)

```bash
# If you have a PostgreSQL instance:
export DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/gridlock"
python -m backend.data.load_data path/to/events.csv
```

### 4. Run the API

```bash
uvicorn main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive API documentation.

### 5. Test Forecasting

```bash
# Standalone prediction test
python predict.py

# Deployment plan generation
python -m backend.optimization.generate_plan --lat 12.9716 --lon 77.5946 --demo-cache
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API** | FastAPI 0.110+ | REST + WebSocket endpoints |
| **Database** | PostgreSQL 15 + PostGIS | Geospatial storage, queries |
| **ORM** | SQLAlchemy 2.0+ | Type-safe DB access |
| **Driver** | psycopg2-binary 2.9+ | PostgreSQL connection |
| **ML - Classification** | scikit-learn 1.5+ | Pipeline, preprocessing |
| **ML - Boosting** | XGBoost 2.1+, LightGBM 4.0+ | Severity, duration models |
| **ML - Serialization** | joblib 1.4+ | Model persistence |
| **ML - Data** | pandas 2.2+, pyarrow 16+ | DataFrames, Parquet |
| **Geospatial** | OSMNX 1.9+, NetworkX 3.4+ | Road graphs, routing |
| **Optimization** | OR-Tools 9.10+ | Resource allocation solver |
| **Data Processing** | pandas 2.2+, numpy (transitive) | Feature engineering |

---

## Data Schema

### Core Tables

#### `tenants`
Multi-tenancy root. One row per city/organization.

```sql
CREATE TABLE tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT,
    environment TEXT NOT NULL DEFAULT 'local',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default seed:
INSERT INTO tenants (id, name, region) 
VALUES ('bengaluru-traffic', 'Bengaluru Traffic Command', 'Bengaluru');
```

#### `app_users`
RBAC: Track officers and their permissions.

```sql
CREATE TABLE app_users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(id),
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'traffic_commander', 'zone_superintendent', 'field_officer'
    police_station TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### `events`
Core incident table. **Note: geom is auto-generated from lat/lon.**

```sql
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    event_type TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    address TEXT,
    event_cause TEXT,
    requires_road_closure BOOLEAN,
    start_datetime TIMESTAMPTZ,
    end_datetime TIMESTAMPTZ,
    status TEXT,  -- 'planned', 'active', 'closed'
    description TEXT,
    corridor TEXT,
    zone TEXT,
    junction TEXT,
    police_station TEXT,
    priority TEXT,  -- 'high', 'normal', 'low'
    duration_minutes INTEGER,
    geom geometry(Point, 4326) GENERATED ALWAYS AS (
        CASE
            WHEN latitude IS NULL OR longitude IS NULL THEN NULL
            ELSE ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
        END
    ) STORED
);

-- Indexes for query performance:
CREATE INDEX idx_events_geom ON events USING GIST (geom);
CREATE INDEX idx_events_zone ON events (zone);
CREATE INDEX idx_events_police_station ON events (police_station);
CREATE INDEX idx_events_start_datetime ON events (start_datetime DESC);
```

**Key Fields**:
- `geom`: PostGIS point geometry for spatial queries (`ST_DWithin`, `ST_Distance`)
- `status`: Lifecycle (planned → active → closed)
- `duration_minutes`: Computed from closed_datetime - start_datetime

#### `police_stations`
Resource inventory per station.

```sql
CREATE TABLE police_stations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    zone TEXT,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    available_personnel INTEGER NOT NULL DEFAULT 0,
    available_barricades INTEGER NOT NULL DEFAULT 0
);

-- Sample stations (Bengaluru):
-- Yelahanka (North Zone 2, 31 personnel, 48 barricades)
-- HAL Old Airport (East Zone 1, 24 personnel, 35 barricades)
-- ... (15 total stations)
```

**Usage**: Source for allocate_personnel() and allocate_barricades().

#### `feedback`
Officer feedback on forecasts and plans.

```sql
CREATE TABLE feedback (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    predicted_severity TEXT,  -- 'HIGH', 'LOW'
    predicted_duration_minutes INTEGER,
    actual_duration_minutes INTEGER,
    officer_rating INTEGER CHECK (officer_rating BETWEEN 1 AND 5),
    plan_accepted BOOLEAN,
    adjusted_personnel INTEGER,
    plan_total_personnel INTEGER,
    plan_json JSONB,  -- Full plan snapshot for traceability
    event_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for feedback aggregation:
CREATE INDEX idx_feedback_created ON feedback (created_at DESC);
```

**Usage**: 
- Compute forecast accuracy: `|predicted - actual| / actual`
- Detect model drift: aggregated error over 30 days
- Retraining data source

#### `plan_workflows`
Plan versioning + approval audit trail.

```sql
CREATE TABLE plan_workflows (
    id BIGSERIAL PRIMARY KEY,
    plan_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,  -- 'draft', 'submitted', 'approved', 'activated', 'closed'
    tenant_id TEXT NOT NULL DEFAULT 'bengaluru-traffic',
    actor TEXT,  -- User ID who performed action
    approval_chain JSONB,  -- [{"role": "traffic_commander", "status": "approved", ...}, ...]
    plan_json JSONB,  -- Full plan object
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes:
CREATE INDEX idx_plan_workflows_plan_id ON plan_workflows (plan_id);
CREATE INDEX idx_plan_workflows_event_id ON plan_workflows (event_id);
CREATE INDEX idx_plan_workflows_status ON plan_workflows (status);
```

**Workflow Example**:
```
Version 1: status=draft (created by command operator)
  ↓ [submit button]
Version 2: status=submitted (actor=commander)
  ↓ [approve button]
Version 3: status=approved (actor=superintendent, approval_chain[0].status=approved)
  ↓ [activate button]
Version 4: status=activated (actor=commander)
  ↓ [close button on incident resolution]
Version 5: status=closed (actor=officer)
```

#### `audit_log`
Immutable compliance log (append-only).

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    audit_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    actor TEXT,
    action TEXT NOT NULL,  -- 'plan.created', 'feedback.recorded', 'field.status.updated'
    resource_type TEXT,  -- 'plan', 'event', 'feedback'
    resource_id TEXT,
    details JSONB,  -- Custom data per action
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for querying audit trail:
CREATE INDEX idx_audit_log_tenant_created ON audit_log (tenant_id, created_at DESC);
```

**Example Record**:
```json
{
  "audit_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "bengaluru-traffic",
  "actor": "officer.123",
  "action": "plan.approved",
  "resource_type": "plan",
  "resource_id": "plan-abc123",
  "details": {
    "event_id": "crash-001",
    "comment": "Approved for deployment",
    "approval_chain": [...]
  },
  "created_at": "2026-06-20T10:30:00Z"
}
```

#### `field_status_updates`
Real-time field officer status updates.

```sql
CREATE TABLE field_status_updates (
    id BIGSERIAL PRIMARY KEY,
    status_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    actor TEXT,  -- Field officer ID
    station TEXT,  -- Police station name
    event_id TEXT NOT NULL,
    control_point_node_id TEXT,  -- OSM node ID
    status TEXT NOT NULL,  -- 'deployed', 'active', 'cleared', 'reassigned'
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    note TEXT,
    photo_url TEXT,  -- S3 URL or similar
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index:
CREATE INDEX idx_field_status_event ON field_status_updates (event_id, created_at DESC);
```

### JSONL Files (Offline Mode)

When PostgreSQL unavailable, system uses JSONL files:

- `feedback_log.jsonl`: Feedback records (one JSON per line)
- `plan_workflows.jsonl`: Plan lifecycle events
- `audit_log.jsonl`: Audit trail

Each line is a complete JSON object (no array wrapper).

---

## Project Structure

The backend is organized into a logical package structure under `backend/`:

```
backend/
├── api/              # REST API & WebSocket endpoints
│   └── main.py       # FastAPI app (entry point for uvicorn)
├── ml/               # Machine learning models & predictions
│   ├── predict.py    # ML prediction pipeline
│   ├── feature_cleaning.py
│   ├── train_models.py
│   └── model_monitoring.py
├── optimization/     # Planning & resource allocation
│   ├── generate_plan.py      # Deployment plan generation
│   ├── allocation.py         # OR-Tools solver
│   ├── multi_incident.py
│   ├── control_points.py
│   ├── diversion.py
│   └── resource_sizing.py
├── geo/              # Geographic & spatial utilities
│   ├── geo_utils.py  # Distance, coordinate helpers
│   ├── road_graph.py # OpenStreetMap network
│   └── enrich_zone.py
├── data/             # Data loading, workflows, audit trails
│   ├── load_data.py  # CSV ingestion
│   ├── workflow.py   # Plan lifecycle & approval
│   └── seed_feedback.py
├── integrations/     # External data sources & APIs
│   └── integrations.py
├── monitoring/       # Operational metrics & compliance
│   ├── operational_monitoring.py
│   ├── roi_metrics.py
│   ├── platform_ops.py
│   └── benchmark_system.py
└── config/           # Configuration management
    └── env_loader.py
```

**Root-level wrapper**: `main.py` delegates to `backend/api/main.py` so the existing uvicorn command works unchanged.

---

## Core Modules

### 1. **backend/data/load_data.py** — CSV Ingestion & Normalization

**Purpose**: Bulk-load Astram CSV exports into PostgreSQL; normalize data quality; auto-seed police stations.

**Main Function**: `main()`

```python
python -m backend.data.load_data path/to/events.csv [--schema path/to/schema.sql]
```

**What It Does**:

1. **Parse CSV** (`load_csv()`)
   - Coerce types: latitude/longitude → float, start_datetime → TIMESTAMPTZ
   - Normalize NULL sentinels: "", "null", "none", "n/a" → pd.NA
   - Drop rows with missing id
   - Deduplicate by id (keep last)
   - Compute duration_minutes from (closed_datetime - start_datetime)
   - Flags: negative durations set to NULL

2. **Infer Zone** (`infer_zone()`)
   - If zone is missing, deterministically infer from lat/lon:
     ```
     latitude >= 13.03 → "North Zone 2"
     longitude >= 77.66 → "East Zone 2"
     longitude <= 77.55 → "West Zone 1"
     latitude <= 12.94 → "South Zone 2"
     77.56 ≤ longitude ≤ 77.61 → "Central Zone 1"
     else → "Central Zone 2"
     ```

3. **Upsert Events** (`upsert_events()`)
   - High-throughput batch insert via psycopg2 execute_values()
   - ON CONFLICT (id) DO UPDATE — enables re-runs without truncation

4. **Seed Police Stations** (`reseed_police_stations()`)
   - Extract top 15 station names from event data
   - Compute station centroid: median(lat/lon) of events for that station
   - Deterministically seed personnel/barricades via `stable_int()` hash
   - Fallback coordinates if station has no location data

5. **Sanity Check** (`print_sanity()`)
   - Reports: event count, date range, null rates, geom coverage

**Outputs**:
```
Loaded 45,231 event rows from events.csv
Upserted 45,231 events and seeded 15 police stations.

Sanity check
Events in table: 45231
Start date range: 2024-01-01 -> 2026-06-15
Events with geometry: 45200
Police stations seeded: 15
Null duration_minutes: 312
Null key columns: latitude=31, longitude=31, ...
```

**Why This Module**: Bridges static CSV exports to dynamic database. Handles 80/20 of data quality issues without manual intervention.

---

### 2. **backend/ml/predict.py** — ML Impact Forecasting

**Purpose**: Core prediction engine. Takes event features → returns severity, duration, risk score, operational metrics.

**Main Function**: `predict_impact(event_features: dict) → dict`

```python
import json
from backend.ml.predict import predict_impact

sample_event = {
    "event_cause": "Accident",
    "corridor": "Outer Ring Road",
    "zone": "East Zone 1",
    "police_station": "HAL Old Airport",
    "veh_type": "Car",
    "start_datetime": "2026-06-20T09:30:00+05:30",
    "latitude": 12.953229,
    "longitude": 77.697134,
}

forecast = predict_impact(sample_event)
print(json.dumps(forecast, indent=2))
```

**Output**:
```json
{
  "severity_label": "HIGH",
  "severity_probability": 0.72,
  "duration_low": 15,
  "duration_median": 28,
  "duration_high": 45,
  "duration_confidence_interval": {
    "low": 15,
    "median": 28,
    "high": 45,
    "cap_minutes": 480,
    "method": "quantile_lightgbm_with_survival_censor_adjustment",
    "censoring_rate": 0.15,
    "sample_count": 1247,
    "adjustment_factor": 1.05
  },
  "risk_score": 0.65,
  "expected_delay_minutes": 22.5,
  "queue_length_m": 450,
  "affected_road_segments": 3,
  "clearance_time_minutes": 35,
  "personnel_demand": 11,
  "confidence_level": 0.78,
  "forecast_explanation": [
    "severity_probability=0.72 from event/corridor/station/time features",
    "risk_score=0.65 from historical corridor-hour density",
    "speed_ratio=0.45 from fleet GPS adapter",
    "rainfall_mm_1h=2.5 from weather adapter",
    "vehicle_count_15m=240 from CCTV/ANPR adapter"
  ],
  "human_override_allowed": true,
  "operational_context": { ... }
}
```

**Key Submodules**:

#### `load_artifacts()`
LRU-cached model loading.

```python
artifacts = {
    "severity": {"pipeline": sklearn.pipeline.Pipeline, "features": [...], "threshold": 0.5},
    "duration": {
        "low": joblib.load("duration_q25_model.pkl"),
        "median": joblib.load("duration_q50_model.pkl"),
        "high": joblib.load("duration_q75_model.pkl"),
    },
    "risk_density": pd.read_parquet("risk_density.parquet"),
    "survival": pd.read_parquet("duration_survival_table.parquet"),
}
```

Raises `FileNotFoundError` if any model missing — user must run `train_models.py` first.

#### `build_feature_frame(event_features, requires_road_closure=None) → pd.DataFrame`

Constructs ML-ready feature matrix:

```python
features = {
    "hour_of_day": int,  # 0-23, or -1 if null
    "day_of_week": int,  # 0-6 (Monday-Sunday), or -1 if null
    "event_type": str,  # normalized (e.g., "accident" → "Accident")
    "event_category": str,  # coarser: "crash", "breakdown", "congestion", etc.
    "event_cause": str,  # normalized
    "corridor": str,  # normalized
    "zone": str,  # normalized
    "police_station": str,  # normalized
    "priority": str,  # normalized
    "veh_type": str,  # normalized
    "requires_road_closure": 0.0 or 1.0,  # bool → float
}
```

**Why**: ML models expect consistent feature ordering and types. Normalization prevents OOV (out-of-vocabulary) issues.

#### `risk_score_for_event(risk_density: pd.DataFrame, event_features: dict) → float`

Lookup historical density heatmap.

**Strategy**:
1. Extract: corridor, hour_bucket (3-hour granules), day_of_week
2. Exact match: Find row where (corridor == X AND hour_bucket == Y AND day_of_week == Z)
   - If found, return risk_score (clamped to [0, 1])
3. Fallback 1: If no exact match, average across all hours for that corridor
4. Fallback 2: If corridor not in data, return global average risk

**Why**: Captures seasonal/temporal patterns without retraining. Fallbacks handle sparse data gracefully.

#### `survival_context_for_event(survival_table: pd.DataFrame, event_features: dict) → dict`

Adjust duration predictions for right-censored historical data.

**Problem**: Historical data may have events ongoing at cutoff (censored), biasing Q50/Q75 downward.

**Solution**: Estimate censoring_rate per corridor/cause/hour, apply adjustment_factor.

```python
censoring_rate = 0.15  # 15% of historical events for this corridor were censored
adjustment_factor = 1 + censoring_rate * 0.35  # 1.0525
adjusted_q50 = raw_q50 * adjustment_factor
```

**Output**:
```json
{
  "method": "quantile_lightgbm_with_survival_censor_adjustment",
  "censoring_rate": 0.15,
  "sample_count": 1247,
  "observed_median_duration": 28.5,
  "adjustment_factor": 1.0525
}
```

#### `operational_metrics(...) → dict`

Compute downstream impact metrics from predictions + live operational context.

```python
metrics = {
    "expected_delay_minutes": 
        duration_median * (0.35 + risk_score * 0.45 + delay_factor * 0.2) * rain_factor,
    "queue_length_m": 
        vehicle_count * (1 - speed_ratio) * 4.8,  # 4.8m per vehicle
    "affected_road_segments": 
        max(1, round(1 + risk_score * 4 + (1 if severity == "HIGH" else 0))),
    "clearance_time_minutes": 
        duration_median * closure_factor + expected_delay_minutes * 0.2,
    "personnel_demand": 
        max(4, round(4 + severity_probability * 8 + risk_score * 6)),  # capped by event type
    "confidence_level": 
        clamp(1 - ((high - low) / high) * 0.45 - penalty, 0.35, 0.92),
}
```

**Integrations**:
- GPS speed data (from `integrations.py`)
- CCTV/ANPR vehicle counts
- Weather API (rainfall)
- Public advisory feeds

**Why**: Converts point estimates into actionable deployment metrics.

---

### 3. **backend/optimization/generate_plan.py** — Deployment Plan Generation

**Purpose**: Orchestrates end-to-end plan generation (control points → resource sizing → allocation → diversions).

**Main Function**: `generate_deployment_plan(event_features: dict, graph=None, control_radius_m=None) → dict`

```python
from backend.optimization.generate_plan import generate_deployment_plan
import json

event = {
    "latitude": 12.9716,
    "longitude": 77.5946,
    "event_cause": "Accident",
    "corridor": "M G Road",
    "severity_label": "HIGH",  # from predict.py
    "severity_probability": 0.72,
    "duration_median": 28,
    # ... other fields
}

plan = generate_deployment_plan(event)
print(json.dumps(plan, indent=2))
```

**Key Steps**:

1. **Validate Input**
   - Extract lat/lon (raise if missing)
   - Ensure prediction fields present (call predict.py if missing)

2. **Load Road Graph** (`get_graph_for_point()`)
   - Download OSM graph centered on event location (~10km radius)
   - Cache to avoid repeated downloads
   - Fallback to demo graph if offline

3. **Find Control Points** (`find_control_points()`)
   - Search radius: 800m (LOW severity) or 1200m (HIGH severity)
   - Prefer arterial roads (higher lane count = wider impact)
   - Limit: 3-5 control points (via `control_point_limit_for_event()`)
   - Output: {node_id, lat, lon, lane_estimate, personnel_needed, barricades_needed}

4. **Size Resources** (`size_event_resources()`)
   - Apply severity modifiers (HIGH → more personnel per control point)
   - Apply event-type modifiers (crash → higher, congestion → lower)
   - Compute total_personnel and total_barricades

5. **Allocate Personnel** (`allocate_personnel()`)
   - Build distance matrix: control_points × police_stations
   - Solve LP: minimize distance × personnel subject to capacity constraints
   - Fallback to greedy if OR-Tools unavailable
   - Output: {allocations, shortfall, solver}

6. **Allocate Barricades** (`allocate_barricades()`)
   - Similar to personnel but always greedy (simpler problem)

7. **Compute Diversions** (`compute_diversions()`)
   - Suggest alternative routes to shift traffic
   - Rank by diversion efficiency

8. **Collect Warnings**
   - No control points found
   - Graph stale/missing
   - Personnel/barricade shortfall
   - Road closure impacts

**Output**:
```json
{
  "event": {
    "latitude": 12.9716,
    "longitude": 77.5946,
    "severity_label": "HIGH",
    "severity_probability": 0.72,
    "duration_median": 28
  },
  "control_points": [
    {
      "node_id": 12345,
      "lat": 12.9720,
      "lon": 77.5950,
      "lane_estimate": 4,
      "personnel_needed": 5,
      "barricades_needed": 3
    },
    {
      "node_id": 12346,
      "lat": 12.9710,
      "lon": 77.5935,
      "lane_estimate": 3,
      "personnel_needed": 4,
      "barricades_needed": 3
    }
  ],
  "total_personnel": 9,
  "total_barricades": 6,
  "allocations": [
    {
      "control_point_node_id": 12345,
      "station_id": 12,
      "station_name": "Cubbon Park",
      "personnel_assigned": 5,
      "distance_m": 280
    },
    {
      "control_point_node_id": 12346,
      "station_id": 15,
      "station_name": "High Ground",
      "personnel_assigned": 4,
      "distance_m": 420
    }
  ],
  "barricade_allocations": [...],
  "personnel_shortfall": 0,
  "barricade_shortfall": 0,
  "allocation_solver": "ortools_cbc",
  "diversions": ["Residency Road", "Brigade Road"],
  "nearest_graph_node": 12345,
  "nearest_graph_distance_m": 15,
  "graph_scope": "city",
  "graph_cache_status": "hit",
  "plan_warnings": [],
  "runtime_seconds": 0.52
}
```

---

### 4. **backend/optimization/allocation.py** — Resource Allocation Optimization

**Purpose**: Solve the assignment problem: given control points and police stations, find optimal allocations.

**Main Functions**:

#### `allocate_personnel(control_points, stations=None, max_radius_m=6000, use_subprocess=True) → dict`

Assign personnel from stations to control points.

**Strategy**:
1. Build candidate pairs: control_points × stations within max_radius_m
2. **Primary Solver** (if `use_subprocess=True` and OR-Tools available):
   ```
   minimize: Σ(distance_m × personnel_assigned) + shortfall_penalty × shortfall
   subject to:
     Σ(personnel_assigned to point i) + shortfall_i = personnel_needed_i
     Σ(personnel_assigned from station j) ≤ effective_personnel_j
     personnel_assigned ≥ 0
   ```
3. **Fallback**: If subprocess fails or solver unavailable, use `_greedy_allocate()`
   - Iterate through control points
   - For each point, greedily pick nearest station with available capacity
   - Suboptimal but fast (<50ms)

**Output**:
```json
{
  "allocations": [
    {
      "control_point_node_id": 12345,
      "station_id": 12,
      "station_name": "Cubbon Park",
      "personnel_assigned": 5,
      "distance_m": 280
    }
  ],
  "shortfall": 2,
  "solver": "ortools_cbc" or "greedy_fallback"
}
```

#### `allocate_barricades(control_points, stations=None, max_radius_m=6000) → dict`

Simpler than personnel (interchangeable units), always uses greedy allocation.

**Why**: Barricades don't have complex constraints; greedy is sufficient.

#### `load_police_stations() → list[dict]`

Query PostgreSQL or fallback to hardcoded FALLBACK_STATIONS.

```python
stations = [
    {
        "id": 1,
        "name": "Yelahanka",
        "zone": "North Zone 2",
        "latitude": 13.101419,
        "longitude": 77.596026,
        "available_personnel": 31,
        "available_barricades": 48,
    },
    # ... 14 more
]
```

**Why**: Enables offline testing + graceful degradation.

---

### 5. **backend/api/main.py** — FastAPI REST API

**Purpose**: Expose forecasting, planning, workflow, and feedback endpoints.

**Server**: `uvicorn main:app --port 8000`

#### Core Architecture

```python
app = FastAPI(title="Bengaluru Traffic Forecasting MVP API", version="0.4.0")

# Middleware
app.add_middleware(CORSMiddleware, ...)

# Context injection
def request_context(
    x_tenant_id: str = Header(default="bengaluru-traffic"),
    x_user_id: str = Header(default="local-demo-user"),
    x_user_role: str = Header(default="traffic_commander"),
) -> RequestContext:
    return RequestContext(tenant_id=x_tenant_id, user_id=x_user_id, role=x_user_role)

# Role-based access control
def require_roles(*allowed_roles: str):
    def dependency(context: RequestContext = Depends(request_context)) -> RequestContext:
        if context.role not in allowed_roles and context.role != "admin":
            raise HTTPException(status_code=403, detail="Insufficient role")
        return context
    return dependency
```

#### Event Resolution

System resolves events from multiple sources in priority order:

```python
def get_event_or_404(event_id: str) -> dict:
    # 1. Try PostgreSQL
    event = lookup_db_event(event_id)
    if event:
        return event
    
    # 2. Try integrations (live feeds, planned permits)
    event = lookup_integrated_event(event_id)
    if event:
        return event
    
    # 3. Try seed data (planned_events_seed.json)
    event = lookup_seed_event(event_id)
    if event:
        return event
    
    # Not found
    raise HTTPException(status_code=404, detail=f"Unknown event_id: {event_id}")
```

**Why**: Seamless blending of live, historical, and test data.

#### Caching

In-memory event signature caching to reduce re-runs:

```python
_FORECAST_CACHE = {}  # key → (time_cached, value)
_PLAN_CACHE = {}

def event_cache_signature(event_id: str, event: dict) -> str:
    return "|".join([
        event_id,
        event.get("status"),
        event.get("event_cause"),
        event.get("corridor"),
        event.get("zone"),
        event.get("start_datetime"),
        # ... more fields
    ])

def cached_value(cache: dict, key: str, ttl_seconds: int) -> dict | None:
    cached = cache.get(key)
    if not cached:
        return None
    cached_at, value = cached
    if time.monotonic() - cached_at > ttl_seconds:
        cache.pop(key, None)
        return None
    return dict(value)
```

**TTL**:
- Forecast cache: 300s (configurable via FORECAST_CACHE_TTL_SECONDS)
- Plan cache: 600s (configurable via PLAN_CACHE_TTL_SECONDS)

**Why**: Avoid re-running expensive ML/optimization for rapidly-polled events.

#### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | API root + docs link |
| `/events/active` | GET | List active incidents |
| `/events/upcoming` | GET | List planned events |
| `/events/{event_id}/forecast` | POST | Predict impact (ML forecast) |
| `/events/{event_id}/plan` | POST | Generate deployment plan |
| `/events/{event_id}/feedback` | POST | Record officer feedback |
| `/plans/multi-incident` | POST | Generate plan for multiple incidents |
| `/workflow/plans` | POST | Create plan record (initiates approval workflow) |
| `/workflow/plans/{plan_id}/approval` | POST | Approve/reject/activate/close plan |
| `/workflow/plans/{plan_id}/history` | GET | Retrieve plan version history |
| `/metrics/summary` | GET | Quick snapshot (active incidents, personnel deployed) |
| `/metrics/roi` | GET | Executive ROI summary (cost savings, time improvements) |
| `/metrics/operational` | GET | Operational details (queue length, delay, etc.) |
| `/field/assignments` | GET | Get assignments for a police station |
| `/field/status` | POST | Record field officer status update |
| `/field/status` | GET | Query field status by event/station |
| `/sla/events/{event_id}` | GET | SLA compliance (response time, clearance time) |
| `/reports/after-action/{event_id}` | GET | Post-incident analysis report |
| `/reports/after-action/{event_id}/csv` | GET | Download report as CSV |
| `/audit/log` | GET | View audit trail |
| `/platform/health` | GET | System health (DB, integrations) |
| `/platform/observability` | GET | Uptime, request stats, latency |
| `/platform/security-review` | GET | RBAC matrix |
| `/platform/retention` | GET | Data retention policy |
| `/models/backtest` | GET | Model backtest results |
| `/models/drift` | GET | Model drift summary |
| `/models/retrain-plan` | GET | Recommend retraining if drift detected |
| `/integrations/status` | GET | Health of data source integrations |
| `/ws/live` | WebSocket | Real-time metrics + newly active events (every 5s) |

#### Example Requests

**1. Forecast an Incident**

```bash
curl -X POST http://localhost:8000/events/crash-001/forecast \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: bengaluru-traffic" \
  -H "X-User-Id: officer.123" \
  -H "X-User-Role: traffic_commander"
```

Response:
```json
{
  "event_id": "crash-001",
  "severity_label": "HIGH",
  "severity_probability": 0.72,
  "duration_median": 28,
  "personnel_demand": 11,
  "forecast_explanation": [...],
  "cache_status": "miss"
}
```

**2. Generate Deployment Plan**

```bash
curl -X POST http://localhost:8000/events/crash-001/plan \
  -H "X-Tenant-Id: bengaluru-traffic"
```

Response:
```json
{
  "event": {...},
  "control_points": [...],
  "allocations": [...],
  "total_personnel": 9,
  "personnel_shortfall": 0,
  "plan_cache_status": "miss"
}
```

**3. Record Feedback**

```bash
curl -X POST http://localhost:8000/events/crash-001/feedback \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: bengaluru-traffic" \
  -d '{
    "accepted": true,
    "actual_duration_minutes": 26,
    "officer_rating": 5,
    "adjusted_personnel": 9
  }'
```

Response:
```json
{
  "event_id": "crash-001",
  "accepted": true,
  "predicted_duration_minutes": 28,
  "plan_total_personnel": 9,
  "stored": true
}
```

**4. Real-time WebSocket**

```bash
wscat -c ws://localhost:8000/ws/live
```

Broadcasts every 5s:
```json
{
  "metrics": {
    "active_incident_count": 3,
    "planned_events_today": 2,
    "total_personnel_deployed": 18,
    "forecast_accuracy_30d": 12.5
  },
  "newly_active_events": [
    {
      "id": "breakdown-002",
      "latitude": 12.978,
      "longitude": 77.596,
      "event_cause": "Vehicle Breakdown",
      "status": "active"
    }
  ],
  "sent_at": "2026-06-20T10:35:00Z"
}
```

---

### 6. **backend/data/workflow.py** — Plan Lifecycle & Audit

**Purpose**: Manage plan versioning, approval chains, and immutable audit trail.

**Key Functions**:

#### `create_plan_record(event_id, plan, actor, tenant_id) → dict`

Initiate a plan with approval workflow.

```python
from backend.data.workflow import create_plan_record

plan_record = create_plan_record(
    event_id="crash-001",
    plan={...},  # from generate_deployment_plan()
    actor="officer.123",
    tenant_id="bengaluru-traffic"
)
```

Creates plan_workflows.jsonl entry:
```json
{
  "record_type": "plan_version",
  "plan_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_id": "crash-001",
  "version": 1,
  "status": "draft",
  "tenant_id": "bengaluru-traffic",
  "created_at": "2026-06-20T10:30:00Z",
  "actor": "officer.123",
  "approval_chain": [
    {"role": "traffic_commander", "status": "pending"},
    {"role": "zone_superintendent", "status": "pending"}
  ],
  "plan": {...},
  "comment": "Plan created"
}
```

Audit logs: `action=plan.created`

#### `update_plan_approval(plan_id, action, actor, tenant_id, comment=None) → dict | None`

State transition: draft → submitted → approved → activated → closed

```python
from backend.data.workflow import update_plan_approval

updated = update_plan_approval(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    action="submit",  # or "approve", "reject", "activate", "close"
    actor="commander.456",
    tenant_id="bengaluru-traffic",
    comment="Ready for deployment"
)
```

**Transitions**:
- `submit`: draft → submitted
- `approve`: submitted → approved (updates approval_chain[0].status)
- `reject`: * → rejected
- `activate`: approved → activated
- `close`: * → closed

**Output** (new version):
```json
{
  "plan_id": "550e8400...",
  "version": 2,
  "status": "submitted",
  "actor": "commander.456",
  "created_at": "2026-06-20T10:35:00Z",
  "approval_chain": [
    {
      "role": "traffic_commander",
      "status": "pending"  // still pending at this step
    },
    {
      "role": "zone_superintendent",
      "status": "pending"
    }
  ]
}
```

Audit logs: `action=plan.submitted`

#### `audit_log(action, actor, tenant_id, resource_type, resource_id, details=None) → dict`

Append to audit_log.jsonl (or PostgreSQL if connected).

```python
from backend.data.workflow import audit_log

log_entry = audit_log(
    action="feedback.recorded",
    actor="officer.123",
    tenant_id="bengaluru-traffic",
    resource_type="event",
    resource_id="crash-001",
    details={"accepted": True, "rating": 5}
)
```

Output:
```json
{
  "audit_id": "550e8400-e29b-41d4-a716-446655440001",
  "created_at": "2026-06-20T10:40:00Z",
  "tenant_id": "bengaluru-traffic",
  "actor": "officer.123",
  "action": "feedback.recorded",
  "resource_type": "event",
  "resource_id": "crash-001",
  "details": {"accepted": true, "rating": 5}
}
```

**Why Immutable**: Enables forensics ("who approved X?"), non-repudiation, compliance audits.

---

### 7. **backend/ml/feature_cleaning.py** — ML Feature Normalization

Canonicalize categorical feature values to prevent ML model brittleness.

**Key Functions**:

```python
normalize_event_cause("Accident") → "accident"
normalize_event_cause("VEH_BREAKDOWN") → "breakdown"
normalize_category("M.G. Road") → "m.g. road"
event_category_for_cause("accident") → "crash"
is_minor_road_defect_context(event) → bool  # potholes, debris
duration_cap_for_event(event, default_cap=480) → int  # event-type-specific ceiling
```

**Why**: ML models trained on specific value distributions; inconsistent feature values cause OOV (out-of-vocabulary) or silent failures.

---

### 8. **backend/integrations/integrations.py** — Live Data Adapters

**Purpose**: Adapter layer for real-time feeds (Google Maps, weather, CCTV, public advisories).

**Key Functions**:

```python
live_incidents() → list[dict]  # Current active incidents from external feeds
planned_permits() → list[dict]  # Upcoming planned events (VIP movements, road work)
integration_status() → list[dict]  # Health status of each feed
operational_context_for_event(event) → dict  # Speed, weather, advisories
```

**Output Example** (`operational_context_for_event`):
```json
{
  "speed": {
    "speed_ratio": 0.45,
    "delay_factor": 0.35,
    "sample_size": 120
  },
  "sensors": {
    "vehicle_count_15m": 240
  },
  "weather": {
    "rainfall_mm_1h": 2.5,
    "temperature_c": 28
  },
  "advisories": [
    "Heavy traffic on MG Road due to VIP movement (12:00-14:00)"
  ]
}
```

**Why**: Enables fusion of heterogeneous data sources. Graceful degradation if a feed is unavailable.

---

### 9. **backend/geo/road_graph.py** — OSM Road Network Management

**Purpose**: Load and cache OpenStreetMap road graphs for spatial queries.

```python
from backend.geo.road_graph import get_graph_for_point, get_graph, cache_demo_graph

# Download graph centered on event location
graph = get_graph_for_point(latitude=12.9716, longitude=77.5946)

# Use cached graph
graph = get_graph(cache_path="./osm_cache/bangalore.pkl")

# Create tiny demo graph for CI (no network calls)
demo_path = cache_demo_graph()
graph = get_graph(cache_path=demo_path)
```

**Why**: OSM provides free, global road data. Caching avoids repeated downloads. Demo graph enables deterministic CI.

---

### 10. **backend/optimization/control_points.py** — Geographic Control Point Discovery

**Purpose**: Identify optimal positions to deploy personnel around an incident.

```python
from backend.optimization.control_points import find_control_points

points = find_control_points(
    latitude=12.9716,
    longitude=77.5946,
    search_radius_m=1200,
    graph=road_graph,
    limit=5
)
```

Output:
```json
[
  {
    "node_id": 12345,
    "lat": 12.9720,
    "lon": 77.5950,
    "lane_estimate": 4,
    "is_arterial": true,
    "selection_method": "optimal",
    "reasoning": ["High lane count", "Direct upstream", "Intersection"]
  },
  ...
]
```

**Why**: Placement matters. Officers on arterial roads (4+ lanes) affect 10× more vehicles than side streets.

---

### 11. **backend/optimization/resource_sizing.py** — Dynamic Resource Calculation

**Purpose**: Convert prediction severity → control point resource needs.

```python
from backend.optimization.resource_sizing import size_event_resources

resources = size_event_resources(control_points, prediction_context)
```

Output:
```json
{
  "control_points": [
    {
      "node_id": 12345,
      "personnel_needed": 5,
      "barricades_needed": 3
    },
    ...
  ],
  "total_personnel": 9,
  "total_barricades": 6
}
```

**Why**: Encodes domain knowledge (HIGH severity → more personnel) without hard-coding in `generate_plan.py`.

---

### 12. **backend/optimization/diversion.py** — Alternative Route Computation

**Purpose**: Suggest traffic diversions to mitigate downstream congestion.

```python
from backend.optimization.diversion import compute_diversions

diversions = compute_diversions(
    latitude=12.9716,
    longitude=77.5946,
    context=prediction_context,
    graph=road_graph
)
```

Output:
```json
["Residency Road", "Brigade Road", "Commissariat Road"]
```

---

### Supporting Modules

#### `geo_utils.py` — Geospatial Utilities

```python
haversine_meters(lat1, lon1, lat2, lon2) → float  # Great-circle distance
nearest_node_by_haversine(graph, lat, lon) → int  # Closest OSM node
node_lat_lon(graph, node_id) → (float, float)  # Node coordinates
```

#### `model_monitoring.py` — Drift Detection

```python
drift_summary(active_events) → dict  # Compare predicted vs. actual
forecast_backtest_summary() → dict  # Hind-sight evaluation
retrain_plan() → dict  # Recommend retraining if drift detected
```

#### `operational_monitoring.py` — Real-time Metrics

```python
operational_metrics_snapshot(plan) → dict  # Queue, delay, segment impacts
```

#### `roi_metrics.py` — Executive Summaries

```python
executive_roi_summary(active_events, planned, feedback) → dict  
# Cost savings, response time improvements, personnsourceel efficiency
```

#### `platform_ops.py` — System Health & Compliance

```python
platform_health(...) → dict  # Uptime, DB connectivity
retention_policy() → dict  # Data retention rules
security_controls() → dict  # RBAC matrix
```

#### `multi_incident.py` — Multi-Incident Coordination

```python
build_multi_incident_plan(events, scenarios) → dict  
# Holistic plan for multiple concurrent incidents
```

#### `train_models.py` — Model Retraining (Offline)

Runs offline to regenerate ML artifacts. Consumes feedback table; outputs:
- `severity_model.pkl`
- `duration_q*.pkl`
- `risk_density.parquet`
- `duration_survival_table.parquet`

#### `seed_feedback.py` — Test Data Generation

Generate synthetic feedback records for development/testing.

#### `benchmark_system.py` — Performance Profiling

Profile system latency, throughput.

---

## API Documentation

### Authentication

All endpoints support multi-tenancy via headers:

```http
X-Tenant-Id: bengaluru-traffic
X-User-Id: officer.123
X-User-Role: traffic_commander|zone_superintendent|field_officer|admin
```

Defaults (if omitted):
```
X-Tenant-Id: bengaluru-traffic
X-User-Id: local-demo-user
X-User-Role: traffic_commander
```

### Error Handling

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad request (validation error) |
| 403 | Forbidden (insufficient role) |
| 404 | Not found (event_id, plan_id) |
| 500 | Internal server error |

Example error response:
```json
{
  "detail": "Unknown event_id: crash-999"
}
```

### Rate Limiting

None enforced at API level (implement at reverse proxy if needed).

### Response Format

All responses are JSON. Timestamps use ISO 8601 with timezone (UTC).

```json
{
  "timestamp": "2026-06-20T10:30:00+00:00",
  "data": {...}
}
```

### Interactive Documentation

Visit http://localhost:8000/docs (Swagger UI) or /redoc (ReDoc).

---

## Installation & Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 15 (optional; JSONL fallback available)
- PostGIS extension (if using PostgreSQL)
- 2GB RAM, 1GB disk space

### Step 1: Clone Repository

```bash
git clone https://github.com/your-org/traffic-forecasting.git
cd traffic-forecasting/TrafficGuide
```

### Step 2: Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies**:
- FastAPI, uvicorn (API)
- SQLAlchemy, psycopg2 (Database)
- pandas, numpy, pyarrow (Data processing)
- scikit-learn, xgboost, lightgbm, joblib (ML)
- networkx, osmnx (Geospatial)
- ortools (Optimization)

### Step 4: Create .env File

```bash
cat > .env <<EOF
# Database (optional; defaults to JSONL if missing)
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/gridlock

# Models
MODEL_DIR=./models

# API
APP_ENV=local
PORT=8000

# Caching (seconds)
FORECAST_CACHE_TTL_SECONDS=300
PLAN_CACHE_TTL_SECONDS=600

# Active events query
ACTIVE_EVENT_LOOKBACK_DAYS=30
ACTIVE_EVENT_LIMIT=1000
ACTIVE_EVENT_INCLUDE_DEMO_FEEDS=false
EOF
```

### Step 5: Set Up Database (Optional)

```bash
# Create database
createdb gridlock

# Apply schema (includes PostGIS setup)
psql gridlock < schema.sql

# Load historical data
python -m backend.data.load_data path/to/events.csv
```

If you skip this, the system falls back to JSONL files and hardcoded police stations.

### Step 6: Verify ML Models

Ensure model artifacts exist:

```bash
ls -la models/
# severity_model.pkl
# duration_q25_model.pkl
# duration_q50_model.pkl
# duration_q75_model.pkl
# risk_density.parquet
# duration_survival_table.parquet
```

If missing, run:

```bash
python -m backend.ml.train_models --feedback-path feedback_log.jsonl
```

### Step 7: Run Server

```bash
uvicorn main:app --reload --port 8000
```

Logs:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

Visit http://localhost:8000/docs

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (None) | PostgreSQL connection string; if missing, use JSONL |
| `MODEL_DIR` | `./models` | Path to ML artifacts |
| `APP_ENV` | `local` | Environment (`local`, `staging`, `prod`) |
| `PORT` | 8000 | API port |
| `FORECAST_CACHE_TTL_SECONDS` | 300 | Forecast cache TTL |
| `PLAN_CACHE_TTL_SECONDS` | 600 | Plan cache TTL |
| `ACTIVE_EVENT_LOOKBACK_DAYS` | (None) | Query events from last N days (None = all) |
| `ACTIVE_EVENT_LIMIT` | 1000 | Max events returned |
| `ACTIVE_EVENT_INCLUDE_DEMO_FEEDS` | false | Include demo feeds in active list |
| `MPLCONFIGDIR` | `/private/tmp/grid_matplotlib` | Matplotlib temp dir (read-only systems) |

### Schema Customization

Edit `schema.sql` to customize:
- Zone boundaries (in `infer_zone()`)
- Police station inventory
- Approval chain roles
- Audit log fields

---

## Usage Examples

### Example 1: Full Workflow (Forecast → Plan → Approve → Deploy)

```python
import requests
import json

BASE_URL = "http://localhost:8000"
HEADERS = {
    "X-Tenant-Id": "bengaluru-traffic",
    "X-User-Id": "command.officer",
    "X-User-Role": "traffic_commander",
}

# 1. Define incident
incident = {
    "id": "crash-001",
    "latitude": 12.9716,
    "longitude": 77.5946,
    "event_cause": "Accident",
    "corridor": "M G Road",
    "zone": "Central Zone 1",
    "police_station": "Cubbon Park",
    "start_datetime": "2026-06-20T09:30:00+05:30",
}

# 2. Forecast impact
forecast_response = requests.post(
    f"{BASE_URL}/events/{incident['id']}/forecast",
    json=incident,
    headers=HEADERS,
)
forecast = forecast_response.json()
print(f"Severity: {forecast['severity_label']}")
print(f"Duration: {forecast['duration_median']}±{forecast['duration_high']-forecast['duration_low']} min")
print(f"Personnel needed: {forecast['personnel_demand']}")

# 3. Generate plan
plan_response = requests.post(
    f"{BASE_URL}/events/{incident['id']}/plan",
    headers=HEADERS,
)
plan = plan_response.json()
print(f"Control points: {len(plan['control_points'])}")
print(f"Personnel allocated: {plan['total_personnel']}")
print(f"Shortfall: {plan['personnel_shortfall']}")

# 4. Create plan record (initiates approval workflow)
workflow_response = requests.post(
    f"{BASE_URL}/workflow/plans",
    json={
        "event_id": incident["id"],
        "plan": plan,
        "actor": "command.officer",
        "tenant_id": "bengaluru-traffic",
    },
    headers=HEADERS,
)
plan_record = workflow_response.json()
plan_id = plan_record["plan_id"]
print(f"Plan created: {plan_id}")

# 5. Approve plan (traffic commander)
approve_response = requests.post(
    f"{BASE_URL}/workflow/plans/{plan_id}/approval",
    json={
        "action": "submit",
        "actor": "command.officer",
        "comment": "Ready for deployment",
    },
    headers=HEADERS,
)
print(f"Plan submitted: {approve_response.status_code}")

# 6. Zone superintendent approves
superintendent_headers = dict(HEADERS)
superintendent_headers["X-User-Id"] = "superintendent.zone1"
superintendent_headers["X-User-Role"] = "zone_superintendent"

approve_response = requests.post(
    f"{BASE_URL}/workflow/plans/{plan_id}/approval",
    json={
        "action": "approve",
        "actor": "superintendent.zone1",
        "comment": "Approved for deployment",
    },
    headers=superintendent_headers,
)
print(f"Plan approved: {approve_response.status_code}")

# 7. Activate plan
activate_response = requests.post(
    f"{BASE_URL}/workflow/plans/{plan_id}/approval",
    json={
        "action": "activate",
        "actor": "command.officer",
    },
    headers=HEADERS,
)
print(f"Plan activated: {activate_response.status_code}")

# 8. Field officers report actual outcome
feedback_response = requests.post(
    f"{BASE_URL}/events/{incident['id']}/feedback",
    json={
        "accepted": True,
        "actual_duration_minutes": 26,
        "officer_rating": 5,
        "adjusted_personnel": 9,
    },
    headers=HEADERS,
)
print(f"Feedback recorded: {feedback_response.status_code}")

# 9. Close plan
close_response = requests.post(
    f"{BASE_URL}/workflow/plans/{plan_id}/approval",
    json={
        "action": "close",
        "actor": "command.officer",
    },
    headers=HEADERS,
)
print(f"Plan closed: {close_response.status_code}")
```

### Example 2: Multi-Incident Coordination

```python
incidents = [
    {"id": "crash-001", "latitude": 12.9716, "longitude": 77.5946, ...},
    {"id": "crash-002", "latitude": 12.9750, "longitude": 77.6000, ...},
]

response = requests.post(
    f"{BASE_URL}/plans/multi-incident",
    json={
        "event_ids": [i["id"] for i in incidents],
        "scenarios": None,  # Use default
    },
    headers=HEADERS,
)
multi_plan = response.json()
print(f"Multi-incident plan generated")
print(f"Total personnel: {multi_plan['total_personnel']}")
print(f"Constraints satisfied: {multi_plan['constraints_satisfied']}")
```

### Example 3: WebSocket Real-Time Updates

```bash
# Terminal 1: WebSocket client
wscat -c ws://localhost:8000/ws/live

# Terminal 2: Trigger an incident
curl -X POST http://localhost:8000/events/crash-001/forecast \
  -H "X-Tenant-Id: bengaluru-traffic"

# Terminal 1: Receives broadcast
{
  "metrics": {
    "active_incident_count": 1,
    "total_personnel_deployed": 9,
    "forecast_accuracy_30d": 12.5
  },
  "newly_active_events": [
    {
      "id": "crash-001",
      "event_cause": "Accident",
      "status": "active"
    }
  ],
  "sent_at": "2026-06-20T10:30:00Z"
}
```

---

## Data Flow

### Forecast to Plan to Feedback

```
1. INCIDENT OCCURS
   └─ Astram/live feed registers crash at 12.97, 77.59

2. API REQUEST: /events/crash-001/forecast
   └─ main.py:post_forecast()
      ├─ lookup_db_event() → not found
      ├─ lookup_integrated_event() → found
      ├─ predict_impact() → call predict.py
      │  ├─ load_artifacts() [LRU cached]
      │  ├─ build_feature_frame()
      │  ├─ severity prediction → P(HIGH)=0.72 → "HIGH"
      │  ├─ duration prediction → Q50=28 min + survival adjustment
      │  ├─ risk_score lookup → 0.65 from heatmap
      │  └─ operational_metrics() → personnel_demand=11, delay=22min
      └─ cached_value() → cache key = "crash-001|active|Accident|M G Road|Central Zone 1|..."
         └─ remember_value() → store in _FORECAST_CACHE
   └─ Response: {severity_label, duration_median, personnel_demand, ...}

3. DECISION: Deploy resources

4. API REQUEST: /events/crash-001/plan
   └─ main.py:post_plan()
      ├─ forecast_event() → get cached forecast
      ├─ generate_deployment_plan()
      │  ├─ get_graph_for_point() → OSM graph (cached)
      │  ├─ find_control_points() → {CP1, CP2, CP3}
      │  ├─ size_event_resources() → personnel/barricades per CP
      │  ├─ allocate_personnel() → OR-Tools solver
      │  │  ├─ candidate_station_pairs() → distance matrix
      │  │  └─ _allocate_with_child_process() → LP solve
      │  ├─ allocate_barricades() → greedy
      │  └─ compute_diversions() → alternate routes
      └─ Response: {control_points, allocations, shortfall, ...}

5. API REQUEST: /workflow/plans
   └─ main.py:post_workflow_plan()
      └─ workflow.py:create_plan_record()
         ├─ Write to plan_workflows.jsonl
         └─ audit_log("plan.created", ...)
   └─ Response: {plan_id, version, approval_chain, ...}

6. APPROVAL WORKFLOW
   POST /workflow/plans/{plan_id}/approval
   └─ workflow.py:update_plan_approval()
      ├─ Fetch latest version
      ├─ Transition state (draft → submitted → approved → activated)
      ├─ Update approval_chain[role].status
      ├─ Write new version
      └─ audit_log("plan.{status}", ...)

7. EXECUTION IN FIELD
   POST /field/status
   └─ workflow.py:record_field_status()
      ├─ Write to field_status_log.jsonl
      └─ audit_log("field.status.updated", ...)

8. OUTCOME RECORDING
   POST /events/crash-001/feedback
   └─ main.py:write_feedback()
      ├─ Get event + forecast
      ├─ Ensure event row in DB (upsert)
      ├─ INSERT into feedback table
      │  ├─ predicted_severity, predicted_duration
      │  ├─ actual_duration ← officer input
      │  ├─ officer_rating ← officer input
      │  ├─ plan_accepted ← bool
      │  └─ plan_json ← snapshot
      ├─ append_local_feedback() if no DB
      └─ audit_log("feedback.recorded", ...)

9. FEEDBACK PROCESSING (Offline)
   └─ train_models.py:retrain()
      ├─ Query feedback table (30-day window)
      ├─ Compute errors: |predicted - actual| / actual
      ├─ Detect drift: error > threshold?
      ├─ Retrain severity + duration models
      └─ Update artifacts (severity_model.pkl, etc.)

10. LOOP CLOSES
    └─ Next forecast uses updated models
```

---

## Performance

### Latency Benchmarks

| Operation | Latency (ms) | Notes |
|-----------|-------------|-------|
| forecast_event (cache hit) | 50–100 | Dict lookup + JSON serialization |
| forecast_event (cache miss) | 1500–2500 | ML inference |
| generate_deployment_plan | 400–800 | OSM graph cached; allocation depends on station count |
| allocate_personnel (OR-Tools) | 50–150 | Depends on control point count |
| allocate_personnel (greedy) | 10–30 | Fast fallback |
| write_feedback | 30–100 | JSONL append or DB insert |
| /ws/live broadcast | 100–200 | Per connected client |
| POST /workflow/plans | 50–100 | Plan record creation |

### Throughput

| Scenario | Throughput |
|----------|-----------|
| Forecast requests (cache hits) | 1000+ RPS |
| Forecast requests (cache miss) | 5–10 RPS (limited by ML) |
| Plan generation | 1–2 RPS (limited by OSM graph I/O) |
| Feedback recording | 100+ RPS |
| WebSocket broadcasts | 1000+ messages/s |

### Memory Usage

| Component | Memory (MB) |
|-----------|----------|
| Python runtime | 50–80 |
| ML artifacts (loaded) | 100–200 |
| Forecast cache (100 entries) | 10–50 |
| Plan cache (100 entries) | 20–100 |
| OSM graph (city-scale) | 500–1000 |
| **Total** | **~1500 MB** |

### Optimization Tips

1. **Increase forecast cache TTL** if predictions rarely change
2. **Use OR-Tools subprocess** for optimal allocation (vs. greedy)
3. **Cache OSM graph** on disk to avoid repeated downloads
4. **Batch feedback writes** if processing high volume
5. **Shard PostgreSQL** by tenant_id if multi-city

---

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t traffic-forecasting .
docker run -e DATABASE_URL=postgresql://... -p 8000:8000 traffic-forecasting
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: traffic-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: traffic-api
  template:
    metadata:
      labels:
        app: traffic-api
    spec:
      containers:
      - name: api
        image: traffic-forecasting:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
        - name: MODEL_DIR
          value: /models
        volumeMounts:
        - name: models
          mountPath: /models
        livenessProbe:
          httpGet:
            path: /platform/health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
      volumes:
      - name: models
        configMap:
          name: ml-models
```

### Production Checklist

- [ ] Enable HTTPS (reverse proxy with SSL cert)
- [ ] Set `APP_ENV=prod`
- [ ] Increase cache TTLs (reduce re-computation)
- [ ] Enable database connection pooling
- [ ] Set up monitoring (Prometheus, Datadog)
- [ ] Configure log aggregation (ELK, CloudWatch)
- [ ] Test failover (DB unavailability, model missing)
- [ ] Set retention policies (delete feedback > 90 days)
- [ ] Audit log archival (e.g., S3)

---

## Testing

### Unit Tests

```bash
cd TrafficGuide
python -m pytest tests/ -v
```

Key test files:

- `tests/test_predict.py` — ML predictions
- `tests/test_generate_plan.py` — Plan generation
- `tests/test_allocation.py` — Resource allocation
- `tests/test_load_data.py` — CSV ingestion
- `tests/test_workflow.py` — Plan lifecycle

### Integration Tests

```bash
# Requires PostgreSQL
export DATABASE_URL="postgresql://user:pass@localhost/test_gridlock"
python -m pytest tests/integration/ -v
```

### Manual Testing

```bash
# Forecast
python predict.py

# Plan generation (demo graph, no network calls)
python -m backend.optimization.generate_plan --lat 12.9716 --lon 77.5946 --demo-cache

# Allocation solver
echo '{"control_points": [...], "stations": [...], "max_radius_m": 6000}' | \
  python allocation.py --solve-json

# API
uvicorn main:app --reload
curl http://localhost:8000/docs
```

### Load Testing

```bash
# Using Apache Bench
ab -n 1000 -c 10 http://localhost:8000/events/active

# Using Locust
locust -f loadtest.py --host=http://localhost:8000
```

---

## Troubleshooting

### "Missing model artifacts: severity_model.pkl"

**Cause**: ML models not trained.

**Solution**:
```bash
python -m backend.ml.train_models --feedback-path feedback_log.jsonl --output-dir models
```

### "DATABASE_URL is required"

**Cause**: PostgreSQL connection string not set.

**Options**:
1. Set environment variable:
   ```bash
   export DATABASE_URL="postgresql://user:pass@localhost:5432/gridlock"
   ```
2. Create .env file (auto-loaded by env_loader.py)
3. Use offline mode (JSONL backend) — just omit DATABASE_URL

### "No usable control points found"

**Cause**: OSM road graph missing or incomplete.

**Solutions**:
1. Verify OSM graph cache:
   ```bash
   ls -la osm_cache/
   ```
2. Delete stale cache and re-download:
   ```bash
   rm -rf osm_cache/
   python -m backend.optimization.generate_plan --lat 12.9716 --lon 77.5946
   ```
3. Use demo graph for testing:
   ```bash
   python -m backend.optimization.generate_plan --demo-cache
   ```

### "Personnel shortfall: X units unavailable"

**Cause**: Insufficient personnel available within allocation radius.

**Solutions**:
1. Increase allocation radius:
   ```python
   allocate_personnel(..., max_radius_m=10_000)
   ```
2. Add more police stations to database
3. Accept shortfall (plan still valid, just incomplete coverage)

### "Forecast accuracy too low (>20% error)"

**Cause**: Model drift or distribution shift.

**Solutions**:
1. Check model drift:
   ```bash
   curl http://localhost:8000/models/drift
   ```
2. Retrain if drift detected:
   ```bash
   python -m backend.ml.train_models
   ```
3. Review feedback for data quality issues

### "WebSocket connection drops after 5 seconds"

**Cause**: Client-side keep-alive timeout or server misconfiguration.

**Solutions**:
1. Client: Increase timeout in WebSocket connect options
2. Server: Check reverse proxy settings (nginx, HAProxy)
3. Verify firewall allows WebSocket upgrades

### "CORS errors from mobile app"

**Cause**: CORS middleware not allowing cross-origin requests.

**Solution**: Update allowed origins in `main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-domain.com",
        "https://mobile-app.your-domain.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Future Enhancements

### Phase 2: Real-time Adaptation

- Recompute plans as incidents evolve
- Dynamic rerouting based on live congestion
- Weather-aware diversions
- Incident escalation (minor → major classification)

### Phase 3: Advanced Optimization

- Multi-objective optimization (personnel cost vs. coverage)
- Stochastic optimization (demand uncertainty)
- Robust optimization (worst-case scenarios)
- Network flow optimization (multi-incident cascades)

### Phase 4: Predictive Maintenance

- Equipment failure prediction (barricade, signage wear)
- Officer fatigue modeling
- Vehicle maintenance scheduling

### Phase 5: City-Scale Deployment

- Multi-city federation
- Inter-city incident propagation
- Regional resource sharing
- Demand forecasting (predict incident rates 24h ahead)

---

## Contributing

### Code Style

- Follow PEP 8
- Use type hints (Python 3.11+)
- Document functions with docstrings

### Testing

- Write tests for new features
- Maintain >80% code coverage
- Test edge cases (null values, empty lists, etc.)

### Commit Messages

```
feat: add multi-incident coordination
fix: handle null geom in OSM graph
docs: update API documentation
test: add allocation solver tests
```

---

## References

### Documentation

- [FastAPI Guide](https://fastapi.tiangolo.com/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [PostGIS Manual](https://postgis.net/docs/)
- [OSMNX Documentation](https://osmnx.readthedocs.io/)
- [OR-Tools Guide](https://developers.google.com/optimization)
- [LightGBM Quantile Regression](https://lightgbm.readthedocs.io/en/latest/Features.html#categorical-features-support)

### Research Papers

- Survival Analysis for Traffic Duration: [Right-Censored Data in Transportation](https://arxiv.org/search/?query=traffic+duration+survival&searchtype=all)
- Resource Allocation: [Vehicle Routing with Time Windows](https://en.wikipedia.org/wiki/Vehicle_routing_problem)
- Traffic Prediction: [Deep Learning for Traffic Flow](https://arxiv.org/search/?query=traffic+prediction+deep+learning)

### Tools

- Postman: API testing (import from `/docs/postman-collection.json`)
- DBeaver: PostgreSQL GUI
- Grafana: Monitoring dashboards
- Locust: Load testing

---

## Changelog

### v0.4.0 (Current)
- Initial MVP release
- Core forecasting + planning + feedback loop
- PostgreSQL + JSONL dual-backend support
- Multi-tenancy foundation

### v0.3.0
- Beta testing with Bengaluru Traffic Police
- Feedback collection from field officers

### v0.2.0
- Prototype: ML model training + API development

### v0.1.0
- POC: Data ingestion + basic forecasting

---

**Last Updated**: June 20, 2026
