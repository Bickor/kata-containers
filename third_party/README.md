# pathrs 0.2.4 compatibility patch

The `pathrs-0.2.4` directory is the published crates.io archive, SHA256
`2fb2311801201fc6fd2e8a9f4841b41eee565e992fbe713731e29e367b8e3f17`,
matching the prior Cargo.lock checksum. Upstream licensing is retained in full.

Only `src/utils/kernel_version.rs` is changed: accept a dot before a distro
suffix after at least two numeric components, retaining malformed-version
rejection. Add Azure Linux MSHV kernel examples to the parser tests.

The unmodified library panics on `6.6.137.mshv1-1.azl3` during the native 4.1
agent's first CopyFile mkdir operation. This was reproduced on a fresh AKS node
using the unified rc.1 release. The patch keeps pathrs containment protections;
it does not replace safe path handling or alter kernel-version comparisons.

The root Cargo patch keeps this dependency and its fix in the same `aks-dev`
source commit as the runtime and agent. Remove the vendored override after an
upstream release includes the fix and guest validation passes.
