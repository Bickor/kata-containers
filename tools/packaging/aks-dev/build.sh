#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
commit=${1:?source commit is required}
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo 'invalid source commit' >&2; exit 1; }
export RUSTUP_TOOLCHAIN=1.95.0
lock_before=$(sha256sum Cargo.lock)
package=$(python3 -c 'import json; print(json.load(open("tools/packaging/aks-dev/release.json"))["packageVersion"])')
make -C src/runtime-rs BUILD_TYPE=release LIBC=gnu USE_BUILTIN_DB=false \
    HYPERVISOR=clh-runtime-rs PACKAGE_VERSION="$package" COMMIT="$commit" runtime
make -C src/agent BUILD_TYPE=release LIBC=gnu COMMIT="$commit" src/version.rs
make -C src/agent BUILD_TYPE=release LIBC=gnu COMMIT="$commit" optimize
make -C src/tools/kata-ctl BUILD_TYPE=release LIBC=gnu USE_BUILTIN_DB=false COMMIT="$commit"

# All tests use the same source tree and protocol definitions as all binaries.
cargo test --locked -p virt_container --lib restore::tests -- --nocapture
cargo test --locked -p resource --lib smb_volume -- --nocapture
cargo test --locked -p resource --lib ephemeral_volume -- --nocapture
cargo test --locked -p resource --lib initial_size -- --nocapture
cargo test --locked -p resource --lib share_fs_volume -- --nocapture
cargo test --locked -p rustjail --lib redundant_kill_failure_requires_verified_empty_scope -- --nocapture
cargo test --locked -p rustjail --lib detach_only_owned_mounts_deepest_first -- --nocapture
cargo test --locked -p kata-agent --bin kata-agent test_do_copy_file_preserve_inode -- --nocapture
test "$lock_before" = "$(sha256sum Cargo.lock)" || { echo 'build changed Cargo.lock' >&2; exit 1; }

# Cloud Hypervisor is an external dependency, pinned by this branch's manifest.
# No binaries or configurations are inherited from an old installer image.
clh_commit=$(python3 -c 'import json; print(json.load(open("tools/packaging/aks-dev/release.json"))["cloudHypervisor"]["commit"])')
clh_repo=$(python3 -c 'import json; print(json.load(open("tools/packaging/aks-dev/release.json"))["cloudHypervisor"]["repository"])')
git init /cloud-hypervisor
git -C /cloud-hypervisor remote add origin "$clh_repo"
git -C /cloud-hypervisor fetch --depth=1 origin "$clh_commit"
git -C /cloud-hypervisor checkout --detach FETCH_HEAD
test "$(git -C /cloud-hypervisor rev-parse HEAD)" = "$clh_commit"
cargo build --locked --manifest-path /cloud-hypervisor/Cargo.toml --release \
    --no-default-features --features mshv --bin cloud-hypervisor
mkdir -p /out/payload
for binary in containerd-shim-kata-v2 kata-agent kata-ctl; do
    install -m 0755 "target/x86_64-unknown-linux-gnu/release/$binary" "/out/payload/$binary"
done
install -m 0755 /cloud-hypervisor/target/release/cloud-hypervisor /out/payload/
python3 tools/packaging/aks-dev/package.py "$commit" /out
