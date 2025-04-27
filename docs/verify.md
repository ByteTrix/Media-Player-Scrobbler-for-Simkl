# Verifying Simkl Media Player Scrobbler Releases (v2.0.5)

This document explains how to verify the authenticity and integrity of the Simkl Media Player Scrobbler release files (`.exe`, `.whl`) downloaded from GitHub. Verification ensures the files haven't been tampered with since they were built and signed by the official GitHub Actions release workflow.

We use [Sigstore/cosign](https://github.com/sigstore/cosign) for signing and verification.

## 1. Prerequisites

You'll need the following tools installed:
*   **cosign**: Follow the [official installation guide](https://docs.sigstore.dev/cosign/installation/).
*   **sha256sum** (Linux/macOS) or **certutil** (Windows): For calculating SHA256 hashes.
    *   Windows: `certutil -hashfile <filename> SHA256`
    *   Linux/macOS: `sha256sum <filename>`

## 2. Download Release Assets

From the [GitHub Releases page](https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/releases/tag/v2.0.5), download the following files into the same directory:
*   The Windows installer: `MPSS_Setup_2.0.5.exe`
*   The installer's signature: `MPSS_Setup_2.0.5.exe.sig`
*   The Python wheel: `simkl_mps-2.0.5-py3-none-any.whl`
*   The wheel's signature: `simkl_mps-2.0.5-py3-none-any.whl.sig`

## 3. Verify Signatures with Cosign

Verify the digital signatures of the downloaded installer and wheel using `cosign`. This confirms they were signed by the expected GitHub Actions workflow.

Run the following commands in your terminal (in the directory where you downloaded the files):

```bash
# Verify the Windows Installer signature
cosign verify-blob \
  --certificate-identity "https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/.github/workflows/create-release.yml@refs/tags/v2.0.5" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  --signature "MPSS_Setup_2.0.5.exe.sig" \
  "MPSS_Setup_2.0.5.exe"

# Verify the Python Wheel signature
cosign verify-blob \
  --certificate-identity "https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/.github/workflows/create-release.yml@refs/tags/v2.0.5" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  --signature "simkl_mps-2.0.5-py3-none-any.whl.sig" \
  "simkl_mps-2.0.5-py3-none-any.whl"
```

If verification is successful for both files, you will see "Verified OK" messages. This confirms the files were signed by the official release workflow (`create-release.yml`) for the tag `v2.0.5`. **Do not proceed if verification fails for either file.**

*Note: The `--certificate-identity` points to this workflow (`create-release.yml`) and the specific release tag (`v2.0.5`) that signed the files.*

## 4. Verify Checksums Manually

As an additional check, manually calculate the SHA256 hash of the downloaded files and compare them against the hashes listed in the table within the GitHub Release notes.

**Example Commands:**

*   **Linux/macOS:**
    ```bash
    sha256sum "MPSS_Setup_2.0.5.exe"
    sha256sum "simkl_mps-2.0.5-py3-none-any.whl"
    ```

*   **Windows (Command Prompt or PowerShell):**
    ```cmd
    certutil -hashfile "MPSS_Setup_2.0.5.exe" SHA256
    certutil -hashfile "simkl_mps-2.0.5-py3-none-any.whl" SHA256
    ```

Compare the output hash for each file with the corresponding hash in the release notes table. They must match exactly. **Do not use the files if the hashes do not match.**

## Build Provenance

This release incorporates artifacts built and verified by GitHub Actions workflow run #70 (ID: 14695353723).
View the release workflow log: https://github.com/kavinthangavel/Media-Player-Scrobbler-for-Simkl/actions/runs/14695353723
