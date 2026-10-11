#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package the single-tree build; retain every source input and payload hash."""
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tomllib

commit, output = sys.argv[1:]
out = pathlib.Path(output)
payload = out / "payload"
recipe = json.loads(pathlib.Path("tools/packaging/aks-dev/release.json").read_text())
config_name = "configuration-clh-azure-runtime-rs-v2.toml"
config = pathlib.Path("src/runtime-rs/config", config_name).read_text()
settings = {
    "path": '"/opt/aks-sandbox-demo/kata-v2/bin/cloud-hypervisor"',
    "kernel": '"/usr/share/cloud-hypervisor/vmlinux.bin"',
    "image": '"/opt/aks-sandbox-demo/kata-v2/share/kata-containers/kata-containers.img"',
    "valid_hypervisor_paths": '["/opt/aks-sandbox-demo/kata-v2/bin/cloud-hypervisor"]',
    "kernel_params": '"cgroup_no_v1=all systemd.unified_cgroup_hierarchy=1"',
    "default_vcpus": "1",
    "default_memory": "2048",
    "overhead_vcpus": "0",
    "overhead_memory": "0",
    "memory_restore_mode": '"copyonwrite"',
    "shared_fs": '"none"',
    "sandbox_cgroup_only": "true",
    "static_sandbox_resource_mgmt": "true",
    "static_sandbox_default_workload_mem": "2048",
    "static_sandbox_default_workload_vcpus": "2",
    "snapshot_root": '"/var/lib/kata/snapshots"',
    "enable_template": "false",
    "template_path": '"/run/vc/vm/kata-v2-template"',
}
for key, value in settings.items():
    config, count = re.subn(rf"^{key}\s*=.*$", f"{key} = {value}", config, flags=re.M)
    if count != 1:
        raise SystemExit(f"expected one config field {key}, found {count}")
if re.search(r"@[A-Z_]+@", config):
    raise SystemExit("unexpanded configuration placeholder")
tomllib.loads(config)
(payload / config_name).write_text(config)
clh = recipe["cloudHypervisor"]["commit"]
(payload / "source-commits").write_text(
    f"KATA_COMMIT={commit}\nKATA_AGENT_COMMIT={commit}\nKATA_CTL_COMMIT={commit}\n"
    f"CLOUD_HYPERVISOR_COMMIT={clh}\n"
)
recipe["commit"] = commit
recipe["platform"] = "linux/amd64"
recipe["components"] = {
    name: {"commit": commit, "version": pathlib.Path("VERSION").read_text().strip()}
    for name in ("runtime", "agent", "kata-ctl")
}
recipe["guestImage"] = {"source": "AKS-managed node image", "agentReplaced": True}
recipe["validation"] = {"focusedTests": "passed", "liveAcceptance": "not-run"}
recipe["files"] = {
    p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
    for p in sorted(payload.iterdir()) if p.is_file()
}
(payload / "release-manifest.json").write_text(json.dumps(recipe, indent=2) + "\n")
(out / "release-manifest.json").write_bytes((payload / "release-manifest.json").read_bytes())
(payload / "payload.sha256").write_text("".join(
    f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
    for p in sorted(payload.iterdir()) if p.is_file()
))
archive = out / "kata-aks-dev-linux-amd64.tar.gz"
subprocess.run(["tar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0", "--numeric-owner",
                "-czf", str(archive), "-C", str(payload), "."], check=True)
(out / "SHA256SUMS").write_text("".join(
    f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
    for p in (archive, out / "release-manifest.json")
))
