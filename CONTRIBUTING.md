# Contributing to PatchPilot

Thanks for taking a look at PatchPilot.

## Best Ways To Contribute

- report bugs with clear reproduction steps
- propose focused features for homelab and small Linux-fleet workflows
- improve docs, installation guidance, and onboarding
- add tests for backend or frontend behavior

## Before You Open A Pull Request

1. Read the relevant docs in `README.md` and `docs/`.
2. Keep changes focused and avoid mixing unrelated work.
3. If your change affects behavior, update documentation in the same PR.
4. If your change introduces a user-visible feature or fix, add an entry to `CHANGELOG.md`.

## Development

### Backend

```bash
cd server
uvicorn app:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Verification

### Frontend build

```bash
cd frontend
npm run build
```

### Backend tests

```bash
cd server
python3 -m pytest -q
```

If `pytest` is missing locally, install the dev dependencies first:

```bash
python3 -m pip install -r requirements-dev.txt
```

## Pull Request Guidelines

- explain the user or operator problem you are solving
- mention affected areas such as server, agent, frontend, or docs
- include manual verification steps
- include screenshots for UI changes when possible
- do not commit generated secrets, databases, or machine-specific config

## Security Reports

Please do not open a public issue for a sensitive vulnerability before reading [SECURITY.md](SECURITY.md).
