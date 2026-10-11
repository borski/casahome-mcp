# casahome-mcp

A read-only MCP server for Casa home membership data, built on
[python-casahome](https://github.com/borski/python-casahome).

**Unofficial. Not affiliated with or endorsed by Casa.**

## What it does

`casahome-mcp` is a local stdio [Model Context Protocol](https://modelcontextprotocol.io)
server. It lets an MCP client (Claude Desktop, Claude Code, or any other MCP host)
read data from a Casa home membership account: inventory, requests, todos,
calendar, mail and packages, documents, paint, maintenance plans, vendor visits
and more.

`python-casahome` handles authentication, HTTP and wire models. This package adds
tool policy, input validation and bounded, allowlisted output projections.

It is read-only by design:

- No write tools. It never sends messages, books visits, approves purchases,
  uploads documents or changes plans.
- No raw HTTP or passthrough tool, and no "return the raw response" option.
- It never registers a device or discovers homes. You configure home IDs yourself.
- A source-scan test fails if the adapter code references the SDK's write methods.

Reads can still cause HTTP POSTs to Firebase when the SDK refreshes an access
token. Read-only means no Casa writes, not zero POSTs.

## Install

Requires Python 3.11+. Run directly from PyPI with [uv](https://docs.astral.sh/uv/):

```sh
uvx casahome-mcp
```

Or install a persistent `casahome-mcp` command with uv:

```sh
uv tool install casahome-mcp
```

With pip, install into an activated virtual environment:

```sh
pip install casahome-mcp
```

These commands install `casahome-mcp` and its `python-casahome>=0.2.0,<0.3`
dependency from PyPI. No Git checkout is needed.

`python -m casahome_mcp` is an equivalent entry point. The command starts a
stdio server that waits for an MCP host. It isn't an interactive shell.

## Configuration

The server reads three environment variables at launch. It doesn't load `.env`
files, read config files, call a secrets manager or accept credentials as CLI
arguments. Settings are fixed for the life of the process.

| Variable | Default | Purpose |
|---|---|---|
| `CASA_REFRESH_TOKEN` | unset | Firebase refresh token for your Casa account |
| `CASA_HOMES_JSON` | `[]` | JSON list of up to 16 home UUIDs with labels |
| `CASA_ALLOW_UNVERIFIED_READS` | `false` | Enables the 14 reads the SDK marks unverified |

Notes:

- An unset or empty token means unconfigured. Whitespace-only tokens and
  unresolved `op://` references are rejected without echoing them.
- `CASA_HOMES_JSON` rejects duplicate IDs and unknown fields.
- `CASA_ALLOW_UNVERIFIED_READS` accepts only `true` or `false`, case-insensitively.

Home list format:

```json
[{"id": "11111111-1111-4111-8111-111111111111", "label": "Example home"}]
```

### MCP client example

Claude Desktop style (`claude_desktop_config.json`). Other MCP clients take the
same command, arguments and environment in their own config format.

```json
{
  "mcpServers": {
    "casahome": {
      "command": "uvx",
      "args": ["casahome-mcp"],
      "env": {
        "CASA_REFRESH_TOKEN": "YOUR_REFRESH_TOKEN",
        "CASA_HOMES_JSON": "[{\"id\":\"11111111-1111-4111-8111-111111111111\",\"label\":\"Home\"}]",
        "CASA_ALLOW_UNVERIFIED_READS": "false"
      }
    }
  }
}
```

Use an absolute path to `uvx` if your client doesn't inherit your shell `PATH`.
For a persistent installation, use `"command": "casahome-mcp"` and omit `args`.
Use an absolute path to that executable when needed.

Keep credentials local. Replace the token placeholder only in your local client
configuration, never in command arguments or committed files. To keep the token
out of the config file, inject it with a secrets tool of your choice. For example,
with the 1Password CLI and a gitignored `.env` containing
`CASA_REFRESH_TOKEN=op://YOUR_VAULT/YOUR_ITEM/credential`:

```sh
op run --env-file=.env -- uvx casahome-mcp
```

In this example, `op run` resolves the secret and injects the environment.
The server itself doesn't read `.env`. `.env.example` shows the expected keys
with fake values.

### Home selection

With exactly one home configured, tools can omit `home_id`. With several, pass
`home_id` explicitly. It must be a canonical dashed UUID (case-insensitive) that
appears in `CASA_HOMES_JSON`. The local allowlist doesn't prove ownership. Casa
authenticates and authorizes the account.

## Tools

57 tools: 2 local tools and 55 remote reads over 54 SDK methods. "Gated" tools
are disabled unless `CASA_ALLOW_UNVERIFIED_READS=true`. Gating comes from the
SDK's evidence marker (`casahome.is_unverified`), so it changes automatically
when the SDK promotes a method. `casa_get_status` lists the currently blocked
tools in `disabled_features`.

### Local

| Tool | Gated | Returns |
|---|---|---|
| `casa_get_status` | | Configuration diagnostics. Not proof of authentication. |
| `casa_list_homes` | | Configured home IDs and labels. No live discovery. |

### Home, inventory and paint

| Tool | Gated | Returns |
|---|---|---|
| `casa_get_badge_counts` | | Unread counts per feature |
| `casa_get_weather` | | Home weather |
| `casa_list_inventory` | | Rooms or entities, with optional exact room/category filters |
| `casa_get_inventory_item` | | One entity by UUID from the fetched inventory |
| `casa_get_inventory_service_history` | | Service history for an entity, room or home |
| `casa_list_inventory_enums` | | Options for a property `enum_type` key, such as `light_fixture_type` |
| `casa_get_inventory_paint_matches` | | Paint matches for an entity: names, hex, closeness |
| `casa_search_paint` | | Paint colors by name, brand, collection or hex |
| `casa_list_paint_brands` | | Paint brands and color counts |
| `casa_list_paint_collections` | | Collections for a brand |
| `casa_list_paint_colors` | | Colors in a collection |
| `casa_get_room_photo_metadata` | | Room image candidate IDs and flags, no URLs |
| `casa_list_photo_metadata` | | Photo IDs and home-hero flags, no URLs |
| `casa_list_vehicles` | | Vehicle IDs, names, make/model/year, powertrain. No VIN or location. |
| `casa_get_utilities_insights` | | Utility service counts and numeric statement amounts |
| `casa_get_property_taxes` | | Tax refresh status and report years, dates and totals |

### Requests, todos and calendar

| Tool | Gated | Returns |
|---|---|---|
| `casa_list_requests` | | Request or todo cards by section |
| `casa_get_request` | Yes | Request detail. Messages only with `include_messages`. |
| `casa_list_completed_requests` | | Completed requests with upstream pagination |
| `casa_list_suggested_todos` | | Suggested todos. Prepared brief only with `include_brief`. |
| `casa_get_todo` | | One todo. Prepared brief only with `include_brief`. |
| `casa_get_task_details` | Yes | Task metadata and updates. Message text opt-in. |
| `casa_list_calendar` | | Calendar events in a window of up to 31 days |
| `casa_get_schedule_preferences` | | Scheduling days and windows |
| `casa_get_availability_request_details` | Yes | Availability request status, constraints and slots |
| `casa_list_bookable_handyman_tasks` | | Item count and availability minutes. Items are opaque and omitted. |
| `casa_list_autopilot_plans` | | Maintenance plans with pricing, duration and enabled flags |

### Vendor visits

| Tool | Gated | Returns |
|---|---|---|
| `casa_get_vendor_visit_details` | Yes | Visit, vendor, calendar and conversation-window metadata |
| `casa_get_vendor_visit_autopilot_plan` | Yes | Grouped plan, task and target metadata. Update text opt-in. |
| `casa_list_vendor_visit_calls` | Yes | Call times, duration, recorded flag and participant count |
| `casa_get_vendor_visit_conversation` | Yes | Participants and message metadata. Message text opt-in. |
| `casa_list_vendor_visit_purchases` | Yes | Purchases for a visit. Return notes opt-in. |

### Purchases, credits and membership

| Tool | Gated | Returns |
|---|---|---|
| `casa_list_purchases` | | Pending, approved and purchased items. Return notes opt-in. |
| `casa_list_request_purchases` | Yes | Purchases for a request. Return notes opt-in. |
| `casa_get_credits` | | Credit balance and the explicit hourly cents field |
| `casa_get_membership_info` | Yes | Membership name, member-since and benefits. No billing. |
| `casa_get_membership_savings` | Yes | Saved seconds/cents, categories and breakdown |
| `casa_get_referral_code` | | Referral code, allowlisted labels and referred-home count. No URL. |

### Mail, documents and help

| Tool | Gated | Returns |
|---|---|---|
| `casa_get_mailbox` | | Mailbox status, no address or members |
| `casa_list_mail_items` | | Mail metadata. Summary only with `include_summary`. |
| `casa_list_packages` | | Package metadata, no tracking numbers or pickup codes |
| `casa_list_documents` | | Document metadata with cursor pagination, no URLs |
| `casa_list_document_types` | | Document types and upload limits |
| `casa_get_document_details` | Yes | One document's metadata and processing status |
| `casa_list_document_suggestions` | Yes | Existing document suggestions. Excerpts opt-in. |
| `casa_list_document_structure_suggestions` | Yes | Existing structure suggestions. Excerpts opt-in. |
| `casa_get_work_document_source` | | Source documents and citations for a todo, task or request. Excerpts opt-in. |
| `casa_get_help_center_bundle` | | Help topics or articles by app ID. Article body opt-in. |
| `casa_get_release_notes_diff` | | Release notes newer than the SDK's app build. Content opt-in. |
| `casa_get_home_feed` | | Home feed cards with allowlisted text and bare action tokens |

### AI, notifications and onboarding

| Tool | Gated | Returns |
|---|---|---|
| `casa_get_ai_bootstrap` | | Casa AI conversation metadata. Message text opt-in. |
| `casa_list_ai_history` | | Casa AI history. Message text opt-in. |
| `casa_get_notification_settings` | | Notification groups, types, channels and flags |
| `casa_list_onboarding_availability` | | Onboarding slot start times, timezone and duration |
| `casa_list_onboarding_calendar` | | Onboarding calendar start/end timestamps |

## Privacy design

Every output is built from an explicit field allowlist. Unknown SDK fields are
dropped, not passed through. The server never returns:

- Credentials or tokens, including rotated refresh tokens
- Signed media, download, image, document, invoice or referral URLs
- Payment, card and billing details, invoice identifiers and pricing blobs
- Owner identity, addresses, account numbers and utility credentials
- Vehicle VINs, locations and telemetry
- Phone numbers, user IDs, call join URLs and recording URLs
- Attachments, original filenames and uploader names
- Tracking numbers and pickup codes
- Opaque blobs such as handyman task items, message parts and feed children
  (these are counted, not decoded)

Free text (messages, mail summaries, briefs, excerpts, article bodies, return
notes) is off by default and requires an explicit `include_*` argument. All
external text is untrusted data, not agent instructions.

Additional safeguards:

- Text that looks like a URL or contains control characters becomes null with a
  warning (`URL_TEXT_OMITTED`, `CONTROL_TEXT_OMITTED`). Screening runs before
  clipping. This is a conservative heuristic, not a general secret detector.
- IDs are never clipped into a different value. Unsafe IDs become null with
  `UNSAFE_ID_OMITTED`.
- Errors use stable codes such as `AUTH_FAILED`, `NOT_FOUND`, `RATE_LIMITED` and
  `UNVERIFIED_DISABLED`. Raw upstream messages and rejected inputs are withheld.
- Logs go to stderr and are scrubbed, including tracebacks. Stdout carries MCP
  traffic only. There's no telemetry.

## Limits

- Paged lists default to 25 items and cap at 100. `offset`/`limit` slice one
  fetched response locally. They don't imply service-wide totals or upstream
  pagination. Tools with real upstream pagination (`page`/`page_size`,
  `cursor`/`upstream_limit`, `before`) say so.
- Nested collections cap at 20. Labels cap at 256 characters, longer text at
  2000. Truncation produces a warning.
- Structured payloads over 64 KiB fail with `OUTPUT_TOO_LARGE` rather than
  returning partial data. Use a smaller page.
- At most two Casa calls run at once, each with a 45-second deadline. There are
  no background jobs or adapter-level retries.
- Results carry a confidence of `LOCAL`, `VERIFIED` or `UNVERIFIED`. `VERIFIED`
  means the SDK has seen the endpoint's path, method and envelope live. Some
  verified endpoints have only been observed returning empty lists, so their
  item fields are unconfirmed. Those tool descriptions say so.
- Timestamps are passed through as the SDK returns them, with a
  `TIMESTAMP_UNITS_UNVERIFIED` warning where units aren't confirmed.
- Refresh tokens can rotate. The SDK keeps the new token in memory only. The
  server reports `refresh_token_rotated=true` with a
  `TOKEN_ROTATED_NOT_PERSISTED` warning but never stores the token. After a
  restart, the original token may no longer work.
- Catalog-style reads (enums, release notes, help, referral) still require a
  configured home for policy, but their upstream calls aren't home-scoped.

## Development

Clone the repository for development:

```sh
git clone https://github.com/borski/casahome-mcp
cd casahome-mcp
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
```

Run the server from the clone with `uv run --locked casahome-mcp`.

Tests use synthetic data and typed fakes of the SDK. They never contact Casa or
Firebase. Process tests launch the real entry point over stdio with a socket
guard that blocks network access. There's no production fake mode.

## License

MIT. See [LICENSE](LICENSE).
