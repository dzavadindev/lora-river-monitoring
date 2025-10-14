#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  decode-esp32-backtrace.sh <path/to/firmware.elf> "<backtrace text>"
  decode-esp32-backtrace.sh <path/to/firmware.elf>    # and paste backtrace on stdin

Examples:
  decode-esp32-backtrace.sh ./build/firmware.ino.elf \
    "0x4038083b:0x3fce9fb0 0x420026e9:0x3fce9fd0 0x40050c32:0x3fce9ff0 0x400552f3:0x3fcea010"

  echo '0x4038083b:0x3fce9fb0 0x420026e9:0x3fce9fd0 ...' \
    | decode-esp32-backtrace.sh ./build/firmware.ino.elf
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 1; }

ELF="$1"
BT="${2:-}"

[[ -f "$ELF" ]] || { echo "ERR: ELF not found: $ELF" >&2; exit 2; }

# Pick an addr2line implementation
A2L=""
for c in xtensa-esp32s3-elf-addr2line xtensa-esp32s2-elf-addr2line xtensa-esp32-elf-addr2line addr2line; do
  if command -v "$c" >/dev/null 2>&1; then A2L="$c"; break; fi
done
[[ -n "$A2L" ]] || { echo "ERR: no addr2line found in PATH" >&2; exit 3; }

# Get backtrace text (arg2 or stdin)
if [[ -z "$BT" ]]; then
  # read everything from stdin (user can paste and Ctrl-D)
  BT="$(cat || true)"
fi
[[ -n "$BT" ]] || { echo "ERR: no backtrace provided" >&2; exit 4; }

# Extract program counters:
# - grab all 0x... tokens
# - keep only code-space addresses (0x4...), skipping SPs like 0x3f...
# - de-duplicate while preserving order
mapfile -t ADDRS < <(
  grep -o '0x[0-9a-fA-F]\+' <<<"$BT" \
  | awk '/^0x4/ { if (!seen[$0]++) print $0 }'
)

(( ${#ADDRS[@]} > 0 )) || { echo "ERR: no code addresses (0x4...) found in input" >&2; exit 5; }

echo "[*] Using: $A2L"
echo "[*] ELF:    $ELF"
echo "[*] PCs:    ${ADDRS[*]}"
echo

# Decode
"$A2L" -pfiaC -e "$ELF" "${ADDRS[@]}"
