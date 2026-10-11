# Single-source AKS development release

`aks-dev` is the integration and release branch. Target new PRs here. Runtime,
guest agent and kata-ctl build from the same 4.1 source commit and protocol tree.
The release includes a newly built MSHV Cloud Hypervisor, whose external commit
is pinned in `release.json`, and a configuration generated from this tree.
It never clones a second Kata branch, applies an external agent patch, or copies
binaries from a historical installer image. The consumer still supplies the
AKS-managed guest kernel/image and injects the released 4.1 agent.

## Source consolidation

Base: Microsoft `msft-main` commit `974aba5fa84c6c1d4b068f8e9c677716c27aecae`.
Preserved changes from the old fork branches:

- PR #2: guest SMB driver, runtime metadata validation and PVC test tooling.
- PR #5: selected-container restart, generation-scoped tmpfs and source clock sync.
- PR #4: verified empty-cgroup cleanup and bundle-contained mount detachment,
  adapted to the native 4.1 agent. Upstream already provides inode-preserving
  CopyFile and restore RPCs, so the 3.32 backports are not reapplied.
- `4699235c1`: large CopyFile chunking, missing from the upstream integration branch.
- PR #3: metadata-only snapshot/rootfs phase timings.

The `review/*`, old `feat/*`, and merged `fix/*` branches are historical inputs,
not release sources. The old `main` is retained as history. No source branch
is deleted or rewritten by this migration.

## Build and release

From a clean repository root:

```bash
docker buildx build -f tools/packaging/aks-dev/Dockerfile \
  --build-arg SOURCE_COMMIT="$(git rev-parse HEAD)" \
  --target artifacts --output type=local,dest=dist .
(cd dist && sha256sum --check SHA256SUMS)
```

The build runs focused restore, storage, resource sizing and guest cleanup tests.
It emits `kata-aks-dev-linux-amd64.tar.gz`, `release-manifest.json`, and
`SHA256SUMS`. Both the archive and individual payload files have checksums.
`packageVersion` is the snapshot compatibility identity, distinct from the shared
upstream 4.1.0 component version. Increment it when publishing a new payload.

After review and merge into `aks-dev`, tag the merged commit with the exact
`release` value from `release.json` and push the tag. The release workflow refuses
tags outside `aks-dev` ancestry or with a mismatched release name. PR builds
produce CI artifacts only. Releases are published once, without asset clobbering.

The demo packages its own installer and CSI helper against this complete payload.
It must verify the release's branch, single commit, archive checksum and component
hashes, then publish an installer and pin its manifest digest. Publication and
consumer adoption follow the Kata PR merge; no pre-merge feature-branch release
is an `aks-dev` release.

## Validation boundary

Build/tests are not live AKS acceptance. Before adopting the new agent, validate
clean-node startup, capture/source recovery, restore continuity with fresh security
containers, policy enforcement and SMB/PVC persistence on a disposable environment.
The demo requires recreated nodes and newly captured snapshots for this package.
