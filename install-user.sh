#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e .
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
cat > "$HOME/.local/bin/private-money" <<EOF
#!/usr/bin/env bash
exec "$ROOT/.venv/bin/private-money" "\$@"
EOF
chmod 700 "$HOME/.local/bin/private-money"
cat > "$HOME/.local/share/applications/private-money.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PrivateMoney
Comment=Local-first personal finance dashboard
Exec=$HOME/.local/bin/private-money
Terminal=false
Categories=Office;Finance;
StartupNotify=true
EOF
chmod 600 "$HOME/.local/share/applications/private-money.desktop"
printf 'Installed PrivateMoney. Launch with: %s\n' "$HOME/.local/bin/private-money"
