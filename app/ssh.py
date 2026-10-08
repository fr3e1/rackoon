"""SSH helpers: connecting, streaming script output, collecting stats."""

import asyncio
import shlex
import socket
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


# Each section starts with a "### Title" line; commands that don't exist on
# the target are skipped so empty sections can be dropped.
DETAILS_SCRIPT = r"""
has() { command -v "$1" >/dev/null 2>&1; }
sec() { echo "### $1"; }
sec "System"
echo "Hostname:  $(hostname)"
[ -r /etc/os-release ] && . /etc/os-release && echo "OS:        $PRETTY_NAME"
echo "Kernel:    $(uname -sr)"
echo "Arch:      $(uname -m)"
has systemd-detect-virt && echo "Virt:      $(systemd-detect-virt 2>/dev/null)"
[ -r /sys/devices/virtual/dmi/id/product_name ] && echo "Hardware:  $(cat /sys/devices/virtual/dmi/id/sys_vendor 2>/dev/null) $(cat /sys/devices/virtual/dmi/id/product_name)"
echo "Booted:    $(uptime -s 2>/dev/null)"
echo "Uptime:   $(uptime -p 2>/dev/null | sed 's/^up//')"
echo "Load:      $(cut -d' ' -f1-3 /proc/loadavg)"
echo "Timezone:  $(date +'%Z (%z)')"
sec "CPU"
if has lscpu; then lscpu | grep -E '^(Model name|CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|CPU max MHz|Virtualization|L3 cache)'; else grep -m1 'model name' /proc/cpuinfo; nproc; fi
sec "Memory"
free -h
sec "Disks"
df -hT -x tmpfs -x devtmpfs -x squashfs -x overlay -x efivarfs 2>/dev/null || df -h
has lsblk && { echo; lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT 2>/dev/null | grep -v loop; }
sec "Network"
if has ip; then ip -br addr | grep -v '^lo'; echo; ip route | grep default; else ifconfig 2>/dev/null; fi
[ -r /etc/resolv.conf ] && grep ^nameserver /etc/resolv.conf
sec "Listening ports"
if has ss; then ss -tulnH | awk '{print $1, $5}' | sort -u -k2; elif has netstat; then netstat -tuln; fi
sec "Top processes (CPU)"
ps -eo pid,user,%cpu,%mem,comm --sort=-%cpu 2>/dev/null | head -11
sec "Top processes (memory)"
ps -eo pid,user,%mem,rss,comm --sort=-%mem 2>/dev/null | head -11
sec "Temperatures"
if has sensors; then sensors 2>/dev/null | grep -E '°C' | head -20
else for z in /sys/class/thermal/thermal_zone*; do [ -r "$z/temp" ] && echo "$(cat $z/type): $(( $(cat $z/temp) / 1000 ))°C"; done; fi
sec "Failed services"
has systemctl && { out=$(systemctl --failed --no-legend --plain 2>/dev/null); echo "${out:-none}"; }
sec "Docker containers"
has docker && docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>&1
sec "Logged-in users"
who
sec "Recent logins"
has last && last -n 10 -w 2>/dev/null | grep -v '^$' | grep -v '^wtmp'
"""


# Prepended to every script. With a password, `sudo` goes through an askpass
# helper that prints $SM_SUDO_PW. The password arrives as the first stdin line
# (bash reads its script from stdin one line at a time, so `read` takes exactly
# that line), so it never appears in a command line, a file or the output.
# Without one, `sudo -n` fails at once instead of waiting for a prompt that can
# never be answered.
SUDO_PASSWORD_SETUP = r"""export SM_SUDO_PW
SM_ASKPASS=$(mktemp) && chmod 700 "$SM_ASKPASS"
cat > "$SM_ASKPASS" <<'SM_EOF'
#!/bin/sh
printf '%s\n' "$SM_SUDO_PW"
SM_EOF
export SUDO_ASKPASS="$SM_ASKPASS"
trap 'rm -f "$SM_ASKPASS"' EXIT
"""
SUDO_WRAPPER = r"""sudo() {
  [ "$1" = "-n" ] && shift
  if [ -n "${SM_SUDO_PW-}" ]; then command sudo -A "$@"; else command sudo -n "$@"; fi
}
export -f sudo
"""


def script_stdin(body: str, sudo_password: str | None) -> str:
    parts = []
    if sudo_password:
        if "\n" in sudo_password or "\r" in sudo_password:
            raise ValueError("Sudo password can't contain line breaks")
        parts += ["IFS= read -r SM_SUDO_PW\n", sudo_password + "\n", SUDO_PASSWORD_SETUP]
    parts += [SUDO_WRAPPER, body.replace("\r\n", "\n")]
    return "".join(parts)


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
    sudo_password: str | None = None,
) -> int | None:
    """Run `body` with bash on the server, streaming (stream, text) chunks.

    The script is piped over stdin so no temp file is left behind.
    `sudo` inside the script uses `sudo_password` when given (see SUDO_WRAPPER).
    Returns the exit code.
    """
    stdin = script_stdin(body, sudo_password)
    cmd = "bash -s"
    if args.strip():
        cmd += " -- " + " ".join(shlex.quote(a) for a in shlex.split(args))
    async with connect(server, timeout) as conn:
        async with conn.create_process(cmd) as proc:
            proc.stdin.write(stdin)
            proc.stdin.write_eof()

            async def pump(stream, name):
                while chunk := await stream.read(4096):
                    await on_output(name, chunk)

            try:
                await asyncio.gather(pump(proc.stdout, "stdout"), pump(proc.stderr, "stderr"))
                result = await proc.wait()
            except asyncio.CancelledError:
                # Best effort: needs OpenSSH 8.1+ on the server. Closing the
                # connection afterwards also ends anything reading stdin/stdout.
                try:
                    proc.send_signal("TERM")
                except Exception:
                    pass
                raise
            return result.exit_status


async def get_details(server: dict, timeout: int = 10) -> list[dict]:
    async with connect(server, timeout) as conn:
        result = await conn.run("bash -s", input=DETAILS_SCRIPT, check=False)
    sections: list[dict] = []
    for line in str(result.stdout).splitlines():
        if line.startswith("### "):
            sections.append({"title": line[4:], "lines": []})
        elif sections:
            sections[-1]["lines"].append(line)
    return [
        {"title": s["title"], "body": "\n".join(s["lines"]).strip("\n")}
        for s in sections
        if any(l.strip() for l in s["lines"])
    ]


def wake_on_lan(mac: str, broadcast: str = "255.255.255.255") -> None:
    hex_mac = "".join(c for c in mac if c.isalnum())
    if len(hex_mac) != 12:
        raise ValueError(f"Invalid MAC address: {mac}")
    packet = b"\xff" * 6 + bytes.fromhex(hex_mac) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, 9))


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
