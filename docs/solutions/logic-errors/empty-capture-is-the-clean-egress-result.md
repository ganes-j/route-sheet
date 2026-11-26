---
title: "A clean macOS pktap capture is an empty file, so a header check can never pass the egress gate"
module: "bin/magnitude-egress-check (capture_problem)"
date: "2026-11-26"
problem_type: logic_error
component: tooling
severity: medium
symptoms:
  - "magnitude-egress-check exits 3: 'is not a pcap/pcapng capture yet (is tcpdump running?)' while tcpdump is running"
  - "The capture file stays at 0 bytes for the whole run"
root_cause: logic_error
resolution_type: code_fix
tags:
  - "tcpdump"
  - "pktap"
  - "egress-check"
  - "liveness-check"
  - "magnitude"
---

# A clean macOS pktap capture is an empty file, so a header check can never pass the egress gate

## Problem

`bin/magnitude-egress-check` gates `llocal --pii` runs on Magnitude. It watches Magnitude's processes with a pid-scoped `tcpdump` capture while it sends canary prompts, and any captured byte fails the check. To prove the capture was live, it required the file to start with pcap or pcapng magic bytes. On macOS, a clean run never produces those bytes, so the check refused to run in exactly the case it exists to confirm: no egress.

## Symptoms

- `tcpdump -i pktap,all -k -U -w FILE -Q 'pid=…' …` prints `listening on pktap,all, link-type PKTAP` and keeps running.
- `ls -la FILE` shows 0 bytes.
- The check exits 3 with `FILE is not a pcap/pcapng capture yet (is tcpdump running?)` and writes no record, so `--pii` stays refused.

## What Didn't Work

- Re-running the check against the same capture: the file never gains a header while no matching packet arrives.
- The unit tests: `setUp` wrote `PCAPNG_MAGIC` into the capture file before every test, so the suite encoded the same wrong assumption as the code and could not catch it. This is the same failure family as `2026-07-22-local-drift-narrow-fixtures-hid-parser-bugs.md`.

## Solution

Prove liveness from the process, not from the file. The check already confirmed (via `ps`) that a running `tcpdump` writes that exact path with a `-Q` filter naming every Magnitude pid. That check is now the liveness proof, and the header test only rejects a file that has content but is not a capture:

```python
# before
with open(pcap, "rb") as f:
    if f.read(4) not in CAPTURE_MAGICS:
        return "%s is not a pcap/pcapng capture yet (is tcpdump running?)" % pcap

# after: an empty file is the clean result; liveness comes from the writer check that follows
with open(pcap, "rb") as f:
    head = f.read(4)
if head and head not in CAPTURE_MAGICS:
    return "%s is not a pcap/pcapng capture" % pcap
```

Any packet makes the file grow (header plus packet), and growth during the run was already an automatic FAIL, so the gate is no weaker.

Tests added in `tests/test_magnitude_egress_check.py`: an empty file with a live writer passes; an empty file with no writer exits 3; an empty file that grows fails; non-capture bytes exit 3. The first two were red before the fix.

## Why This Works

On the `pktap` interface, macOS `tcpdump` writes no file header until the first packet that matches the filter. With `-Q pid=…` and a loopback exclusion, a Magnitude that sends nothing off the machine produces no matching packet, so the file stays at 0 bytes. The magic-byte test therefore measured "has traffic happened", which is the failure condition, not "is the capture running". The process check measures liveness directly.

## Prevention

- **A liveness check must not depend on an artifact that the success case never produces.** Ask what the file, log or output looks like when everything goes right, and make sure the check accepts that.
- **Test the good outcome with a real tool once, not only with fixtures.** The fixture wrote the header the author expected. The first live run with real `tcpdump` showed the actual behaviour.
- When a gate checks for silence, prove that the observer is running separately from whatever the observer records.
