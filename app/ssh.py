"""SSH helpers: connecting, streaming script output, collecting stats."""

import asyncio
import shlex
from collections.abc import Awaitable, Callable

import asyncssh

# Read from /proc so it works on any Linux box without extra tools.
STATS_SCRIPT = r"""
read -r _ u1 n1 s1 i1 w1 x1 y1 z1 _ < /proc/stat
sleep 0.5
read -r _ u2 n2 s2 i2 w2 x2 y2 z2 _ < /proc/stat
t1=$((u1+n1+s1+i1+w1+x1+y1+z1)); t2=$((u2+n2+s2+i2+w2+x2+y2+z2))
echo "cpu=$(( (100*((t2-t1)-(i2-i1)-(w2-w1))) / ((t2-t1) > 0 ? (t2-t1) : 1) ))"
echo "cores=$(nproc 2>/dev/null || echo 1)"
awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{print "mem_total=" t*1024; print "mem_used=" (t-a)*1024}' /proc/meminfo
df -PB1 / | awk 'NR==2{print "disk_total=" $2; print "disk_used=" $3}'
echo "uptime=$(cut -d' ' -f1 /proc/uptime)"
echo "load=$(cut -d' ' -f1-3 /proc/loadavg)"
echo "hostname=$(hostname)"
. /etc/os-release 2>/dev/null && echo "os=$PRETTY_NAME"
"""


def _connect_kwargs(server: dict, timeout: int) -> dict:
    kw = {
        "host": server["host"],
        "port": int(server.get("port") or 22),
        "username": server.get("username") or None,
        # Host keys are not verified: this is meant for trusted LAN machines
        # whose keys change whenever they are reinstalled.
        "known_hosts": None,
        "connect_timeout": timeout,
    }
    method = server.get("auth", "default")
    if method == "password":
        kw["password"] = server.get("password") or ""
        kw["client_keys"] = None
    elif method == "key_data" and server.get("key_data"):
        kw["client_keys"] = [
            asyncssh.import_private_key(server["key_data"], server.get("key_passphrase") or None)
        ]
    elif method == "key_path" and server.get("key_path"):
        kw["client_keys"] = [server["key_path"]]
        if server.get("key_passphrase"):
            kw["passphrase"] = server["key_passphrase"]
    # "default": asyncssh tries ssh-agent and ~/.ssh/id_* on its own.
    return kw


def connect(server: dict, timeout: int = 10):
    return asyncssh.connect(**_connect_kwargs(server, timeout))


async def check_online(host: str, port: int, timeout: float = 3) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def run_script(
    server: dict,
    body: str,
    args: str,
    on_output: Callable[[str, str], Awaitable[None]],
    timeout: int = 10,
) -> int | None:
    """Run `body` with bash on the server, streaming (stream, text) chunks.

    The script is piped over stdin so no temp file is left behind.
    Returns the exit code.
    """
    cmd = "bash -s"
    if args.strip():
        cmd += " -- " + " ".join(shlex.quote(a) for a in shlex.split(args))
    async with connect(server, timeout) as conn:
        async with conn.create_process(cmd) as proc:
            proc.stdin.write(body.replace("\r\n", "\n"))
            proc.stdin.write_eof()

            async def pump(stream, name):
                while chunk := await stream.read(4096):
                    await on_output(name, chunk)

            await asyncio.gather(pump(proc.stdout, "stdout"), pump(proc.stderr, "stderr"))
            result = await proc.wait()
            return result.exit_status


async def get_stats(server: dict, timeout: int = 10) -> dict:
    async with connect(server, timeout) as conn:
        result = await conn.run("bash -s", input=STATS_SCRIPT, check=False)
    stats: dict = {}
    for line in str(result.stdout).splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        try:
            stats[key] = float(value) if key not in ("load", "hostname", "os") else value
        except ValueError:
            stats[key] = value
    return stats
