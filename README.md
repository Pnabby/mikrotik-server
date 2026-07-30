# MikroTik hotspot backend

A FastAPI backend and status page for querying hotspot voucher usage and active
sessions across multiple MikroTik routers. One backend process serves every configured
site; callers select a router by its server-defined ID and can never supply a connection
host.

## Router registry

Non-secret router metadata lives in `src/mikrotik/routers.py`.

| Router ID | Display name | WireGuard/API host | API port | Hotspot network |
| --- | --- | --- | ---: | --- |
| `flint-main` | Flint Main | `10.20.20.2` | 8728 | `192.168.88.0/23` |
| `platinum` | Platinum | `10.20.20.3` | 8728 | `192.168.90.0/23` |

Only the exact IDs `flint-main` and `platinum` resolve to a router. Hosts and ports are never
accepted from an HTTP request. The `/api/routers` discovery response intentionally omits
API hosts and credentials.

## Configuration

Copy `.env.example` to `.env` and set the shared RouterOS API credentials:

```powershell
Copy-Item .env.example .env
```

```dotenv
MIKROTIK_USERNAME=backend-api-user
MIKROTIK_PASSWORD=replace-me
```

`.env` is ignored by Git and must not be committed. Both routers use these shared
credentials. Router hosts and ports come exclusively from the registry, so the old
`MIKROTIK_HOST` and `MIKROTIK_PORT` variables are no longer used.

Set `MIKROTIK_PLAINTEXT_LOGIN=true` for the RouterOS API login flow used by these
routers. API traffic, including authentication, must remain inside the encrypted
WireGuard tunnel.

The optional `MIKROTIK_ROUTER_ID` variable selects the router for the interactive
`python -m mikrotik` command only; it defaults to `flint-main`. API requests always use the
router ID in their URL.

## Install and run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest
mikrotik-api
```

Runtime dependencies only:

```powershell
python -m pip install -r requirements.txt
```

The API listens on `API_HOST` and `API_PORT` (`0.0.0.0:8000` by default). In production,
keep credentials in the service environment or a root-readable environment file, and
run the existing `mikrotik-api` entry point behind the deployment's HTTPS reverse proxy.
The Oracle host must retain WireGuard address `10.20.20.1` and routes to both configured
router addresses.

## API

All router operations are scoped by a configured `{router_id}`:

```text
GET  /health
GET  /api/routers
GET  /api/routers/{router_id}/hotspot/users/{username}/status
POST /api/routers/{router_id}/hotspot/user-lookup
POST /api/routers/{router_id}/hotspot/users/{username}/devices/{session_id}/logout
```

Status and logout responses include `router_id` and `router_name`, making the selected
site explicit to clients. An unknown ID returns an error before RouterOS credentials are
loaded or a connection is attempted.

Each connected-device entry also includes `device_type`. Classification first uses the
DHCP lease `active-class-id`: Android values are shown as `Phone`, MSFT values as `PC`,
ChromeOS as `Chromebook`, and Linux values as `Linux device`. When the class ID is
missing (as with many Apple devices), recognizable DHCP hostnames such as iPhone, iPad,
and MacBook are used as a fallback; generic or hidden hostnames remain `Unknown`.

## Status page integration

The root/status page stores the selected router ID with the locked hotspot username and
device identifiers in HTTP-only cookies. Its JavaScript sends status, authenticated
voucher lookup, refresh, and device logout requests only to router-scoped API paths.
The voucher lookup dialog also requires the user to choose a configured site.

Configure each MikroTik hotspot status page to launch the shared backend with its fixed
router ID. For example:

```text
https://status.example.com/launch-status?router_id=flint-main&username=$(username)&ip=$(ip)&mac=$(mac)
https://status.example.com/launch-status?router_id=platinum&username=$(username)&ip=$(ip)&mac=$(mac)
```

`POST /launch-status` accepts the same fields. Calls that omit `router_id` default to
`flint-main` for compatibility with the original single-router launch link. An unconfigured
router ID is rejected.

## Project structure

```text
src/mikrotik/api.py       FastAPI routes and RouterOS client dependency
src/mikrotik/client.py    RouterOS operations and shared credential loading
src/mikrotik/pages.py     Status page, launch cookies, and browser API integration
src/mikrotik/routers.py   Server-side router allowlist and site metadata
tests/                    API, registry, client, and smoke tests
pyproject.toml            Project metadata, entry points, and tooling
```
