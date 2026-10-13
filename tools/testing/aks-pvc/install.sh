#!/usr/bin/env bash
# Install an isolated experimental handler; run in a privileged hostPID pod.
set -euo pipefail
root=/opt/kata-pvc-test
host() { nsenter -t 1 -m -u -i -n -p -- "$@"; }
test ! -e "/host$root"
mkdir -p "/host$root/bin" "/host$root/share/kata-containers" "/host$root/guest"
cp /payload/{containerd-shim-kata-v2,cloud-hypervisor,kata-ctl} "/host$root/bin/"
cp /payload/configuration-clh-azure-runtime-rs-v2.toml "/host$root/configuration.toml"
python3 - <<'PY'
from pathlib import Path
p = Path('/host/opt/kata-pvc-test/configuration.toml')
s = p.read_text().replace('/opt/aks-sandbox-demo/kata-v2', '/opt/kata-pvc-test')
s = s.replace('enable_template = true', 'enable_template = false')
s = s.replace('/var/lib/kata/snapshots', '/opt/kata-pvc-test/snapshots')
p.write_text(s)
PY
image="$root/share/kata-containers/kata-containers.img"
cp --reflink=auto /host/usr/share/kata-containers/kata-containers.img "/host$image"
truncate -s +64M "/host$image"
host parted -s "$image" resizepart 1 100%
loop=$(host losetup --find --show --partscan "$image")
trap 'host umount "$root/guest" 2>/dev/null || true; host losetup -d "$loop" 2>/dev/null || true' EXIT
host e2fsck -f -y "${loop}p1"
host resize2fs "${loop}p1"
host mount "${loop}p1" "$root/guest"
cp /payload/kata-agent "/host$root/guest/usr/bin/kata-agent"
host umount "$root/guest"
host losetup -d "$loop"
trap - EXIT
mkdir -p "/host$root/snapshots"
cp /host/etc/containerd/config.toml "/host$root/containerd-config.before"
python3 - <<'PY'
from pathlib import Path
import tomllib
p = Path('/host/etc/containerd/config.toml')
s = p.read_text()
assert 'runtimes.kata-pvc-test' not in s
s += '''
# BEGIN kata-pvc-test
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-pvc-test]
  runtime_type = "io.containerd.kata.v2"
  runtime_path = "/opt/kata-pvc-test/bin/containerd-shim-kata-v2"
  privileged_without_host_devices = true
  snapshotter = "erofs"
  pod_annotations = ["io.katacontainers.*"]
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-pvc-test.options]
    ConfigPath = "/opt/kata-pvc-test/configuration.toml"
# END kata-pvc-test
'''
tomllib.loads(s)
p.write_text(s)
PY
if ! host containerd config dump >/dev/null; then
    cp "/host$root/containerd-config.before" /host/etc/containerd/config.toml
    exit 1
fi
host systemctl restart containerd
for attempt in $(seq 1 60); do
    if host crictl info >/dev/null 2>&1; then
        touch "/host$root/.installed"
        /payload/containerd-shim-kata-v2 --version
        exit 0
    fi
    sleep 2
done
cp "/host$root/containerd-config.before" /host/etc/containerd/config.toml
host systemctl restart containerd
exit 1
