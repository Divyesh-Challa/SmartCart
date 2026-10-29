import { createHmac, randomUUID } from "node:crypto";
import type { Page } from "@playwright/test";
import { E2E_JWT_SECRET } from "../playwright.config";

const b64url = (data: string | Buffer) => Buffer.from(data).toString("base64url");

function accessToken(userId: string, email: string): string {
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const exp = Math.floor(Date.now() / 1000) + 3600;
  const payload = b64url(JSON.stringify({ sub: userId, email, aud: "authenticated", role: "authenticated", exp }));
  const signature = createHmac("sha256", E2E_JWT_SECRET).update(`${header}.${payload}`).digest("base64url");
  return `${header}.${payload}.${signature}`;
}

/** Signs the browser in by storing a session where supabase-js keeps it (no email round trip). */
export async function signIn(page: Page, email: string) {
  const id = randomUUID();
  const session = {
    access_token: accessToken(id, email),
    refresh_token: "e2e-refresh",
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    user: { id, email, aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}, created_at: new Date().toISOString() },
  };
  await page.addInitScript((value) => localStorage.setItem("sb-localhost-auth-token", value), JSON.stringify(session));
}

export async function setLocation(page: Page, postalCode = "T6E 2A1") {
  await page.goto("/");
  await page.getByLabel("Your postal code").fill(postalCode);
  await page.getByRole("button", { name: "Set location" }).click();
  await page.getByText(/Showing stores near/).waitFor();
}
