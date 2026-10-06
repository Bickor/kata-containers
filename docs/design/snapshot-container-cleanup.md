# Restored container cleanup compatibility

Selective security-sidecar replacement restores a VM with frozen container cgroups,
then removes selected captured processes before enabling the target network.
The 3.32-compatible guest agent exposed two removal failures in that path:

1. systemd `KillUnit` returned InvalidArgs after rustjail had already signaled the
   processes. Cleanup now tolerates a failed redundant kill only after observing
   an empty cgroup, with a bounded wait; populated cgroups still fail closed.
2. Recursive bundle deletion traversed surviving read-only bind mounts. Cleanup
   now detaches mount points contained within that container's bundle, deepest
   first, before deleting the runtime directory. It does not recursively delete
   the backing storage through a mounted filesystem.

Snapshots embed the guest agent's memory. A new guest image alone cannot fix an
already captured snapshot; validation uses a fresh source and snapshot.

The companion runtime's CopyFileRequest field 9 (`preserve_inode`) also needs a
3.32-compatible implementation. Without it, PrepareGuestMount truncates the
existing backing file, then legacy CopyFile renames a replacement over it. The
restored bind mount remains attached to the truncated inode: resolv.conf/hosts/
hostname become empty despite a successful copy RPC. Preserve-inode requests now
update only an existing canonical, singly-linked regular backing file in place,
with bounds checks and O_NOFOLLOW. A focused test verifies existing open file
handles observe the new bytes and hardlinked targets are rejected.
