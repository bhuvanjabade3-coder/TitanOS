# Security

## Threat model

TITAN gives an AI model the ability to act on your computer. The main risks:
the model doing something destructive (by mistake or because a web page or file
it read told it to), another program or web page driving TITAN's API, and
plugins overreaching. The design goal is that **nothing irreversible, privileged
or outward-facing happens without you approving that specific action**.

## Controls

| Control | Detail |
|---|---|
| Loopback only | Core binds 127.0.0.1. |
| API token | Every `/api` and `/ws` request needs the token from `api_token` (mode 600). Compared in constant time. |
| One registry | UI, assistant, voice and plugins share one permission-checked entry point. |
| Risk gates | Low runs; medium asks unless you allowed that category; **high always asks**. |
| Always high | Permanent deletion, `sudo`/privileged or destructive shell commands, piping into a shell, command substitution, killing processes, writing to shell dotfiles / autostart / systemd / `.desktop` / `~/.local/bin`, changing TITAN's own permissions (when asked by the assistant). |
| Approvals | Store exact parameters, single-use, expire after 15 minutes, claimed atomically. |
| File confinement | Home directory only; `.ssh`, `.gnupg`, browser profiles, keyrings, cloud credentials and TITAN's data directory are off limits; symlinks resolved first; no silent overwrite. |
| Terminal | Allowlist classifier; child processes never inherit `ANTHROPIC_API_KEY`, `TITAN_*` or other secret-looking variables. |
| Web fetch | http(s) only, no embedded credentials, private/loopback/link-local addresses refused on every redirect hop; 401/403 are reported, not worked around. |
| Input automation | Asks by default; session-control shortcuts are refused. |
| Secrets | API key only from the environment, held as `SecretStr`, redacted from logs, never returned by the API. No passwords are stored anywhere. |
| Memory | The assistant can only propose a memory; you approve it. Everything is reviewable, editable, deletable, exportable. |
| Audit log | Every action attempt with actor and outcome (file contents truncated). |
| Service | systemd *user* unit with `NoNewPrivileges`; the installer refuses to run as root. |

TITAN does not implement, and the assistant is instructed not to attempt:
bypassing logins or CAPTCHAs, reading credential stores, covert monitoring, or
acting against systems you do not own.

## Known limitations (read these)

- **Plugins are not sandboxed.** They are Python running inside Core. The
  permission system stops a well-behaved plugin from overreaching through
  TITAN's API; it cannot stop hostile code. Enable only plugins you trust.
- **The command classifier is a heuristic.** It is conservative (unknown → ask),
  and approval shows you the exact command, but a command you approve can do
  anything your user can do.
- **Same-user processes are trusted.** Anything running as you can read the
  token file. TITAN protects against web pages and other users, not against
  malware already running in your account.
- **Prompt injection.** A page or file the assistant reads may contain
  instructions. Gates and approvals bound the damage; they do not make the model
  immune. Read approval prompts before approving.
- `allow` on the terminal category lets medium-risk commands (e.g. `pip install`,
  `git commit`) run unprompted. Leave it on the default unless you want that.
- Not yet independently reviewed or penetration-tested.

## Reporting

Open a private security advisory on the GitHub repository.
