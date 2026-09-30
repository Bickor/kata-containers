# AKS guest SMB PVC experiment

This test ports [Microsoft Kata PR #561](https://github.com/microsoft/kata-containers/pull/561)
to the exact snapshot-demo runtime base `4699235`. It is not a general filesystem
PVC implementation. With `shared_fs = "none"`, ordinary host filesystem mounts
still take the CopyFile path and do not persist guest writes.

The compatible Azure Files CSI path is selected with a dedicated StorageClass:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: kata-pvc-test-smb
provisioner: file.csi.azure.com
parameters:
  skuName: Standard_LRS
  confidentialContainerLabel: kubernetes.azure.com/kata-vm-isolation
  runtimeClassHandler: kata-pvc-test
reclaimPolicy: Delete
volumeBindingMode: Immediate
mountOptions:
  - vers=3.0
  - nosharesock
  - actimeo=0
```

The node driver must enable `--enable-kata-cc-mount=true`. The label parameter
selects the existing sandbox-node label; it does not make this a confidential
VM. The handler parameter must match the test RuntimeClass handler. CSI supplies
Kata direct-volume metadata and credentials so the guest mounts the SMB share.
The CSI-managed Secret is used for SMB authentication; no keys are embedded in
the source or manifests. Deployment uses the existing Azure CLI identity.

## Build

Build from repository root with `KATA_COMMIT` set to the pushed feature commit:

```sh
docker build -f tools/testing/aks-pvc/Dockerfile \
  --build-arg KATA_COMMIT=<feature-commit> \
  -t <registry>/runtime/kata-pvc-test:<tag> .
```

The image builds the Rust runtime plus focused SMB unit tests. Its guest agent
uses fork commit `ce08dce9739bdd4dc531f245afeb81a3b721dfaa` (AKS-compatible 3.32
with restore backports), applying the three agent-side files from the SMB port.
The base installer contributes the pinned Cloud Hypervisor and known-good config.

## Live test

Scripts are deliberately pinned to `aks-agent-poc-wus3-admin` and its current
Kata node. Review those constants before using another cluster.

```sh
python3 tools/testing/aks-pvc/deploy.py <image-by-digest>
python3 tools/testing/aks-pvc/live-test.py setup
python3 tools/testing/aks-pvc/live-test.py verify
```

The installer references the namespaced `acr-test-pull` imagePullSecret. Create
it using an ephemeral ACR login token before deployment when the cluster lacks
pull access; remove it with the test namespace afterwards. Do not enable
anonymous registry access for this experiment.

On the first CSI guest-mount request, the current node driver can discover the
custom Kata node label only at publish time, after staging omitted the metadata.
If the pod reports missing staging `mountInfo.json`, delete both consumers of
that test claim, wait for volume unstage, then recreate them. This required one
retry in the live test; subsequent mounts and pod replacements worked.

Run Kata tests sequentially on small OS disks: the EROFS snapshotter can consume
substantial host storage per pod. The verification script removes extra Kata
consumers as each case finishes.

Installation adds `/opt/kata-pvc-test` and one isolated containerd handler,
then restarts containerd to load it. Existing handlers are preserved. Failed
containerd readiness restores the saved configuration. The script refuses to
overwrite an existing test installation.

Tests cover standard filesystem PVC behavior, real guest CIFS mounts, independent
backing-store readers, pod replacement, sharing between Kata VMs, read-only
mounts, and raw-block persistence. The optional `direct <pod-name>` mode manually
stages metadata for runtime-only diagnosis and is not a replacement CSI driver.

Delete the test namespace and test StorageClass after testing; verify PVC/PV
and Azure disk/share deletion. The isolated runtime can remain available for
subsequent experiments. Recreating the node removes this temporary installation.
