# KYBER OS &nbsp; [![build badge](https://github.com/LandLandeiro/kyber-os/actions/workflows/build.yml/badge.svg)](https://github.com/LandLandeiro/kyber-os/actions/workflows/build.yml)

KYBER OS is a dedicated gaming console: a 3D-printed enclosure, a custom
operating system image, and a purpose-built launcher.

This repository holds the operating system half of the project. The image is
built with [BlueBuild](https://blue-build.org/) on top of
[Bazzite](https://bazzite.gg/), which already provides Steam, Proton,
gamescope, and the GPU drivers a console needs. Building on Bazzite means KYBER
inherits its update cadence and hardware support instead of reinventing them.

Builds are published to `ghcr.io/landlandeiro/kyber` and signed with
[Sigstore](https://www.sigstore.dev/)'s [cosign](https://github.com/sigstore/cosign).

## Status

Early, but it boots into something. The image currently ships the KYBER
launcher and the session that runs it. The game-profile daemon
(`gameprofiled`) is not in the image yet, so the launcher runs against its
mock data adapter — the interface is real, the numbers behind it are not.

## The session

Selecting **KYBER** at the login screen starts a gamescope session with a kiosk
browser inside it and no desktop behind it. Three pieces make that work:

| Piece | Where |
| --- | --- |
| Session entry, shown by the display manager | `/usr/share/wayland-sessions/kyber.desktop` |
| Session definition — sets `CLIENTCMD`, waits for the server | `/usr/share/gamescope-session-plus/sessions.d/kyber` |
| Local static server for the launcher | `kyber-launcher.service` → `127.0.0.1:8787` |
| The launcher itself | `/usr/share/kyber/launcher/` |

The session plugs into `gamescope-session-plus`, the same mechanism Bazzite's
own Steam session uses. That framework starts gamescope and runs our
`CLIENTCMD` inside it, so KYBER does not carry a session script of its own.
This is why the base image is `bazzite-deck` rather than plain `bazzite` —
`gamescope-session-plus` only exists in that build stage.

**The launcher is served over HTTP on loopback, never opened as a file.** It is
38 ES modules plus a `fetch()`, and a `file://` origin is opaque, so the
browser's CORS rules block both and the screen stays blank. `darkhttpd` costs
63 KB installed and removes the whole class of problem.

Fonts are embedded in the image (152 KB, SIL OFL) rather than loaded from
Google Fonts. A console has to draw its first screen without a network.

## The launcher

The launcher lives in its own repository, **[kyber-shell](https://github.com/LandLandeiro/kyber-shell)**,
and is *not* checked into this one. The build fetches it: `.github/workflows/build.yml`
checks out kyber-shell at a pinned ref and copies `index.html` and `src/` into
`files/system/usr/share/kyber/launcher/`, where the recipe's `files` module picks
it up like any other file in the image tree.

Only the runtime half travels. kyber-shell also carries `docs/`, `telas/` and
`scripts/`, which are development material and stay out of `/usr`.

That path is listed in `.gitignore` on purpose. This repository used to hold a
hand-copied duplicate of the launcher with nothing explaining how it got there,
which is a copy that drifts quietly: the image keeps building green while
shipping a launcher older than the source. Committing the directory back would
recreate exactly that.

### Updating the launcher in the image

The version is pinned in one place — `KYBER_SHELL_REF` in
`.github/workflows/build.yml`. To ship new launcher work:

1. Tag the state you want in kyber-shell:
   ```bash
   git -C ../kyber-shell tag -a v0.5.0 -m "Etapa 5" && git -C ../kyber-shell push origin v0.5.0
   ```
2. Change `KYBER_SHELL_REF` to that tag and push.

It accepts a tag or a full commit SHA, never a branch. A moving branch would
make yesterday's image unreproducible today, and the whole point of an image is
that it rebuilds into the same bytes. Prefer a tag: six months from now a bare
SHA tells nobody which version of the launcher an image shipped. The build log
prints the resolved commit, so any published image can be traced back to
launcher source.

If the staged launcher comes up missing or incomplete, the build fails on the
spot. That check is deliberate — a missing launcher does not break the image
build on its own, it just produces a console that boots to a connection error,
which is a far more expensive way to discover the problem.

### Building locally

There is no local build in this repository — no Justfile, no Makefile, no
script. Builds happen in CI. If you want to reproduce one on a machine with
`podman` and the [BlueBuild CLI](https://blue-build.org/how-to/setup/), the
workflow's steps by hand are:

```bash
# 1. Stage the launcher exactly as CI does, at the pinned ref
git clone https://github.com/LandLandeiro/kyber-shell .kyber-shell
git -C .kyber-shell checkout <KYBER_SHELL_REF from build.yml>
mkdir -p files/system/usr/share/kyber/launcher
cp -R .kyber-shell/index.html .kyber-shell/src files/system/usr/share/kyber/launcher/

# 2. Build
bluebuild build ./recipes/recipe.yml
```

Both `.kyber-shell/` and the staged launcher are gitignored, so a local build
leaves nothing to accidentally commit.

## Installation

> [!WARNING]
> Rebasing to a custom image is [an experimental feature of Fedora Atomic](https://www.fedoraproject.org/wiki/Changes/OstreeNativeContainerStable).
> Try it at your own discretion, and read the rollback section before you start.

You need a machine already running an atomic Fedora variant (Bazzite,
Silverblue, Kinoite, and so on). Rebasing happens in two stages: first to the
unsigned image, so the signing keys and policy files land on disk, then to the
signed image.

1. Rebase to the unsigned image:
   ```bash
   rpm-ostree rebase ostree-unverified-registry:ghcr.io/landlandeiro/kyber:latest
   ```
2. Reboot to complete the rebase:
   ```bash
   systemctl reboot
   ```
3. Rebase to the signed image:
   ```bash
   rpm-ostree rebase ostree-image-signed:docker://ghcr.io/landlandeiro/kyber:latest
   ```
4. Reboot again to finish:
   ```bash
   systemctl reboot
   ```

At the login screen, pick **KYBER** from the session selector.

The `latest` tag always points to the newest build. That build stays on the
Fedora version pinned by the Bazzite `stable` channel in `recipes/recipe.yml`,
so you will not be pulled onto the next major Fedora release by accident.

## Verification

Download `cosign.pub` from this repository and verify the published image
against it:

```bash
cosign verify --key cosign.pub ghcr.io/landlandeiro/kyber
```

A successful run confirms the image in the registry was signed by this
repository's private key.

## Testing

Each layer can be checked on its own, and most of them without console
hardware. Work down the list — the first failure tells you which layer broke.

### Without any hardware: inspect the built image

Pull the image and look inside it. This proves the files landed where the
session expects them, which is most of what can go wrong.

```bash
podman run --rm ghcr.io/landlandeiro/kyber:latest bash -c '
  ls /usr/share/kyber/launcher/index.html
  ls /usr/share/wayland-sessions/kyber.desktop
  ls /usr/share/gamescope-session-plus/sessions.d/kyber
  ls /usr/lib/systemd/system/kyber-launcher.service
  command -v chromium chromium-browser darkhttpd
  ls /usr/share/kyber/launcher/src/assets/fonts/*.woff2 | wc -l   # expect 10
'
```

Also worth checking that the session file produces the command you expect,
since a bad `CLIENTCMD` fails at boot with nothing useful on screen:

```bash
podman run --rm ghcr.io/landlandeiro/kyber:latest bash -c '
  . /usr/share/gamescope-session-plus/sessions.d/kyber && echo "$CLIENTCMD"'
```

### Without any hardware: the launcher in a normal browser

The launcher is plain HTML/CSS/JS, so any machine can run it. Serve it from a
kyber-shell checkout the same way the console does, and open
`http://127.0.0.1:8787`:

```bash
git clone https://github.com/LandLandeiro/kyber-shell && cd kyber-shell
python3 -m http.server 8787 --bind 127.0.0.1
```

Check out the ref pinned in `KYBER_SHELL_REF` if you want the version a
published image actually shipped, rather than the tip of the branch.

Keyboard navigation stands in for the controller. Two things to confirm here:
the typography is Familjen Grotesk and Figtree rather than a system fallback,
and the network tab shows **no requests to fonts.googleapis.com**. Loading the
same directory as a `file://` URL is the useful negative test — it should fail
with CORS errors in the console, which is exactly why the server exists.

### On the console

```bash
# The server the launcher is fetched from
systemctl status kyber-launcher.service
curl -I http://127.0.0.1:8787/

# The session entry the display manager reads
ls /usr/share/wayland-sessions/

# The session's own log — gamescope-session-plus runs under `set -x`,
# so this is verbose on purpose
journalctl --user -b | grep -i gamescope
```

KYBER is the session that starts automatically — the image ships
`/etc/sddm.conf.d/zzz-kyber-autologin.conf`, which sorts after the file Bazzite
rewrites on every boot and so wins. It sets only `Session`; the username still
comes from Bazzite's file, which resolves it at boot time. To check that the
merge landed the way you expect:

```bash
ls /etc/sddm.conf.d/            # zzz-kyber-* must sort last
grep -r . /etc/sddm.conf.d/     # Session=kyber.desktop, User=<you>
```

To boot into the desktop instead, mask the file:

```bash
sudo ln -sf /dev/null /etc/sddm.conf.d/zzz-kyber-autologin.conf
```

If the session fails to start, it falls back to the desktop rather than looping
— `short_session_recover` in the session file calls `steamos-session-select
desktop`. That is the intended escape hatch: log into the desktop and read the
journal.

## Rolling back

**To undo the last update** and boot the previous deployment:

```bash
rpm-ostree rollback
systemctl reboot
```

`rpm-ostree status` lists the deployments currently on disk, so you can check
what you are rolling back to first. Note that rpm-ostree keeps only two
deployments by default — a rollback is available immediately after an update,
but not several updates later.

**To leave KYBER entirely** and return to stock Bazzite:

```bash
rpm-ostree rebase ostree-unverified-registry:ghcr.io/ublue-os/bazzite-deck:stable
systemctl reboot
```

Your home directory and anything else under `/var` survives a rebase, since
only the OS image is being swapped. Packages you layered manually with
`rpm-ostree install` do not carry over — reinstall them after the rebase.

## ISO

An offline installer ISO can be generated with the
[BlueBuild ISO instructions](https://blue-build.org/how-to/generate-iso/#_top).
These ISOs are too large to distribute through GitHub for free, so they are not
published here.

## Repository layout

| Path | Purpose |
| --- | --- |
| `recipes/recipe.yml` | The image definition: base image, version, and modules |
| `files/system/` | Files copied into the image's root filesystem `/` |
| `files/system/usr/share/gamescope-session-plus/sessions.d/kyber` | The KYBER session definition |
| `files/system/usr/share/wayland-sessions/kyber.desktop` | Session entry for the display manager |
| `files/system/usr/lib/systemd/system/` | Custom systemd units |
| `files/system/etc/sddm.conf.d/` | Autologin override that makes KYBER the default session |
| `files/scripts/` | Scripts available to the `script` module during build |
| `modules/` | Custom BlueBuild modules specific to KYBER |
| `.github/workflows/build.yml` | The build and publish pipeline, and the pinned launcher version |
| `cosign.pub` | Public key used to verify the published image |

The launcher is not in this table because it is not in this repository — see
[The launcher](#the-launcher) above.
