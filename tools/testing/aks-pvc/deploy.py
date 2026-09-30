"""Deploy the explicit image into the designated agent test cluster."""
import json
from pathlib import Path
import subprocess
import sys

context = "aks-agent-poc-wus3-admin"
namespace = "kata-pvc-test"
image = sys.argv[1]
script = Path(__file__).with_name("install.sh").read_text()
items = [
    {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace,
        "labels": {"pod-security.kubernetes.io/enforce": "privileged"}}},
    {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "installer", "namespace": namespace},
        "data": {"install.sh": script}},
    {"apiVersion": "node.k8s.io/v1", "kind": "RuntimeClass", "metadata": {"name": "kata-pvc-test"},
        "handler": "kata-pvc-test", "scheduling": {"nodeSelector": {"kubernetes.io/hostname": "aks-kata-94127873-vmss00000b"}}},
    {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "installer", "namespace": namespace},
        "spec": {"nodeName": "aks-kata-94127873-vmss00000b", "hostPID": True,
            "automountServiceAccountToken": False, "restartPolicy": "Never",
            "containers": [{"name": "installer", "image": image,
                "command": ["bash", "-c", "sleep infinity"],
                "securityContext": {"privileged": True, "runAsUser": 0},
                "volumeMounts": [{"name": "host", "mountPath": "/host", "mountPropagation": "Bidirectional"},
                                 {"name": "script", "mountPath": "/script", "readOnly": True}]}],
            "volumes": [{"name": "host", "hostPath": {"path": "/", "type": "Directory"}},
                        {"name": "script", "configMap": {"name": "installer"}}]}}
]
manifest = json.dumps({"apiVersion": "v1", "kind": "List", "items": items})
for dryrun in (True, False):
    args = ["kubectl", "--context", context, "apply", "-f", "-"]
    if dryrun:
        args.append("--dry-run=client")
    subprocess.run(args, input=manifest, text=True, check=True)
subprocess.run(["kubectl", "--context", context, "-n", namespace, "wait", "pod/installer",
                "--for=condition=Ready", "--timeout=180s"], check=True)
subprocess.run(["kubectl", "--context", context, "-n", namespace, "exec", "installer", "--",
                "bash", "/script/install.sh"], check=True)
