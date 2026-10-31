# WordArc 0.10.2 — verification (October 24, 2026)

The update check could hang on `Checking…`: an SSL error raised while the
default certificate store loaded escaped the worker, so neither a result
nor an error ever reached the UI.

## Fix

- The update query and the download build their HTTPS context explicitly
  from the packaged certifi CA roots and keep it in memory. `CERT_REQUIRED`
  and hostname verification stay on; verification is never disabled.
- SSL, network, and malformed-response paths all become UpdateError. The
  worker also logs unexpected exceptions and forwards a terminal error to
  the UI.
- A 30-second Qt timer settles a long check and re-enables the button. Every
  check has an identity; a late reply from an expired check cannot change a
  later check's state.
- Retrying clears the stale download offer; up-to-date and error outcomes
  restore the buttons consistently.

## Verification

- The two tests reproducing the logged SSL failure failed before the fix;
  after it, the update/UI group passes (full suite **710 passed, 2 skipped,
  12 subtests**).
- Audit gates (imports, build, installer flags, dependency scan) passed with
  no known issues.
- Real click-through on a Settings window completed the check with an
  up-to-date result and a live button (~0.80 s, TLS verified).
- Frozen-app acceptance is now part of `verify_release_package.py`: a real
  GitHub request plus Qt callback result plus certificate verification.
- Shipped inner EXE: real HTTPS + Qt check in **0.35 s** with a latest
  result; isolated `--version` 4.51 s (extraction included). Embedded source,
  version, assets, engine manifest, and repair ZIP verified.
- `WordArc-0.10.2.exe`: 312,221,827 bytes; SHA256
  `b5db20fa2c4fbcfb2ed7359a4231de82dff0a060d212153aab8a5c383252358e`.
  `WordArcVulkan-1.9.2.zip` unchanged.

## Limits

The single root cause (one bad certificate vs. store loading) was not
proven; what is proven is that a store-loading failure is now caught and
reported. Python threads doing network I/O are never killed; a post-timeout
reply is ignored. An installed app is never replaced automatically.
