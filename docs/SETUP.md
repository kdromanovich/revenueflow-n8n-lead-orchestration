# Setup

## Prerequisites

- An n8n instance that supports the included node versions, n8n Variables, and Gmail **Send and Wait for Response**
- OpenRouter API key
- HubSpot private app token with contact read/write access
- Gmail OAuth2 credential
- Telegram bot credential and destination chat ID
- An externally reachable HTTPS n8n base URL for approval callback links

The official references are the n8n [workflow import guide](https://docs.n8n.io/workflows/export-import/), [Variables guide](https://docs.n8n.io/code/variables/), [Webhook node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/), [Gmail message operations](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/message-operations/), and HubSpot's current [CRM search](https://developers.hubspot.com/docs/api-reference/latest/crm/search-the-crm) and [contacts guide](https://developers.hubspot.com/docs/api-reference/latest/crm/objects/contacts/guide).

## 1. Import and run the demo

1. Import `workflows/revenueflow-ai-lead-qualification.json`.
2. Confirm the workflow is inactive.
3. Do not assign live credentials yet.
4. Run **Run Demo**.
5. Confirm the final node returns `status: demo_completed`, `score: 98`, and `tier: hot`.

Demo mode is the default even when no Variables are configured.

## 2. Configure n8n Variables

| Variable | Required live | Example / purpose |
| --- | --- | --- |
| `REVENUEFLOW_DEMO_MODE` | Yes | Set to `false` only after staged setup |
| `REVENUEFLOW_BOOKING_URL` | Yes | Scheduling URL included in outreach |
| `REVENUEFLOW_APPROVAL_EMAIL` | Yes | Manager who approves HOT messages |
| `REVENUEFLOW_TELEGRAM_CHAT_ID` | Yes | Sales destination for HOT alerts |
| `REVENUEFLOW_OPENROUTER_MODEL` | No | Defaults to `openai/gpt-5.1` |
| `REVENUEFLOW_BRAND_NAME` | No | Defaults to `Asterline Automation` |
| `REVENUEFLOW_SENDER_NAME` | No | Defaults to `Alex` |

The Runtime Configuration node refuses to start live processing when the booking URL, approval email, or Telegram chat ID is missing.

If your n8n plan or deployment does not expose Variables, replace only the non-secret settings in **Runtime Configuration**. Keep API tokens in credentials, never in Code nodes.

## 3. Create credentials

### OpenRouter

Create an **HTTP Header Auth** credential:

| Field | Value |
| --- | --- |
| Name | `Authorization` |
| Value | `Bearer <OPENROUTER_API_KEY>` |

Assign it to **OpenRouter: Analyze Lead**. The OpenRouter request uses this repository URL in `HTTP-Referer`; replace it with your application URL if needed.

### HubSpot

Create a HubSpot private app with the minimum contact scopes needed for search and write. Create a separate **HTTP Header Auth** credential:

| Field | Value |
| --- | --- |
| Name | `Authorization` |
| Value | `Bearer <HUBSPOT_PRIVATE_APP_TOKEN>` |

Assign the same credential to **HubSpot: Search Contact** and **HubSpot: Create or Update**.

### Gmail

Create or select a Gmail OAuth2 credential and assign it to:

- **Gmail: Request Approval**
- **Gmail: Send HOT Outreach**
- **Gmail: Send WARM Outreach**

Approval links resume an n8n execution. For self-hosted n8n, configure the HTTPS `WEBHOOK_URL` and reverse proxy correctly before testing. The approval wait is limited to 72 hours.

### Telegram

Create a Telegram API credential and assign it to **Telegram: Alert Sales**. Use a dedicated test chat first and obtain its ID through your controlled bot setup.

## 4. Stage the live path

1. Keep the workflow inactive and use test/sandbox accounts.
2. Replace the fictional sample with a consented internal test address.
3. Configure all Variables except `REVENUEFLOW_DEMO_MODE`.
4. Assign credentials and confirm their scopes.
5. Set `REVENUEFLOW_DEMO_MODE=false`.
6. Execute with a controlled payload from the editor.
7. Test website fallback, OpenRouter parsing, HubSpot search/upsert, approval callback, Gmail delivery, and Telegram status.
8. Test rejection and allow the approval to expire once in a non-production environment.
9. Return to demo mode if any expected state is missing.

## 5. Protect the webhook

The intake endpoint is externally reachable and must remain protected. Before activation:

- enforce HTTPS and a request-body size limit at the reverse proxy;
- add rate limiting and bot/honeypot/CAPTCHA controls at the form boundary;
- restrict accepted methods and content types;
- redact sensitive fields in execution logs according to your retention policy;
- add an n8n Error Workflow for operational alerting;
- keep the built-in consent validation and document its legal basis for your jurisdiction.

## 6. Activate

Activate the workflow only after the staged matrix passes. n8n exposes separate test and production webhook URLs; connect the production form only to the production URL.

The webhook acknowledges receipt immediately. Monitor execution status or add a separate status store if callers need asynchronous result retrieval.
