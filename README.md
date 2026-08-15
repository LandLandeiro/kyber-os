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

Early. This is currently the **base image**: Bazzite plus KYBER's signing setup
and file overlay, with none of the KYBER-specific software yet. The launcher and
the game-profile daemon are not part of the image at this point — they land in
later commits, once the build pipeline is proven green.

## Installation

> [!WARNING]
> Rebasing to a custom image is [an experimental feature of Fedora Atomic](https://www.fedoraproject.org/wiki/Changes/OstreeNativeContainerStable).
> Try it at your own discretion, and read the rollback section before you start.

You need a machine already running an atomic Fedora variant (Bazzite, Silverblue,
Kinoite, and so on). Rebasing happens in two stages: first to the unsigned image,
so the signing keys and policy files land on disk, then to the signed image.

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

The `latest` tag always points to the newest build. That build stays on the
Fedora version pinned by the Bazzite `stable` channel in `recipes/recipe.yml`, so
you will not be pulled onto the next major Fedora release by accident.

## Verification

Download `cosign.pub` from this repository and verify the published image
against it:

```bash
cosign verify --key cosign.pub ghcr.io/landlandeiro/kyber
```

A successful run confirms the image in the registry was signed by this
repository's private key.

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
rpm-ostree rebase ostree-unverified-registry:ghcr.io/ublue-os/bazzite:stable
systemctl reboot
```

Your home directory and anything else under `/var` survives a rebase, since only
the OS image is being swapped. Packages you layered manually with
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
| `files/scripts/` | Scripts available to the `script` module during build |
| `modules/` | Custom BlueBuild modules specific to KYBER |
| `.github/workflows/build.yml` | The build and publish pipeline |
| `cosign.pub` | Public key used to verify the published image |
