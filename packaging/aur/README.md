# Publishing to the AUR

The AUR stores only a build recipe: `PKGBUILD` plus the generated `.SRCINFO`. It doesn't store the code. The
recipe downloads a release tarball from the project's public repository, builds a wheel, runs the tests and
installs it. Users install it with `yay -S niri-live-wallpaper` (or `paru`, …), and their AUR helper also
builds the `mpvpaper` dependency from the AUR.

The name `niri-live-wallpaper` was free on 2026-10-25.

## One-time setup

### 1. Decide the open questions in `PKGBUILD`

- **License:** done. The project is MIT licensed (`LICENSE`, `license = "MIT"` in `pyproject.toml`,
  `license=('MIT')` in `PKGBUILD`). If you change it, change all three.
- **Maintainer line and `url=`:** done (GitHub noreply address; change it if you want a different contact).

### 2. Put the code in a public git repository (done: github.com/toczekmj/niri-live-wallpaper)

```sh
cd ~/Git/NiriLiveWallpaper
git init -b main
git add .
git commit -m "Niri Live Wallpaper 0.1.0"
# create an empty repository named niri-live-wallpaper on GitHub/Codeberg/GitLab, then:
git remote add origin git@github.com:YOU/niri-live-wallpaper.git
git push -u origin main
```

`PKGBUILD` assumes GitHub's tarball URL and its top folder name (`niri-live-wallpaper-0.1.0/`). On Codeberg
the URL is `$url/archive/v$pkgver.tar.gz` and the folder is `niri-live-wallpaper/`, so change `source=` and the
`cd` lines.

### 3. Create an AUR account with an SSH key

1. Register at <https://aur.archlinux.org/register>.
2. Create a key if you don't want to reuse one: `ssh-keygen -t ed25519 -f ~/.ssh/aur`.
3. Paste the **public** key (`~/.ssh/aur.pub`) into *My Account → SSH Public Key*.
4. Add this to `~/.ssh/config`:
   ```
   Host aur.archlinux.org
       IdentityFile ~/.ssh/aur
       User aur
   ```

### 4. Install the packaging tools

```sh
sudo pacman -S --needed base-devel python-build python-installer python-setuptools python-wheel namcap devtools
```

## Every release (including the first)

1. **Set the version** in `niri_live_wallpaper/__init__.py` and `pyproject.toml`. Move the `[Unreleased]`
   notes in `CHANGELOG.md` under the new version with today's date.
2. **Tag and push** the release in the project repository:
   ```sh
   git commit -am "Release 0.1.0" && git tag v0.1.0 && git push && git push --tags
   ```
3. **Update `PKGBUILD`:** `pkgver=0.1.0`, `pkgrel=1`. Then fill in the real checksum (this replaces `SKIP`):
   ```sh
   cd packaging/aur && updpkgsums
   ```
4. **Test the build** in a clean chroot, which catches missing dependencies, and lint it:
   ```sh
   extra-x86_64-build            # from devtools; or at least: makepkg -sf
   namcap PKGBUILD *.pkg.tar.zst
   ```
5. **Publish** to the AUR git repository. It's separate from the project repository and contains only the
   recipe:
   ```sh
   git clone ssh://aur@aur.archlinux.org/niri-live-wallpaper.git ~/aur/niri-live-wallpaper   # first time only
   cd ~/aur/niri-live-wallpaper
   cp ~/Git/NiriLiveWallpaper/packaging/aur/PKGBUILD .
   makepkg --printsrcinfo > .SRCINFO      # always regenerate after editing PKGBUILD
   git add PKGBUILD .SRCINFO
   git commit -m "Update to 0.1.0"
   git push                               # the AUR only accepts the master branch
   ```
   Cloning a package name that doesn't exist yet gives you an empty repository, and the first push creates the
   package page.
6. **Commit the updated `packaging/aur/PKGBUILD`** in the project repository too, so it stays the source of truth.

A change to the recipe only (dependencies, description) keeps `pkgver` and increases `pkgrel`.

## Good to know

- Pure-Python AUR packages install into `/usr/lib/python3.X/site-packages`. When Arch moves to a new Python
  version (e.g. 3.14 → 3.15), users must rebuild the package (`yay -S niri-live-wallpaper --rebuild`).
  Bumping `pkgrel` then is a courtesy. The systemd unit the app writes keeps working, and it's rewritten the
  next time a wallpaper is selected.
- Optionally, also publish `niri-live-wallpaper-git` (builds the latest commit) for people who want unreleased
  changes. That needs a separate PKGBUILD with a `git+` source and a `pkgver()` function.
- Rules for AUR submissions: <https://wiki.archlinux.org/title/AUR_submission_guidelines>;
  Python packaging on Arch: <https://wiki.archlinux.org/title/Python_package_guidelines>.
