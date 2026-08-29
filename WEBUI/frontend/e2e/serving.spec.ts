import { expect, test } from "@playwright/test";

test("serves the built SPA while API routes retain precedence", async ({ request }) => {
  const root = await request.get("/");
  expect(root.status()).toBe(200);
  const html = await root.text();
  expect(root.headers()["content-type"]).toContain("text/html");
  expect(html).toContain('<div id="root">');

  const assetPath = html.match(/(?:src|href)="(\/assets\/[^"]+)"/)?.[1];
  expect(assetPath).toBeTruthy();
  const asset = await request.get(assetPath!);
  expect(asset.status()).toBe(200);
  expect(asset.headers()["content-type"]).not.toContain("text/html");

  const deepRoute = await request.get("/projects/nonexistent-project/dashboard");
  expect(deepRoute.status()).toBe(200);
  expect(deepRoute.headers()["content-type"]).toContain("text/html");
  expect(await deepRoute.text()).toContain('<div id="root">');

  const health = await request.get("/api/v1/health");
  expect(health.status()).toBe(200);
  expect(health.headers()["content-type"]).toContain("application/json");
  expect(await health.json()).toEqual({ status: "ok", api_version: "v1" });

  const unknownApi = await request.get("/api/v1/definitely-not-a-real-route");
  expect(unknownApi.status()).toBe(404);
  expect(unknownApi.headers()["content-type"]).toContain("application/json");
  expect(await unknownApi.text()).not.toContain('<div id="root">');
});
