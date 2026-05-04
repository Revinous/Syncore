import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

function read(rel) {
  return readFileSync(new URL(rel, import.meta.url), "utf8");
}

test("dashboard page has loading/empty/error states", () => {
  const page = read("../pages/index.tsx");
  assert.match(page, /Loading dashboard summary/);
  assert.match(page, /No recent events/);
  assert.match(page, /ErrorState/);
});

test("workspaces page has empty state", () => {
  const page = read("../pages/workspaces.tsx");
  assert.match(page, /No workspaces registered yet/);
});

test("tasks page has empty state", () => {
  const page = read("../pages/tasks\/index.tsx");
  assert.match(page, /No tasks found/);
});

test("diagnostics page renders service health", () => {
  const page = read("../pages/diagnostics.tsx");
  assert.match(page, /Service Health/);
  assert.match(page, /getServicesHealth/);
});

test("notifications page has empty state", () => {
  const page = read("../pages/notifications.tsx");
  assert.match(page, /No unread notifications/);
});

test("analyst page renders digest controls", () => {
  const page = read("../pages/analyst.tsx");
  assert.match(page, /Analyst Digest/);
  assert.match(page, /Generate Digest/);
});

test("task detail page renders model strategy controls", () => {
  const page = read("../pages/tasks/[taskId].tsx");
  assert.match(page, /Model Strategy/);
  assert.match(page, /Execution Outcome/);
  assert.match(page, /Verification Commands/);
  assert.match(page, /optimization_goal/);
  assert.match(page, /Save strategy/);
});
