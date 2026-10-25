#!/usr/bin/env bash
# Niri Live Wallpaper installer.
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/toczekmj/niri-live-wallpaper/main/install.sh)"
#
# Options go after a `--` in that one-liner, e.g. ... install.sh)" -- --dry-run
#   --yes        don't ask before installing
#   --dry-run    show what would be done, change nothing
#   --uninstall  remove the app (your videos and settings are kept)
#   --help       show this help
#
# Arch-based systems (Arch, EndeavourOS, CachyOS, Manjaro, …) get a pacman package, built with the same
# recipe as the AUR package (packaging/aur/PKGBUILD); mpvpaper comes from the AUR. Other systems get the app
# in its own Python virtual environment, plus a list of the programs still missing.
#
# The whole script is one function called on the last line, so a half-downloaded copy runs nothing.

set -euo pipefail

main() {
  REPO="toczekmj/niri-live-wallpaper"
  RAW="https://raw.githubusercontent.com/$REPO/main"
  PKGNAME="niri-live-wallpaper"
  UNIT="niri-live-wallpaper.service"
  DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/niri-live-wallpaper"
  VENV_DIR="$DATA_DIR/app"            # next to videos/, which uninstalling keeps
  BIN_DIR="$HOME/.local/bin"
  OS_RELEASE="${NLW_OS_RELEASE:-/etc/os-release}"  # overridable for testing

  ASSUME_YES=0
  DRY_RUN=0
  ACTION=install
  for arg in "$@"; do
    case "$arg" in
      --yes|-y) ASSUME_YES=1 ;;
      --dry-run|-n) DRY_RUN=1 ;;
      --uninstall) ACTION=uninstall ;;
      --help|-h) usage; return 0 ;;
      *) die "unknown option: $arg (try --help)" ;;
    esac
  done

  setup_colors
  [ "$(id -u)" -ne 0 ] || die "run this as your normal user, not as root; it asks for sudo when it needs it"
  detect_system

  if [ "$ACTION" = uninstall ]; then
    uninstall
    return
  fi

  if ! command -v systemctl >/dev/null || [ ! -d /run/systemd/system ]; then
    die "Niri Live Wallpaper currently needs systemd (the wallpaper runs as a systemd user service)."
  fi
  command -v niri >/dev/null || warn "niri isn't installed; the app is made for the niri compositor."

  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
  # The PKGBUILD on main always names the latest release, so it's also where we read the version from.
  curl -fsSL "$RAW/packaging/aur/PKGBUILD" -o "$WORK/PKGBUILD" \
    || die "couldn't download from GitHub; check your internet connection"
  VERSION="$(sed -n 's/^pkgver=//p' "$WORK/PKGBUILD")"
  PKGREL="$(sed -n 's/^pkgrel=//p' "$WORK/PKGBUILD")"
  [ -n "$VERSION" ] || die "couldn't read the latest version"

  printf '\n%sNiri Live Wallpaper %s installer%s  (%s)\n' "$BOLD" "$VERSION" "$RESET" "$OS_NAME"
  [ "$DRY_RUN" = 1 ] && printf '%sDry run: nothing will be changed.%s\n' "$YELLOW" "$RESET"
  if [ "$IS_ARCH" = 1 ]; then plan_arch; else plan_generic; fi
  if ! confirm "Continue?"; then
    info "Nothing was changed."
    return 0
  fi

  if [ "$IS_ARCH" = 1 ]; then install_arch; else install_generic; fi
  check_programs
  if systemctl --user is-active --quiet "$UNIT" 2>/dev/null; then
    step "Restarting the running wallpaper with the new version"
    run systemctl --user restart "$UNIT"
  fi

  step "Done"
  info "Start it with:  ${BOLD}nlw${RESET}"
  info "The checks at the top of the app show what's left to set up."
  info "Guide: https://github.com/$REPO#readme"
}

usage() {
  cat <<'EOF'
Niri Live Wallpaper installer

  bash -c "$(curl -fsSL https://raw.githubusercontent.com/toczekmj/niri-live-wallpaper/main/install.sh)" [-- OPTIONS]

Options:
  --yes, -y      don't ask before installing
  --dry-run, -n  show what would be done, change nothing
  --uninstall    remove the app (your videos and settings are kept)
  --help, -h     show this help
EOF
}

# ----------------------------------------------------------------------------- output helpers

setup_colors() {
  if [ -t 1 ]; then
    BOLD=$'\e[1m' DIM=$'\e[2m' RED=$'\e[31m' GREEN=$'\e[32m' YELLOW=$'\e[33m' RESET=$'\e[0m'
  else
    BOLD='' DIM='' RED='' GREEN='' YELLOW='' RESET=''
  fi
}

step() { printf '\n%s==>%s %s%s%s\n' "${GREEN-}" "${RESET-}" "${BOLD-}" "$*" "${RESET-}"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s  ! %s%s\n' "${YELLOW-}" "$*" "${RESET-}" >&2; }
die() { printf '%sError:%s %s\n' "${RED-}" "${RESET-}" "$*" >&2; exit 1; }

# Run a command, or with --dry-run only show it.
run() {
  if [ "$DRY_RUN" = 1 ]; then
    printf '    %s[dry-run]%s %s\n' "$DIM" "$RESET" "$*"
  else
    "$@"
  fi
}

# Run a command inside a directory (which may not exist yet in a dry run).
run_in() {
  local dir="$1"
  shift
  if [ "$DRY_RUN" = 1 ]; then
    printf '    %s[dry-run]%s (in %s) %s\n' "$DIM" "$RESET" "$dir" "$*"
  else
    (cd "$dir" && "$@")
  fi
}

# Yes/no question. Reads the answer from the terminal, so it also works when the script itself arrives
# through a pipe (curl ... | bash).
confirm() {
  [ "$ASSUME_YES" = 1 ] && return 0
  [ "$DRY_RUN" = 1 ] && return 0
  local answer=""
  printf '\n%s%s [Y/n] %s' "$BOLD" "$1" "$RESET"
  if ! read -r answer 2>/dev/null </dev/tty; then  # 2> first: it must also hide the failed </dev/tty
    printf '\n'
    die "no terminal to ask on; rerun with --yes to install without asking"
  fi
  case "$answer" in
    ""|y|Y|yes|Yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

# ----------------------------------------------------------------------------- system detection

detect_system() {
  local id="" like="" name=""
  if [ -r "$OS_RELEASE" ]; then
    id="$(. "$OS_RELEASE"; printf '%s' "${ID:-}")"
    like="$(. "$OS_RELEASE"; printf '%s' "${ID_LIKE:-}")"
    name="$(. "$OS_RELEASE"; printf '%s' "${PRETTY_NAME:-${NAME:-}}")"
  fi
  OS_NAME="${name:-unknown system}"
  IS_ARCH=0
  case " $id $like " in
    *" arch "*) command -v pacman >/dev/null && IS_ARCH=1 ;;
  esac
}

aur_helper() {
  local helper
  for helper in yay paru; do
    if command -v "$helper" >/dev/null; then
      printf '%s' "$helper"
      return 0
    fi
  done
  return 1
}

# ----------------------------------------------------------------------------- Arch-based systems

ARCH_PACKAGES=(base-devel git python ffmpeg fzf fd wl-clipboard glib2 xdg-utils)

plan_arch() {
  local helper
  printf '\nThis will:\n'
  info "1. install from the Arch repositories (if missing): ${ARCH_PACKAGES[*]}"
  if pacman -Q mpvpaper >/dev/null 2>&1; then
    info "2. mpvpaper: already installed"
  elif helper="$(aur_helper)"; then
    info "2. install mpvpaper from the AUR with $helper"
  else
    info "2. build and install mpvpaper from the AUR (https://aur.archlinux.org/packages/mpvpaper)"
  fi
  info "3. build and install the $PKGNAME $VERSION pacman package (runs its tests)"
  info "pacman may ask for your password (sudo)."
}

install_arch() {
  local helper installed
  command -v sudo >/dev/null || die "sudo is needed to install packages"

  step "Installing packages from the Arch repositories"
  run sudo pacman -S --needed --noconfirm "${ARCH_PACKAGES[@]}"

  step "mpvpaper (plays the video)"
  if pacman -Q mpvpaper >/dev/null 2>&1; then
    info "already installed"
  elif helper="$(aur_helper)"; then
    run "$helper" -S --needed --noconfirm mpvpaper
  else
    run git clone --depth 1 https://aur.archlinux.org/mpvpaper.git "$WORK/mpvpaper"
    run_in "$WORK/mpvpaper" makepkg -si --noconfirm --needed
  fi

  step "$PKGNAME $VERSION"
  installed="$(pacman -Q "$PKGNAME" 2>/dev/null | cut -d' ' -f2 || true)"
  if [ "$installed" = "$VERSION-$PKGREL" ]; then
    info "already installed and up to date"
    return 0
  fi
  mkdir -p "$WORK/build"
  cp "$WORK/PKGBUILD" "$WORK/build/"
  # -s installs missing dependencies, -r removes the build-only ones afterwards, -i installs the result.
  run_in "$WORK/build" makepkg -sri --noconfirm
}

# ----------------------------------------------------------------------------- other systems

plan_generic() {
  printf '\nThis will:\n'
  info "1. install $PKGNAME $VERSION into its own Python environment: $VENV_DIR"
  info "2. add the nlw command: $BIN_DIR/nlw"
  info "3. check which programs it needs are still missing, and suggest how to install them"
  info "No sudo needed. Your system packages aren't touched."
}

install_generic() {
  command -v python3 >/dev/null || die "python3 is needed"
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || die "Python 3.10 or newer is needed (found $(python3 --version 2>&1))"
  python3 -c 'import venv, ensurepip' 2>/dev/null \
    || die "Python's venv module is missing (Debian/Ubuntu: sudo apt install python3-venv)"

  step "$PKGNAME $VERSION"
  if [ -x "$VENV_DIR/bin/nlw" ] && [ "$("$VENV_DIR/bin/nlw" --version 2>/dev/null)" = "nlw $VERSION" ]; then
    info "already installed and up to date"
  else
    run python3 -m venv --clear "$VENV_DIR"
    run "$VENV_DIR/bin/pip" install --quiet --disable-pip-version-check \
      "https://github.com/$REPO/archive/refs/tags/v$VERSION.tar.gz"
  fi
  run mkdir -p "$BIN_DIR"
  run ln -sfn "$VENV_DIR/bin/nlw" "$BIN_DIR/nlw"
  case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR isn't in your PATH. Add it to your shell config, or start the app as $BIN_DIR/nlw" ;;
  esac
}

# ----------------------------------------------------------------------------- dependency report

check_programs() {
  step "Programs it uses"
  MISSING_REQUIRED=()
  MISSING_OPTIONAL=()
  need required "niri" niri
  need required "mpvpaper: plays the video" mpvpaper
  need required "ffmpeg: video info, optimized copies" ffprobe
  need required "fzf: the import picker" fzf
  need optional "fd: faster import search" fd fdfind
  need optional "wl-clipboard: copy the niri config lines" wl-copy
  need optional "gdbus: open the video folder in your file manager" gdbus
  need optional "xdg-open: fallback for opening the folder" xdg-open
  if [ "${#MISSING_REQUIRED[@]}" -gt 0 ] || [ "${#MISSING_OPTIONAL[@]}" -gt 0 ]; then
    suggest_packages
  fi
}

# need required|optional "label" command [alternative commands...]
need() {
  local kind="$1" label="$2" cmd
  shift 2
  for cmd in "$@"; do
    if command -v "$cmd" >/dev/null; then
      info "${GREEN}✓${RESET} $label"
      return 0
    fi
  done
  if [ "$kind" = required ]; then
    info "${RED}✗${RESET} $label ${RED}(needed)${RESET}"
    MISSING_REQUIRED+=("$label")
  else
    info "${YELLOW}–${RESET} $label ${DIM}(optional)${RESET}"
    MISSING_OPTIONAL+=("$label")
  fi
}

suggest_packages() {
  printf '\n'
  info "Suggested install command for $OS_NAME (package names can differ between versions):"
  if command -v pacman >/dev/null; then
    info "  sudo pacman -S --needed ${ARCH_PACKAGES[*]:2}   and mpvpaper from the AUR"
  elif command -v apt-get >/dev/null; then
    info "  sudo apt install ffmpeg fzf fd-find wl-clipboard libglib2.0-bin xdg-utils"
    info "  mpvpaper isn't packaged: build it from https://github.com/GhostNaN/mpvpaper"
  elif command -v dnf >/dev/null; then
    info "  sudo dnf install ffmpeg-free fzf fd-find wl-clipboard glib2 xdg-utils"
    info "  mpvpaper: from the Terra repository, or build it from https://github.com/GhostNaN/mpvpaper"
  elif command -v zypper >/dev/null; then
    info "  sudo zypper install mpvpaper ffmpeg fzf fd wl-clipboard glib2-tools xdg-utils"
  elif command -v nix-env >/dev/null || [ -d /etc/nixos ]; then
    info "  add to your configuration: mpvpaper ffmpeg fzf fd wl-clipboard glib xdg-utils"
  else
    info "  install with your package manager: mpvpaper, ffmpeg, fzf, fd, wl-clipboard, glib (gdbus), xdg-utils"
  fi
  if [ "${#MISSING_REQUIRED[@]}" -gt 0 ]; then
    warn "The app can't play videos until the programs marked ✗ are installed."
  fi
}

# ----------------------------------------------------------------------------- uninstall

uninstall() {
  local unit_file="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$UNIT"
  printf '\n%sUninstall Niri Live Wallpaper%s\n' "$BOLD" "$RESET"
  [ "$DRY_RUN" = 1 ] && printf '%sDry run: nothing will be changed.%s\n' "$YELLOW" "$RESET"
  info "Removes the app and its background service. Keeps your videos, settings and cache."
  if ! confirm "Continue?"; then
    info "Nothing was changed."
    return 0
  fi

  if command -v systemctl >/dev/null; then
    if systemctl --user is-enabled --quiet "$UNIT" 2>/dev/null || systemctl --user is-active --quiet "$UNIT" 2>/dev/null; then
      step "Stopping the wallpaper service"
      run systemctl --user disable --now "$UNIT"
    fi
    if [ -f "$unit_file" ]; then
      run rm -f "$unit_file"
      run systemctl --user daemon-reload
    fi
  fi
  if command -v pacman >/dev/null && pacman -Q "$PKGNAME" >/dev/null 2>&1; then
    step "Removing the $PKGNAME package"
    run sudo pacman -R --noconfirm "$PKGNAME"
  fi
  if [ -d "$VENV_DIR" ]; then
    step "Removing $VENV_DIR"
    run rm -rf "$VENV_DIR"
  fi
  if [ -L "$BIN_DIR/nlw" ]; then
    run rm -f "$BIN_DIR/nlw"
  fi

  step "Done"
  info "Kept (delete them yourself if you want them gone):"
  info "  videos:   $DATA_DIR/videos"
  info "  settings: ${XDG_CONFIG_HOME:-$HOME/.config}/niri-live-wallpaper"
  info "  cache:    ${XDG_CACHE_HOME:-$HOME/.cache}/niri-live-wallpaper"
  info "mpvpaper and the other programs stay installed, since other apps may use them."
}

main "$@"
