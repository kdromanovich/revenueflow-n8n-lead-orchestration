# Data contract

## Intake payload

The webhook accepts a JSON object directly in the request body. Unknown fields are ignored by the normalized lead model.

| Field | Type | Required | Normalization / rule |
| --- | --- | --- | --- |
| `first_name` | string | Yes | Alias: `firstName`; trimmed; max 80 characters |
| `last_name` | string | No | Alias: `lastName`; trimmed; max 80 characters |
| `email` | string | Yes | Lowercase; max 180; basic email format check |
| `phone` | string | No | Trimmed; max 60 |
| `company` | string | Yes | Alias: `company_name`; max 160 |
| `website` | string | No | Alias: `company_website`; max 300 |
| `company_description` | string | No | Alias: `companyDescription`; max 1,500 |
| `country` | string | No | Max 100 |
| `employees` | number | No | Alias: `company_size`; rounded; minimum 0 |
| `budget_usd` | number | No | Alias: `budget`; minimum 0 |
| `timeline_days` | number | No | Alias: `timeline`; rounded; minimum 0 |
| `need` | string | Yes | Aliases: `message`, `project_description`; 20–2,500 characters |
| `source` | string | No | Defaults to `website`; max 100 |
| `consent` | boolean-like | Yes | Accepts `true`, `1`, `yes`, or `on` |

Control characters are replaced with spaces and repeated whitespace is collapsed before downstream processing.

Example: [`sample-data/valid-hot-lead.json`](../sample-data/valid-hot-lead.json).

## Request metadata

The common intake node adds:

```json
{
  "request_meta": {
    "request_id": "req_<timestamp>_<random-suffix>",
    "received_at": "ISO-8601 timestamp",
    "received_via": "webhook | manual_demo"
  }
}
```

## Idempotency identity

The fingerprint is calculated from normalized `email`, lowercased `company`, and the first 240 characters of lowercased `need` using a compact 32-bit FNV-1a-style hash:

```text
lead_<8 lowercase hexadecimal characters>
```

The compact hash supports the included demo. For concurrent processing, store the identity in a database with an atomic unique constraint.

## Intelligence object

Both the model and deterministic fallback are normalized to:

| Field | Contract |
| --- | --- |
| `fit_score` | Integer clamped to `0..100` |
| `intent` | `research`, `purchase`, `partnership`, `support`, or `unknown` |
| `urgency` | `high`, `medium`, or `low` |
| `summary` | String, max 500 characters |
| `pain_points` | Up to 3 strings, each max 180 characters |
| `recommended_action` | String, max 500 characters |
| `email_subject` | Single line, max 160 characters |
| `email_body` | Plain text, max 2,500 characters |

`intelligence_meta.provider` is `deterministic_demo`, `openrouter`, or `deterministic_fallback`. `fallback_used` makes the decision source explicit.

## Score calculation

| Component | Points |
| --- | --- |
| Budget | `30` at ≥ $10,000; `24` at ≥ $5,000; `16` at ≥ $2,000; `8` when positive; otherwise `0` |
| Timeline | `20` at 1–14 days; `16` at 15–30; `10` at 31–60; `5` above 60; otherwise `0` |
| Company size | `15` at ≥ 50 employees; `12` at ≥ 10; `7` when positive; otherwise `3` |
| Business email | `3` for an enumerated free-mail domain; otherwise `10` |
| AI fit | Rounded `fit_score × 0.2`, clamped to `0..20` |
| Completeness | `5` when at least 3 of phone, website, country, description exist; otherwise `3` |

Default routing thresholds are HOT ≥ 75, WARM ≥ 50, and COLD below 50.

## HubSpot property mapping

| Workflow value | HubSpot property |
| --- | --- |
| `lead.email` | `email` |
| `lead.first_name` | `firstname` |
| `lead.last_name` | `lastname` |
| `lead.company` | `company` |
| `lead.website` | `website` |
| `lead.phone` | `phone` |
| Constant | `lifecyclestage = lead` |
| HOT / WARM / COLD | `hs_lead_status = OPEN / NEW / UNQUALIFIED` |

The workflow searches contacts by email at `POST /crm/objects/2026-03/contacts/search`. If it finds a match, it sends `PATCH /crm/objects/2026-03/contacts/{id}`; otherwise it sends `POST /crm/objects/2026-03/contacts`.

## Final success result

```json
{
  "success": true,
  "status": "demo_completed",
  "request_id": "req_...",
  "lead_id": "lead_1234abcd",
  "lead": {
    "name": "Maya Chen",
    "company": "Asterline Logistics",
    "email": "maya.chen@asterline.example"
  },
  "score": 98,
  "tier": "hot",
  "priority": "P1",
  "score_breakdown": {},
  "assessment": {},
  "crm": {},
  "approval": {},
  "delivery": {},
  "processed_at": "ISO-8601 timestamp"
}
```

## Terminal statuses

| Status | Meaning |
| --- | --- |
| `rejected_invalid_input` | Required or consent rule failed; no external calls |
| `ignored_duplicate` | Fingerprint is already processing or recently completed |
| `rejected_by_human` | HOT outreach was explicitly rejected or approval failed closed |
| `demo_completed` | Credential-free simulated path completed |
| `completed` | Live routing and required actions completed |

Because the webhook uses immediate acknowledgement, these objects are workflow execution outputs rather than synchronous HTTP response bodies.
