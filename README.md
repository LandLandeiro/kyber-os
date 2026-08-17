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

Early, but it boots into something. The image ships the KYBER launcher, the
session that runs it, and `gameprofiled`, which measures the machine and
applies performance profiles.

The two halves are joined. The daemon publishes to `/run/kyber/state.json` and
kyber-shell's `SystemAdapter` (v0.6.0) reads it over the same loopback server
that serves the launcher, so the temperatures, the watts and the running game on
screen come from this machine. The Steam side — library, cover art, downloads —
is still the mock until Etapa 7; the two arrive separately because `useAdapter`
composes partial implementations.

What the launcher does with a daemon that is not there is not an afterthought:
no `state.json` means SEM LEITURA, and a `state.json` whose `at` stops advancing
means LEITURA PARADA. Both are drawn, and the second is the one worth having —
stale telemetry that looks current makes a broken console look healthy.

## The session

Selecting **KYBER** at the login screen starts a gamescope session with a kiosk
browser inside it and no desktop behind it. Three pieces make that work:

| Piece | Where |
| --- | --- |
| Session entry, shown by the display manager | `/usr/share/wayland-sessions/kyber.desktop` |
| Session definition — sets `CLIENTCMD`, waits for the server | `/usr/share/gamescope-session-plus/sessions.d/kyber` |
| Local static server for the launcher | `kyber-launcher.service` → `127.0.0.1:8787` |
| The launcher itself | `/usr/share/kyber/launcher/` |
| Machine state and performance profiles | `kyber-gameprofiled.service` → `/run/kyber/state.json` |
| Profile writes, unprivileged | `kyber-api.service` → `127.0.0.1:8788` |

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

1. Push the launcher's `main`, **then** tag it, then push the tag:
   ```bash
   git -C ../kyber-shell push origin main
   git -C ../kyber-shell tag -a v0.7.0 -m "Editor de perfil grava de verdade"
   git -C ../kyber-shell push origin v0.7.0
   ```
   Or `git -C ../kyber-shell push origin main --follow-tags`, which does both in
   that order in one command.
2. Change `KYBER_SHELL_REF` to that tag and push.

**The order in step 1 is not tidiness, and the trap has already been sprung.**
A tag push carries the tagged commit and its ancestors and nothing else. So
`git push origin v0.7.0` on its own is enough for the CI checkout to succeed
while every commit made *after* that tag exists only on the machine it was
written on.

Nothing goes red. The build stages a launcher, finds `index.html`, finds
`src/main.js`, counts the fonts, publishes a signed image, and prints a resolved
commit that is perfectly real. The console boots into a launcher that is not the
one on the machine that built it, and no line anywhere says so.

It is the same failure the vendored copy of the launcher used to produce — an
image quietly shipping older code than its source — arriving through a different
door. Deleting the checked-in duplicate closed the door where a *directory*
drifts. This is the one where a *ref* drifts, and the fix has the same shape:
the publishing step has to carry everything it claims to publish.

Pushing `main` first means the tag can only ever name something the remote
already has.

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

#### Why the build does not check the pin for staleness

**The incident above is invisible to CI, and it is worth knowing why.** Any
check comparing `KYBER_SHELL_REF` against kyber-shell's `main` sees only what
GitHub has. Unpushed work is not late — it does not exist as far as the check is
concerned, and `main` and the pin agree perfectly. The only machine that can
detect it is the one holding the commits, which is why the mitigation above is
in the push command rather than in a workflow.

What such a check *would* see is the pin sitting behind a published `main` —
which is the normal state for as long as launcher work is in progress, meaning
most days. A warning that is right on most days and important on one is a
warning nobody reads by the time it matters.

The check that is free of false alarms is narrower: `KYBER_SHELL_REF` must be an
ancestor of kyber-shell's `main`. A pin that is not on `main` at all is always
wrong — a tag on an abandoned branch, a SHA that was force-pushed away — and
that is never a matter of timing. Cheap, real, and it does not address drift.

The other direction stays on the table. A tag push in kyber-shell is the act
that *means* "publish this", so a check triggered there — does `KYBER_SHELL_REF`
name this tag yet? — fires on intent and never on an ordinary commit. It inverts
the coupling, which is why it is written down here instead of built.

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

## The state daemon

`gameprofiled` is the other half of the console: it measures the machine, applies
the performance profile of whatever is running, and publishes both to
`/run/kyber/state.json` once a second. It is stdlib-only Python living in
`/usr/lib/kyber/gameprofiled/`, with no package of its own and no dependency to
install.

**It exposes no HTTP.** Joining "takes input from outside" with "runs as root"
is hard to undo later, so writes arrive over a Unix socket carrying a closed
list of two verbs, and the thing that speaks HTTP is `kyber-api` — a separate,
unprivileged process. The JSON files stay the read channel. See
[Writing a profile](#writing-a-profile).

### How the launcher reaches it

The daemon writes to `/run/kyber/` and `/var/lib/kyber/`, neither of which the
launcher can see: the launcher speaks HTTP and only sees the tree `darkhttpd`
serves. Two absolute symlinks join them, created at build time by
`files/scripts/kyber-gameprofiled.sh`:

```
/usr/share/kyber/launcher/state.json    -> /run/kyber/state.json
/usr/share/kyber/launcher/profiles.json -> /var/lib/kyber/profiles.json
```

They answer different questions, which is why they are different files:
`state.json` is **what the machine did**, `profiles.json` is **what was asked
for**. A profile can request `schedutil` on a machine that does not offer it —
the request lives in the second, the `unavailable` lives in the first, and the
profile editor needs both.

The second one is not a copy published into `/run`: it points at the real file
in `/var/lib`, so there is no window in which the two versions disagree. Reading
it over HTTP is safe against torn reads for the same reason `state.json` is —
every write to it is `.tmp` + `rename(2)`, and it is written `0644` explicitly
rather than inheriting whatever umask the writer had.

`darkhttpd` follows it because it never resolves paths — no `lstat`, no
`realpath`, no `O_NOFOLLOW`, it just `open()`s the target. That is also why its
unit must never gain `--chroot`; the comment there says so at length.

Two traps come with polling a file, and both are handled in `state.py`:

**Torn reads.** `darkhttpd` stats and `sendfile`s with no lock, so reading during
a write returns truncated JSON. Every publish goes to `state.json.tmp` on the
same tmpfs and lands with `os.replace()`. Only `state.json` is symlinked, so the
half-written file is never reachable over HTTP at all.

**Conditional requests.** `darkhttpd` compares `If-Modified-Since` as a string,
at one-second granularity. Two writes inside one second make the client get a
304, serve the cached body, see a repeated `at`, and declare the telemetry
stalled on a perfectly healthy console. The daemon publishes at most once a
second **with its phase anchored at X.5s**, so consecutive writes can never share
a whole second. Asking for a shorter `--interval` raises it back to 1.0 and logs
why.

### state.json

```jsonc
{
  "schema": 1,
  "at": 1786969941000,        // epoch ms the daemon MEASURED, not when you read
  "intervalMs": 1000,

  "cpuTemp": 61,              // °C, or null
  "gpuTemp": 68,
  "cpuWatts": 38.4,           // W, CPU package only
  "gpuWatts": 96.8,           // W, GPU only

  "watts": 50,                // ALWAYS from the curve. See below.
  "intensity": 0.5,           // 0..1, position on the gauge
  "fps": null,                // never measured; see the axes table

  "wattsIdle": 22,
  "wattsPerPoint": 7,

  "runningGame": { "appid": 553850, "startedAt": 1786900120000 },

  "profile": {
    "origin": "/var/lib/kyber/profiles.json",
    "applies": "553850",       // or "idle"
    "axes": {
      "governor": {
        "requested": "performance",
        "current": "performance",
        "state": "applied",
        "available": ["powersave", "performance"]
      }
      // ... gpuLevel, fpsLimit, priority
    }
  },

  "sources": {                 // one entry per measurable field, never omitted
    "cpuTemp": { "kind": "measured", "driver": "coretemp",
                 "path": "/sys/class/hwmon/hwmon7/temp1_input",
                 "label": "Package id 0" },
    "watts":   { "kind": "estimated", "note": "..." },
    "fps":     { "kind": "absent", "note": "..." }
  },

  "daemon": { "version": "0.1.0", "startedAt": 1786969940000 }
}
```

`at` is the producer's timestamp, and it is the only field that separates "the
daemon just measured and nothing changed" from "the daemon stopped measuring" —
every other field looks identical in both cases. kyber-shell's telemetry watcher
counts repeated `at` values and calls it a stalled reading after three.

Every entry in `sources` has a `kind`, including the absent ones:

| `kind` | Means |
| --- | --- |
| `measured` | a sensor reading of the thing the field claims to be |
| `estimated` | computed from a model, not read from anything |
| `absent` | no source, with a `note` saying where we looked |

Absence is published as `null` with a reason, never as zero. Zero is a value, and
a value is the claim that somebody measured.

### Sensor discovery

Nothing is hardcoded. `hwmonN` is driver bind order, not identity — the same
sensor changes number between boots — and the two machines this project targets
do not even share drivers. The test box is an i5-13400F (`coretemp`, no iGPU)
with an RX 7600 (discrete `amdgpu`); the console is a Ryzen 5 5700G (`k10temp`)
with integrated Vega 8. A fixed path would work on one and silently measure the
wrong thing on the other.

| Field | Searched, in order | Chosen by |
| --- | --- | --- |
| `cpuTemp` | `/sys/class/hwmon/*/name` ∈ `k10temp`, `zenpower`, `coretemp`; then `/sys/class/thermal/*/type` | label `Tdie` → `Tctl` → `Package id 0` → `Tccd1` → lowest input |
| `gpuTemp` | `/sys/class/drm/card*/device/hwmon/*` with `DRIVER=amdgpu` | label `edge` → `junction` → first |
| `gpuWatts` | same hwmon | `power1_average` → `power1_input` |
| `cpuWatts` | `/sys/class/powercap/intel-rapl:*` named `package-*` | `energy_uj`, differentiated over time |
| governor | `/sys/devices/system/cpu/cpufreq/policy*` | written per policy, read back |
| gpuLevel | `<card>/device/power_dpm_force_performance_level` | written, read back |

`Tdie` beats `Tctl` because `Tctl` carries an offset on some AMD families.
`Package id 0` beats the core sensors because the header shows the package, not
the hottest core. The GPU is found through the card rather than the flat hwmon
list because with two `amdgpu` cards the name is ambiguous; with more than one,
the largest VRAM wins and every candidate is logged.

RAPL is an energy counter, not a power reading, so the first read returns
nothing — there is no prior interval to divide by — and counter wraparound is
handled. The node is called `intel-rapl` on both vendors: since 5.11 the
`intel_rapl_msr` driver also binds AMD's energy MSRs from family 17h up.

The whole search is printed to the journal at startup, hits and misses alike:

```
sensor cpuTemp   /sys/class/hwmon/hwmon7/temp1_input (coretemp, Package id 0)
sensor gpuTemp   /sys/class/drm/card1/device/hwmon/hwmon2/temp1_input (amdgpu, edge)
eixo   governor  driver intel_pstate; disponíveis: powersave, performance
eixo   fpsLimit  NÃO APLICÁVEL nesta máquina
```

A sensor that stops answering after having answered triggers rediscovery, which
is what survives a driver rebind without rescanning sysfs every second.

### What it applies, and what it does not

The four axes do not have equal footing, and `state.json` says which is which
instead of treating them alike.

| Axis | Mechanism | Verifiable? |
| --- | --- | --- |
| `governor` | writes `scaling_governor` on every policy | **yes** — written, read back, compared |
| `gpuLevel` | writes `power_dpm_force_performance_level` | the *setting* yes; the *effect* on clocks only indirectly |
| `priority` | `nice` + `ionice` across the game's process tree | yes, by re-reading `/proc/PID/stat` |
| `fpsLimit` | `gamescopectl debug_set_fps_limit` into the user's session | only if the convar reads back; discovered, not assumed |

Each axis publishes one of six states, and each maps to a different thing the
launcher should draw:

`applied` · `degraded` (written, read back different) · `failed` · `unavailable`
(the axis works but a precondition is missing right now) · `unsupported` (this
build has nowhere to write; it will never work here) · `observed` (nothing was
requested; the value is just what the machine has).

**`fpsLimit` goes through the compositor, and the daemon crosses into the user's
session to reach it.** There is still no kernel file for frame limiting;
`gamescopectl` talks to gamescope at runtime over the `gamescope_control`
protocol, and `debug_set_fps_limit 30` / `... 0` was confirmed on hardware
without relaunching the session.

That `debug_` prefix is not decoration. The convar can be renamed or removed in a
gamescope update, and Bazzite updates fast, so its presence is **detected before
it is depended on** — three empirical layers, each degrading with its reason
written into the axis:

1. `/usr/bin/gamescopectl` exists → otherwise `unsupported`.
2. A graphical session was found → otherwise `unavailable`, *not* `unsupported`.
   The axis works; the precondition is missing right now. The daemon comes up on
   `multi-user.target` and the session only exists after login.
3. `gamescopectl help` lists `debug_set_fps_limit` → otherwise `unsupported`,
   with the note recording what `help` *did* list, so a rename is one journal
   line away.

Layer 3 has already failed once, through its own fault, and the episode is worth
keeping. `gamescopectl help` writes its convar list to **stderr**; the probe read
only stdout, so a convar that existed came back `unsupported`.

The mechanism was right. Faced with a check that did not pass, it fell back to
`unsupported` with the reason written down rather than applying anyway and
becoming a silent no-op — which is the whole point of detecting before depending.
A false negative costs a disabled feature and a log line; a false positive would
cost a control in the editor that does nothing and nobody finds out. The layer
read the wrong channel, not the wrong verdict.

But the message was identical to the one a genuinely removed convar produces, so
the note now carries a fingerprint of what was seen — how many lines `help`
returned, and how many mention `fps`:

| Note says | Means |
| --- | --- |
| `não respondeu` | nothing came back on either channel. The convar is not the problem; the reading is |
| `N linhas, 0 citando fps` | the convar is gone |
| `N linhas, M citando fps` | it was renamed, and the candidates are quoted in the note |

Every call now reads both channels, and the readback parser is deliberately
strict: it accepts a bare integer or `debug_set_fps_limit = N`, and nothing else.
A wrong readback is worse than no readback, because it feeds the comparison in
`apply()` — a number scraped out of an error message would become an invented
`degraded`, or an `applied` by coincidence.

Crossing into the session is the interesting part, and the reasoning is in
`session.py`. Three decisions worth repeating here:

**The axis stays in the daemon.** An unprivileged helper inside the session would
be cleaner — session process doing session things — but **whoever applies is
whoever reports**. `state.json` is written by the daemon, and an applier on the
other side would need a write channel back: the Unix socket the architecture
deferred. Without it, the axis would publish unknown state forever, and both the
profile editor and screen 17 consume per-axis state. Restore is triggered by the
game exiting, which only the daemon sees.

**The session is discovered, never assumed.** No fixed uid, no `id -nu 1000`. The
daemon already walks `/proc`; it finds a process that is *inside* the session and
takes uid, gid, `XDG_RUNTIME_DIR` and the display name from that one process, so
they cannot disagree. The marker is `GAMESCOPE_WAYLAND_DISPLAY`, which
gamescope-session-plus sets once gamescope reports its socket and which
everything it starts inherits — the launcher's Chromium among them.

**Privilege drops before the call.** `subprocess(user=, group=, extra_groups=[])`:
stdlib, `setuid`/`setgid` between fork and exec, no sudo, no PAM, no shell. Root
*could* open the socket — Wayland authenticates nothing beyond file permissions —
but a root Wayland client leaves root-owned files in someone else's runtime
directory, and inverting privilege into a user session is worth avoiding even
where it works. `extra_groups=[]` because otherwise the child keeps root's
supplementary groups after dropping uid. Every call carries a 2s timeout: a
Wayland client waiting on a compositor that went away is a client that blocks,
and a blocked publish loop is a frozen `at`, which the launcher correctly reads
as stalled telemetry.

That drop cost the unit two things, and both failed silently on the first boot
with the same contextless `Operation not permitted`:

- **`CAP_SETUID` and `CAP_SETGID`.** `setuid(1000)` needs the capability *even
  when dropping* privilege — the kernel does not look at the direction, it looks
  at whether the target uid is one the process already holds. `setgid()` and
  `setgroups([])` need `CAP_SETGID` for the same reason.
- **`ProtectHome=` loosened from `yes` to `read-only`.** `yes` makes `/home`,
  `/root` *and `/run/user`* inaccessible, and the gamescope socket lives in
  `/run/user/<uid>/`. Nothing in the log pointed at this: session discovery reads
  the path out of a process's environment, never out of the directory, so it
  reports success while the directory is empty as far as the unit is concerned.
  `read-only` keeps `/home` and `/root` unwritable; `connect()` on a socket is
  not blocked by a read-only mount, since the kernel only refuses writes to
  regular files, directories and symlinks.

The unit's header enumerates all three hardening concessions this daemon has
made, each with what it bought and what the alternative would have cost. Read it
before shortening the capability list.

**Restore is assumed, not captured — until the getter proves otherwise.** This is
the one place this axis is weaker than `governor`, and the difference deserves
saying out loud. The governor reads the previous value out of sysfs before
writing, so it puts back exactly what it found. This axis captures only if
`gamescopectl debug_set_fps_limit` with no argument prints the current value —
plausible, since gamescope's convar system is Source-descended, and detected at
probe time rather than assumed. Without it, restore writes `0`.

And `0` is a **guess**. The session does start unlimited, but that does not make
the daemon the only writer: `gamescopectl` is public, and any process in the
session — or anyone over SSH — can have set a limit first. Restoring to zero
erases whatever that other hand did. It is still what happens, for one reason:
removing a limit never wedges a console, and being stuck at 30 fps after closing
a game is the same class of failure as a governor stuck on `performance`. The
safe direction is the loose one, and the axis note says the value is assumed.

**`priority: tempo real` is deliberately not offered.** `SCHED_FIFO` on a game
process can wedge the console, and there is no cgroup-level protection in this
version. It is left out of `available` rather than quietly reinterpreted as
`alta` — a label that promises one thing while the machine does another is worse
than a missing option.

### The profile comes from disk

The profile the daemon applies comes from `/var/lib/kyber/profiles.json`, seeded
on first run from `/usr/share/kyber/profiles.default.json`. Everything writes
there and nothing writes anywhere else: `vi` edits it, and so does the command
socket. That is the point — one path, so the editor and the file cannot tell
different stories.

**With no game running the daemon applies nothing** — it observes and reports.
Two practical reasons: not fighting Bazzite's own power management on a console
that idles most of the time, and not forcing a low DPM level underneath the
launcher, which is a 60 fps UI on the same hardware.

When a game appears, the daemon captures the current value of each axis before
writing. When it exits, it writes them back — including values outside the
console's vocabulary, because the machine might have been on `ondemand` and
returning it to `powersave` would leave it different from how we found it.
Stopping the daemon with a game running restores too.

This is not tidiness. The launcher's close-game dialog promises, in as many
words, that closing reverts the performance profile. Without the write-back that
sentence is a lie and the console stays pinned on `performance` until reboot.

#### Editing it while a game runs

The file is polled once a second, and a change to the running title's profile
lands on the next tick — no relaunch, no restart. That is the whole mechanism
the profile editor will use: the editor writes the file, the daemon reacts to
it. Editing with `vi` and saving from the console's own screen go through
exactly the same path, and that is the point. A second path — something telling
the daemon out of band — would let the file and the screen tell different
stories on the day they disagreed.

**The reapply does not capture again.** `capturado` holds what the machine had
*before the game started*, and that is what goes back when the game exits.
Capturing again on reapply would store what the daemon itself had just written:
closing the game would restore `performance` instead of the `powersave` that was
actually there, and the console would stay pinned hot until the next boot —
precisely the failure the write-back exists to prevent.

That one raises no error anywhere. It arrives months later as "my PC runs hot
after I play", with nothing in the journal pointing at it. So the capture lives
on one line of `_aplicar()` and the writing lives in `_escrever()`: the
difference between the two transitions is that line, and it is visible instead
of buried inside a method that does both.

A change that does not reach the running title writes nothing. The file carries
every title's profile, and editing one that is not running is no reason to
rewrite the sysfs of one that is.

The change is noticed by `(mtime, size, inode)`, not by mtime alone. Every
disciplined write here is `.tmp` + `os.replace()`, which swaps the inode — `vi`
with a backup does the same. mtime alone would suffice only if it always had
nanosecond resolution, and it does not: ext4 with 128-byte inodes rounds to the
second, which would make the second of two writes inside one second invisible
until a third arrived.

### Game detection

`/proc` is scanned for Steam's per-title cgroup, `steam_app_<appid>`. That beats
parsing command lines on three counts: `/proc/PID/cgroup` is world-readable
where `environ` would need `CAP_SYS_PTRACE`, the cgroup catches the whole tree
rather than just the `reaper`, and the PID list it yields is exactly what the
priority axis needs to renice.

Underneath it is `reaper` → Proton wrappers → the game binary, with a varying
number of rungs between (pressure-vessel, wine, the title's own launcher). No
attempt is made to guess which one "is the game": they all belong to the session
and all go on the list. `startedAt` comes from the *oldest* process in the group,
since the launch began with the reaper and the binary comes up seconds later.

Two fallbacks cover older Steam or a title running outside the scope it creates:
`SteamAppId` in `environ`, which survives any depth of the tree, and
`SteamLaunch AppId=` in `cmdline`, which identifies the reaper.

The game's *name* is deliberately not resolved here. It would mean parsing
`libraryfolders.vdf` and `appmanifest_*.acf` under `/home`, and `state.json` is
world-readable because `nobody` has to serve it. The launcher already has that
library data and can look up the name by appid.

### The power curve is a guess, and says so

`watts` is **never a measurement**, not even with a calibrated curve. It always
comes out of `wattsIdle + score × wattsPerPoint`.

Neither target machine can measure what the console draws. RAPL covers the CPU
package, `power1_average` covers the GPU, and their sum still ignores the
motherboard, the memory and the power supply's losses. Publishing that sum as
`watts` would give a number the shape of a measurement without the substance.

So the components are published as themselves, and `sources.watts.note` carries
the comparison:

```
"curva NÃO calibrada (22 W de repouso + 7 W por ponto, chute do protótipo);
 estimado 50 W contra 135.2 W somando os componentes medidos, que não cobrem
 placa-mãe, memória nem perda da fonte"
```

The same line goes to the journal every ten minutes. It exists so that nobody
watching this gauge every day gets used to a number nobody checked.

To calibrate: put a wall meter on the console, read it at idle and again with the
profile at its highest reachable score, then set `wattsIdle` to the first,
`wattsPerPoint` to `(second − first) / score`, and flip `calibrated` to `true`.
Note the divisor is the score you can actually reach, not 8 — see the next
section.

### What else the compositor exposes

Found while chasing the frame limiter, recorded because it is cheap to write down
and expensive to rediscover. **None of it is implemented** — it is raw material
for the video settings screen in Etapa 7a, and the names below are where to look.

`xprop -root` on the gamescope display carries:

| Property | On the test machine | What it is for |
| --- | --- | --- |
| `GAMESCOPE_DISPLAY_MODE_LIST_EXTERNAL` | `1920x1080@144/165/120/60` | every mode the monitor accepts — the list a resolution/refresh picker has to be built from, rather than guessed |
| `GAMESCOPE_VRR_CAPABLE` | `1` | variable refresh is supported |
| `GAMESCOPE_VRR_ENABLED` | `0` | …and is off. A real control with a real toggle behind it |

`gamescopectl help` also lists `drm_allow_dynamic_modes_for_external_display`,
which suggests mode changes without a session relaunch — the same shape as the
frame limiter, and therefore the same three-layer detection would apply.

Two cautions carried over from the frame limiter. These are convars and X
properties, not a stable API: anything built on them needs the presence detected
before it is depended on. And every one of them lives inside the user's session,
so any daemon-side use pays the same crossing that `session.py` already pays.

### What this pushed back to kyber-shell

Four things this work surfaced that the launcher had to answer. Three are
answered — two in kyber-shell v0.6.0, one by the frame limiter landing on this
side. One is still open, and it is the one that already caused damage.

**1. `schedutil` was a dead control. ANSWERED.** With `intel_pstate` in active
mode — the default on the test machine — `scaling_available_governors` offers
only `performance` and `powersave`. The profile editor offered three governors,
and on that machine one of them did nothing. Same for `fpsLimit`, `unsupported`
everywhere, and `priority: tempo real`, never offered: five dead controls on one
screen.

This is why `available` is in the format. The editor now reads it and strikes
what the machine cannot do, achromatically — struck label, recessed surface, and
no `tabindex`, so the D-pad cannot reach it. It disables rather than removes: the
option row is a flex, and dropping an item would change the screen's shape
between machines, and `schedutil` existing but being unavailable is worth
teaching.

**2. The gauge could not reach AGRESSIVO. ANSWERED — by the limitation ending,
not by moving the scale.** The score model gives `fpsLimit` up to 2 points and
`priority` up to 2. With `fpsLimit` unapplied and `tempo real` never offered, the
best reachable score was 2 + 2 + 0 + 1 = **5 of 8** → `nominal`, at 57 W, while
`hot` needs 6. The top third of the ruler — the signature element of the whole
interface — was unreachable by construction.

With `fpsLimit` applying through `gamescopectl`, the ceiling is 2 + 2 + 2 + 1 =
**7 of 8**, and the factory profile alone scores 6. AGRESSIVO is reachable.

Nothing about the scale changed, and that was the point of leaving it alone.
Normalising against what the machine could do in August would have been
optimising against a limitation that turned out to last three weeks — and the
rescaled ruler would now have to be un-rescaled, with every stored profile's
meaning shifting underneath it. `tests/test_score.py` still pins the same nine
watt values; the model was never touched.

**3. Two sources of truth for the score model. OPEN, AND IT ALREADY BIT.** The
model lives in `gameprofiled/score.py` and in kyber-shell's `src/data/mock.js`:
two repositories, two languages, one product decision about how four selectors
become a position on a ruler. `tests/test_score.py` pins the nine watt values and
the level thresholds, so a change here breaks the build — but a change *there*
breaks nothing.

The one-directional mitigation is exactly as weak as it sounded. The daemon
publishes `current: null` for `fpsLimit` on every machine and for `priority` at
rest; `score.py` treats an unknown axis as weight 0, and the launcher's copy did
not — it used `indexOf` without handling `-1`, so `FPS_WEIGHT[-1]` was
`undefined` and the score became `NaN`. The gauge painted **AGRESSIVO at
`NaN W`**: an invented value wearing the appearance of a measurement, in the most
alarming third of the ruler. Fixed in v0.6.0, on the launcher side, by hand,
after it shipped. The real fix is still one model in one place.

**4. The adapter had to send `cache: "no-store"`. ANSWERED.** Phase-locked
publishing makes a false 304 impossible from the writer's side; `no-store`
removes the conditional request from the reader's side, so there is no 304 to
serve a cached body behind. Both ends now, on a failure that otherwise shows up
as a healthy console reporting stalled telemetry.

## Writing a profile

The profile editor has to actually apply, and the daemon runs as root. Those two
facts are what the whole shape below exists to reconcile.

```
launcher (Chromium)  --HTTP-->  kyber-api (unprivileged)
kyber-api            --Unix socket-->  gameprofiled (root)
gameprofiled         --writes-->  /var/lib/kyber/profiles.json
gameprofiled         --polls, next tick-->  applies
```

The daemon gains no HTTP port. It gains a Unix socket carrying a **closed list
of two verbs**, and the list being closed is the security property — not an
implementation detail that can be loosened later because it got tight.

| Verb | Payload | Why it exists |
| --- | --- | --- |
| `set-profile` | `appid`, `axes` | The SAVE button. Without it there is no Etapa 5. |
| `clear-profile` | `appid` | RESTORE DEFAULT, with a meaning that survives. |

The second one is not strictly needed to make the editor work — X only resets
the local copy, and what follows is a `set-profile` carrying the default's
values. It exists so the label does not lie. Writing "today's default" into the
title's entry pins it to a snapshot: the next image update changes the default
and that title silently stops following it. It is also the only way the file
ever shrinks.

**Two verbs, not one verb with a sentinel.** `set-profile` with `axes: {}` would
do the same work. In a closed list the value is in each entry meaning exactly one
thing; a parser with a special case is where a closed list starts to leak.

The launcher reaches `clear-profile` without a button of its own: SAVE compares
the edited profile against the resolved default and sends a delete when they
match. Two actions arrive there meaning the same thing — RESTORE DEFAULT then
SAVE, and opening a title that has no entry and saving without changing
anything — and both should leave the file saying "follows the default" rather
than pinning a snapshot of it.

There is **no read verb**. That is also a property: a protocol that cannot read
cannot leak, and "the JSON is the read channel" stays true. What is stored is
served at `/profiles.json`; what is applied is served at `/state.json`.

What is deliberately *not* there, each with its reason:

| Not a verb | Why not |
| --- | --- |
| `apply-now` | It would be the second path. The socket writes the **file**; the daemon notices by mtime, exactly as it notices `vi`. |
| `set-curve` | The watt curve is calibrated with a wall meter, once in the console's life. A verb that changes the meaning of every published watt, for a one-off, is surface without demand. |
| `set-default` | No screen edits the console-wide profile; screen 04 is per title. It arrives when the screen does. |
| anything writing sysfs directly | The parallel path under another name. |

### The message, and the answer

One JSON object per connection, newline-terminated, 4 KiB ceiling, one command
per connection.

```jsonc
{"v": 1, "cmd": "set-profile", "appid": 553850,
 "axes": {"governor": "performance", "gpuLevel": "auto",
          "fpsLimit": "60", "priority": "alta"}}
```

A refusal carries a machine-readable code and a human-readable note, the same
discipline as `sources` in `state.json`:

```jsonc
{"v": 1, "ok": false, "error": "eixo_indisponivel", "axis": "governor",
 "value": "schedutil", "available": ["powersave", "performance"],
 "note": "esta máquina não aplica 'schedutil' em governor; aplica ..."}
```

The codes are a closed set: `mensagem_invalida`, `versao_desconhecida`,
`comando_desconhecido`, `appid_invalido`, `eixo_desconhecido`,
`valor_fora_do_vocabulario`, `eixo_indisponivel`, `limite_de_titulos`,
`escrita_falhou`.

A success says **written**, not **applied** — they are different claims. What
was applied shows up in `state.json` on the next tick, per axis, with
`requested`, `current`, `state` and a note. The same distinction the axes have
always published, now reaching the socket's reply.

### Validation is on the root side

`kyber-api` deliberately does **not** know the vocabulary. If it validated,
there would be two lists of valid values that diverge the day someone edits one
— and, worse, someone would come to believe that process protects something.

It does not. With the socket at `0660 root:kyber-api`, the set of things that
can open it is `{kyber-api, root}` — *not* "anything in the session". That is
worth stating out loud, because the opposite belief, left standing for six
months, becomes the argument for making the socket `0666`.

The daemon validates as if every message were hostile anyway, for a different
reason than it first appears: `kyber-api` takes input from a TCP port. It is the
piece that can be compromised.

- `appid` is an **integer**, 1 to 2³¹−1. Not a string, not a float, not a boolean
  (which is an `int` in Python and would slip through), and never a file path.
  The file path is a constant of the daemon; no field of any message influences
  any path.
- The axis vocabulary is `score`'s — the same one `config` already uses to filter
  the file. A second list here would be the project's third source of truth, and
  the second one already cost a `NaN` on the gauge.
- An unknown key in `axes` is **refused**, not dropped. Dropping in silence is
  how a client comes to believe it saved what it did not.
- At most 1024 titles. Not a product limit: it is what stops a `set-profile` loop
  from filling `/var`, which on a read-only-image console is the only writable
  place there is.

### `available` is authority, but only when it has something to say

Asking for `schedutil` on a machine running `intel_pstate` in active mode is
refused, with the reason and the list of what does exist. The editor already
strikes the unavailable option, but an interface is not a boundary: its reading
is taken once at mount, and the machine can have changed since.

**An empty `available` does not refuse.** Empty means two very different things —
"this build will never do it" and "a precondition is missing *right now*", like
the frame limiter before the graphical session comes up — and refusing a save
because a probe failed for two seconds would turn transient state into lost work.

More than that: the launcher already draws that case. In a group where nothing is
applicable the LED leaves every option and the stored value comes back as a word
in the group header — "perfil pede 60". That drawing exists to show that the
profile holds a value nobody applies. Refusing the write would erase exactly what
it was built to show.

So: non-empty list and a value outside it → refused. Empty list → accepted, with
a **warning** in the reply. The file stays a portable artifact, which is what
lets the disk move to another machine and the axis start working there.

### Who runs what

`kyber-api` runs as a dedicated system user and group, declared in
`/usr/lib/sysusers.d/kyber-api.conf` — processed by `systemd-sysusers` at boot,
which is the right mechanism on an OSTree image where `/usr` is read-only.

The daemon creates the socket and chowns it `root:kyber-api`, mode `0660`.
Connecting to a Unix socket requires **write** permission on the file, so that
line is literally the list of who can talk to the daemon.

The default already fails closed: a socket created by root under umask 022 comes
out `0755`, which is closed to everyone but root. The chown/chmod is a deliberate
*loosening*, done only when there is a group to loosen in favour of. If the group
is missing — someone removed the sysusers file, or it is the suite running on a
Mac — the socket stays `0600` and the journal says only root will reach it. The
opposite, dropping to `0666` because a config file was missing, is how a daemon
becomes an open door.

Rejected alternatives: **`nobody`**, because it is shared by design with every
service that needs no privilege, and granting it write access to a socket that
reconfigures the hardware hands that access to any future `nobody` service.
**`DynamicUser=yes`**, which looks made for this and is not: the gid would be
transient, and the daemon has to resolve the group at *its own* start, which
happens before `kyber-api` exists.

**The socket costs the daemon's unit nothing.** `RestrictAddressFamilies=AF_UNIX`
already allowed it, `RuntimeDirectory=` already provides the directory,
`CAP_CHOWN` is already in the bounding set for `RuntimeDirectory`, and
`@system-service` already includes `@network-io`. There is no fourth hardening
concession here.

### Why `kyber-api` is on its own port

`darkhttpd` serves static files and nothing else — no CGI, no proxy, by design.
So either the writer lives on another port and pays for CORS, or it absorbs the
static serving and CORS disappears.

The second option costs the property the console has today: the interface opens
with the daemon down and draws SEM LEITURA. Putting the writer inside the static
server turns "saving fails" into a connection-error screen at boot. That is the
same trade the `darkhttpd` unit refuses in its `--chroot` comment.

So: its own port, explicit CORS, and the launcher still opens when this piece
does not.

**The CORS header here is not a defence**, and saying so is the point of writing
it down. It stops a *page* from another origin reading the reply; it does nothing
about a local process, which is the realistic threat on a machine whose browser
is a kiosk on a fixed URL. What it does buy, narrowly: requiring
`Content-Type: application/json` makes any cross-origin request a preflight, and
the preflight fails on an `Access-Control-Allow-Origin` that is exact and never
`*`.

### The socket must never freeze `at`

A client holding the publish loop past the next instant makes `at` repeat, and a
repeated `at` is what the launcher reports as stalled telemetry. The daemon would
play dead by answering the phone.

So the loop `select`s on the socket instead of sleeping, and never yields the
publish instant: 100 ms for a client to deliver a complete message over a local
socket, at most 8 conversations per round, and the wait is sliced at 250 ms
because Python resumes `select` after a signal rather than returning from it
(PEP 475) — an unsliced wait would hold SIGTERM until the next publish.

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

  # The daemon and the one link that joins it to the launcher. The link is
  # dangling in the image on purpose — /run is only populated at runtime —
  # so check the target string, not the target.
  ls /usr/lib/kyber/gameprofiled/__main__.py
  ls /usr/lib/systemd/system/kyber-gameprofiled.service
  ls /usr/share/kyber/profiles.default.json
  readlink /usr/share/kyber/launcher/state.json      # /run/kyber/state.json
  readlink /usr/share/kyber/launcher/profiles.json  # /var/lib/kyber/profiles.json

  # The write path: an unprivileged API and the user that owns it. The
  # sysusers file is what creates the group the daemon chowns the socket to;
  # without it the socket stays 0600 and only root can write a profile.
  ls /usr/lib/kyber/kyberapi/__main__.py
  ls /usr/lib/systemd/system/kyber-api.service
  ls /usr/lib/sysusers.d/kyber-api.conf

  # The frame limiter goes through the compositor, so this is what the
  # fpsLimit axis needs to exist before it can be anything but unsupported.
  command -v gamescopectl
  ls /usr/share/user-tmpfiles.d/kyber-gamescope.conf
'
```

The symlink is the whole joint. Lose it and nothing goes red: the daemon keeps
publishing, the launcher keeps asking, the request 404s, and the console draws
SEM LEITURA forever with no log line pointing at the cause.

Also worth checking that the session file produces the command you expect,
since a bad `CLIENTCMD` fails at boot with nothing useful on screen:

```bash
podman run --rm ghcr.io/landlandeiro/kyber:latest bash -c '
  . /usr/share/gamescope-session-plus/sessions.d/kyber && echo "$CLIENTCMD"'
```

### Without any hardware: the gameprofiled unit tests

The daemon is stdlib-only Python and every filesystem access goes through an
injectable root, so the whole discovery and profile layer runs on a laptop —
macOS included. There is no build step and nothing to install:

```bash
python3 -m unittest discover -s tests -t .
```

The tests run against three fake sysfs trees, each there to prove something
different:

| Tree | Proves |
| --- | --- |
| `intel_rx7600` | the dev box, with **hwmon indices deliberately shuffled** — `coretemp` at `hwmon7`, the SSD at `hwmon0`. Discovery that sorts by index measures the SSD and never notices |
| `ryzen_5700g` | the console: `k10temp` with no `Tdie`, and an integrated GPU that exposes **no temperature at all** |
| `bare` | nothing. No hwmon, no card, no cpufreq |
| `dual_gpu` | integrated and discrete together; the choice must land on the one with more VRAM |

The three most valuable tests are the atomic write, the phase lock, and the one
that proves a mid-game profile change does not re-capture — all three guard
against failures that raise no error. The first hands the launcher truncated
JSON, the second makes a healthy console report itself stalled, and the third
leaves the machine pinned on `performance` after the game closes.

You can also render a `state.json` from a fake tree without any hardware:

```bash
mkdir -p /tmp/kyber-fake
PYTHONPATH=files/system/usr/lib/kyber:. python3 -c '
from tests import fakefs
fakefs.intel_rx7600("/tmp/kyber-fake"); fakefs.sessao_steam("/tmp/kyber-fake")'
PYTHONPATH=files/system/usr/lib/kyber python3 -P -m gameprofiled \
    --root /tmp/kyber-fake --once
cat /tmp/kyber-fake/run/kyber/state.json
```

`--root` swaps the filesystem and only the filesystem. `setpriority` and
`ioprio_set` talk to the real kernel by PID, and a fake tree's PIDs are numbers
that exist on the machine you are inspecting — so a simulated root refuses to
touch processes at all, and the priority axis reports `failed` with that as its
reason. Everything else in the output is real.

### Without any hardware: the launcher in a normal browser

The launcher is plain HTML/CSS/JS, so any machine can run it. Since v0.6.0 it
also reads `state.json`, so a plain static server is no longer the whole test —
kyber-shell carries a harness that plays both halves, the loopback server and
the daemon:

```bash
git clone https://github.com/LandLandeiro/kyber-shell && cd kyber-shell
./scripts/servir.py              # http://127.0.0.1:8787, fixture dev-box
./scripts/servir.py --lista      # the five fixtures
```

It republishes `state.json` once a second with the `at` advancing, atomically and
phase-locked at X.5s, the same as `gameprofiled`. A static JSON would not test
anything: the timestamp never changes, and the launcher correctly calls that a
stalled reading within ten seconds. With it running, `p` freezes the telemetry
(→ LEITURA PARADA), `d` takes the daemon down (→ SEM LEITURA), `l` brings it
back.

Four of the five fixtures came out of `gameprofiled` itself, run against this
repository's fake sysfs trees, so they match what the daemon publishes rather
than someone's memory of the format. `sem-governor` is the test machine as it
really is — `intel_pstate` active, no `schedutil` — and it is the one that shows
the struck-out options in the profile editor.

`?mock` on the URL puts the launcher back on simulated telemetry, for interface
work with no state server alongside. Without it and without a `state.json`, the
launcher shows SEM LEITURA, which is what a console with a dead daemon shows.

Check out the ref pinned in `KYBER_SHELL_REF` if you want the version a
published image actually shipped, rather than the tip of the branch.

Keyboard navigation stands in for the controller. Two things to confirm here:
the typography is Familjen Grotesk and Figtree rather than a system fallback,
and the network tab shows **no requests to fonts.googleapis.com**. Loading the
same directory as a `file://` URL is the useful negative test — it should fail
with CORS errors in the console, which is exactly why the server exists.

### The gamescope runtime leftovers

`gamescope-session-plus` creates a directory per session with `mktemp -d` under
`/run/user/<uid>` and does not remove it on exit — six `gamescope.XXXXXXX`
directories after a day of testing. It is tmpfs and it is small, but a console
that powers on and off daily leaks one per login.

The leak is upstream's; the cleanup is ours, in
`/usr/share/user-tmpfiles.d/kyber-gamescope.conf`. It runs at the start of each
user session, before gamescope comes up, so it sweeps the previous sessions'
leftovers without touching the one starting.

Not a `trap` in our `sessions.d/kyber`: that file is `source`d into upstream's
shell under `set -a`, so an EXIT trap there would either clobber theirs or need
chaining through `trap -p` — and it would fail silently, which is the worst way
for a cleanup to fail.

> [!NOTE]
> **Unverified on hardware.** The rule carries `!`, restricting it to the
> instance's boot. That is a deliberate choice between two ways of failing:
> without it, a `systemd-tmpfiles --user --create --remove` fired mid-session
> would delete the *live* session's directory and take gamescope down with it.
> With it, the worst case is the line never running and the leak continuing. But
> if the user instance of `systemd-tmpfiles-setup` does not pass `--boot`, the
> line is skipped in silence. To check:
>
> ```bash
> ls -d /run/user/$UID/gamescope.*        # before and after a re-login
> systemctl --user cat systemd-tmpfiles-setup.service | grep ExecStart
> systemd-tmpfiles --user --boot --remove --dry-run 2>&1 | grep gamescope
> ```

### On the console

```bash
# The server the launcher is fetched from
systemctl status kyber-launcher.service
curl -I http://127.0.0.1:8787/

# The state daemon, and what it found on this machine. The discovery lines
# are printed once at startup and are the first thing to read when the
# header shows a dash instead of a number.
systemctl status kyber-gameprofiled.service
journalctl -u kyber-gameprofiled -b | grep -E 'sensor|eixo|watts'

# The file itself, through the same path the launcher uses. If this 404s,
# the symlink or the daemon is missing — and that is exactly what the
# launcher will draw as SEM LEITURA.
curl -s http://127.0.0.1:8787/state.json | python3 -m json.tool

# It has to change every second. Two identical `at` values from a running
# daemon means the publish loop is stuck; three in a row is what the
# launcher calls a stalled reading.
for i in 1 2 3; do curl -s http://127.0.0.1:8787/state.json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["at"])'; sleep 1; done

# The session entry the display manager reads
ls /usr/share/wayland-sessions/

# What the frame limiter axis resolved to, and why. Three layers: binary,
# session, convar — the log line names the one that failed.
journalctl -u kyber-gameprofiled -b | grep -E 'sessão|fpsLimit'

# The session's own log — gamescope-session-plus runs under `set -x`,
# so this is verbose on purpose
journalctl --user -b | grep -i gamescope
```

### Writing a profile, layer by layer

Three layers, and each one proves itself without the one above it. Work up from
the bottom: the layer that answers tells you where the failure is.

**Layer 1 — the stored profile is served.** No socket, no API, no launcher: this
is a symlink and a static file.

```bash
curl -s http://127.0.0.1:8787/profiles.json | python3 -m json.tool
```

A 404 means the symlink is missing or the file was never seeded — check
`readlink /usr/share/kyber/launcher/profiles.json` and
`ls -l /var/lib/kyber/profiles.json`, which must be `0644`. This is what the
profile editor reads to open showing what was saved, and it keeps answering with
`kyber-api` dead.

**Layer 2 — the socket takes commands.** No browser in the middle. The socket is
`0660 root:kyber-api`, so this needs `sudo`; running it without `sudo` and
getting `Permission denied` is how you confirm the permission is real.

```bash
kyber-cmd() {
  sudo python3 -c '
import socket, sys
s = socket.socket(socket.AF_UNIX); s.connect("/run/kyber/control.sock")
s.sendall(sys.argv[1].encode() + b"\n"); print(s.recv(4096).decode().strip())
' "$1"
}

# Accepted — writes the file. Nothing else happens yet.
kyber-cmd '{"v":1,"cmd":"set-profile","appid":553850,
            "axes":{"governor":"powersave","gpuLevel":"baixo"}}'

# Refused, with the reason and the list of what this machine does offer.
kyber-cmd '{"v":1,"cmd":"set-profile","appid":553850,
            "axes":{"governor":"schedutil"}}'

# Removes the entry; the title goes back to following the default.
kyber-cmd '{"v":1,"cmd":"clear-profile","appid":553850}'
```

With the title running, the sysfs write lands on the **next** tick, not on the
reply — the reply says written, the journal says applied:

```bash
journalctl -u kyber-gameprofiled -f | grep -E 'socket|config|perfil'
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor
```

`nc -U` works too if it is installed, but `python3` is guaranteed here — the
daemon is written in it.

**Layer 3 — HTTP.** Now the API, still with no browser.

```bash
systemctl status kyber-api.service
journalctl -u kyber-api -b

# The preflight. Both header values must come back exact.
curl -s -i -X OPTIONS http://127.0.0.1:8788/profile/553850 \
  -H 'Origin: http://127.0.0.1:8787' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type' | grep -i 'HTTP/\|access-control'

# Accepted → 200. Refused → 400 with the same body the socket returned.
curl -s -w '\n%{http_code}\n' -X POST http://127.0.0.1:8788/profile/553850 \
  -H 'Origin: http://127.0.0.1:8787' -H 'Content-Type: application/json' \
  -d '{"axes":{"governor":"powersave"}}'

# Daemon stopped → 503, not 500 and not silence. The launcher needs to tell
# "it refused" from "it was not there"; they are different screens.
sudo systemctl stop kyber-gameprofiled
curl -s -w '\n%{http_code}\n' -X POST http://127.0.0.1:8788/profile/553850 \
  -H 'Content-Type: application/json' -d '{"axes":{"governor":"powersave"}}'
sudo systemctl start kyber-gameprofiled
```

If layer 3 fails and layer 2 passed, the problem is `kyber-api` — most likely
its user is not in the socket's group, which shows up as `PermissionError` in
`journalctl -u kyber-api`.

Only then the screen: open a title, X for the profile editor, change an option
and SALVAR. The toast says PERFIL SALVO; the axis rows on screen 17 change on
the next tick. Asking for something the machine cannot do keeps you on the
editor with PERFIL RECUSADO and the reason — it does not pop the screen, because
the screen is where the choice gets fixed.

The screen is the other half of the check, and it is faster: the header's CPU
and GPU readings should move on their own, and stopping the daemon
(`systemctl stop kyber-gameprofiled`) should turn them into dashes and put SEM
LEITURA on the gauge within a second. If the numbers sit still instead, the
daemon is publishing but the launcher is not reading — check that
`/usr/share/kyber/launcher/state.json` is still a symlink, since that is the
only thing joining the two.

KYBER is the session that starts automatically — the image ships
`/etc/sddm.conf.d/zzz-kyber-autologin.conf`, which sorts after the file Bazzite
rewrites on every boot and so wins. It sets only `Session`; the username still
comes from Bazzite's file, which resolves it at boot time. To check that the
merge landed the way you expect:

```bash
ls /etc/sddm.conf.d/            # zzz-kyber-* must sort last
grep -r . /etc/sddm.conf.d/     # Session=kyber.desktop, User=<you>
```

**On a machine you have not run this on before**, look before it writes. The
daemon takes `--no-apply`, which detects the game and publishes everything while
touching no sysfs at all:

```bash
sudo systemctl stop kyber-gameprofiled
sudo PYTHONPATH=/usr/lib/kyber python3 -P -m gameprofiled --no-apply --once \
    --state /tmp/state.json
python3 -m json.tool /tmp/state.json
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
| `files/system/usr/lib/kyber/gameprofiled/` | The state daemon — stdlib-only Python, no package |
| `files/system/usr/share/kyber/profiles.default.json` | Factory profiles and power curve, seeded into `/var/lib/kyber/` on first run |
| `tests/` | Unit tests for the daemon against fake sysfs trees. Not shipped in the image |
| `files/system/etc/sddm.conf.d/` | Autologin override that makes KYBER the default session |
| `files/scripts/` | Scripts available to the `script` module during build |
| `files/scripts/kyber-gameprofiled.sh` | Verifies the daemon imports and creates the `state.json` symlink |
| `modules/` | Custom BlueBuild modules specific to KYBER |
| `.github/workflows/build.yml` | The build and publish pipeline, and the pinned launcher version |
| `cosign.pub` | Public key used to verify the published image |

The launcher is not in this table because it is not in this repository — see
[The launcher](#the-launcher) above.
