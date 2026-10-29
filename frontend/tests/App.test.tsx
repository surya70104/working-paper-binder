import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "../src/App";
import { mockApi } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());

test("the shell renders its title and opens on the binder list", async () => {
  mockApi({ "GET /api/binders": [], "GET /api/templates": [] });
  window.location.hash = "#/";
  render(<App />);
  expect(screen.getByRole("link", { name: "Working Paper Binder" })).toBeInTheDocument();
  expect(await screen.findByText("No binders yet.")).toBeInTheDocument();
});
