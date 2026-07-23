import test from "node:test";
import assert from "node:assert/strict";
import { routeForRole } from "../app/lib/auth-routing.mjs";

test("root auth routing sends each role to its demo workspace", () => {
  assert.equal(routeForRole("CUSTOMER"), "/customer");
  assert.equal(routeForRole("ANALYST"), "/analyst");
  assert.equal(routeForRole("SUPERVISOR"), "/supervisor");
  assert.equal(routeForRole("ADMIN"), "/supervisor");
});
