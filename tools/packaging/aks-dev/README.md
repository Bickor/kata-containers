# Single-source AKS development release

`msft-main` is the integration and release branch in `Bickor/kata-containers`.
Target new PRs here. Runtime,
guest agent and kata-ctl build from the same 4.1 source commit and protocol tree.
The release includes a newly built MSHV Cloud Hypervisor, whose external commit
is pinned in `release.json`, and a configuration generated from this tree.
It never clones a second Kata branch, applies an external agent patch, or copies
binaries from a historical installer image. The consumer still supplies the
AKS-managed guest kernel/image and injects the released 4.1 agent.

## Source consolidation

Base: Microsoft `msft-main` commit `24aa86c97d58cdacc8f8758ddfdb11120750f5b0`,
merged on top of the existing `aks-dev` release history. Its 18 new commits
include CoW/hotplug-memory fixes, hostname handling, template clock/RNG refresh,
restored teardown and disk-backed `.restore` workspaces. The merge retains our
cold-container replacement selection and timing imports while using upstream's
disk-backed workspace path.
Preserved changes from the old fork branches:

- PR #2: guest SMB driver, runtime metadata validation and PVC test tooling.
- PR #5: selected-container restart, generation-scoped tmpfs and source clock sync.
- PR #4: verified empty-cgroup cleanup and bundle-contained mount detachment,
  adapted to the native 4.1 agent. Upstream already provides inode-preserving
  CopyFile and restore RPCs, so the 3.32 backports are not reapplied.
- `4699235c1`: large CopyFile chunking, missing from the upstream integration branch.
- PR #3: metadata-only snapshot/rootfs phase timings.
- PR #7 (Microsoft PR #574): explicitly sparse Cloud Hypervisor disks regardless
  of discard requests, and removal of the obsolete two-second disconnect delay.
  Snapshot phase timing instrumentation remains enabled.

The `aks-dev`, `review/*`, old `feat/*`, and merged `fix/*` branches are historical inputs,
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

After review and merge into `msft-main`, tag the merged commit with the exact
`release` value from `release.json` and push the tag. The release workflow refuses
tags outside `msft-main` ancestry or with a mismatched release name. PR builds
produce CI artifacts only. Releases are published once, without asset clobbering.

The demo packages its own installer and CSI helper against this complete payload.
It must verify the release's branch, single commit, archive checksum and component
hashes, then publish an installer and pin its manifest digest. Publication and
consumer adoption follow the Kata PR merge; no pre-merge feature-branch release
is an `msft-main` release.

The build directory `tools/packaging/aks-dev` and archive filename
`kata-aks-dev-linux-amd64.tar.gz` remain compatibility identifiers, not source
branch selections. The manifest records `branch: msft-main` and the exact
Microsoft baseline. The release workflow is `msft-main-release.yaml`.

## Keeping up with Microsoft

Keep the two repositories distinct: `origin` is Bickor's fork; `upstream` is
`https://github.com/microsoft/kata-containers.git`. GitHub's recorded fork parent
is the community repository, so verify the remote URL before fetching updates.
For each update, create a worktree/feature branch from `origin/msft-main`, fetch
Microsoft's `msft-main`, inspect its new commits and merge the chosen exact SHA
into the feature branch. Open a PR back to **Bickor's** `msft-main`. Never reset
the fork branch to Microsoft's tip: that would discard fork-only fixes.

Update `release.json`'s upstream SHA and release/package identity in the same PR.
Check whether upstream supersedes a fork patch before replaying it; keep the
pathrs MSHV parser patch until an equivalent upstream fix is verified. Run the
release build and live snapshot/security/PVC tests before consumer adoption.

Repository default-branch selection is a separate GitHub setting. After this PR
is reviewed, the owner can choose `msft-main` as default and freeze `aks-dev`.
This PR does not change that setting or merge any open PR.

## Demo adoption after review

The currently deployed rc.2 remains pinned and available. Once this PR is merged
and a new release is validated, update the demo's release verifier to require
`msft-main` and the `msft-main-v*` tag prefix (including its ancestry lookup and
negative tests). Update its lock, catalog-derived provenance and deployment
preflight/import branch checks together. Publish a newly built installer and
pin its actual manifest digest. Do not loosen the branch check to accept any
branch or point the existing `aks-dev` release at new source.

The new upstream runtime writes restored writable layers beneath
`snapshot_root/.restore`, not `/run`. Validate cleanup after restore and shim
failure, cold security-container replacement, PVCs and forced Blob restore on
fresh nodes. Old snapshots have a different package identity and must not be
silently reused.

## Validation boundary

Build/tests are not live AKS acceptance. Before adopting the new agent, validate
clean-node startup, capture/source recovery, restore continuity with fresh security
containers, policy enforcement and SMB/PVC persistence on a disposable environment.
The demo requires recreated nodes and newly captured snapshots for this package.
