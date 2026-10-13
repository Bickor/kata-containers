# Cold replacement of selected containers during VM restore

The optional Pod annotation `io.katacontainers.snapshot-restart-containers` is a
JSON array of CRI container names. Operators must restrict it through admission
and permit it in containerd's Pod annotation allowlist. The selection is captured
in `kata-snapshot.json`; restore requires the same selection. Old snapshots with
no selection retain strict adoption behavior. The pause container cannot be selected.

Selected completed containers run again instead of synthesizing completion.
Selected live containers are removed through the guest agent while captured
cgroups remain frozen and the target network remains fenced, then their captured
rootfs references are released. Subsequent create requests use ordinary cold
creation with the destination OCI settings. Unselected containers still require
the exact canonical execution fingerprint and retain host-to-guest ID mapping.

Memory-backed emptyDir paths include the sandbox generation so newly created
security processes cannot attach to captured credentials/sockets by volume name.
Applications that share those volumes with adopted processes require a deliberate
sharing contract; this initial use case isolates security-only volumes.

Source capture recovery synchronizes guest wall time before resuming containers,
as restore already does. Otherwise expiring credentials and external authorization
leases observe capture-duration wall-clock skew even after the VM resumes.

The Security Enhancement consumer integration reruns deny-first network setup and
clears connection tracking before cold bootstrap. Adoption is not an authorization
decision: the management layer still requires fresh runtime binding and current
enforcement before exposing the workload. Full live validation and guest-agent
cleanup fixes are recorded in the companion aks-sandbox-demo PR.
