# DPP Resolver Prototype Frontend

Simple Angular frontend for operating and inspecting the Resolver Prototype federation.
This is more a convenience tool for testing and debugging the Resolver Prototype federation.

## Functionality

- Live federation overview with resolver and platform status.
- Platform management: spawn, pause, resume, reset, delete, and inspect logs.
- DPP platform detail views with DPP lists, revision history, JSON viewing, creation, and revision editing.
- Resolver detail view with subject types, supporting platforms, schemas, schema viewing/editing, and resolver logs.
- Scenario runner for S1, S2, and S3 with copyable status and rendered reports.
- Visual error and status feedback for failed backend calls.

## Start Locally

The frontend expects the Factory API at `http://localhost:8000`.

```bash
npm install
npm start
```

Open `http://localhost:4200`.

## Useful Commands

```bash
npm run build
npm test
npm run e2e
```

To run it through Docker from the repository root:

```bash
docker compose up -d --build frontend
```
