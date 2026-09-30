"""Test standard CSI PVCs and an explicitly staged SMB direct-volume adapter.

The adapter is a test fixture, not a CSI driver: metadata is created before the
Kata workload is scheduled and removed during cleanup. Credentials are read
from the CSI-generated Secret and transmitted only via kubectl stdin.
"""
import base64
import json
import subprocess
import sys

CTX = "aks-agent-poc-wus3-admin"
NS = "kata-pvc-test"
NODE = "aks-kata-94127873-vmss00000b"
IMAGE = "mcr.microsoft.com/oss/busybox/busybox:1.33.1"


def k(*args, data=None):
    p = subprocess.run(["kubectl", "--context", CTX, "-n", NS, *args],
                       input=data, capture_output=True, text=True, timeout=180)
    if p.returncode:
        # Do not include stdin, which can contain ephemeral SMB credentials.
        raise RuntimeError(f"kubectl {args[:3]}: {p.stderr}")
    return p.stdout


def apply(obj):
    return k("apply", "-f", "-", data=json.dumps(obj))


def pod(name, claim, runtime="kata-pvc-test", gate=False, block=False):
    c = {"name": "probe", "image": IMAGE, "command": ["sh", "-c", "sleep 7200"],
         "resources": {"requests": {"cpu": "100m", "memory": "512Mi"},
                       "limits": {"cpu": "1", "memory": "512Mi"}}}
    c["volumeDevices" if block else "volumeMounts"] = [
        {"name": "data", "devicePath": "/dev/probe"} if block else
        {"name": "data", "mountPath": "/data"}]
    spec = {"runtimeClassName": runtime, "automountServiceAccountToken": False,
            "nodeSelector": {"kubernetes.io/hostname": NODE}, "restartPolicy": "Never",
            "terminationGracePeriodSeconds": 5, "containers": [c],
            "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": claim}}]}
    if gate:
        spec["schedulingGates"] = [{"name": "test.kata.local/metadata-ready"}]
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": NS}, "spec": spec}


def ready(name):
    print(k("wait", f"pod/{name}", "--for=condition=Ready", "--timeout=120s"), end="")


def run(name, command):
    print(k("exec", name, "--", "sh", "-ec", command), end="")


def stage(name):
    p = json.loads(k("get", "pod", name, "-o", "json"))
    claim = json.loads(k("get", "pvc", "files", "-o", "json"))
    pv = json.loads(k("get", "pv", claim["spec"]["volumeName"], "-o", "json"))
    parts = pv["spec"]["csi"]["volumeHandle"].split("#")
    account, share = parts[1:3]
    secrets = json.loads(k("get", "secrets", "-o", "json"))["items"]
    secret = next(s for s in secrets if "azurestorageaccountkey" in s.get("data", {})
                  and base64.b64decode(s["data"]["azurestorageaccountname"]).decode() == account)
    password = base64.b64decode(secret["data"]["azurestorageaccountkey"]).decode()
    source = f'/var/lib/kubelet/pods/{p["metadata"]["uid"]}/volumes/kubernetes.io~csi/{pv["metadata"]["name"]}/mount'
    request = {"source": source, "info": {"volume-type": "azurefile",
               "device": f"//{account}.file.core.windows.net/{share}", "fstype": "cifs",
               "options": ["vers=3.0", "serverino", "nosharesock", "actimeo=0"],
               "metadata": {"sensitiveMountOptions": f"username={account},password={password}"}}}
    # Resolve on the node and write a root-only metadata file without logging it.
    program = '''import base64,json,os,pathlib,socket,sys
r=json.load(sys.stdin)
host=r['info']['device'].split('/')[2]
r['info']['options'].append('ip='+socket.gethostbyname(host))
root=pathlib.Path('/host/run/kata-containers/shared/direct-volumes')
p=root/base64.urlsafe_b64encode(r['source'].encode()).decode()
p.mkdir(parents=True,exist_ok=False,mode=0o700)
f=p/'mountInfo.json'
fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as out: json.dump(r['info'],out)
with open('/host/opt/kata-pvc-test/metadata-paths','a') as out: out.write(str(p)+'\\n')
print('SMB test metadata staged')
'''
    print(k("exec", "-i", "installer", "--", "python3", "-c", program, data=json.dumps(request)), end="")
    print(k("patch", "pod", name, "--type=json", "-p", '[{"op":"remove","path":"/spec/schedulingGates"}]'), end="")


def setup():
    print(apply({"apiVersion": "storage.k8s.io/v1", "kind": "StorageClass",
          "metadata": {"name": "kata-pvc-test-smb"}, "provisioner": "file.csi.azure.com",
          "reclaimPolicy": "Delete", "volumeBindingMode": "Immediate",
          "parameters": {"skuName": "Standard_LRS",
                         "confidentialContainerLabel": "kubernetes.azure.com/kata-vm-isolation",
                         "runtimeClassHandler": "kata-pvc-test"},
          "mountOptions": ["vers=3.0", "nosharesock", "actimeo=0"]}), end="")
    for name, sc, mode, access in [("files", "azurefile-csi", "Filesystem", "ReadWriteMany"),
                                  ("files-direct", "kata-pvc-test-smb", "Filesystem", "ReadWriteMany"),
                                  ("disk", "managed-csi", "Filesystem", "ReadWriteOnce"),
                                  ("block", "managed-csi", "Block", "ReadWriteOnce")]:
        print(apply({"apiVersion": "v1", "kind": "PersistentVolumeClaim",
              "metadata": {"name": name, "namespace": NS}, "spec": {"storageClassName": sc,
              "volumeMode": mode, "accessModes": [access], "resources": {"requests": {"storage": "1Gi"}}}}), end="")
    for name, claim, runtime, block in [("files-observer", "files", "runc", False),
                                      ("files-standard", "files", "kata-pvc-test", False),
                                      ("disk-standard", "disk", "kata-pvc-test", False),
                                      ("disk-observer", "disk", "runc", False),
                                      ("files-csi-direct", "files-direct", "kata-pvc-test", False),
                                      ("files-csi-observer", "files-direct", "runc", False),
                                      ("block", "block", "kata-pvc-test", True)]:
        print(apply(pod(name, claim, runtime, block=block)), end="")


def replace(name, claim, block=False):
    print(k("delete", "pod", name, "--wait=true", "--timeout=90s"), end="")
    print(apply(pod(name, claim, block=block)), end="")
    ready(name)


def verify():
    for name in ["files-standard", "files-observer", "disk-standard", "disk-observer",
                 "files-csi-direct", "files-csi-observer", "block"]:
        ready(name)
    for prefix in ["files", "disk"]:
        name = prefix + "-standard"
        observer = prefix + "-observer"
        run(name, "df -T /data; printf 'copy-only-marker' > /data/copy-only-marker; sync")
        run(observer, "test ! -e /data/copy-only-marker; printf 'CONFIRMED standard PVC still copy-only\\n'")
        replace(name, prefix)
        run(name, "test ! -e /data/copy-only-marker; printf 'CONFIRMED marker lost after replacement\\n'")
    name, observer = "files-csi-direct", "files-csi-observer"
    run(name, "uname -r; df -T /data; grep ' /data .* cifs ' /proc/mounts; printf 'direct-persistent-marker' > /data/direct-marker; sync")
    run(observer, "test \"$(cat /data/direct-marker)\" = direct-persistent-marker; printf 'observer-response' > /data/response; sync; printf 'PASS independent reader sees Kata write\\n'")
    run(name, "test \"$(cat /data/response)\" = observer-response; printf 'PASS Kata sees live external update\\n'")
    replace(name, "files-direct")
    run(name, "test \"$(cat /data/direct-marker)\" = direct-persistent-marker; printf 'PASS SMB persists across Kata pod replacement\\n'")
    print(apply(pod("files-csi-second", "files-direct")), end="")
    ready("files-csi-second")
    run("files-csi-second", "test \"$(cat /data/direct-marker)\" = direct-persistent-marker; printf 'second-kata' > /data/second; sync")
    run(name, "test \"$(cat /data/second)\" = second-kata; printf 'PASS live sharing across independent Kata VMs\\n'")
    readonly = pod("files-csi-readonly", "files-direct")
    readonly["spec"]["volumes"][0]["persistentVolumeClaim"]["readOnly"] = True
    readonly["spec"]["containers"][0]["volumeMounts"][0]["readOnly"] = True
    print(apply(readonly), end="")
    ready("files-csi-readonly")
    run("files-csi-readonly", "test \"$(cat /data/direct-marker)\" = direct-persistent-marker; if touch /data/should-not-exist 2>/dev/null; then exit 1; fi; printf 'PASS read-only mount rejects writes\\n'")
    run("block", "test -b /dev/probe; printf 'raw-persist-test' | dd of=/dev/probe bs=4096 conv=fsync")
    replace("block", "block", block=True)
    run("block", "test \"$(dd if=/dev/probe bs=1 count=16 2>/dev/null)\" = raw-persist-test; printf 'PASS raw block persistence regression\\n'")


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        setup()
    elif sys.argv[1] == "verify":
        verify()
    elif sys.argv[1] == "direct":
        name = sys.argv[2]
        print(apply(pod(name, "files", gate=True)), end="")
        stage(name)
        ready(name)
