# Server Manager

A small self-hosted web dashboard for the machines on your LAN:

- Add servers by IP or hostname. Each one shows an online/offline dot (a TCP check on its SSH port).
- Live stats over SSH: CPU, memory, disk, uptime and load.
- Write your own bash scripts and run them on one or many servers at once, with output streamed live.
- Every run is saved to History with its output and exit code.
- The UI is protected by a password, which you set on first launch.

## Run

```bash
./run.sh                 # creates .venv on first run, serves on http://0.0.0.0:8080
SM_PORT=9000 ./run.sh    # different port
SM_HOST=127.0.0.1 ./run.sh   # only this machine, not the LAN
```

Or with Docker:

```bash
docker compose up -d     # data persisted in ./data
```

For a permanent install, see `server-manager.service` (systemd).

## Moving to another machine

All servers, scripts and settings live in **`data/config.json`**. Run history is
kept separately in `data/history.db`. Either:

- copy the `data/` folder to the new machine, which keeps the login password too, or
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
Arguments you type in the Run tab become `$1`, `$2`, … (shell-quoted). For sudo,
the user needs passwordless sudo (`NOPASSWD`) because scripts run without a TTY.

## Notes

- Host keys are not verified. This is meant for trusted LAN machines.
- Stats use `/proc`, so they work on Linux targets only. Scripts work on anything with bash.
