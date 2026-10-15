# Public release verification — v1.0.0

**Verified on 2026-10-15.** A separate AI agent downloaded the actual public GitHub release after publication and installed each distribution into a separate fresh virtual environment outside the development checkout. These are constructed acceptance checks, not a shop deployment or an engineering validation.

- [Public release and downloadable artifacts](https://github.com/waxwingfactor/gage-window/releases/tag/v1.0.0)
- Exact source revision: `4a3b134764544a5f2e169f8d0f1b7f0d8b21a0aa`
- [Required CI on that revision](https://github.com/waxwingfactor/gage-window/actions/runs/38794207405): nine successful combinations of Windows/macOS/Linux and Python 3.10/3.12/3.13; each runs 31 tests from source and again against isolated installed wheel and sdist.
- [Sanitized machine-readable verification](verification/v1.0.0.json), also attached to the release as `PUBLIC-VERIFICATION.json`.
- [Independent verifier](../scripts/verify_public_release.py), also attached to the release as `public-verify.py`.

## Actual public artifact checks

The agent used unauthenticated HTTPS to fetch release metadata and artifacts. Downloaded bytes matched GitHub API digests and sizes, published SHA256SUMS, PROVENANCE.json, the public tag and exact-revision passing required-ci. The source archive includes documentation, examples, acceptance and regression tests, and distribution-check tooling.

Both the published wheel and published sdist installed noneditably into fresh macOS arm64 / Python 3.12.14 environments, with PYTHONPATH/PYTHONHOME removed, Python isolation, no inherited site packages and verified module locations inside the new environment. All **31 published tests passed for each installed artifact**. Only test files were copied out of the downloaded sdist for those installed-package runs; no source tree was added to the import path.

Each installation independently exercised:

- Installed console command and constructed example: nine accounted records, six cases, three unresolved rows, exact category counts.
- Complete six-case reviewed/escalated decision roundtrip and report reproduction.
- Existing-output refusal without modification; rejection of stale decisions, unsupported naive-window timestamps and tampered report contents.
- Relocation and verification after original input files and original report paths were removed, with Python socket constructors and create_connection disabled during principal/failure flows.

The existing release artifacts were not replaced. Verification evidence and its script were added after the checks completed.

## SHA-256

| File | SHA-256 |
| --- | --- |
| gage_window-1.0.0-py3-none-any.whl | `fd3f0812a9af274965c68f440196885b613d8a345f91c0604f886b65a978e9fc` |
| gage_window-1.0.0.tar.gz | `1bdb4438a45d9998aabde0cb80784f601e28f6d87050ff0001b73ec23886fda1` |
| PUBLIC-VERIFICATION.json | `c3ce94e26ecb67c9f865418a76df92262a7799c4a28ed57f1f24fb2caeb86927` |
| public-verify.py | `d7ad6440dfd34bc707c645050e850ba73894374327ebf55659054fb6e3e22df5` |

Hashes establish matching public bytes, not an independent cryptographic publisher identity. Independent public-download execution covered one local OS/Python environment; CI provides the other advertised combinations. No customer adoption, measured savings, complete external history, regulatory certification, safety assurance or engineering correctness is claimed. Users still supply their own evidence, mappings, review windows and human judgments.

The verifier is pinned to v1.0.0. To preserve separation from development files, copy it to a clean directory outside any product checkout, then rerun with Python 3.10+ using `python verify_public_release.py --expected-commit 4a3b134764544a5f2e169f8d0f1b7f0d8b21a0aa --report verification.json`. It downloads public files and needs network access for downloads and sdist build tooling. Runtime workflow checks themselves disable sockets. Output is sanitized; temporary verification environments are retained beside the script for inspection.
