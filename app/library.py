"""Premade scripts users can copy into their own script list.

Scripts that need root call `sudo` when not already root. The runner's sudo
wrapper uses the server's sudo password if one is configured, and fails fast
otherwise (see ssh.SUDO_WRAPPER).
"""

SUDO = 'SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"\n'

LIBRARY = [
    # --- updates ---
    {
        "category": "Updates",
        "name": "Update all packages",
        "description": "Upgrades every package with apt, dnf, pacman, zypper or apk (detected automatically).",
        "body": SUDO + r"""set -e
if command -v apt-get >/dev/null; then
  $SUDO apt-get update && DEBIAN_FRONTEND=noninteractive $SUDO apt-get -y upgrade
elif command -v dnf >/dev/null; then
  $SUDO dnf -y upgrade
elif command -v pacman >/dev/null; then
  $SUDO pacman -Syu --noconfirm
elif command -v zypper >/dev/null; then
  $SUDO zypper -n update
elif command -v apk >/dev/null; then
  $SUDO apk upgrade --update
else
  echo "No supported package manager found" >&2; exit 1
fi
[ -f /var/run/reboot-required ] && echo "*** Reboot required ***"
exit 0""",
    },
    {
        "category": "Updates",
        "name": "Check for updates",
        "description": "Lists available package updates without installing anything.",
        "body": r"""if command -v apt >/dev/null; then
  apt list --upgradable 2>/dev/null | tail -n +2
elif command -v dnf >/dev/null; then
  dnf -q check-update; true
elif command -v checkupdates >/dev/null; then
  checkupdates
elif command -v pacman >/dev/null; then
  pacman -Qu
elif command -v zypper >/dev/null; then
  zypper -q list-updates
elif command -v apk >/dev/null; then
  apk version -l '<'
fi
[ -f /var/run/reboot-required ] && echo "*** Reboot required ***"
exit 0""",
    },
    {
        "category": "Updates",
        "name": "Reboot in 1 minute",
        "description": "Schedules a reboot. Cancel it on the server with: shutdown -c",
        "body": SUDO + r"""$SUDO shutdown -r +1 "Reboot scheduled by Rackoon" && echo "Reboot scheduled in 1 minute" """,
    },
    # --- system ---
    {
        "category": "System",
        "name": "Top processes",
        "description": "The 15 processes using the most CPU and the most memory.",
        "body": r"""echo "== By CPU =="
ps -eo pid,user,%cpu,%mem,etime,comm --sort=-%cpu | head -16
echo
echo "== By memory =="
ps -eo pid,user,%mem,rss,etime,comm --sort=-%mem | head -16""",
    },
    {
        "category": "System",
        "name": "Memory usage",
        "description": "RAM and swap usage with a breakdown.",
        "body": r"""free -h
echo
grep -E '^(MemTotal|MemAvailable|Buffers|Cached|SwapTotal|SwapFree|Dirty)' /proc/meminfo""",
    },
    {
        "category": "System",
        "name": "Recent errors in the journal",
        "description": "Error-level log messages from the last hour. Argument: time window, e.g. '24 hours ago'.",
        "body": r"""SINCE="${1:-1 hour ago}"
journalctl -p err --since "$SINCE" --no-pager -q | tail -n 100 || dmesg --level=err,crit 2>/dev/null | tail -n 50""",
    },
    {
        "category": "System",
        "name": "Hardware info",
        "description": "CPU, memory, block devices and PCI/USB devices.",
        "body": r"""lscpu 2>/dev/null | head -20
echo
lsblk -o NAME,SIZE,TYPE,MODEL,FSTYPE,MOUNTPOINT 2>/dev/null
echo
command -v lspci >/dev/null && lspci
echo
command -v lsusb >/dev/null && lsusb
exit 0""",
    },
    # --- services ---
    {
        "category": "Services",
        "name": "Failed services",
        "description": "systemd units that are in a failed state.",
        "body": r"""systemctl --failed --no-pager""",
    },
    {
        "category": "Services",
        "name": "Service status",
        "description": "Status and recent log lines of a service. Argument: service name (e.g. nginx).",
        "body": r"""[ -z "$1" ] && { echo "Usage: give the service name as argument" >&2; exit 1; }
systemctl status "$1" --no-pager -l
echo
journalctl -u "$1" -n 30 --no-pager""",
    },
    {
        "category": "Services",
        "name": "Restart service",
        "description": "Restarts a systemd service and shows its status. Argument: service name.",
        "body": SUDO + r"""[ -z "$1" ] && { echo "Usage: give the service name as argument" >&2; exit 1; }
$SUDO systemctl restart "$1" && systemctl status "$1" --no-pager -l""",
    },
    # --- docker ---
    {
        "category": "Docker",
        "name": "List containers",
        "description": "All containers with status, plus their current resource usage.",
        "body": r"""docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}'
echo
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}'""",
    },
    {
        "category": "Docker",
        "name": "Container logs",
        "description": "Last 100 log lines of a container. Argument: container name.",
        "body": r"""[ -z "$1" ] && { echo "Usage: give the container name as argument" >&2; exit 1; }
docker logs --tail 100 --timestamps "$1" 2>&1""",
    },
    {
        "category": "Docker",
        "name": "Restart container",
        "description": "Restarts a container. Argument: container name.",
        "body": r"""[ -z "$1" ] && { echo "Usage: give the container name as argument" >&2; exit 1; }
docker restart "$1" && docker ps --filter "name=^$1$" --format 'table {{.Names}}\t{{.Status}}'""",
    },
    {
        "category": "Docker",
        "name": "Update compose project",
        "description": "Pulls new images and recreates the containers. Argument: directory containing docker-compose.yml.",
        "body": r"""set -e
cd "${1:?Usage: give the compose project directory as argument}"
docker compose pull
docker compose up -d --remove-orphans
docker image prune -f""",
    },
    {
        "category": "Docker",
        "name": "Clean up Docker",
        "description": "Removes stopped containers, unused networks, dangling images and build cache.",
        "body": r"""docker system df
echo
docker system prune -f
echo
docker system df""",
    },
    # --- disk ---
    {
        "category": "Disk",
        "name": "Biggest directories",
        "description": "Largest directories one level deep. Argument: path (default /).",
        "body": SUDO + r"""$SUDO du -xh --max-depth=1 "${1:-/}" 2>/dev/null | sort -rh | head -n 20""",
    },
    {
        "category": "Disk",
        "name": "Find large files",
        "description": "Files larger than a size. Arguments: path (default /) and size (default 500M).",
        "body": SUDO + r"""$SUDO find "${1:-/}" -xdev -type f -size +"${2:-500M}" -exec ls -lh {} + 2>/dev/null \
  | awk '{print $5, $9}' | sort -rh | head -n 30""",
    },
    {
        "category": "Disk",
        "name": "Free up disk space",
        "description": "Cleans the package cache and trims the systemd journal to 7 days.",
        "body": SUDO + r"""df -h /
echo
if command -v apt-get >/dev/null; then $SUDO apt-get -y autoremove && $SUDO apt-get clean
elif command -v dnf >/dev/null; then $SUDO dnf -y autoremove && $SUDO dnf clean all
elif command -v pacman >/dev/null; then $SUDO pacman -Sc --noconfirm
fi
command -v journalctl >/dev/null && $SUDO journalctl --vacuum-time=7d
echo
df -h /""",
    },
    {
        "category": "Disk",
        "name": "Disk health (SMART)",
        "description": "SMART health summary for every disk. Needs smartmontools installed.",
        "body": SUDO + r"""command -v smartctl >/dev/null || { echo "smartctl not installed (package: smartmontools)" >&2; exit 1; }
for d in $(lsblk -dno NAME,TYPE | awk '$2=="disk"{print $1}'); do
  echo "== /dev/$d =="
  $SUDO smartctl -H -i /dev/$d | grep -E 'Model|Serial|Capacity|overall-health|result'
  echo
done""",
    },
    # --- network ---
    {
        "category": "Network",
        "name": "Listening ports",
        "description": "Open TCP/UDP ports and the processes behind them.",
        "body": SUDO + r"""$SUDO ss -tulpn 2>/dev/null || ss -tuln""",
    },
    {
        "category": "Network",
        "name": "Public IP",
        "description": "The server's external IP address.",
        "body": r"""curl -fsS https://ifconfig.me 2>/dev/null || wget -qO- https://ifconfig.me
echo""",
    },
    {
        "category": "Network",
        "name": "Connectivity test",
        "description": "Pings a host and checks DNS resolution. Argument: host (default 1.1.1.1).",
        "body": r"""HOST="${1:-1.1.1.1}"
ping -c 4 -W 2 "$HOST"
echo
getent hosts example.com >/dev/null && echo "DNS: OK" || echo "DNS: FAILED" """,
    },
    # --- security ---
    {
        "category": "Security",
        "name": "Failed SSH logins",
        "description": "The most recent failed SSH login attempts and their top source IPs.",
        "body": SUDO + r"""LOG=$($SUDO journalctl -u ssh -u sshd --since "7 days ago" --no-pager -q 2>/dev/null || $SUDO cat /var/log/auth.log 2>/dev/null)
echo "$LOG" | grep -iE 'failed password|invalid user' | tail -n 20
echo
echo "== Top source IPs (7 days) =="
echo "$LOG" | grep -iE 'failed password|invalid user' | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort | uniq -c | sort -rn | head""",
    },
    {
        "category": "Security",
        "name": "Recent logins",
        "description": "Who logged in recently and who is logged in now.",
        "body": r"""echo "== Logged in now =="
who
echo
echo "== Recent logins =="
last -n 20 -w 2>/dev/null || echo "last not available" """,
    },
]
