import test from "node:test";
import assert from "node:assert/strict";
import {
  activeVerificationCases,
  highRiskQuickFill,
  normalQuickFill,
  unseenVerificationIds,
} from "../app/demo-utils.mjs";

test("notification is derived from real MUSTERI_DOGRULAMA status", () => {
  const items = [
    { case: { id: "one", status: "INCELENIYOR" } },
    { case: { id: "two", status: "MUSTERI_DOGRULAMA" } },
  ];
  assert.deepEqual(activeVerificationCases(items).map((item) => item.case.id), ["two"]);
});

test("polling does not generate duplicate notification IDs", () => {
  const items = [{ case: { id: "case-1", status: "MUSTERI_DOGRULAMA" } }];
  assert.deepEqual(unseenVerificationIds(items, new Set()), ["case-1"]);
  assert.deepEqual(unseenVerificationIds(items, new Set(["case-1"])), []);
});

test("quick fills contain inputs but never hardcode AI output", () => {
  for (const fill of [highRiskQuickFill(), normalQuickFill()]) {
    assert.equal("risk_score" in fill, false);
    assert.equal("risk_level" in fill, false);
    assert.equal("decision" in fill, false);
  }
  assert.equal(highRiskQuickFill().amount, "48500");
  assert.equal(normalQuickFill().transaction_type, "FATURA");
});
