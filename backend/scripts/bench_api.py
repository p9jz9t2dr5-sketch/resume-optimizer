"""Measure latency of the read paths and the bcrypt login against a running API.

Only hits non-model endpoints, so it is safe to run against production:

    python scripts/bench_api.py                        # container -> backend
    python scripts/bench_api.py http://nginx/api       # through the reverse proxy
    python scripts/bench_api.py http://<host>/api 15   # from the public internet

Small sample sizes are deliberate — this reports an honest order of magnitude,
not a load test.
"""

import statistics
import sys
import time
from collections.abc import Callable

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 15

EMAIL = "demo@resume-optimizer.dev"
PASSWORD = "demo1234"


def timed(fn: Callable[[], object], rounds: int) -> list[float]:
    samples: list[float] = []
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return samples


def report(label: str, samples: list[float]) -> None:
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    print(
        f"{label:<28} 中位 {statistics.median(ordered):7.1f} ms   "
        f"P95 {p95:7.1f} ms   最小 {ordered[0]:7.1f} ms"
    )


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=60) as client:
        token = client.post(
            "/auth/login", json={"email": EMAIL, "password": PASSWORD}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        resume_id = client.get("/resumes", headers=headers).json()["resumes"][0]["id"]

        print(f"目标 {BASE}    每项 {ROUNDS} 次\n")
        report("GET /health", timed(lambda: client.get("/health"), ROUNDS))
        report(
            "POST /auth/login (bcrypt)",
            timed(
                lambda: client.post(
                    "/auth/login", json={"email": EMAIL, "password": PASSWORD}
                ),
                ROUNDS,
            ),
        )
        report("GET /auth/me", timed(lambda: client.get("/auth/me", headers=headers), ROUNDS))
        report(
            "GET /auth/me/stats",
            timed(lambda: client.get("/auth/me/stats", headers=headers), ROUNDS),
        )
        report("GET /resumes", timed(lambda: client.get("/resumes", headers=headers), ROUNDS))
        report(
            "GET /resumes/{id}",
            timed(lambda: client.get(f"/resumes/{resume_id}", headers=headers), ROUNDS),
        )
        report(
            "GET /companies/search",
            timed(lambda: client.get("/companies/search", params={"q": "腾讯"}), ROUNDS),
        )
        report(
            "GET /chat/sessions",
            timed(lambda: client.get("/chat/sessions", headers=headers), ROUNDS),
        )


if __name__ == "__main__":
    main()
