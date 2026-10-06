#!/usr/bin/env python3
"""Agenteresolve coding runner.

HTTP service that the orchestrator (website) calls to implement/review a card
inside the coder container. It clones/updates the target repository, creates a
branch, runs the opencode agent headlessly, commits, pushes and opens a PR.

Endpoints:
    POST /implement  { card, repository } -> { ok, branch, pr_url, summary }
    POST /review     { card, repository } -> { ok, summary }

Auth: header `X-Runner-Token` must equal RUNNER_TOKEN.

Only the Python standard library is used (no pip installs).
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.environ.get("HOME", "/home/opencode")
WORKSPACE = os.environ.get("WORKSPACE_DIR", os.path.join(HOME, "agenteresolve"))
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_ORG = os.environ.get("GITHUB_ORG", "alex-pimentel")
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL", "")
AGENT_CMD = os.environ.get("RUNNER_AGENT_CMD", "")  # testing override
PORT = int(os.environ.get("RUNNER_PORT", "8090"))
AGENT_TIMEOUT = int(os.environ.get("RUNNER_AGENT_TIMEOUT", "900"))

BRANCH_PREFIX = {
    "feature": "feature",
    "fix": "fix",
    "refactor": "refactor",
    "chore": "chore",
    "doc": "docs",
}


def run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def log(message):
    print(f"runner: {message}", file=sys.stderr, flush=True)


def repo_dir(slug):
    return os.path.join(WORKSPACE, slug)


def ensure_repo(slug, github_url, default_branch):
    path = repo_dir(slug)
    if not os.path.isdir(os.path.join(path, ".git")):
        os.makedirs(WORKSPACE, exist_ok=True)
        url = github_url or f"https://github.com/{GITHUB_ORG}/{slug}.git"
        clone = run(["git", "clone", url, path], timeout=1200)
        if clone.returncode != 0:
            raise RuntimeError("clone falhou: " + clone.stderr[-400:])

    run(["git", "fetch", "origin", "--prune"], cwd=path)
    run(["git", "checkout", default_branch], cwd=path)
    run(["git", "reset", "--hard", f"origin/{default_branch}"], cwd=path)
    log(f"repo ready at {path}")
    return path


def run_agent(prompt, cwd):
    if AGENT_CMD:
        cmd = AGENT_CMD.split() + [prompt]
    else:
        cmd = ["opencode", "run", "--auto"]
        if OPENCODE_MODEL:
            cmd += ["--model", OPENCODE_MODEL]
        cmd += [prompt]

    log(f"agent cmd: {' '.join(cmd[:6])} ...")

    try:
        result = run(cmd, cwd=cwd, timeout=AGENT_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        partial = (error.stdout or b"")[-1500:]
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        log(f"agent timeout after {AGENT_TIMEOUT}s")
        return 124, "TIMEOUT: " + partial

    output = (result.stdout or "")[-4000:] + (result.stderr or "")[-2000:]
    log(f"agent output tail: {output[-600:].replace(chr(10), ' ')}")
    return result.returncode, output


def create_pr(slug, branch, base, title, body):
    if not GITHUB_TOKEN:
        return None

    payload = json.dumps({"title": title, "head": branch, "base": base, "body": body}).encode()
    request = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_ORG}/{slug}/pulls",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "agenteresolve-orchestrator",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response).get("html_url")
    except urllib.error.HTTPError as error:
        if error.code == 422:  # PR already exists for this head/base
            return None
        raise RuntimeError(f"PR HTTP {error.code}")


def implement(payload):
    card = payload.get("card", {})
    repo = payload.get("repository", {})
    slug = repo.get("slug") or ""
    if not slug:
        return {"ok": False, "error": "repository.slug ausente"}

    default_branch = repo.get("default_branch") or "main"
    log(f"implement start card={card.get('id')} slug={slug}")
    path = ensure_repo(slug, repo.get("github_url"), default_branch)

    prefix = BRANCH_PREFIX.get(card.get("type"), "feature")
    branch = f"{prefix}/card-{card.get('id')}"

    run(["git", "checkout", "-B", branch], cwd=path)

    prompt = (
        f"Você está no repositório '{slug}'. Implemente a tarefa abaixo de forma completa e mínima, "
        "seguindo as convenções do projeto. Rode lint e testes relevantes e corrija o que quebrar. "
        "NÃO faça commit nem push; apenas edite os arquivos e deixe o repositório pronto.\n\n"
        f"Tarefa #{card.get('id')} ({card.get('type')}): {card.get('title')}\n\n"
        f"Descrição:\n{card.get('description') or '(sem descrição)'}\n"
    )

    code, output = run_agent(prompt, path)
    log(f"agent finished card={card.get('id')} exit={code}")

    status = run(["git", "status", "--porcelain"], cwd=path).stdout.strip()
    if not status:
        log(f"no changes card={card.get('id')}")
        return {"ok": False, "error": "Agente não produziu alterações.", "summary": output[-1200:]}

    run(["git", "config", "user.email", "orchestrator@agenteresolve.local"], cwd=path)
    run(["git", "config", "user.name", "Agenteresolve Orchestrator"], cwd=path)
    run(["git", "add", "-A"], cwd=path)
    commit = run(
        ["git", "commit", "-m", f"{card.get('type', 'chore')}(card-{card.get('id')}): {card.get('title', 'task')}"],
        cwd=path,
    )
    if commit.returncode != 0:
        return {"ok": False, "error": "commit falhou: " + commit.stderr[-400:]}

    push = run(["git", "push", "-u", "origin", branch, "--force"], cwd=path)
    if push.returncode != 0:
        log(f"push failed card={card.get('id')}: {push.stderr[-200:]}")
        return {"ok": False, "error": "push falhou: " + push.stderr[-400:], "branch": branch}

    pr_url = create_pr(
        slug,
        branch,
        default_branch,
        f"{card.get('title', 'task')} (card #{card.get('id')})",
        output[-1500:] or "Implementado pelo orquestrador Agenteresolve.",
    )
    log(f"done card={card.get('id')} branch={branch} pr={pr_url}")

    return {"ok": True, "branch": branch, "pr_url": pr_url, "summary": output[-1500:]}


def review(payload):
    card = payload.get("card", {})
    repo = payload.get("repository", {})
    slug = repo.get("slug") or ""
    path = repo_dir(slug) if slug else WORKSPACE

    if not os.path.isdir(path):
        path = WORKSPACE

    prompt = (
        f"Revise as mudanças do card #{card.get('id')} ({card.get('title')}) no repositório '{slug}'. "
        "Aponte riscos, bugs, testes faltando e bloqueios de merge. Seja objetivo e curto."
    )

    _, output = run_agent(prompt, path)

    return {"ok": True, "summary": output[-2000:]}


class Handler(BaseHTTPRequestHandler):
    server_version = "agenteresolve-runner"

    def log_message(self, *args):  # keep logs quiet (no secrets)
        return

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.endswith("/ping"):
            return self._send(200, {"ok": True, "service": "agenteresolve-runner"})
        if self.path.endswith("/diag"):
            if RUNNER_TOKEN and self.headers.get("X-Runner-Token") != RUNNER_TOKEN:
                return self._send(401, {"ok": False, "error": "unauthorized"})
            version = run(["opencode", "--version"], timeout=30)
            return self._send(200, {
                "ok": True,
                "opencode": (version.stdout or version.stderr or "").strip(),
                "model": OPENCODE_MODEL or "(opencode.json)",
                "has_openrouter_key": bool(os.environ.get("OPENROUTER_API_KEY")),
                "has_github_token": bool(GITHUB_TOKEN),
                "agent_cmd_override": bool(AGENT_CMD),
                "workspace": WORKSPACE,
            })
        if self.path.endswith("/agentcheck"):
            if RUNNER_TOKEN and self.headers.get("X-Runner-Token") != RUNNER_TOKEN:
                return self._send(401, {"ok": False, "error": "unauthorized"})
            code, output = run_agent("Responda apenas: ok", WORKSPACE)
            return self._send(200, {"ok": code == 0, "exit": code, "output": output[-1500:]})
        return self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if RUNNER_TOKEN and self.headers.get("X-Runner-Token") != RUNNER_TOKEN:
            return self._send(401, {"ok": False, "error": "unauthorized"})

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"

        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"ok": False, "error": "invalid json"})

        try:
            if self.path.endswith("/implement"):
                return self._send(200, implement(payload))
            if self.path.endswith("/review"):
                return self._send(200, review(payload))
        except Exception as error:  # noqa: BLE001
            return self._send(500, {"ok": False, "error": str(error)})

        return self._send(404, {"ok": False, "error": "not found"})


def main():
    if not RUNNER_TOKEN:
        print("runner: RUNNER_TOKEN não definido; recusando subir.", file=sys.stderr)
        sys.exit(1)

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"runner: listening on 127.0.0.1:{PORT}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
