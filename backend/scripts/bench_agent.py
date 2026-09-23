"""对运行中的后端真跑 N 次 Agent 任务，记录每次都结果，产出可靠性数据。

用法（在 backend 目录下执行）：

    python scripts/bench_agent.py --runs 12
    python scripts/bench_agent.py --runs 20 --output bench_agent.json
    python scripts/bench_agent.py --runs 5 --base-url http://47.119.113.82/api

设计说明：

- 默认每次新建独立账号：长期记忆互不影响，N 次试验才算互相独立；用
  ``--reuse-account`` 可以让多次任务共享记忆（那是另一种实验：验证记忆是否生效）。
- 会真实调用模型并产生费用（一次 Agent 任务约 2 万 token 量级），所以默认只跑 12 次。
- 默认结束后删除临时账号（连带简历、轨迹、长期记忆一起清）；``--keep-accounts``
  保留，便于用 scripts/agent_stats.py 从库里复核同一批数据。
"""

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_RESUME = """张三
手机：13800000000  邮箱：zhangsan@example.com
求职意向：AI 应用开发实习生

教育背景
某某大学 计算机科学与技术 本科 | 2023.09 - 2027.06

项目经历
AI 简历优化平台 — 独立开发 | 2026.03 - 至今
- 用 FastAPI + PostgreSQL + Redis 实现简历解析、JD 匹配与 SSE 流式改写
- 前端 Next.js，用 Docker Compose + nginx 部署到云服务器

专业技能
Python、FastAPI、PostgreSQL、Redis、Docker、Next.js
"""

DEFAULT_JD = """AI 应用开发（实习生）
职责：参与 AI Agent 相关开发，负责任务规划、工具调用、记忆管理等核心功能；
结合大语言模型特性设计 RAG 检索链路，并做效果迭代。
要求：熟悉 Python，了解 LangChain / 向量数据库 / Function Calling。
"""

PASSWORD = "Passw0rd!123"


def _request(method: str, url: str, payload=None, token: str | None = None, timeout: int = 60):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, data=data, headers=headers, method=method)


class Client:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def json(self, method: str, path: str, payload=None, token: str | None = None):
        request = _request(method, self.base + path, payload, token)
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())

    def signup(self, email: str) -> str:
        try:
            self.json("POST", "/auth/register", {"email": email, "password": PASSWORD})
        except urllib.error.HTTPError as exc:
            if exc.code != 400:  # 400 = 已注册，可继续
                raise
        return self.json("POST", "/auth/login", {"email": email, "password": PASSWORD})["access_token"]

    def delete_account(self, token: str) -> None:
        self.json("DELETE", "/auth/me", token=token)

    def upload_resume(self, token: str, text: str, filename: str = "bench-resume.txt") -> str:
        boundary = "----bench" + uuid.uuid4().hex[:8]
        body = b"".join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: text/plain\r\n\r\n".encode(),
            text.encode("utf-8"),
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        request = urllib.request.Request(
            self.base + "/resumes/upload",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode())["id"]

    def run_agent(self, token: str, resume_id: str, jd_text: str, max_steps: int) -> dict:
        """跑一次 Agent 任务，消费整个 SSE 流，返回这次运行的统计。"""
        request = _request(
            "POST",
            self.base + "/agent/optimize",
            {"resume_id": resume_id, "jd_text": jd_text, "max_steps": max_steps},
            token,
        )
        started = time.perf_counter()
        outcome = {
            "run_id": None,
            "status": "failed",
            "stopped_reason": None,
            "steps": 0,
            "tool_calls": 0,
            "tool_names": [],
            "tool_errors": 0,
            "tokens": 0,
            "report_chars": 0,
            "error": None,
        }
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                for raw in response:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    kind = event.get("type")
                    if kind == "run":
                        outcome["run_id"] = event.get("run_id")
                    elif kind == "tool_call":
                        outcome["tool_names"].append(event.get("tool"))
                    elif kind == "tool_result" and not event.get("ok"):
                        outcome["tool_errors"] += 1
                    elif kind == "content" and isinstance(event.get("content"), str):
                        outcome["report_chars"] += len(event["content"])
                    elif kind == "done":
                        outcome["status"] = "succeeded" if event.get("stopped_reason") in (
                            "completed",
                            "max_steps",
                        ) else "failed"
                        outcome["stopped_reason"] = event.get("stopped_reason")
                        outcome["steps"] = event.get("steps") or 0
                        outcome["tool_calls"] = event.get("tool_calls") or 0
                        outcome["tokens"] = int(event.get("prompt_tokens") or 0) + int(
                            event.get("completion_tokens") or 0
                        )
                    elif kind == "error":
                        outcome["error"] = event.get("message")
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = f"{type(exc).__name__}: {exc}"
        outcome["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent 端到端压测 / 可靠性采样")
    parser.add_argument("--runs", type=int, default=12, help="跑多少次任务（默认 12）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--resume-file", default=None)
    parser.add_argument("--jd-file", default=None)
    parser.add_argument("--output", default="bench_agent.json", help="明细 JSON 落盘路径")
    parser.add_argument("--reuse-account", action="store_true", help="复用同一账号（共享长期记忆）")
    parser.add_argument("--keep-accounts", action="store_true", help="保留临时账号，便于从库里复核")
    args = parser.parse_args(argv)

    resume_text = Path(args.resume_file).read_text(encoding="utf-8") if args.resume_file else DEFAULT_RESUME
    jd_text = Path(args.jd_file).read_text(encoding="utf-8") if args.jd_file else DEFAULT_JD
    client = Client(args.base_url)

    shared_token = None
    results = []
    for index in range(1, args.runs + 1):
        email = f"bench-agent-{uuid.uuid4().hex[:10]}@example.com"
        token = shared_token or client.signup(email)
        if args.reuse_account:
            shared_token = token
        try:
            resume_id = client.upload_resume(token, resume_text)
            outcome = client.run_agent(token, resume_id, jd_text, args.max_steps)
            outcome["email"] = email
            results.append(outcome)
            flag = "OK  " if outcome["status"] == "succeeded" else "FAIL"
            print(
                f"[{index:>2}/{args.runs}] {flag} {outcome['duration_ms'] / 1000:>5.1f}s "
                f"tools={outcome['tool_calls']:>2} ok={outcome['tool_calls'] - outcome['tool_errors']:>2} "
                f"tokens={outcome['tokens']:>6} 报告 {outcome['report_chars']:>5} 字"
                + (f"  错误: {outcome['error']}" if outcome["error"] else ""),
                flush=True,
            )
        finally:
            if not args.reuse_account and not args.keep_accounts:
                try:
                    client.delete_account(token)
                except Exception as exc:  # noqa: BLE001
                    print(f"      ⚠ 清理账号失败: {exc}", flush=True)

    succeeded = [item for item in results if item["status"] == "succeeded"]
    durations = [item["duration_ms"] for item in results]
    tokens = [item["tokens"] for item in results if item["tokens"]]
    tool_total = sum(item["tool_calls"] for item in results)
    tool_errors = sum(item["tool_errors"] for item in results)

    summary = {
        "runs": len(results),
        "succeeded": len(succeeded),
        "success_rate": round(len(succeeded) / len(results), 3) if results else None,
        "duration_ms": {
            "median": int(statistics.median(durations)) if durations else None,
            "max": max(durations) if durations else None,
        },
        "tokens": {
            "median": int(statistics.median(tokens)) if tokens else None,
            "total": sum(tokens),
        },
        "tool_calls": {"total": tool_total, "errors": tool_errors},
        "stopped_reasons": sorted({str(item["stopped_reason"]) for item in results}),
    }

    payload = {"summary": summary, "runs": results}
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 汇总 ===")
    print(f"  成功率        : {summary['success_rate']:.1%}（{summary['succeeded']}/{summary['runs']}）")
    print(f"  耗时中位数    : {summary['duration_ms']['median']} ms（最大 {summary['duration_ms']['max']} ms）")
    print(f"  token 中位数  : {summary['tokens']['median']}")
    print(f"  工具调用      : {tool_total} 次，失败 {tool_errors} 次")
    print(f"  明细已写入    : {args.output}")
    print("  提示：这只是一次采样，写进简历时请写明样本量；想复核轨迹请加 --keep-accounts 再跑一次。")
    return 0 if len(succeeded) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
