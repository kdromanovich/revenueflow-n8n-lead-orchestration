#!/usr/bin/env node

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, '..');
const workflow = JSON.parse(
  fs.readFileSync(path.join(root, 'workflows', 'revenueflow-ai-lead-qualification.json'), 'utf8'),
);
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const nodes = new Map(workflow.nodes.map((node) => [node.name, node]));
const staticData = {};

async function executeCode(name, inputJson, lookups = {}, variables = {}) {
  const node = nodes.get(name);
  assert(node, `Missing node: ${name}`);
  assert.equal(node.type, 'n8n-nodes-base.code', `${name} is not a Code node`);

  const inputItems = inputJson === undefined ? [] : [{ json: inputJson }];
  const $input = {
    first: () => inputItems[0],
    all: () => inputItems,
  };
  const $getWorkflowStaticData = () => staticData;
  const $ = (nodeName) => ({
    first: () => {
      assert(Object.hasOwn(lookups, nodeName), `Missing mocked lookup for ${nodeName}`);
      return { json: lookups[nodeName] };
    },
  });
  const fn = new AsyncFunction(
    '$input',
    '$vars',
    '$execution',
    '$getWorkflowStaticData',
    '$',
    node.parameters.jsCode,
  );
  const result = await fn($input, variables, { id: 'offline-demo' }, $getWorkflowStaticData, $);
  assert(Array.isArray(result) && result.length === 1, `${name} must return one item`);
  assert(result[0] && typeof result[0].json === 'object', `${name} returned an invalid item`);
  return result[0].json;
}

let data = await executeCode('Load Demo Lead');
data = await executeCode('Normalize Intake Envelope', data);
data = await executeCode('Runtime Configuration', data);
assert.equal(data.config.demo_mode, true, 'default must be demo mode');
data = await executeCode('Validate and Normalize Lead', data);
assert.equal(data.validation.valid, true, 'demo fixture must validate');
data = await executeCode('Create Idempotency Key', data);
assert.match(data.identity.fingerprint, /^lead_[0-9a-f]{8}$/);
data = await executeCode('Generate Demo Intelligence', data);
data = await executeCode('Calculate Deterministic Score', data);
assert.equal(data.scoring.total, 98);
assert.equal(data.scoring.tier, 'hot');
assert.equal(data.scoring.breakdown.ai_fit, 18);
data = await executeCode('Simulate HubSpot Upsert', data);
data = await executeCode('Prepare Personalized Outreach', data);
const preparedOutreach = data;
assert.match(data.outreach.body, /cal\.com\/example\/discovery/);
data = await executeCode('Simulate Email and Alert', data);
data = await executeCode('Record Metrics and Return Result', data);
assert.equal(data.success, true);
assert.equal(data.status, 'demo_completed');
assert.equal(data.crm.status, 'success');
assert.equal(data.delivery.email_status, 'simulated');
assert.equal(data.assessment.provider, 'deterministic_demo');

let invalid = {
  first_name: '',
  email: 'not-an-email',
  company: '',
  need: 'Too short',
  consent: false,
};
invalid = await executeCode('Normalize Intake Envelope', invalid);
invalid = await executeCode('Runtime Configuration', invalid);
invalid = await executeCode('Validate and Normalize Lead', invalid);
assert.equal(invalid.validation.valid, false);
assert.deepEqual(invalid.validation.errors, [
  'first_name is required',
  'email format is invalid',
  'company is required',
  'need must contain at least 20 characters',
  'consent must be true',
]);

const privateUrl = await executeCode('Prepare Safe Website URL', {
  lead: { website: 'http://127.0.0.1/admin' },
});
assert.equal(privateUrl.enrichment.safe, false);
const ipv6Url = await executeCode('Prepare Safe Website URL', {
  lead: { website: 'http://[::1]/admin' },
});
assert.equal(ipv6Url.enrichment.safe, false);
const publicUrl = await executeCode('Prepare Safe Website URL', {
  lead: { website: 'https://example.com/about' },
});
assert.equal(publicUrl.enrichment.safe, true);

const lookup = { 'Prepare Personalized Outreach': preparedOutreach };
const approved = await executeCode('Parse Approval Decision', { approvalStatus: 'approved' }, lookup);
assert.equal(approved.approval.approved, true);
assert.equal(approved.approval.raw_status, 'approved');
const rejected = await executeCode('Parse Approval Decision', { data: { approvalStatus: 'declined' } }, lookup);
assert.equal(rejected.approval.approved, false);
assert.equal(rejected.approval.raw_status, 'rejected');
const timedOut = await executeCode('Parse Approval Decision', {}, lookup);
assert.equal(timedOut.approval.approved, false);
assert.equal(timedOut.approval.raw_status, 'unrecognized_or_timed_out');

console.log('PASS: offline demo executed 11 production Code nodes without external calls');
console.log('PASS: valid HOT lead scored 98/100 and completed simulated CRM, approval, email, and alert path');
console.log('PASS: invalid intake, IPv4/IPv6 literal rejection, HTTPS URL acceptance, and three approval outcomes completed');
