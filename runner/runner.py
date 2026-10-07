#!/usr/bin/env python3
"""Agenteresolve coding runner.

HTTP service the orchestrator (website) calls to implement/review a card
inside the coder container. It clones/updates the target repository, creates a
branch, produces the changes (via the LLM config sent by the orchestrator, or
optionally via the opencode CLI), commits, pushes and opens a PR.

Endpoints:
    POST /implement  { card, repository, llm } -> { ok, branch, pr_url, summary }
    POST /review     { card, repository, llm } -> { ok, summary }
    GET  /ping
    GET  /diag       (X-Runner-Token)
    GET  /agentcheck (X-Runner-Token, X-OpenRouter-Key, X-Model)

Auth: header `X-Runner-Token` must equal RUNNER_TOKEN.
Only the Python standard library is used.
"""
import json
import os
import signal
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
AGENT_CMD = os.environ.get("RUNNER_AGENT_CMD", "")
PORT = int(os.environ.get("RUNNER_PORT", "8090"))
AGENT_TIMEOUT = int(os.environ.get("RUNNER_AGENT_TIMEOUT", "900"))


def config():
    return {
        "home": os.environ.get("HOME", "/home/opencode"),
        "workspace": os.environ.get("WORKSPACE_DIR", os.path.join(os.environ.get("HOME", "/home/opencode"), "agenteresolve")),
        "runner_token": os.environ.get("RUNNER_TOKEN", ""),
        "github_token": os.environ.get("GITHUB_TOKEN", ""),
        "github_org": os.environ.get("GITHUB_ORG", "alex-pimentel"),
        "opencode_model": os.environ.get("OPENCODE_MODEL", ""),
        "agent_cmd": os.environ.get("RUNNER_AGENT_CMD", ""),
        "agent_mode": os.environ.get("RUNNER_AGENT_MODE", "llm"),
        "skip_push": os.environ.get("RUNNER_SKIP_PUSH", "0") == "1",
        "gate": os.environ.get("RUNNER_GATE", "0") == "1",
        "max_iterations": int(os.environ.get("RUNNER_MAX_ITERATIONS", "2")),
        "port": int(os.environ.get("RUNNER_PORT", "8090")),
        "agent_timeout": int(os.environ.get("RUNNER_AGENT_TIMEOUT", "900")),
    }


BRANCH_PREFIX = {
    "feature": "feature",
    "fix": "fix",
    "refactor": "refactor",
    "chore": "chore",
    "doc": "docs",
}


def log(message):
    print(f"runner: {message}", file=sys.stderr, flush=True)


def run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def repo_dir(slug):
    return os.path.join(WORKSPACE, slug)


def repo_name_from(github_url, slug):
    """Real GitHub repo name (from the URL), falling back to the board slug."""
    if github_url:
        base = github_url.rstrip("/").split("/")[-1]
        if base.endswith(".git"):
            base = base[:-4]
        if base:
            return base
    return slug


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


def repo_context(path):
    listing = run(["git", "ls-files"], cwd=path).stdout.splitlines()[:120]
    readme = ""
    for name in ("README.md", "README", "readme.md"):
        full = os.path.join(path, name)
        if os.path.isfile(full):
            with open(full, encoding="utf-8", errors="replace") as handle:
                readme = handle.read()[:2000]
            break
    return "Arquivos do repositório:\n" + "\n".join(listing) + "\n\nREADME (trecho):\n" + readme


def llm_chat(llm, messages, max_tokens=2500):
    base = (llm.get("base_url") or "").rstrip("/")
    key = llm.get("api_key")
    model = llm.get("model")
    if not base or not model:
        raise RuntimeError("llm.base_url/model ausentes")

    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }).encode()

    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key

    request = urllib.request.Request(base + "/chat/completions", data=body, method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.load(response)

    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or message.get("reasoning") or message.get("reasoning_content") or ""
    return content


def extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise RuntimeError("LLM não retornou JSON: " + text[:160])
    return json.loads(text[start:end + 1])


def safe_path(base, relative):
    candidate = os.path.normpath(os.path.join(base, relative))
    if not candidate.startswith(os.path.normpath(base) + os.sep):
        raise RuntimeError("caminho inválido: " + relative)
    return candidate


def run_agent(prompt, cwd, env=None, model=None):
    cfg = config()
    if cfg["agent_cmd"]:
        cmd = cfg["agent_cmd"].split() + [prompt]
    else:
        cmd = ["opencode", "run", "--auto"]
        chosen = model or cfg["opencode_model"]
        if chosen:
            cmd += ["--model", chosen]
        cmd += [prompt]

    log(f"agent cmd: {' '.join(cmd[:6])} ...")

    process = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=cfg["agent_timeout"])
        output = (stdout or "")[-4000:] + (stderr or "")[-2000:]
        return process.returncode, output
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        stdout, stderr = process.communicate()
        partial = ((stdout or "") + (stderr or ""))[-1500:]
        log(f"agent timeout after {cfg['agent_timeout']}s")
        return 124, "TIMEOUT: " + partial


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
        if error.code == 422:
            return None
        raise RuntimeError(f"PR HTTP {error.code}")


def implement(payload):
    card = payload.get("card", {})
    repo = payload.get("repository", {})
    llm = payload.get("llm") or {}
    cfg = config()
    slug = repo.get("slug") or ""
    if not slug:
        return {"ok": False, "error": "repository.slug ausente"}

    default_branch = repo.get("default_branch") or "main"
    name = repo_name_from(repo.get("github_url"), slug)
    log(f"implement start card={card.get('id')} repo={name}")
    path = ensure_repo(name, repo.get("github_url"), default_branch)

    prefix = BRANCH_PREFIX.get(card.get("type"), "feature")
    branch = f"{prefix}/card-{card.get('id')}"
    run(["git", "checkout", "-B", branch], cwd=path)

    if cfg["agent_mode"] == "opencode":
        summary = run_agent_implement(card, path, llm)
        if summary is None:
            return {"ok": False, "error": "Agente opencode falhou (ver logs do runner)."}
    else:
        summary = run_llm_implement(card, path, llm)
        if isinstance(summary, dict):
            return summary

    status = run(["git", "status", "--porcelain"], cwd=path).stdout.strip()
    if not status:
        return {"ok": False, "error": "Nenhuma alteração aplicada."}

    run(["git", "config", "user.email", "orchestrator@agenteresolve.local"], cwd=path)
    run(["git", "config", "user.name", "Agenteresolve Orchestrator"], cwd=path)
    run(["git", "add", "-A"], cwd=path)
    commit = run(
        ["git", "commit", "-m", f"{card.get('type', 'chore')}(card-{card.get('id')}): {card.get('title', 'task')}"],
        cwd=path,
    )
    if commit.returncode != 0:
        return {"ok": False, "error": "commit falhou: " + commit.stderr[-400:]}

    pr_url = None
    if not cfg["skip_push"]:
        push = run(["git", "push", "-u", "origin", branch, "--force"], cwd=path)
        if push.returncode != 0:
            return {"ok": False, "error": "push falhou: " + push.stderr[-400:], "branch": branch}
        pr_url = create_pr(
            name, branch, default_branch,
            f"{card.get('title', 'task')} (card #{card.get('id')})",
            summary or "Implementado pelo orquestrador Agenteresolve.",
        )

    log(f"done card={card.get('id')} branch={branch} pr={pr_url}")
    return {"ok": True, "branch": branch, "pr_url": pr_url, "summary": summary}


def agent_task_prompt(card, path):
    task = (
        f"Tarefa #{card.get('id')} ({card.get('type')}): {card.get('title')}\n"
        f"Descrição:\n{card.get('description') or '(sem descrição)'}\n"
    )
    return (
        "Você é um engenheiro de software sênior. Implemente a tarefa no repositório atual, "
        "de forma mínima e completa, seguindo as convenções do projeto. Edite os arquivos "
        "diretamente. Rode os testes/lint relevantes antes de terminar. Não faça commit nem push; "
        "o orquestrador cuidará disso. Ao final, responda com um resumo curto.\n\n"
        + task + "\n\n" + repo_context(path)
    )


def run_agent_implement(card, path, llm):
    env, model = agent_env_and_model(llm)
    code, output = run_agent(agent_task_prompt(card, path), cwd=path, env=env, model=model)
    if code != 0:
        log(f"opencode agent failed card={card.get('id')} code={code}")
        return None
    return output[-1500:]


def run_llm_implement(card, path, llm):
    task = (
        f"Tarefa #{card.get('id')} ({card.get('type')}): {card.get('title')}\n"
        f"Descrição:\n{card.get('description') or '(sem descrição)'}\n"
    )

    messages = [
        {"role": "system", "content": (
            "Você é um engenheiro de software sênior. Implemente a tarefa de forma completa e mínima, "
            "seguindo as convenções do projeto. Responda SOMENTE com JSON puro no formato: "
            '{"summary": "resumo curto", "files": [{"path": "caminho/relativo", "content": "conteúdo completo do arquivo"}]}. '
            "Inclua o conteúdo COMPLETO de cada arquivo criado ou alterado. Não use cercas de código."
        )},
        {"role": "user", "content": task + "\n\n" + repo_context(path)},
    ]

    try:
        content = llm_chat(llm, messages)
        data = extract_json(content)
    except Exception as error:  # noqa: BLE001
        log(f"llm failed card={card.get('id')}: {error}")
        return {"ok": False, "error": f"LLM falhou: {error}"}

    files = data.get("files") or []
    if not files:
        return {"ok": False, "error": "LLM não propôs arquivos.", "summary": str(data.get("summary", ""))[:800]}

    for entry in files:
        rel = entry.get("path")
        body = entry.get("content")
        if not rel or body is None:
            continue
        target = safe_path(path, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(body)

    return str(data.get("summary") or "")[:1500]


def review(payload):
    card = payload.get("card", {})
    repo = payload.get("repository", {})
    llm = payload.get("llm") or {}
    slug = repo.get("slug") or ""
    path = repo_dir(repo_name_from(repo.get("github_url"), slug)) if slug else WORKSPACE

    if not os.path.isdir(path):
        path = WORKSPACE

    default_branch = repo.get("default_branch") or "main"
    diff = run(["git", "diff", f"origin/{default_branch}...HEAD"], cwd=path).stdout[:6000]

    messages = [
        {"role": "system", "content": "Você é um revisor de código. Aponte riscos, bugs, testes faltando e bloqueios de merge. Seja objetivo e curto."},
        {"role": "user", "content": f"Card #{card.get('id')}: {card.get('title')}\n\nDiff:\n{diff or '(sem diff)'}"},
    ]

    try:
        content = llm_chat(llm, messages, max_tokens=1200)
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "summary": f"Revisão falhou: {error}"}

    return {"ok": True, "summary": content[-2000:]}


def agent_env_and_model(llm):
    llm = llm or {}
    env = dict(os.environ)
    api_key = llm.get("api_key")
    model = llm.get("model")
    oc_model = None
    if isinstance(model, str) and model:
        if "/" in model:
            oc_model = model
        else:
            oc_model = f"openrouter/{model}"
    if isinstance(api_key, str) and api_key:
        if oc_model and oc_model.startswith("opencode/"):
            env["OPENCODE_API_KEY"] = api_key
        else:
            env["OPENROUTER_API_KEY"] = api_key
    return env, oc_model


class Handler(BaseHTTPRequestHandler):
    server_version = "agenteresolve-runner"

    def log_message(self, *args):
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
                "workspace": WORKSPACE,
            })
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
            log(f"error: {error}")
            return self._send(500, {"ok": False, "error": str(error)})

        return self._send(404, {"ok": False, "error": "not found"})


def main():
    if not RUNNER_TOKEN:
        print("runner: RUNNER_TOKEN não definido; recusando subir.", file=sys.stderr)
        sys.exit(1)

    host = os.environ.get("RUNNER_HOST", "127.0.0.1")
    port = int(os.environ.get("RUNNER_PORT", str(PORT)))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"runner: listening on {host}:{port}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
