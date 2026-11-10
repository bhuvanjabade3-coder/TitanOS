# TITAN Shell (frontend)

React + TypeScript + Tailwind v4 + Framer Motion. Design tokens live in
`src/styles.css`.

```bash
npm install
npm test         # vitest
npm run build    # type-check + production build
npm run dev      # http://127.0.0.1:5173, proxies to TITAN Core on :8710
```

The dev server reads the core's `api_token` file and attaches it server-side,
so the token never reaches browser JavaScript. Set `TITAN_DATA_DIR` if the core
uses a non-default data directory.
