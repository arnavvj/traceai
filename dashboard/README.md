# TraceAI Dashboard

The v0.1 dashboard is a single-file vanilla JS + HTML page (`index.html`).
It requires no build step and is served by `traceai open`.

## Future: React Dashboard

The `dist/` directory is reserved for a compiled React + TypeScript bundle.
When the React app is built (`npm run build`), drop the output here.
The FastAPI server will serve `dist/index.html` automatically if it exists.
