# TraceAI Dashboard

The TraceAI dashboard is a React 18 + TypeScript + Vite + Tailwind CSS single-page application served by `traceai open`.

---

## Stack

| Layer | Technology |
|---|---|
| UI framework | React 18 |
| Language | TypeScript (strict) |
| Build tool | Vite |
| Styling | Tailwind CSS v3 |
| HTTP client | `fetch` (native) |
| Icons / badges | Inline SVG + Tailwind utilities |

---

## Development

```bash
# Install dependencies
cd dashboard
npm install

# Start dev server with hot reload
# Proxies /api/* to the TraceAI backend at localhost:7474
npm run dev
```

The dev server runs at `http://localhost:5173`. It expects the TraceAI backend to be running:

```bash
# In a separate terminal
traceai open --no-browser
```

API calls from the dev server are proxied to `http://localhost:7474` via the Vite config.

---

## Production Build

```bash
# Linux / macOS
npm run build

# Windows (Node/npm must be run in WSL)
wsl -e bash -c "cd /mnt/c/path/to/traceai/dashboard && npm run build"
```

The compiled bundle is written to `dashboard/dist/` and then copied into the Python package at `traceai/dashboard/dist/` by the CI release workflow. The FastAPI server serves `dist/index.html` for all non-API routes.

---

## Project Structure

```
dashboard/
├── src/
│   ├── App.tsx                  Root component, trace selection state
│   ├── main.tsx                 React entry point
│   ├── index.css                Tailwind base + CSS variables (theme tokens)
│   │
│   ├── types/
│   │   └── api.ts               Shared TypeScript interfaces (Span, Trace, …)
│   │
│   ├── api/
│   │   └── client.ts            fetch wrappers for all REST endpoints
│   │
│   ├── hooks/
│   │   ├── useTraces.ts         Paginated trace list with search + filter
│   │   ├── useProviders.ts      Provider key detection (GET /api/providers)
│   │   └── useCompare.ts        Compare-mode selection state
│   │
│   ├── utils/
│   │   └── compare.ts           Replay-family detection + span matching logic
│   │
│   └── components/
│       ├── TraceList.tsx         Left panel — paginated, filterable trace list
│       ├── TraceListItem.tsx     Single trace row with connectors for replays
│       ├── TraceDetail.tsx       Middle panel — span waterfall + header
│       ├── TraceHeader.tsx       Trace summary bar + replay controls
│       ├── SpanDetail.tsx        Right panel — inputs, outputs, metadata, replay
│       ├── CompareView.tsx       Side-by-side span diff for two traces
│       ├── ReplayBanner.tsx      Cost + token comparison on replayed traces
│       ├── ModelPicker.tsx       Provider-grouped model dropdown
│       ├── StatusBadge.tsx       Coloured ok / error / pending badge
│       └── JsonViewer.tsx        Collapsible JSON tree renderer
│
├── public/                      Static assets
├── index.html                   HTML entry point
├── vite.config.ts               Vite config (proxy, build output path)
├── tailwind.config.js           Tailwind theme (colours, CSS variables)
├── tsconfig.json                TypeScript config (strict)
└── package.json
```

---

## Theme

Design tokens are defined as CSS variables in `src/index.css` and referenced throughout via Tailwind's `theme.extend`. The palette uses an indigo/violet accent on a neutral dark background, matching the TraceAI brand colours.

Key variables:

| Variable | Usage |
|---|---|
| `--color-bg` | Page background |
| `--color-panel` | Sidebar and panel backgrounds |
| `--color-border` | All dividers and outlines |
| `--color-accent` | Primary interactive colour (indigo-500) |
| `--color-text-primary` | Main text |
| `--color-text-muted` | Secondary / metadata text |
| `--connector-color` | Trace tree connector lines |

---

## API Endpoints Consumed

The dashboard talks to the TraceAI FastAPI server. All endpoints are prefixed `/api/`:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/traces` | Paginated trace list |
| `GET` | `/api/traces/{id}` | Single trace |
| `GET` | `/api/traces/{id}/spans` | All spans for a trace |
| `POST` | `/api/traces/{id}/replay` | Cascade replay with model swap |
| `GET` | `/api/spans/{id}` | Single span |
| `POST` | `/api/spans/{id}/replay` | Single span replay |
| `GET` | `/api/experiments` | Experiment aggregate stats |
| `GET` | `/api/experiments/{name}/traces` | Traces for one experiment |
| `GET` | `/api/providers` | Key presence detection |
| `DELETE` | `/api/traces/{id}` | Delete a trace |
| `DELETE` | `/api/traces` | Clear all traces |

---

## Type Checking

```bash
# TypeScript check only (no emit)
npx tsc --noEmit
```

The project uses `strict: true` in `tsconfig.json`. All components are fully typed — no `any` except at explicit API boundary casts.
