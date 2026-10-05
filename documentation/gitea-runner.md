# Gitea Actions Runner — gitea-runner-dictation

Self-hosted runner for the parakeet-dictation Gitea Actions CI.

## Where it runs

CT 102 (`192.168.1.22`), Docker container `gitea-runner-dictation`.

| Property | Value |
|----------|-------|
| Forge | `https://gitea.home.lan/stefanlindqvist/parakeet-dictation` |
| Runner label | `dictation` |
| Deploy dir | `/srv/docker/runner-dictation/` on CT 102 |
| Job image | `catthehacker/ubuntu:act-latest` (Ubuntu 24.04) |
| act_runner image | `gitea/act_runner:latest` (Alpine) |

## Files

```
infra/runner-dictation/
├── docker-compose.yml   # service definition
├── config.yaml          # act_runner config (capacity 2, cache off)
└── entrypoint.sh        # CA cert install + register + daemon start
```

The `env` file (on CT 102 only, not in repo) holds `GITEA_RUNNER_REGISTRATION_TOKEN`.

## Deploy / update

```powershell
# Copy updated config to CT 102
& 'C:\Windows\System32\OpenSSH\scp.exe' -O -P 22 `
    infra/runner-dictation/config.yaml `
    root@192.168.1.22:/srv/docker/runner-dictation/config.yaml

# Restart to pick up changes
& 'C:\Windows\System32\OpenSSH\ssh.exe' root@192.168.1.22 `
    "docker compose -f /srv/docker/runner-dictation/docker-compose.yml up -d --force-recreate"
```

## Rotate registration token

```powershell
$token = (Get-Content 'C:\Users\stefa\.gitea_token' -Raw).Trim()
$reg = Invoke-RestMethod -SkipCertificateCheck -Method POST `
    -Uri "https://gitea.home.lan/api/v1/repos/stefanlindqvist/parakeet-dictation/actions/runners/registration-token" `
    -Headers @{ Authorization = "token $token" }
# Update /srv/docker/runner-dictation/env with new token, then restart
```

## Watch CI runs

Gitea REST recipes: global `~/.claude/CLAUDE.md` § Gitea (filter `/actions/runs` by `head_sha`).

## CI workflow design notes

- Ubuntu 24.04 enforces PEP 668 — always pass `--break-system-packages`.
- `onnxruntime-directml` and `pynput` are guarded `; sys_platform == 'win32'` — they have no Linux wheels.
- `security-audit` job scopes pip-audit to project deps only (not Ubuntu system packages) by extracting deps from `pyproject.toml` via `tomllib`.
- `config.yaml` must NOT have `container.options` with a docker socket bind — act_runner adds it automatically; duplicating it causes container launch failure.
