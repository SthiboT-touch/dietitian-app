/** Isolated frontend error/health helper tests. No real API or client data. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');

async function main() {
  const js = fs.readFileSync(path.join(__dirname, '../front-end/app.js'), 'utf8');
  const start = js.indexOf('async function request(url, options = {})');
  const end = js.indexOf('// Medical documents are protected API resources');
  assert(start >= 0 && end > start);
  const content = js.slice(start, end);
  const indicator = { dataset: {} };
  const statusText = { textContent: '' };
  let fakeFetch = async () => new Response(JSON.stringify({ status: 'online', database: 'online' }));
  const context = {
    Headers, FormData, Response, Error,
    sessionStorage: { getItem: () => null },
    adminTokenKey: 'a', dietitianTokenKey: 'd', clientTokenKey: 'c', staffTokenKey: 's',
    document: {
      hidden: false,
      querySelector: selector => ({ '#connectionStatus': indicator, '#connectionStatusText': statusText, '#workspace': { hidden: false } })[selector],
      addEventListener: () => {},
    },
    window: { addEventListener: () => {} },
    fetch: (...args) => fakeFetch(...args),
  };
  vm.createContext(context);
  vm.runInContext(content, context);

  fakeFetch = async () => new Response(JSON.stringify({ detail: 'Service unavailable', request_id: 'ref-a' }), { status: 500, headers: { 'X-Request-ID': 'ref-a' } });
  await assert.rejects(() => context.request('/api/v1/example'), /Service unavailable Reference: ref-a/);

  fakeFetch = async () => new Response(JSON.stringify({ detail: 'Not authorized' }), { status: 403 });
  await assert.rejects(() => context.request('/api/v1/example'), /^Error: Not authorized$/);

  fakeFetch = async () => { throw new Error('secret-internal-fetch-error'); };
  await assert.rejects(() => context.request('/api/v1/example'), /Cannot reach NutriCare/);
  assert.equal(indicator.dataset.state, 'offline');

  fakeFetch = async () => new Response(JSON.stringify({ status: 'degraded', database: 'offline' }), { status: 200 });
  await context.refreshConnectionStatus();
  assert.equal(statusText.textContent, 'Database unavailable');
  assert.equal(indicator.dataset.state, 'degraded');

  fakeFetch = async () => new Response(JSON.stringify({ status: 'online', database: 'online' }), { status: 200 });
  await context.refreshConnectionStatus();
  assert.equal(statusText.textContent, 'Workspace connected');
  assert.equal(indicator.dataset.state, 'online');
  console.log('Frontend request errors, support references, and health status: PASS');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
