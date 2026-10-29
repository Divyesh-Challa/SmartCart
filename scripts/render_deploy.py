"""
Create or update the SmartCart service on Render and deploy it.

    python scripts/render_deploy.py --branch feat/deploy-ready          # dry run: shows the plan
    python scripts/render_deploy.py --branch feat/deploy-ready --yes    # actually deploys

Reads RENDER_API_KEY and the SMARTCART_* settings from .env. Secrets are sent
to Render's API only and never printed. It also adds the service's address to
the Supabase project's sign-in redirect list (needs SUPABASE_ACCESS_TOKEN and
SUPABASE_PROJECT_REF), so magic links work on the live site.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
RENDER_API = "https://api.render.com/v1"
REPO = "https://github.com/Divyesh-Challa/SmartCart"
SERVICE_NAME = "smartcart-app"

# Settings copied from .env to the service. Development-only values are left out.
SYNCED_SETTINGS = (
    "SMARTCART_DATABASE_URL",
    "SMARTCART_SUPABASE_URL",
    "SMARTCART_SUPABASE_ANON_KEY",
    "SMARTCART_SUPABASE_SERVICE_ROLE_KEY",
    "SMARTCART_ADMIN_EMAILS",
    "SMARTCART_ADMIN_TOKEN",
    "SMARTCART_SENTRY_DSN",
)
FIXED_SETTINGS = {"SMARTCART_ENVIRONMENT": "production", "SMARTCART_RUN_SCHEDULER": "true"}


def fail(message: str) -> None:
    sys.exit(f"error: {message}")


def render(client: httpx.Client, method: str, path: str, **kwargs):
    resp = client.request(method, f"{RENDER_API}{path}", **kwargs)
    if resp.status_code >= 400:
        fail(f"Render API {method} {path} returned {resp.status_code}: {resp.text[:300]}")
    return resp.json() if resp.content else None


def find_service(client: httpx.Client):
    for entry in render(client, "GET", "/services", params={"name": SERVICE_NAME, "limit": 20}):
        if entry["service"]["name"] == SERVICE_NAME:
            return entry["service"]
    return None


def owner_id(client: httpx.Client) -> str:
    owners = render(client, "GET", "/owners", params={"limit": 20})
    if not owners:
        fail("this Render API key can't see any workspace")
    if len(owners) > 1:
        names = ", ".join(o["owner"]["name"] for o in owners)
        print(f"Several Render workspaces found ({names}); using the first.")
    return owners[0]["owner"]["id"]


def create_service(client: httpx.Client, branch: str) -> dict:
    body = {
        "type": "web_service",
        "name": SERVICE_NAME,
        "ownerId": owner_id(client),
        "repo": REPO,
        "branch": branch,
        "autoDeploy": "no",
        "serviceDetails": {
            "runtime": "docker",
            "plan": "free",
            "region": "virginia",
            "healthCheckPath": "/healthz",
            "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": "."},
        },
    }
    return render(client, "POST", "/services", json=body)["service"]


def env_vars(settings: dict, service_url: str) -> list:
    values = dict(FIXED_SETTINGS)
    for key in SYNCED_SETTINGS:
        if settings.get(key):
            values[key] = settings[key]
    values["SMARTCART_CORS_ORIGINS"] = json.dumps([service_url])
    return [{"key": k, "value": v} for k, v in values.items()]


def allow_supabase_redirect(settings: dict, service_url: str) -> None:
    token, ref = settings.get("SUPABASE_ACCESS_TOKEN"), settings.get("SUPABASE_PROJECT_REF")
    if not (token and ref):
        print(f"Supabase token not set: add {service_url}/account to Auth > URL Configuration by hand.")
        return
    url = f"https://api.supabase.com/v1/projects/{ref}/config/auth"
    headers = {"Authorization": f"Bearer {token}"}
    current = httpx.get(url, headers=headers, timeout=20).json()
    allowed = [u for u in (current.get("uri_allow_list") or "").split(",") if u]
    wanted = f"{service_url}/account"
    if wanted not in allowed:
        allowed.append(wanted)
    resp = httpx.patch(url, headers=headers, timeout=20,
                       json={"site_url": service_url, "uri_allow_list": ",".join(allowed)})
    if resp.status_code >= 400:
        fail(f"Supabase auth config update returned {resp.status_code}")
    print(f"Supabase sign-in now allows {wanted} (site URL {service_url}).")


def wait_for_deploy(client: httpx.Client, service_id: str, deploy_id: str) -> str:
    terminal = {"live", "build_failed", "update_failed", "canceled", "pre_deploy_failed", "deactivated"}
    while True:
        status = render(client, "GET", f"/services/{service_id}/deploys/{deploy_id}")["status"]
        print(f"  deploy status: {status}")
        if status in terminal:
            return status
        time.sleep(15)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--branch", required=True, help="Git branch Render builds from")
    parser.add_argument("--yes", action="store_true", help="Make the changes (without it, only shows the plan)")
    args = parser.parse_args()

    settings = dotenv_values(ROOT / ".env")
    key = settings.get("RENDER_API_KEY")
    if not key:
        fail("RENDER_API_KEY is missing from .env (Render dashboard > Account Settings > API Keys)")
    missing = [k for k in ("SMARTCART_DATABASE_URL", "SMARTCART_SUPABASE_URL", "SMARTCART_SUPABASE_ANON_KEY") if not settings.get(k)]
    if missing:
        fail(f"missing from .env: {', '.join(missing)}")

    with httpx.Client(headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=30) as client:
        service = find_service(client)
        print(f"Service {SERVICE_NAME}: {'exists' if service else 'will be created'}; branch {args.branch}.")
        print("Settings to sync:", ", ".join(sorted({*FIXED_SETTINGS, *(k for k in SYNCED_SETTINGS if settings.get(k)), 'SMARTCART_CORS_ORIGINS'})))
        if not args.yes:
            print("Dry run only. Re-run with --yes to deploy.")
            return

        if service is None:
            service = create_service(client, args.branch)
        elif service.get("branch") != args.branch:
            render(client, "PATCH", f"/services/{service['id']}", json={"branch": args.branch})
        service_url = service["serviceDetails"]["url"].rstrip("/")

        render(client, "PUT", f"/services/{service['id']}/env-vars", json=env_vars(settings, service_url))
        allow_supabase_redirect(settings, service_url)

        # Render answers 202 with no body when a deploy is already queued (a new
        # service starts one itself), so follow the latest deploy either way.
        render(client, "POST", f"/services/{service['id']}/deploys", json={"clearCache": "do_not_clear"})
        latest = render(client, "GET", f"/services/{service['id']}/deploys", params={"limit": 1})[0]["deploy"]
        status = wait_for_deploy(client, service["id"], latest["id"])
        print(f"Deploy finished: {status}. Site: {service_url}")
        if status != "live":
            sys.exit(1)


if __name__ == "__main__":
    main()
