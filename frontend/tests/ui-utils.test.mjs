import test from "node:test";
import assert from "node:assert/strict";
import {
  apiErrorText,
  countBy,
  isUuid,
  loginErrorText,
  newlyEarnedBadges,
  remainingSlaSeconds,
  summarizeCases,
} from "../app/lib/ui-utils.mjs";

test("login errors distinguish invalid credentials, lockout, and service failure", () => {
  assert.match(loginErrorText({ status: 401 }), /401/);
  assert.match(
    loginErrorText({ status: 429, code: "ACCOUNT_LOCKED", details: { remaining_seconds: 37 } }),
    /37 saniye/,
  );
  assert.match(loginErrorText({ status: 503, code: "SERVICE_UNAVAILABLE" }), /ulaşılamıyor/);
});

test("general API errors preserve status-specific user guidance", () => {
  assert.match(apiErrorText({ status: 403, message: "forbidden" }), /403/);
  assert.match(apiErrorText({ status: 422, message: "invalid transition" }), /422/);
  assert.match(apiErrorText({ status: 429, message: "limited" }), /429/);
});

test("SLA, badge, and supervisor summaries are derived from live values", () => {
  assert.equal(remainingSlaSeconds("2026-07-23T10:00:30Z", Date.parse("2026-07-23T10:00:00Z")), 30);
  assert.deepEqual(newlyEarnedBadges([], ["ILK_YAKALAMA"]), ["ILK_YAKALAMA"]);
  assert.deepEqual(
    summarizeCases([
      { status: "YENI", assigned_analyst_id: null, sla_exceeded: false, transaction: { risk_level: "BELIRSIZ" } },
      { status: "INCELENIYOR", assigned_analyst_id: "analyst", sla_exceeded: true, transaction: { risk_level: "KRITIK" } },
      { status: "KAPANDI", assigned_analyst_id: "analyst", sla_exceeded: false, transaction: { risk_level: "KRITIK" } },
    ]),
    { active: 2, critical: 1, slaExceeded: 1, queued: 1 },
  );
  assert.deepEqual(countBy(["KRITIK", "DUSUK", "KRITIK"]), [
    { label: "KRITIK", count: 2 },
    { label: "DUSUK", count: 1 },
  ]);
  assert.equal(isUuid("c1510888-5812-45b4-83fa-9d1d83e36c0a"), true);
  assert.equal(isUuid("not-a-uuid"), false);
});
