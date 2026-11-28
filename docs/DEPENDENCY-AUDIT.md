# Dependency audit — Madrasa Pro 1.0.8

**Result: no known vulnerabilities** in the runtime lock (22 packages), the dev/test lock, or the npm build tooling.
Run on 2026-11-28 (Asia/Dhaka, UTC+6) with pip-audit 2.10.1 and npm 11 / Node 24 on a clean virtual environment.

## Commands and output

```text
$ cd "Madrasa Admin Project"
$ pip-audit -r requirements.lock --require-hashes --disable-pip
No known vulnerabilities found

$ pip-audit -r requirements-dev.lock --require-hashes --disable-pip
No known vulnerabilities found

$ pip install --require-hashes -r requirements.lock --dry-run      # lock is complete and consistent
(all 22 pinned packages resolve; no extra package is pulled in)

$ npm ci && npm audit             # devDependencies: alpinejs 3.17.5, tailwindcss 3.4.19 (+ 72 transitive)
found 0 vulnerabilities
$ npm audit --omit=dev
found 0 vulnerabilities
```

## Lockfile consistency

- `requirements.txt` holds the 10 direct pins (1.0.5 adds `cryptography==50.0.2`, which pulls in `cffi` and `pycparser`); `requirements.lock` repeats each with the **same version** plus every
  transitive package (anyio, h11, click, idna, starlette, pydantic-core, typing-extensions, ...) and sha256 hashes.
  Regenerate: `uv pip compile requirements.txt --generate-hashes --universal --python-version 3.11 -o requirements.lock`.
- Installed and tested from the lock on Python **3.12.16** (full test suite) and **3.11.17** (install + import).
- `start.sh`, `start.bat`, `start.ps1` and the `Dockerfile` all install with `pip install --require-hashes -r requirements.lock`.
- `requirements-dev.txt` uses `==` pins only and is hash-locked in `requirements-dev.lock`.
- Every pin exists on PyPI (checked 2026-11-26): fastapi 0.165.0, starlette 1.10.0, uvicorn 0.54.0,
  sqlalchemy 2.1.9, jinja2 3.1.6, markupsafe 3.0.4, python-multipart 0.0.34, itsdangerous 2.2.0, pydantic 2.14.4.
- `package-lock.json` (lockfileVersion 3, real registry integrity hashes) is in sync with `package.json`.
  `static/vendor/alpine.min.js` is byte-identical to `alpinejs@3.17.5/dist/cdn.min.js`
  (sha256 `b4036e9e9ac22fa6f6ae1ba292e015e1f3e9c85d0d79e73e4c8eb9bb139b522e`); re-copy with `npm run build:vendor`.
- Docker base image: `python:3.12.16-slim` pinned by digest `sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b`.

## Runtime packages audited (pip-audit JSON)

| Package | Version | Known vulnerabilities |
|---|---|---|
| annotated-doc | 0.0.7 | 0 |
| annotated-types | 0.8.0 | 0 |
| anyio | 4.16.0 | 0 |
| click | 8.5.1 | 0 |
| fastapi | 0.165.0 | 0 |
| h11 | 0.16.0 | 0 |
| idna | 3.20 | 0 |
| itsdangerous | 2.2.0 | 0 |
| jinja2 | 3.1.6 | 0 |
| markupsafe | 3.0.4 | 0 |
| opentelemetry-api | 1.45.2 | 0 |
| pydantic | 2.14.4 | 0 |
| pydantic-core | 2.50.5 | 0 |
| python-multipart | 0.0.34 | 0 |
| sqlalchemy | 2.1.9 | 0 |
| starlette | 1.10.0 | 0 |
| typing-extensions | 4.16.0 | 0 |
| typing-inspection | 0.4.5 | 0 |
| uvicorn | 0.54.0 | 0 |

Developer: Syed Abue Tayeb Al-Zeyed
