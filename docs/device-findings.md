# Device observations and unresolved questions

Collected October 24, 2026. [O] denotes a recorded observation; [I] denotes an inference. Local evidence is retained privately; these findings need independent replication.

## Platform and management

[O] The device's setup interface identifies a Lexmark Optra Compute 550 platform. The inspected device reported firmware `3.5.4` and build target `granite2v8-sifter`. Exact SoC, board pinout, and debug access remain unverified.

[O] The local HTTPS setup interface uses device-password authentication. Observed management routes include settings, encrypted support logs, external diagnostic URLs, and proxy configuration. Downloaded support logs were encrypted; local plaintext decoding was not demonstrated.

## Proxy experiment

[O] TLS interception was rejected with an unknown-CA error. That establishes rejection of the test certificate, not the exact contents of the device trust store.

[O] Pass-through proxying carried some connections, but jobs failed during testing. Changing the proxy also interrupted the device's management/cloud connection. The failure mechanism was not isolated; insufficient proxy throughput is an unproven hypothesis.

[O] The final historical verification returned empty `ProxyAddress` and `ProxyPort` fields. The device subsequently reconnected to the cloud. Do not assume this experimental proxy is still configured based solely on later job failures.

## Current troubleshooting lead

[O] A later job displayed “Unable to start job due to system error” while the portal reported the device connected. The owner reported a solid green power light and stopped rollers.

[O] Roca's [support homepage](https://support.rocarobotics.com/hc/en-us/) displayed a high-server-load notice when checked on October 24, 2026, including a request not to delete batches. This is a time-specific notice.

[I] Service-side delay or failure is plausible, but neither the notice nor the green light establishes the cause of an individual job failure.

The official [light guide](https://support.rocarobotics.com/hc/en-us/articles/47929740990733-Roca-Sifter-Buttons-Lights-and-Sounds) distinguishes the power light from roller-path alerts. Use the [error guide](https://support.rocarobotics.com/hc/en-us/articles/47929818068237-Roca-Sifter-Errors-and-Resolution-Steps) for specific reported faults.

## Open questions

- Can a stalled job be correlated with upload failures or cloud processing delays?
- What recovery sequence preserves all scanned records?
- Is a higher-resolution export available through a supported route?
- Can vendor-provided firmware or documented hardware access support owner backups?

No working firmware extraction, UART pinout, secure-boot bypass, or offline operation has been demonstrated here.
