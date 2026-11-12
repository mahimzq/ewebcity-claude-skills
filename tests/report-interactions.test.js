"use strict";

// Exercise the constant interaction script with a small DOM test double.
// This is a logic test, not a browser layout, accessibility or print-render test.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../skills/ewebcity-seo-optimizer/scripts/reporting.py"), "utf8");
const script = source.match(/_SCRIPT\s*=\s*r?'''([\s\S]*?)'''/)[1];

function fixture({ storageFails = false, storedTheme = null } = {}) {
  class Element {
    constructor(values = {}) {
      Object.assign(this, { dataset: {}, hidden: false, open: false, value: "", textContent: "", tagName: "DIV", handlers: {} }, values);
    }
    addEventListener(name, handler) { this.handlers[name] = handler; }
    fire(name) { this.handlers[name]?.(); }
    focus() { document.activeElement = this; }
    scrollIntoView() { this.scrolled = true; }
    querySelector(selector) { assert.equal(selector, "details"); return this.details; }
    set innerHTML(_value) { throw new Error("Unsafe DOM insertion is not allowed"); }
  }
  const cards = [
    ["fail", "high", "indexing", "https://example.com/a", "Broken canonical target"],
    ["warning", "low", "content", "https://example.com/b", "Missing image alternative"],
    ["pass", "info", "content", "https://example.com/a", "Descriptive title observed"],
    ["not_checked", "info", "performance", "https://example.com/b", "Core Web Vitals unmeasured"],
  ].map(([status, severity, category, page, textContent]) => new Element({ dataset: { status, severity, category, page }, textContent, details: new Element({ open: true }) }));
  const pageRows = [new Element({ textContent: "Page alpha" }), new Element({ textContent: "Page beta" })];
  const jumps = [new Element({ dataset: { pageJump: "https://example.com/a" } }), new Element({ dataset: { pageJump: "https://example.com/b" } })];
  const elements = {};
  for (const id of ["finding-search", "status-filter", "severity-filter", "category-filter", "page-filter", "finding-count", "no-findings", "expand-findings", "page-search", "theme-choice", "reset-filters", "findings", "page-count", "no-pages", "print-report"]) {
    assert.ok(source.includes(`id="${id}"`), `Rendered report must expose ${id}`);
    elements[id] = new Element({ tagName: id.endsWith("search") ? "INPUT" : id.endsWith("filter") || id === "theme-choice" ? "SELECT" : "DIV" });
  }
  elements["status-filter"].value = "issues";
  for (const id of ["severity-filter", "category-filter", "page-filter"]) elements[id].value = "all";
  const classes = new Set();
  const root = new Element({ classList: { add: (value) => classes.add(value) } });
  const document = {
    documentElement: root, activeElement: null,
    getElementById(id) { assert.ok(elements[id], `Unknown control ${id}`); return elements[id]; },
    querySelectorAll(selector) {
      if (selector === ".finding") return cards;
      if (selector === ".page-row") return pageRows;
      if (selector === "[data-page-jump]") return jumps;
      if (selector === "details") return cards.map((card) => card.details);
      throw new Error(`Unexpected DOM query ${selector}`);
    },
  };
  const window = new Element();
  window.print = () => { window.fire("beforeprint"); window.fire("afterprint"); };
  const storage = {};
  const localStorage = {
    getItem() { if (storageFails) throw new Error("Storage unavailable"); return storedTheme; },
    setItem(key, value) { if (storageFails) throw new Error("Storage unavailable"); storage[key] = value; },
  };
  vm.runInNewContext(script, { document, window, localStorage }, { timeout: 1000 });
  const change = (id, value) => { elements[id].value = value; elements[id].fire(elements[id].tagName === "INPUT" ? "input" : "change"); };
  return { cards, pageRows, jumps, elements, root, classes, document, window, storage, change, visible: () => cards.filter((card) => !card.hidden) };
}

test("report starts with observed issues and collapsible evidence", () => {
  const f = fixture();
  assert.equal(f.visible().length, 2);
  assert.equal(f.elements["finding-count"].textContent, "Showing 2 of 4 recorded checks");
  assert.ok(f.cards.every((card) => !card.details.open));
  assert.ok(f.classes.has("enhanced"));
});

test("search, empty state and reset update actual visible records", () => {
  const f = fixture();
  f.change("status-filter", "all");
  f.change("finding-search", "  DESCRIPTIVE TITLE  ");
  assert.equal(f.visible().length, 1);
  f.change("finding-search", "nothing matches");
  assert.equal(f.visible().length, 0);
  assert.equal(f.elements["no-findings"].hidden, false);
  assert.equal(f.elements["expand-findings"].disabled, true);
  f.elements["reset-filters"].fire("click");
  assert.equal(f.visible().length, 4);
  assert.equal(f.document.activeElement, f.elements["finding-search"]);
});

test("status, severity, category and page filters compose", () => {
  const f = fixture();
  f.change("status-filter", "all");
  f.change("category-filter", "content");
  f.change("severity-filter", "low");
  f.change("page-filter", "https://example.com/b");
  assert.deepEqual(f.visible().map((card) => card.dataset.status), ["warning"]);
  f.change("status-filter", "pass");
  assert.equal(f.visible().length, 0);
});

test("page drill-down resets unrelated filters and expands only visible evidence", () => {
  const f = fixture();
  f.change("finding-search", "unmatched");
  f.jumps[0].fire("click");
  assert.equal(f.visible().length, 2);
  assert.equal(f.document.activeElement, f.elements["page-filter"]);
  assert.equal(f.elements.findings.scrolled, true);
  f.elements["expand-findings"].fire("click");
  assert.ok(f.visible().every((card) => card.details.open));
  assert.ok(f.cards.filter((card) => card.hidden).every((card) => !card.details.open));
  f.elements["expand-findings"].fire("click");
  assert.ok(f.cards.every((card) => !card.details.open));
});

test("print events include every record and restore the exact filter and disclosure state", () => {
  const f = fixture();
  f.cards[0].details.open = true;
  f.change("finding-search", "unmatched");
  f.change("page-search", "alpha");
  const previous = [...f.cards, ...f.pageRows].map((node) => node.hidden);
  f.window.fire("beforeprint");
  f.window.fire("beforeprint");
  assert.ok([...f.cards, ...f.pageRows].every((node) => !node.hidden));
  assert.ok(f.cards.every((card) => card.details.open));
  f.window.fire("afterprint");
  assert.deepEqual([...f.cards, ...f.pageRows].map((node) => node.hidden), previous);
  assert.equal(f.cards[0].details.open, true);
  assert.ok(f.cards.slice(1).every((card) => !card.details.open));
});

test("page search changes only the page overview", () => {
  const f = fixture();
  f.change("page-search", "beta");
  assert.deepEqual(f.pageRows.map((row) => row.hidden), [true, false]);
  assert.equal(f.visible().length, 2);
  assert.equal(f.elements["page-count"].textContent, "1 of 2 observed pages");
});

test("appearance works when local storage is blocked or contains an unknown value", () => {
  for (const options of [{ storageFails: true }, { storedTheme: "unexpected" }]) {
    const f = fixture(options);
    assert.equal(f.root.dataset.theme, "system");
    f.change("theme-choice", "dark");
    assert.equal(f.root.dataset.theme, "dark");
  }
  const f = fixture({ storedTheme: "light" });
  assert.equal(f.root.dataset.theme, "light");
});
