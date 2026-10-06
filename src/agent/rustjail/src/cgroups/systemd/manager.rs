// Copyright 2021-2022 Kata Contributors
//
// SPDX-License-Identifier: Apache-2.0
//

use crate::cgroups::Manager as CgroupManager;
use crate::protocols::agent::CgroupStats;
use anyhow::{anyhow, Result};
use cgroups::freezer::FreezerState;
use libc::{self, pid_t};
use oci::LinuxResources;
use oci_spec::runtime as oci;
use serde::{Deserialize, Serialize};
use std::any::Any;
use std::collections::HashMap;
use std::convert::TryInto;
use std::string::String;
use std::vec;

use super::super::fs::Manager as FsManager;

use super::cgroups_path::CgroupsPath;
use super::common::{CgroupHierarchy, Properties};
use super::dbus_client::{DBusClient, SystemdInterface};
use super::subsystem::transformer::Transformer;
use super::subsystem::{cpu::Cpu, cpuset::CpuSet, memory::Memory, pids::Pids};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Manager {
    pub paths: HashMap<String, String>,
    pub mounts: HashMap<String, String>,
    pub cgroups_path: CgroupsPath,
    pub cpath: String,
    // dbus client for set properties
    dbus_client: DBusClient,
    // fs manager for get properties
    fs_manager: FsManager,
    // cgroup version for different dbus properties
    cg_hierarchy: CgroupHierarchy,
}

impl CgroupManager for Manager {
    fn apply(&self, pid: pid_t) -> Result<()> {
        if self.dbus_client.unit_exists()? {
            let subcgroup = self.fs_manager.subcgroup();
            self.dbus_client.add_process(pid, subcgroup)?;
        } else {
            self.dbus_client.start_unit(
                (pid as u32).try_into().unwrap(),
                self.cgroups_path.slice.as_str(),
                &self.cg_hierarchy,
            )?;
        }

        Ok(())
    }

    fn set(&self, r: &LinuxResources, _: bool) -> Result<()> {
        let mut properties: Properties = vec![];

        let systemd_version = self.dbus_client.get_version()?;
        let systemd_version_str = systemd_version.as_str();

        Cpu::apply(r, &mut properties, &self.cg_hierarchy, systemd_version_str)?;
        Memory::apply(r, &mut properties, &self.cg_hierarchy, systemd_version_str)?;
        Pids::apply(r, &mut properties, &self.cg_hierarchy, systemd_version_str)?;
        CpuSet::apply(r, &mut properties, &self.cg_hierarchy, systemd_version_str)?;

        self.dbus_client.set_properties(&properties)?;

        Ok(())
    }

    fn get_stats(&self) -> Result<CgroupStats> {
        self.fs_manager.get_stats()
    }

    fn freeze(&self, state: FreezerState) -> Result<()> {
        match state {
            FreezerState::Thawed => self.dbus_client.thaw_unit(),
            FreezerState::Frozen => self.dbus_client.freeze_unit(),
            _ => Err(anyhow!("Invalid FreezerState")),
        }
    }

    fn destroy(&mut self) -> Result<()> {
        if let Err(error) = self.dbus_client.kill_unit() {
            // Container::destroy already sent SIGKILL to every process. Some
            // systemd/kernel combinations reject KillUnit for an emptied scope
            // (including restored frozen scopes). Never treat that as success
            // while the actual cgroup still contains a process.
            if !wait_for_empty_scope(
                || self.fs_manager.get_pids(),
                100,
                || {
                    std::thread::sleep(std::time::Duration::from_millis(10));
                },
            )? {
                return Err(error);
            }
        }
        self.fs_manager.destroy()
    }

    fn get_pids(&self) -> Result<Vec<pid_t>> {
        self.fs_manager.get_pids()
    }

    fn update_cpuset_path(&self, guest_cpuset: &str, container_cpuset: &str) -> Result<()> {
        self.fs_manager
            .update_cpuset_path(guest_cpuset, container_cpuset)
    }

    fn get_cgroup_path(&self, cg: &str) -> Result<String> {
        self.fs_manager.get_cgroup_path(cg)
    }

    fn as_any(&self) -> Result<&dyn Any> {
        Ok(self)
    }

    fn name(&self) -> &str {
        "systemd"
    }
}

fn wait_for_empty_scope(
    mut pids: impl FnMut() -> Result<Vec<pid_t>>,
    attempts: usize,
    mut wait: impl FnMut(),
) -> Result<bool> {
    for _ in 0..attempts {
        if pids()?.is_empty() {
            return Ok(true);
        }
        wait();
    }
    Ok(false)
}

#[cfg(test)]
mod removal_tests {
    use super::*;
    #[test]
    fn redundant_kill_failure_requires_verified_empty_scope() {
        assert!(wait_for_empty_scope(|| Ok(vec![]), 1, || {}).unwrap());
        assert!(!wait_for_empty_scope(|| Ok(vec![123]), 2, || {}).unwrap());
        assert!(wait_for_empty_scope(|| Err(anyhow!("unreadable cgroup")), 2, || {}).is_err());
        let mut count = 0;
        assert!(wait_for_empty_scope(
            || {
                count += 1;
                Ok(if count == 2 { vec![] } else { vec![123] })
            },
            2,
            || {}
        )
        .unwrap());
    }
}

impl Manager {
    pub fn new(cgroups_path_str: &str) -> Result<Self> {
        let cgroups_path = CgroupsPath::new(cgroups_path_str)?;
        let (parent_slice, unit_name) = cgroups_path.parse()?;
        let cpath = parent_slice + "/" + &unit_name;

        let fs_manager = FsManager::new_systemd(cpath.as_str())?;

        Ok(Manager {
            paths: fs_manager.paths.clone(),
            mounts: fs_manager.mounts.clone(),
            cgroups_path,
            cpath,
            dbus_client: DBusClient::new(unit_name),
            fs_manager,
            cg_hierarchy: if cgroups::hierarchies::is_cgroup2_unified_mode() {
                CgroupHierarchy::Unified
            } else {
                CgroupHierarchy::Legacy
            },
        })
    }
}
