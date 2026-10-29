import { expect, test } from "vitest";

import { href, parseRoute } from "../src/router";

test("routes are parsed from the hash and rendered back", () => {
  expect(parseRoute("")).toEqual({ name: "binders" });
  expect(parseRoute("#/")).toEqual({ name: "binders" });
  expect(parseRoute("#/binders/b1")).toEqual({ name: "binder", id: "b1" });
  expect(parseRoute("#/papers/p1")).toEqual({ name: "paper", id: "p1" });
  expect(parseRoute("#/binders/b1/assembly")).toEqual({ name: "assembly", id: "b1" });
  expect(parseRoute("#/binders/b1/review-notes")).toEqual({ name: "review-notes", id: "b1" });
  expect(href({ name: "review-notes", id: "b1" })).toBe("#/binders/b1/review-notes");
  expect(href({ name: "assembly", id: "b1" })).toBe("#/binders/b1/assembly");
  expect(parseRoute("#/nonsense/x/y")).toEqual({ name: "binders" });
  expect(href({ name: "binder", id: "b1" })).toBe("#/binders/b1");
  expect(href({ name: "paper", id: "p1" })).toBe("#/papers/p1");
});
