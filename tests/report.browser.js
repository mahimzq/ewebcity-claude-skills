"use strict";

// Optional browser gate: requires a developer-provided Playwright installation.
// The runtime package and generated reports do not depend on Playwright.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require(process.env.EWEBCITY_PLAYWRIGHT_MODULE || "playwright");

async function main() {
  const report = path.resolve(process.argv[2] || "examples/demo-report.html");
  const output = process.env.EWEBCITY_REPORT_ARTIFACTS || fs.mkdtempSync(path.join(os.tmpdir(), "ewebcity-report-browser-"));
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.EWEBCITY_CHROMIUM ? { executablePath: process.env.EWEBCITY_CHROMIUM } : {}),
    args: process.getuid?.() === 0 ? ["--no-sandbox"] : [],
  });
  const checks = [];
  const verified = (name) => checks.push(name);
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, colorScheme: "light" });
    const page = await context.newPage();
    const errors = [], network = [];
    page.on("pageerror", (error) => errors.push(String(error)));
    page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
    page.on("request", (request) => { if (/^https?:/.test(request.url())) network.push(request.url()); });
    await page.goto(pathToFileURL(report).href);
    await page.waitForFunction(() => document.documentElement.classList.contains("enhanced"));
    const allCount = await page.locator(".finding").count();
    assert.ok(allCount > 0, "Example must exercise actual findings");
    const issueCount = await page.locator('.finding[data-status="fail"], .finding[data-status="warning"]').count();
    assert.equal(await page.locator(".finding:not([hidden])").count(), issueCount);
    verified("Initial issue filter and script CSP");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(output, "desktop.png"), fullPage: false });
    verified("Desktop layout without page overflow");

    await page.selectOption("#status-filter", "all");
    assert.equal(await page.locator(".finding:not([hidden])").count(), allCount);
    await page.fill("#finding-search", "zzzz-no-matching-evidence-zzzz");
    assert.equal(await page.locator(".finding:not([hidden])").count(), 0);
    assert.equal(await page.locator("#no-findings").isVisible(), true);
    await page.click("#reset-filters");
    assert.equal(await page.locator(".finding:not([hidden])").count(), allCount);
    assert.equal(await page.locator("#finding-search").evaluate((element) => element === document.activeElement), true);
    verified("Search, empty state and reset keyboard focus");

    await page.selectOption("#status-filter", "not_checked");
    assert.equal(await page.locator(".finding:not([hidden])").count(), await page.locator('.finding[data-status="not_checked"]').count());
    await page.click("#reset-filters");
    const category = await page.locator(".finding").first().getAttribute("data-category");
    await page.selectOption("#category-filter", category);
    assert.equal(await page.locator(".finding:not([hidden])").evaluateAll((elements, value) => elements.every((element) => element.dataset.category === value), category), true);
    const severity = await page.locator(".finding:not([hidden])").first().getAttribute("data-severity");
    await page.selectOption("#severity-filter", severity);
    assert.equal(await page.locator(".finding:not([hidden])").evaluateAll((elements, value) => elements.every((element) => element.dataset.severity === value), severity), true);
    verified("Status, category and impact filtering");

    await page.locator("[data-page-jump]").first().click();
    const selectedURL = await page.inputValue("#page-filter");
    assert.notEqual(selectedURL, "all");
    assert.equal(await page.locator(".finding:not([hidden])").evaluateAll((elements, url) => elements.every((element) => element.dataset.page === url), selectedURL), true);
    await page.click("#expand-findings");
    assert.equal(await page.locator(".finding:not([hidden]) details:not([open])").count(), 0);
    await page.click("#expand-findings");
    assert.equal(await page.locator(".finding:not([hidden]) details[open]").count(), 0);
    verified("Page drill-down and evidence expand/collapse");

    await page.fill("#page-search", "zzzz-no-page-zzzz");
    assert.equal(await page.locator(".page-row:not([hidden])").count(), 0);
    await page.fill("#page-search", "");
    assert.ok(await page.locator(".page-row:not([hidden])").count() > 0);
    await page.selectOption("#theme-choice", "dark");
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, "dark.png"), fullPage: false });
    await page.selectOption("#theme-choice", "light");
    verified("Page search and appearance controls");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => scrollTo(0, 0));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(output, "mobile.png"), fullPage: false });
    verified("390px mobile layout without page overflow");

    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.click("#reset-filters");
    await page.fill("#finding-search", "zzzz-no-matching-evidence-zzzz");
    await page.emulateMedia({ media: "print" });
    await page.evaluate(() => dispatchEvent(new Event("beforeprint")));
    assert.equal(await page.locator(".finding:not([hidden])").count(), allCount);
    assert.equal(await page.locator(".finding details:not([open])").count(), 0);
    assert.equal(await page.locator("#no-findings").isVisible(), false);
    assert.equal(await page.locator(".sidebar").isVisible(), false);
    await page.pdf({ path: path.join(output, "report-print.pdf"), format: "A4", printBackground: true });
    await page.evaluate(() => dispatchEvent(new Event("afterprint")));
    await page.emulateMedia({ media: "screen" });
    assert.equal(await page.locator(".finding:not([hidden])").count(), 0);
    verified("Complete print/PDF evidence and restored interactive state");

    assert.deepEqual(network, []);
    assert.deepEqual(errors, []);
    verified("No external requests, CSP errors or JavaScript exceptions");
    await context.close();

    const noJS = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    const staticPage = await noJS.newPage();
    await staticPage.goto(pathToFileURL(report).href);
    assert.equal(await staticPage.locator(".finding:not([hidden])").count(), allCount);
    assert.equal(await staticPage.locator(".finding details[open]").count(), allCount);
    assert.equal(await staticPage.locator("#status-filter").isVisible(), false);
    assert.equal(await staticPage.locator("noscript").isVisible(), true);
    assert.equal(await staticPage.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    verified("No-JavaScript evidence and mobile fallback");
    await noJS.close();
    const result = { passed: checks.length, checks, external_requests: 0, browser_errors: 0, artifacts: output };
    fs.writeFileSync(path.join(output, "browser-results.json"), JSON.stringify(result, null, 2) + "\n");
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
