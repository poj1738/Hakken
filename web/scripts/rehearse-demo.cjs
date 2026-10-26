// Demo rehearsal: walks the docs/DEMO_SCRIPT.md click path against the API in
// SAMPLE_MODE, screenshots every scene and prints what each one showed.
//
// Start from a fresh server (it remembers identity decisions and feedback):
//   SAMPLE_MODE=true STATE_DIR=$(mktemp -d) python3 run.py serve          # repo root
//   VITE_API_MODE=live VITE_API_URL=http://localhost:8000 npx vite --port 5174   # in web/
// Then, in web/ (Playwright is not a project dependency):
//   npm i --no-save playwright && npx playwright install chromium
//   node scripts/rehearse-demo.cjs /tmp/demo-shots
// UI=<url> overrides http://localhost:5174/. A rehearsal aid only: these are
// sample-mode screens, never output_examples/.
const { chromium } = require('playwright');
const OUT = process.argv[2];
const UI = process.env.UI || 'http://localhost:5174/';
// Settled: nothing spinning, and either a result section or the identity review is on screen.
const settle = (p) =>
  p.waitForFunction(() => !document.querySelector('.spinner') && (document.querySelector('[role="tabpanel"] .finding, [role="tabpanel"] .sec-empty') || document.querySelector('.identity')), null, { timeout: 180000 });
// After "Same patient" the run resumes: wait for the review to go and the result to arrive.
const settleResumed = (p) =>
  p.waitForFunction(() => !document.querySelector('.identity') && !document.querySelector('.spinner') && document.querySelector('[role="tabpanel"] .finding, [role="tabpanel"] .sec-empty'), null, { timeout: 180000 });
const notes = [];
const note = (scene, s) => notes.push(`[${scene}] ${s}`);
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('response', (r) => r.status() >= 400 && errs.push(`${r.status()} ${r.request().method()} ${r.url()}`));
  const shot = (n) => p.screenshot({ path: `${OUT}/${n}.png`, fullPage: true });
  const run = async (mrn) => { await p.selectOption('#patient', mrn); const t = Date.now(); await p.click('.run-btn'); await settle(p); return ((Date.now() - t) / 1000).toFixed(1); };
  // Sections are the left rail's links (role="tab"; the name includes its count).
  const tab = (name) => p.getByRole('tab', { name }).click();

  await p.goto(UI); await p.waitForSelector('#patient:not([disabled])');
  note('0', `header: ${(await p.locator('.hd-right').innerText()).replace(/\n/g, ' | ')}`);
  note('0', `steps: ${(await p.locator('.steps').innerText()).replace(/\n/g, ' ')}; why: ${(await p.locator('.why-line').innerText()).slice(0, 80)}…`);
  await shot('scene0-landing');

  // Scene 1: identity (MRN0000015)
  note('1', `run settled in ${await run('MRN0000015')} s`);
  note('1', `identity card: ${await p.locator('.identity').count()} | match: ${await p.locator('.identity .match').allInnerTexts()}`);
  note('1', `withheld reason: ${(await p.locator('.identity .guard').first().innerText()).slice(0, 160)}`);
  await shot('scene1a-identity-review');
  await p.locator('.id-table').getByRole('button', { name: 'Same patient' }).first().click();
  await settleResumed(p);
  note('1', `after confirm: silos ${(await p.locator('.silo').allInnerTexts()).map((s) => s.replace(/\n/g, ' ')).join(' / ')}`);
  note('1', `hub: ${(await p.locator('.hub').innerText()).replace(/\n/g, ' ')}; findings: ${(await p.locator('.finding-title h3').allInnerTexts()).join(', ')}`);
  note('1', `powered by: ${(await p.locator('.pipe').innerText()).replace(/\n/g, ' ')}`);
  note('1', `"Verify first" pills: ${await p.locator('.pill-verify').count()}`);
  await shot('scene1b-confirmed-discrepancies');
  // The Meterless engines show as tags on the processing-log steps.
  await tab('Processing log');
  note('1', `engine tags in the processing log: ${[...new Set(await p.locator('.tag-engine').allInnerTexts())].join(', ') || 'none'}`);
  await p.locator('[role="tabpanel"]').screenshot({ path: `${OUT}/scene1c-log-engines.png` });

  // Scene 2: the grid (MRN0000089)
  note('2', `run settled in ${await run('MRN0000089')} s`);
  note('2', `findings: ${(await p.locator('.finding-title').allInnerTexts()).map((s) => s.replace(/\n/g, ' ')).join(' || ')}`);
  // Evidence lives behind "More" on each finding.
  const first = p.locator('.finding').first();
  await first.getByRole('button', { name: 'More' }).click();
  note('2', `first finding's records: ${(await first.locator('.chip').allInnerTexts()).join(', ')}`);
  await shot('scene2a-discrepancies');
  await first.getByRole('button', { name: 'Less' }).click();
  await tab('Medication history');
  const rows = await p.locator('.row:not(.row-head)').count();
  const noRow = await p.locator('.gcell .no-row').count();
  const listed = await p.locator('.gcell .c-listed, .gcell .c-conflict').count();
  note('2', `grid rows ${rows}; listed/disagree cells ${listed}; cells with no cited record ${noRow}; unknown cells ${await p.locator('.gcell .c-unknown').count()}`);
  // The cell DEMO_SCRIPT.md scene 2 clicks: Dapagliflozin, Patient interview (columns: chart, GP, pharmacy, interview).
  const cited = p.locator('.row', { hasText: 'Dapagliflozin' }).locator('.gcell').nth(3);
  if (await cited.locator('.no-row').count()) note('2', 'Dapagliflozin interview cell has NO cited record: provenance cannot be shown');
  await cited.click(); await p.mouse.move(0, 0);
  note('2', `provenance panel: ${(await p.locator('.insp').innerText()).replace(/\n/g, ' | ').slice(0, 220)}`);
  await shot('scene2b-medication-history');
  await tab('Actions');
  note('2', `actions: ${await p.locator('.action').count()}`);
  await shot('scene2c-actions');

  // Scene 3: learning pair (MRN0000003 -> MRN0000007)
  note('3', `P0003 run settled in ${await run('MRN0000003')} s`);
  await tab('Medication history');
  const cand = p.locator('.row', { hasText: 'Candesartan' });
  note('3', `candesartan reconciled: ${(await cand.locator('.recon').innerText()).replace(/\n/g, ' | ')}`);
  await cand.locator('.gcell').nth(1).click(); await p.mouse.move(0, 0);
  await shot('scene3a-candesartan-gp-cell');
  await p.getByRole('button', { name: /Mark GP daily dose as outdated/ }).click();
  await p.locator('.insp .pill.sev-low').waitFor();
  note('3', `after marking: ${(await p.locator('.insp .pill.sev-low').innerText())}`);
  note('3', `learning card: ${(await p.locator('.learn').innerText()).replace(/\n/g, ' ')}`);
  await tab('Source confidence');
  note('3', `change box: ${(await p.locator('.change-box').first().innerText()).replace(/\n/g, ' ')}`);
  await shot('scene3b-source-confidence');
  note('3', `P0007 run settled in ${await run('MRN0000007')} s`);
  note('3', `P0007 findings: ${(await p.locator('.finding-title').allInnerTexts()).map((s) => s.replace(/\n/g, ' ')).join(' || ') || 'none'}`);
  note('3', `P0007 learning card: ${(await p.locator('.learn').innerText()).replace(/\n/g, ' ')}`);
  await shot('scene3c-p0007-discrepancies');
  await tab('Medication history');
  note('3', `rosuvastatin reconciled: ${(await p.locator('.row', { hasText: 'Rosuvastatin' }).locator('.recon').innerText()).replace(/\n/g, ' | ')}`);
  await shot('scene3d-p0007-history');
  await tab('Source confidence');
  note('3', `P0007 GP daily dose row: ${(await p.locator('.trow', { hasText: 'Daily dose' }).nth(1).innerText()).replace(/\n/g, ' ')}`);
  await shot('scene3e-p0007-confidence');

  note('end', `header model: ${await p.locator('.hd-status').nth(2).innerText()}`);
  console.log(notes.join('\n'));
  console.log(errs.length ? 'ERRORS:\n' + errs.join('\n') : 'no page or HTTP errors');
  await b.close();
})();
