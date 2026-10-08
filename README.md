# 🦝 Rackoon

*A tiny raccoon that tends your server rack.*

Rackoon is a small self-hosted web dashboard for the machines on your LAN:

- Add servers by IP or hostname. Each one shows an online/offline dot (a TCP check on its SSH port).
- Live stats over SSH: CPU, memory, disk, uptime and load.
- Write your own bash scripts and run them on one or many servers at once, with output streamed live.
- **Details** view per server: OS, hardware, CPU, memory, disks, network, listening ports, top processes, temperatures, failed services, Docker containers and logins.
- **Script library** with 24 premade scripts (updates, services, Docker, disk cleanup, SMART, network, security) that you can copy into your scripts with one click.
- Ad-hoc commands without saving a script, plus a Stop button for running scripts.
- Filter servers by name, IP or tag, and use Wake-on-LAN for servers with a MAC address.
- Themes: System, Light and Dark use the Rackoon ash-and-amber palette; Nord, Dracula, Gruvbox and Solarized are also available. The choice is saved per browser.
- Every run is saved to History with its output and exit code.
- The UI is protected by a password, which you set on first launch.

## Run

```bash
./run.sh                 # creates .venv on first run, serves on http://0.0.0.0:8080
RACKOON_PORT=9000 ./run.sh    # different port
RACKOON_HOST=127.0.0.1 ./run.sh   # only this machine, not the LAN
```

Or with Docker:

```bash
docker compose up -d     # data kept in the "rackoon-data" Docker volume
```

For a permanent install, see `rackoon.service` (systemd).

## Moving to another machine

Your data is stored **outside the project folder**, so it can't end up on GitHub:

```
~/.local/share/rackoon/      (or $XDG_DATA_HOME/rackoon, or $RACKOON_DATA_DIR)
├── config.json   servers, scripts, settings, login (chmod 600)
└── history.db    run history
```

The folder itself is `chmod 700`. Data from older locations (`./data`, `~/.local/share/server-manager`) is
moved automatically on first start. `.gitignore` also blocks `data/`, databases,
`config.json`, exports and certificates as a backup.

To move to another machine, either:

- copy that folder to the new machine, which keeps the login password too, or
- use **Settings → Export config**, then **Import** on the new machine. The export doesn't include the login password.

The config file contains SSH passwords/keys in plain text, so keep it private.
It is written with `chmod 600`.

## Server authentication options

| Option | Use when |
|---|---|
| SSH agent / ~/.ssh keys | Your key is already in the server's `authorized_keys` (the keys of the machine running the manager are used) |
| Password | Password login is enabled on the server |
| Paste private key | You want the key stored in the config, so it moves with it |
| Key file path | The key file sits on the manager's machine |

## Scripts

Scripts are piped to `bash -s` on the target server, so nothing is copied to its disk.
Arguments you type in the Run tab become `$1`, `$2`, … (shell-quoted).

## Sudo passwords

Each server has a **Sudo password** setting:

| Mode | Where the password comes from |
|---|---|
| Not needed | Root login, `NOPASSWD`, or no sudo use. `sudo` fails right away instead of hanging |
| Same as the SSH password | The server's SSH login password (Password authentication only) |
| Save a sudo password | Stored in `config.json` like the other credentials |
| Ask every time | You type it in the Run tab. It's used for that run only and never stored |

Scripts just call `sudo …` as normal. Behind the scenes:

- The password goes to the server as the first line of the script's stdin, never in a command line, so it doesn't show in `ps`.
- `sudo` reads it through a `SUDO_ASKPASS` helper. The helper file holds no secret and is deleted when the script ends.
- It works in child processes too (`bash -c 'sudo …'`).
- If a script prints the password, it's replaced with `********` in the live output and in History.

## HTTPS

Passwords typed in the browser travel to the manager over plain HTTP unless you enable TLS.
On anything but a trusted home network, use a certificate:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=rackoon" \
  -keyout ~/.local/share/rackoon/key.pem -out ~/.local/share/rackoon/cert.pem
RACKOON_SSL_CERT=~/.local/share/rackoon/cert.pem RACKOON_SSL_KEY=~/.local/share/rackoon/key.pem ./run.sh
```

Then open `https://<ip>:8080`. The browser will warn about the self-signed certificate once. The login cookie is marked `Secure` automatically over HTTPS.

## Notes

- Host keys are not verified. This is meant for trusted LAN machines.
- Wake-on-LAN sends a UDP broadcast, so under Docker it needs `network_mode: host`.
- Stop sends SIGTERM (OpenSSH 8.1+ on the server) and closes the SSH session.
- Stats use `/proc`, so they work on Linux targets only. Scripts work on anything with bash.

## AI usage disclosure

This project was built with help from AI coding assistants, mainly
[Claude Code](https://claude.com/claude-code) (Anthropic).

- **Code:** [FILL IN: how much of the code was AI-written vs. written by you]
- **Repo prep:** The license, commit history cleanup, GitHub publishing steps and the UI theme were done with Claude Code.
- **Review:** I reviewed every change and tested the app on my own LAN. Bugs are still possible, especially in the SSH and credential handling, so read the code before you trust it with real servers.

Commits made with AI help have a `Co-Authored-By: Claude` line.
