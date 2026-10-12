# casahome-mcp

A local MCP server for Casa home membership reads and explicitly confirmed actions, built on
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

Reads remain isolated from the action surface:

- Actions are disabled by default. Named prepare tools never mutate the account.
  A separate single-use execute tool requires specific user approval first.
- No booking, billing, purchases or mailbox claims.
- Writes the SDK still marks unverified need a second operator flag,
  `CASA_ALLOW_UNVERIFIED_ACTIONS`, and their previews say so.
- No raw HTTP or passthrough tool, and no "return the raw response" option.
- It never registers a device or discovers homes. You configure home IDs yourself.
- Source scans forbid SDK writes in read modules. Action invocations have an exact
  allowlist and never expose generic paths, URLs or HTTP.

Reads can still cause HTTP POSTs to Firebase when the SDK refreshes an access
token. Read tools don't perform Casa writes.

## Install

### TEMPDEV release blocker

This checkout is **0.2.0, local only**. It requires `python-casahome>=0.3,<0.4`.
SDK 0.3 isn't published to PyPI yet. `[tool.uv.sources]` temporarily selects the
editable sibling `../python-casahome`. The lockfile records that local dependency.
Don't tag, publish or recommend this development version as a PyPI install.
Before release, publish/review SDK 0.3 separately, remove the temporary source,
relock against the published SDK and rerun the full offline validation suite.

Requires Python 3.11+. Run this checkout with:

```sh
uv run --locked casahome-mcp
```

Previously published versions can still be installed from PyPI with `uvx`.
They don't provide the action tools described here.

`python -m casahome_mcp` is an equivalent entry point. The command starts a
stdio server that waits for an MCP host. It isn't an interactive shell.

## Configuration

The server reads seven environment variables at launch. It doesn't load `.env`
files, read config files, call a secrets manager or accept credentials as CLI
arguments. Settings are fixed for the life of the process.

| Variable | Default | Purpose |
|---|---|---|
| `CASA_REFRESH_TOKEN` | unset | Firebase refresh token for your Casa account |
| `CASA_HOMES_JSON` | `[]` | JSON list of up to 16 home UUIDs with labels |
| `CASA_ALLOW_UNVERIFIED_READS` | `false` | Enables reads the SDK still marks unverified |
| `CASA_ALLOW_ACTIONS` | `false` | Allows household action preparation and execution |
| `CASA_ALLOW_MESSAGES` | `false` | Additionally allows Casa AI and request-thread text sends |
| `CASA_ALLOW_UPLOADS` | `false` | Additionally allows explicit local file snapshots and uploads |
| `CASA_ALLOW_UNVERIFIED_ACTIONS` | `false` | Additionally allows prepares whose SDK write is still marked unverified |

Notes:

- An unset or empty token means unconfigured. Whitespace-only tokens and
  unresolved `op://` references are rejected without echoing them.
- `CASA_HOMES_JSON` rejects duplicate IDs and unknown fields.
- All flags accept only `true` or `false`, case-insensitively.
- Messages, uploads and unverified actions also require `CASA_ALLOW_ACTIONS=true`.
  Setting only their specialized flag doesn't authorize them. Household todo creation and concierge
  handoff use ACTIONS. They aren't AI/request-thread message sends.
- Flags are operator policy, not authorization from a user to perform an action.

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

102 tools: 57 read/local tools plus 43 action prepares, execute and cancel.
55 remote reads use 54 SDK methods. "Gated" read tools
are disabled unless `CASA_ALLOW_UNVERIFIED_READS=true`. Gating comes from the
SDK's evidence marker (`casahome.is_unverified`), so it changes automatically
when the SDK promotes a method. `casa_get_status` lists the tools currently blocked
by either unverified gate (reads and actions) in `disabled_features`.

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
| `casa_get_request` | | Request detail. Messages only with `include_messages`. |
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
| `casa_list_request_purchases` | | Purchases for a request. Return notes opt-in. |
| `casa_get_credits` | | Credit balance and the explicit hourly cents field |
| `casa_get_membership_info` | | Membership name, member-since and benefits. No billing. |
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
| `casa_get_document_details` | | One document's metadata and processing status |
| `casa_list_document_suggestions` | | Existing suggestions. Optional `view`, default `all`. No other view values. |
| `casa_list_document_structure_suggestions` | | Existing structure suggestions and guard values. Excerpts opt-in. |
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

## Preview-first actions

The following prepares use only the named, verified SDK method variants.
They never perform a Casa write:

| Tool | Scope |
|---|---|
| `casa_prepare_move_entity_to_room` | Move an inventory UUID to a room UUID |
| `casa_prepare_rate_ai_message` | `good` or `bad`, no clear variant |
| `casa_prepare_respond_to_suggested_todo` | Required `decision="accept"` only |
| `casa_prepare_send_todo_to_concierge` | Concierge destination only |
| `casa_prepare_answer_todo_question` | Single/multi-select answer, `skip=false` only |
| `casa_prepare_submit_todo_question_round` | Explicit single/multi-select round answers |
| `casa_prepare_update_autopilot_plan` | `every_quarter`, explicit enabled/date, empty association map |
| `casa_prepare_update_notification_settings` | Explicit notification type and `push` pairs |
| `casa_prepare_send_ai_message` | Text only, additionally requires MESSAGES |
| `casa_prepare_send_request_message` | Member-role text only, additionally requires MESSAGES |
| `casa_prepare_create_todo_result` | Text-only todo, preserves support-confirmation flag |
| `casa_prepare_upload_document` | One explicit file snapshot, additionally requires UPLOADS |
| `casa_prepare_delete_todo` | Permanent deletion, no related-work cleanup |
| `casa_prepare_update_entity_model` | Nonblank model name with empty props only |
| `casa_prepare_respond_to_document_structure_suggestion` | Required `accepted` decision and exact `expected_values` |
| `casa_prepare_add_mailbox_recipient` | Explicit first and last names only, each 1 to 256 characters. No business/kind/primary fields. |
| `casa_prepare_update_mailbox_auto_archive` | Required `mailbox_auto_archive_days`, exactly integer `30` or explicit `null` only |

Both mailbox prepares require ACTIONS only. Recipient previews preserve the exact
first and last names and warn that adding a recipient may change account mail
handling. Auto-archive previews preserve the nullable field exactly and warn that
retention and disposal behavior is unverified. Neither `30` nor `null` guarantees
no effect. Execution returns status only, never recipient names, kind or addresses.

### Unverified-contract actions

These prepares call SDK writes reconstructed from the app. Each requires
`CASA_ALLOW_ACTIONS=true`. Every one whose SDK method carries the unverified marker
(`casahome.is_unverified`) also requires `CASA_ALLOW_UNVERIFIED_ACTIONS=true`, at
both prepare and execute. Their previews carry `contract_warning`:
`UNVERIFIED_CONTRACT: reconstructed from the app, not yet confirmed against Casa.
May fail or behave differently.` Gate, description and warning all follow the SDK
marker, so a promoted method automatically needs ACTIONS only.

| Tool | Scope |
|---|---|
| `casa_prepare_update_todo` | Title, prepared brief or emoji. At least one. No attachments |
| `casa_prepare_reject_suggested_todo` | Optional `dismissed` or `already_handled` reason |
| `casa_prepare_confirm_todo_support` | Explicit `is_support_question` Boolean |
| `casa_prepare_retry_todo` | Bodyless retry of todo preparation |
| `casa_prepare_reorder_todo_section` | `ready_for_scheduling` or `send_to_concierge`, revision guard, 1 to 100 IDs |
| `casa_prepare_update_document` | Name, type slug, date or explicit `clear_document_date` |
| `casa_prepare_analyze_document` | Explicit `reanalyze` Boolean |
| `casa_prepare_organize_document` | Bodyless organization start |
| `casa_prepare_update_schedule_preferences` | Both lists required, days 0 to 7 (at most 7), window IDs |
| `casa_prepare_update_availability_slots` | Up to 100 integer windows, units unknown |
| `casa_prepare_cancel_vendor_visit` | Warns of possible cancellation fees. Not undoable |
| `casa_prepare_remove_mailbox_recipient` | One recipient ID |
| `casa_prepare_mark_mail_item_read` / `_unread` | One mail item ID |
| `casa_prepare_set_mail_item_archived` | Explicit `archived` Boolean. Archive isn't shredding |
| `casa_prepare_validate_package_tracking_number` | Execution returns only `tracking_number_valid` and safe `carrier_ids` |
| `casa_prepare_add_tracked_package` | Carrier ID, tracking number, name, `inbound`/`outbound`/`unknown` |
| `casa_prepare_update_package` | Archive, deleted, name or direction. `deleted=true` previews a deletion warning |
| `casa_prepare_requeue_package_pickup` | One package ID |
| `casa_prepare_set_package_auto_archive` | Required key, 1 to 365 (local policy) or `null` |
| `casa_prepare_create_inventory_entity` | Room UUID only. Body home always equals the selected home |
| `casa_prepare_create_inventory_lighting` | Room UUID, fixture type ID, bulb kind slug, optional bulb type ID |
| `casa_prepare_create_paint_from_library` | Integer library color ID and 1 to 100 room UUIDs |
| `casa_prepare_update_entity_properties` | Up to 50 props, each exactly one of `value`, `enum_id` or `multi_enums` |
| `casa_prepare_clear_ai_message_rating` | One AI message ID. The unknown response is discarded |
| `casa_prepare_update_access_preferences` | Verified SDK contract, ACTIONS only. All four fields required, each may be `null` |

No image upload IDs or attachments are accepted, because no tool can create those
uploads. Not exposed: `create_package_pickup_item` (needs an official package-image
upload receipt the SDK can't obtain), `claim_mailbox` (one-time account action),
`save_and_publish_entity`, `materialize_todo` and `create_todo` (same verified wire
contracts as existing prepares) and the internal document-upload steps.

1. Call the named prepare tool with explicit parameters.
2. Show the user the exact preview, including its home, targets, full content and risks.
3. Obtain the user's specific approval for that action. Implementation, flags and
   possession of a token aren't proof of human consent.
4. Call `casa_execute_action(confirmation_token, confirmed=true)` once.
   `confirmed=false` makes zero SDK calls and doesn't consume the token.

`casa_cancel_action(confirmation_token)` consumes a preview locally, releasing its
snapshot. Tokens are random, memory-only and expire after five minutes. They bind
the selected home, named operation and validated immutable payload. Execution
rechecks home, flags and authentication configuration. It atomically consumes the
token before any await or SDK call. Concurrent or repeated execution can't send twice.
Shutdown clears all pending previews.

SDK failures and timeouts return `outcome="UNKNOWN"`. A write or an earlier upload
step may already have happened. The token stays consumed. Never automatically retry,
prepare a replacement or perform follow-up actions. Read the relevant resource to
reconcile an uncertain outcome. Invalid, expired, cancelled and replayed tokens use
one private error. Outputs contain status only, not raw SDK models or response text.

Examples of prepare inputs. None authorizes execution by itself:

```json
{"todo_id": "todo-example"}
```

Use with `casa_prepare_send_todo_to_concierge`, then show its exact preview and ask
for approval. `casa_cancel_action` can discard it instead.

```json
{"request_id": "request-example", "content": "Please check the kitchen tap.\nIt still drips."}
```

Use with `casa_prepare_send_request_message`. Only named content fields allow
multiline text. Invisible controls and unknown fields remain forbidden.

```json
{"file_path": "/explicit/path/report.pdf", "filename": "report.pdf", "mimetype": "application/pdf", "find_todos": false}
```

Use with `casa_prepare_upload_document`. Paths can be anywhere the process can
read. No folder restriction, glob, directory scan or path-based execute is exposed.
Symlinks to regular files are allowed. Nonblocking open plus descriptor `fstat`
rejects FIFOs, devices and directories before reading. Bytes are snapshotted once,
bounded to 25 MiB and the Casa document-type/size policy fetched before writes.
The preview includes basename, MIME type, size, SHA-256, `find_todos` and the risk
of document creation and suggested todos. Source bytes are never returned or logged.
Execution passes immutable bytes to SDK `upload_document`, never rereads the path,
and never accepts a storage URL. The SDK restricts storage uploads to its supported
Google Storage host. Partial steps aren't automatically undone.

At most 16 previews and 64 MiB of pending upload snapshots are retained. Expired
previews are purged before allocation. Cancellation and shutdown release snapshots.
Plan updates can affect paid future services. Empty association-map preservation
semantics remain unverified. Other cadences, notification channels, question skipping
and attachments aren't exposed.

## Privacy design

Every output is built from an explicit field allowlist. Unknown SDK fields are
dropped, not passed through. The server never returns:

- Credentials, including rotated refresh tokens. Local action confirmation tokens
  are intentionally returned by prepare tools only.
- Signed media, download, image, document, invoice or referral URLs
- Payment, card and billing details, invoice identifiers and pricing blobs
- Owner identity, addresses, account numbers and utility credentials
- Vehicle VINs, locations and telemetry
- Phone numbers, user IDs, call join URLs and recording URLs
- Attachments and uploader names. Read tools omit original filenames. Upload
  previews intentionally include the chosen basename, never the local source path.
- Tracking numbers and pickup codes
- Opaque blobs such as handyman task items, unknown message parts and feed children.
  Opted-in AI parts expose only text and `data-todo` type, todo ID, title and status.

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
