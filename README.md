# casahome-mcp

Local stdio MCP server for the unofficial Casa home-membership SDK.

`python-casahome` owns authentication, HTTP and wire models. This separate
adapter owns tool policy, input validation and bounded output projections.
It doesn't discover homes, register devices, send messages or expose write tools.

## Current status

Implemented and tested with synthetic data, including real MCP stdio subprocesses.
No live Casa or Firebase calls have been used to validate this adapter.
Most SDK read contracts remain unverified, and account activation blocks further
traffic capture. Experimental reads are **disabled by default**.

The default server exposes all tools for discovery. Local status and home listing
work without credentials. Feature tools return a policy error until the operator
enables experimental reads and supplies configuration. A successful synthetic
test or a parsable upstream response doesn't verify a wire contract.

## Local setup

Requirements: Python 3.11+, uv, and a sibling `../python-casahome` checkout.
The local SDK is an editable uv source. Its working-tree changes are used.
There's no assumption that either package has been published to PyPI.

```sh
uv sync --locked
uv run --locked casahome-mcp
```

Equivalent module entry point:

```sh
uv run --locked python -m casahome_mcp
```

These commands start a stdio server that waits for an MCP host. They aren't an
interactive shell. Use an absolute interpreter/entry-point path when a host's
working directory differs. Runtime dependencies are locked, including official
`mcp==2.3.0`. Both automatic and legacy MCP client modes are tested. OpenCode
configuration hasn't been changed or exercised against a live installation.

This checkout is a development installation, not a portable `uvx` release.
Before release, replace the sibling source with an approved published SDK version
or immutable private Git revision. Don't publish the current development setup.

## Configuration

The process reads only these three settings at launch. It doesn't load `.env`,
invoke 1Password, read configuration files or accept credential CLI arguments.

| Variable | Default | Purpose |
|---|---|---|
| `CASA_REFRESH_TOKEN` | Unconfigured | Firebase refresh credential injected externally |
| `CASA_HOMES_JSON` | `[]` | Up to 16 operator-configured home UUIDs and labels |
| `CASA_ALLOW_UNVERIFIED_READS` | `false` | Operator opt-in to unverified feature reads |

Unset and empty tokens are unconfigured. Whitespace-only tokens and unresolved
`op://` references are rejected without echoing them. The gate accepts only
`true` or `false`, case-insensitively. Home configuration rejects duplicates and
unknown fields. Settings remain immutable for the process lifetime.

Synthetic example for local diagnostics:

```sh
export CASA_HOMES_JSON='[{"id":"11111111-1111-4111-8111-111111111111","label":"Example home"}]'
uv run --locked casahome-mcp
```

Replace the example UUID with an authorized home ID before enabling feature reads.
Home IDs are configured deliberately. Bootstrap registers a device with Casa and
is never called by this server, including for startup or home discovery.

Optional external 1Password launch:

1. Configure the CLI using an exported service-account token outside this repo.
2. Keep a gitignored `.env` with a credential reference such as
   `CASA_REFRESH_TOKEN=op://YOUR_VAULT/YOUR_ITEM/credential` and the other settings.
3. Run the following without putting credentials in arguments:

```sh
op run --env-file=.env -- uv run --locked casahome-mcp
```

The operator handles secret injection. The adapter never runs `op` or updates its
vault. `.env.example` contains fake data and an empty token only.

When exactly one home is configured, feature tools can omit `home_id`. Multiple
homes require explicit selection. An explicit tool home ID must be a canonical
dashed UUID, case-insensitive, and must match the configured allowlist. Request
IDs are limited to ASCII letters, digits, underscores and hyphens, 1 to 128
characters. The local allowlist doesn't establish ownership. Casa authenticates
and authorizes the account.

## Tools

| Tool | Behavior |
|---|---|
| `casa_get_status` | Configuration diagnostics, never authentication proof |
| `casa_list_homes` | Configured IDs and labels only, no live discovery |
| `casa_get_badge_counts` | Unread counts per feature |
| `casa_get_weather` | Home weather fields |
| `casa_list_inventory` | Room or inventory-entity summaries |
| `casa_list_requests` | Request or todo cards with section membership |
| `casa_get_request` | Request summary, messages only when explicitly requested |
| `casa_list_calendar` | Raw calendar timestamps in a bounded requested window |
| `casa_get_credits` | Credit summary and the explicit hourly cents field |
| `casa_get_mailbox` | Mailbox status metadata |
| `casa_list_mail_items` | Mail metadata, summary text only when explicitly requested |
| `casa_list_packages` | Package metadata without tracking numbers or pickup codes |

All ten remote tools use explicit SDK methods. The experimental gate is a process
setting, never a tool argument. Denied calls don't reach the SDK. No tokens, raw
HTTP tools, writes, signed-download fetching or hidden mutation tools are exposed.
Reads can refresh Firebase tokens through POST requests, so read-oriented doesn't
mean zero HTTP POSTs. Unverified GET endpoints aren't guaranteed free of upstream
side effects.

## Data and bounds

Results carry source, confidence, selected home, retrieval timestamp, warnings
and typed data. Configuration data is marked `LOCAL`. Experimental upstream
results remain `UNVERIFIED`. Retrieval time isn't upstream observation time.

Explicit field projections exclude unknown SDK fields, Matterport passwords,
payment records, attachments, arbitrary summary objects and signed media URLs.
Request messages require `include_messages=true`. Mail summaries require
`include_summary=true`. These texts are untrusted data, never agent instructions.
There's no raw-data escape hatch.

List tools use `offset` and `limit` for **local slicing of one fetched response**.
Limits range from 1 to 100, default 25. Offsets are nonnegative. Metadata includes
`total_in_response`, `has_more_in_response` and `next_offset`. It doesn't claim
service-wide totals or upstream pagination. Every page refetches, so changing
upstream collections can shift between calls. Empty collections carry
`UPSTREAM_COMPLETENESS_UNKNOWN`.

Titles/labels are capped at 256 characters, narrative text at 2000, and nested ID
lists at 100, with explicit truncation warnings. Identity strings aren't clipped.
Badge keys aren't truncated or merged. Projected structured payloads above 64 KiB
produce `OUTPUT_TOO_LARGE`. Reduce the page size rather than requesting raw data.

Calendar inputs must include seconds and a timezone, for example
`2026-01-01T00:00:00Z`. The window must be positive and at most 31 days.
The SDK assumes Unix seconds when converting input dates. Upstream units and
interval semantics aren't verified. Raw result timestamps are preserved, with
`TIMESTAMP_UNITS_UNVERIFIED` warnings. Credits are returned without inventing
balance units or currency.

## Lifecycle and failure behavior

Import, startup, tool discovery, status and configured-home listing make no
Casa/Firebase requests. One SDK session and auth object are shared per process.
At most two feature calls run concurrently. Each has a 45-second outer deadline,
including queue wait and authentication. Cancellation and cleanup are tested.
There are no polling jobs or adapter retry loops. The SDK's own single 401
refresh/retry behavior remains in place.

Refresh tokens can rotate. The SDK keeps the new value in memory and the adapter
sets `refresh_token_rotated=true` plus `TOKEN_ROTATED_NOT_PERSISTED`. It never
returns, prints, writes or saves the credential. Restarting with the original
injected credential may fail. Secure durable rotation storage must be settled
before unattended deployment. Recover by securely reprovisioning a current
credential through the established login process.

Failures are MCP tool errors with stable prefixes such as `UNVERIFIED_DISABLED`,
`AUTH_FAILED`, `SCHEMA_MISMATCH` and `RATE_LIMITED`. Raw upstream messages and
validation inputs are withheld. The documented MCP middleware refusal hook
checks input before default SDK error formatting. That hook is provisional:
update the SDK only with the compatibility and privacy tests passing.

Logs go to stderr. Library diagnostics are deliberately scrubbed, including
tracebacks that might contain response bodies. Stdout contains MCP traffic only.
No telemetry exporter is configured.

## Development

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv build
```

Tests use synthetic models and typed fake SDK calls. Process tests load the real
entry point in a sanitized environment with a test-only socket egress guard.
Negative controls prove that guard blocks connection attempts. They test both
MCP client modes, EOF shutdown, stdout purity, token-safe errors, field omissions,
policy precedence, pagination and concurrency. No production fake mode exists.

Live traffic verification, OpenCode wiring, release, remote deployment and write
support are separate steps. None is enabled by this implementation.
