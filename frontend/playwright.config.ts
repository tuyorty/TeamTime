import { defineConfig, devices } from "@playwright/test";

/**
 * E2E-смоуки и скриншоты для README. Нужен поднятый стек в демо-режиме:
 *   DEMO=1 DEMO_NOW=2026-10-23T19:40:00+05:00 docker compose up
 * Адрес — E2E_BASE_URL (по умолчанию dev-сервер Vite).
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: { baseURL, locale: "ru-RU", trace: "retain-on-failure" },
  projects: [
    { name: "smoke", testMatch: /(?:smoke|tv)\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    { name: "screenshots", testMatch: /screenshots\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
  ],
});
