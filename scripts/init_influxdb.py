"""Idempotent Initialization Script for Local InfluxDB v2 Instance.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 3 Implementation
Classification: [IMPLEMENTATION DECISION]

Initializes the local development InfluxDB instance:
1. Pings the InfluxDB server to verify it is running.
2. Checks /api/v2/setup to see if initial onboarding is needed.
3. If uninitialized, executes initial onboarding with:
   - Organization: INFLUXDB_ORG (default: industrial_iot)
   - Bucket: INFLUXDB_BUCKET (default: motor_telemetry)
   - Admin Token: INFLUXDB_TOKEN (from .env or config/settings.py)
4. If already initialized, checks if the target bucket exists, creating it if needed.
"""

import sys
import time
from pathlib import Path
from typing import Optional

import requests

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings


def check_influxdb_health(url: str, timeout: float = 3.0) -> bool:
    """Check if InfluxDB instance is listening and healthy."""
    try:
        resp = requests.get(f"{url.rstrip('/')}/health", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def is_onboarding_allowed(url: str, timeout: float = 3.0) -> bool:
    """Check whether InfluxDB has not yet been onboarded (fresh installation)."""
    try:
        resp = requests.get(f"{url.rstrip('/')}/api/v2/setup", timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("allowed", False)
        return False
    except requests.RequestException:
        return False


def setup_initial_onboarding(url: str, org: str, bucket: str, token: str, username: str = "admin", password: str = "dev_password_123!") -> bool:
    """Execute initial InfluxDB v2 setup onboarding."""
    payload = {
        "username": username,
        "password": password,
        "org": org,
        "bucket": bucket,
        "token": token,
    }
    try:
        resp = requests.post(f"{url.rstrip('/')}/api/v2/setup", json=payload, timeout=5.0)
        if resp.status_code in (200, 201):
            print(f"[SUCCESS] Initial onboarding completed. Org: '{org}', Bucket: '{bucket}'")
            return True
        else:
            print(f"[ERROR] Onboarding failed ({resp.status_code}): {resp.text}")
            return False
    except requests.RequestException as exc:
        print(f"[ERROR] Request exception during onboarding: {exc}")
        return False


def ensure_bucket_exists(url: str, org: str, bucket_name: str, token: str) -> bool:
    """Verify target bucket exists under the organization; create if missing."""
    headers = {"Authorization": f"Token {token}"}
    
    # 1. Get org_id
    try:
        org_resp = requests.get(f"{url.rstrip('/')}/api/v2/orgs", headers=headers, params={"org": org}, timeout=5.0)
        if org_resp.status_code != 200:
            print(f"[WARNING] Could not list orgs ({org_resp.status_code}): {org_resp.text}")
            return False
        orgs = org_resp.json().get("orgs", [])
        if not orgs:
            print(f"[WARNING] Organization '{org}' not found.")
            return False
        org_id = orgs[0]["id"]
    except requests.RequestException as exc:
        print(f"[ERROR] Failed fetching organization ID: {exc}")
        return False

    # 2. Check if bucket exists
    try:
        buckets_resp = requests.get(
            f"{url.rstrip('/')}/api/v2/buckets",
            headers=headers,
            params={"name": bucket_name, "orgID": org_id},
            timeout=5.0
        )
        if buckets_resp.status_code == 200:
            buckets = buckets_resp.json().get("buckets", [])
            if any(b.get("name") == bucket_name for b in buckets):
                print(f"[OK] Bucket '{bucket_name}' already exists in org '{org}'.")
                return True

        # 3. Create bucket if missing
        create_payload = {
            "name": bucket_name,
            "orgID": org_id,
            "retentionRules": [{"type": "expire", "everySeconds": 2592000}],  # 30 days retention
        }
        create_resp = requests.post(f"{url.rstrip('/')}/api/v2/buckets", headers=headers, json=create_payload, timeout=5.0)
        if create_resp.status_code in (200, 201):
            print(f"[SUCCESS] Created bucket '{bucket_name}' in org '{org}'.")
            return True
        else:
            print(f"[ERROR] Failed to create bucket ({create_resp.status_code}): {create_resp.text}")
            return False
    except requests.RequestException as exc:
        print(f"[ERROR] Exception checking/creating bucket: {exc}")
        return False


def main() -> None:
    settings = get_settings()
    url = settings.influxdb_url
    org = settings.influxdb_org
    bucket = settings.influxdb_bucket
    token = settings.influxdb_token

    print("==========================================================")
    print("Edge-IoT Predictive Maintenance - InfluxDB Initializer")
    print(f"Target URL: {url} | Org: {org} | Bucket: {bucket}")
    print("==========================================================")

    if not check_influxdb_health(url):
        print(f"[ERROR] InfluxDB is not responding at {url}.")
        print("Please ensure the InfluxDB service/process is running before initializing.")
        sys.exit(1)

    print("[OK] InfluxDB service is alive and healthy.")

    if is_onboarding_allowed(url):
        print("[INFO] InfluxDB is uninitialized. Executing initial onboarding...")
        success = setup_initial_onboarding(url, org, bucket, token)
        if not success:
            sys.exit(1)
    else:
        print("[INFO] InfluxDB is already onboarded. Verifying target bucket exists...")
        success = ensure_bucket_exists(url, org, bucket, token)
        if not success:
            print("[WARNING] Could not confirm bucket exists with configured token. Check token permissions.")

    print("[SUCCESS] InfluxDB initialization complete.")


if __name__ == "__main__":
    main()
