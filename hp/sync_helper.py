# -*- coding: utf-8 -*-
#
# H3C Technologies Co., Limited Copyright 2003-2015, All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_log import log as logging
from neutron.plugins.ml2.drivers.hp.common import tools
from neutron.plugins.ml2.drivers.hp.common import db
from neutron.plugins.ml2.drivers.hp.common import mythread


LOG = logging.getLogger(__name__)


class SyncHelper(object):
    def __init__(self, leaf_topology, spine_topology,
                 rpc_clients, timeout, overlap):
        self.timer = mythread.Timer(timeout)
        self.timer_lock = self.timer.get_lock()
        self.overlap = overlap
        self.leaf_topology = leaf_topology
        self.spine_topology = spine_topology
        self.rpc_clients = rpc_clients

    def start(self):
        self.timer.start(self.do_sync)

    def collect_leaf_config(self):
        leaf_config = {}
        host_vlan = db.get_host_vlan()
        leaf_generator = tools.topology_generator(self.leaf_topology)
        leaf_ref_vlans = {}
        for leaf_ip, topology in leaf_generator:
            host_connect = topology['host']
            if host_connect in host_vlan:
                leaf_ref_vlans.setdefault(leaf_ip, set([]))
                vlan_list = host_vlan[host_connect]
                leaf_ref_vlans[leaf_ip] |= set(vlan_list)
                leaf_config.setdefault(leaf_ip, {})
                leaf_config[leaf_ip].setdefault('port_vlan', [])
                leaf_config[leaf_ip]['port_vlan'].\
                    append((topology['ports'], vlan_list))
        for leaf_ip in leaf_ref_vlans:
            leaf_config[leaf_ip].setdefault('vlan_create', [])
            leaf_config[leaf_ip]['vlan_create'] = \
                list(leaf_ref_vlans[leaf_ip])
        return leaf_config, leaf_ref_vlans

    def collect_spine_config(self, leaf_config, leaf_ref_vlans):
        LOG.info(_("Sync spine configuration, spine topo %s, "
                   "leaf configured list %s"),
                 self.spine_topology, leaf_config)
        dev_config = leaf_config
        spine_generator = tools.topology_generator(self.spine_topology)
        spine_ref_vlans = {}
        for spine_ip, topology in spine_generator:
            leaf_ip = topology['leaf_ip']
            if leaf_ip in dev_config:
                vlan_list = list(leaf_ref_vlans[leaf_ip])
                spine_ref_vlans.setdefault(spine_ip, set([]))
                spine_ref_vlans[spine_ip] |= leaf_ref_vlans[leaf_ip]
                dev_config.setdefault(spine_ip, {})
                dev_config[spine_ip].setdefault('vlan_create', [])
                dev_config[spine_ip].setdefault('port_vlan', [])
                dev_config[spine_ip]['port_vlan'].\
                    append((topology['spine_ports'], vlan_list))
                dev_config[leaf_ip]['port_vlan'].\
                    append((topology['leaf_ports'], vlan_list))

        for spine_ip in spine_ref_vlans:
            if spine_ip in dev_config:
                dev_config[spine_ip]['vlan_create'] = \
                    list(spine_ref_vlans[spine_ip])
        return dev_config

    def do_sync(self):
        """When our physical device is reboot,
           it will be used to smooth configuration to device.
        """
        LOG.info(_("Synchronizing is start."))
        with self.timer_lock:
            host_vlan = db.get_host_vlan()
            if len(host_vlan) == 0:
                LOG.info(_("No objects need sync."))
                return

            leaf_config, leaf_ref_vlans = self.collect_leaf_config()
            dev_config = self.collect_spine_config(leaf_config, leaf_ref_vlans)
            LOG.info(_("Sync device config %s"), dev_config)
            for dev_ip in dev_config:
                rpc_client = self.rpc_clients.get(dev_ip, None)
                if rpc_client is not None:
                    vlan_list = dev_config[dev_ip]['vlan_create']
                    port_vlan_tuple_list = dev_config[dev_ip]['port_vlan']
                    result = rpc_client.create_vlan_bulk(vlan_list,
                                                         overlap=self.overlap)
                    if result is True:
                        rpc_client.port_trunk_bulk(port_vlan_tuple_list)
                        LOG.info(_("Sync config %s to %s successful"),
                                 port_vlan_tuple_list, dev_ip)
                    else:
                        LOG.warn(_("Failed to sync %s to %s"),
                                 port_vlan_tuple_list, dev_ip)
        LOG.info(_("Synchronizing is end."))

    def get_lock(self):
        return self.timer_lock
