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

from oslo.config import cfg
from neutron.plugins.ml2 import driver_api
from oslo_log import log as logging
from neutron.common import constants as n_const

from neutron.plugins.ml2.drivers.hp.common import tools
from neutron.plugins.ml2.drivers.hp.common import config
from neutron.plugins.ml2.drivers.hp.common import db
from neutron.plugins.ml2.drivers.hp.rpc import netconf as netconf_cfg
from neutron.plugins.ml2.drivers.hp.rpc import restful as restful_cfg
from neutron.plugins.ml2.drivers.hp import sync_helper


LOG = logging.getLogger(__name__)


class HPDriver(driver_api.MechanismDriver):
    """
    Ml2 Mechanism driver for HP networking hardware.
    Automation for VLANs configure with HP switches.
    """
    def __init__(self, rpc=None):
        config.HPML2Config()
        self.leaf_topology = config.HPML2Config.leaf_topology
        self.spine_topology = config.HPML2Config.spine_topology
        self.sync_overlap = cfg.CONF.ml2_hp.sync_overlap
        self.sync_lock = None
        self.sync_timeout = int(cfg.CONF.ml2_hp.sync_time)
        self.username = cfg.CONF.ml2_hp.username
        self.password = cfg.CONF.ml2_hp.password
        self.url_schema = cfg.CONF.ml2_hp.schema.lower()
        self.default_oem = cfg.CONF.ml2_hp.oem.lower()
        self.rpc_backend = cfg.CONF.ml2_hp.rpc_backend.lower()
        self.sync_helper = None
        self.rpc_clients = {}

    def initialize(self):
        """ MechanismDriver will call it after __init__. """
        if self.rpc_backend == 'netconf':
            self._create_nc_clients()
        elif self.rpc_backend == 'restful':
            self._create_rest_clients()
        LOG.info(_("leaf %s, spine %s, user %s, pass %s, url schema %s,"
                   "timeout %d, rpc backend %s"),
                 self.leaf_topology, self.spine_topology,
                 self.username, self.password, self.url_schema,
                 self.sync_timeout, self.rpc_backend)
        # Create a thread.for sync configuration to physical device.
        self.sync_helper = sync_helper.SyncHelper(self.leaf_topology,
                                                  self.spine_topology,
                                                  self.rpc_clients,
                                                  self.sync_timeout,
                                                  self.sync_overlap)
        self.sync_lock = self.sync_helper.get_lock()
        self.sync_helper.start()

    def _create_rest_clients(self):
        """ Create restful instances foreach leaf and spine device."""
        for leaf in self.leaf_topology:
            rest_client = restful_cfg.RestfulCfg(leaf['ip'],
                                                 self.username,
                                                 self.password)
            self.rpc_clients.setdefault(leaf['ip'], rest_client)

        for spine in self.spine_topology:
            rest_client = restful_cfg.RestfulCfg(spine['ip'],
                                                 self.username,
                                                 self.password)
            self.rpc_clients.setdefault(spine['ip'], rest_client)

    def _create_nc_clients(self):
        """ Create NETCONF instances for each leaf and spine device."""
        for leaf in self.leaf_topology:
            if leaf['oem'] == '':
                leaf['oem'] = self.default_oem
            nc_client = netconf_cfg.NetConfigClient(leaf['oem'],
                                                    leaf['ip'],
                                                    self.url_schema,
                                                    self.username,
                                                    self.password)
            self.rpc_clients.setdefault(leaf['ip'], nc_client)

        for spine in self.spine_topology:
            if spine['oem'] == '':
                spine['oem'] = self.default_oem
            nc_client = netconf_cfg.NetConfigClient(spine['oem'],
                                                    spine['ip'],
                                                    self.url_schema,
                                                    self.username,
                                                    self.password)
            self.rpc_clients.setdefault(spine['ip'], nc_client)

    def _get_client(self, device_ip):
        """ Return a RPC client instance specified by device IP. """
        client = None
        if self.rpc_clients is not None:
            client = self.rpc_clients.get(device_ip, None)
            if client is None:
                LOG.warn(_("No such switch whose IP is %s in "
                           "the configuration file."),
                         str(device_ip))
        return client

    def create_network_precommit(self, context):
        """ We don't care it."""
        pass

    def create_network_postcommit(self, context):
        """ Just insert network information into database.
            When the port is created, we do real operations
            in our physical device.
        """
        LOG.info(_("Create network postcommit begin."))
        network = context.current
        network_id = network['id']
        tenant_id = network['tenant_id']
        segments = context.network_segments
        if not db.is_network_created(tenant_id, network_id):
            LOG.info(_("Create network with id %s."), network_id)
            # [{'segmentation_id': id, 'physical_network': value,
            # 'id': id, 'network_type': gre | vlan | vxlan }]
            segment_type = segments[0]['network_type']
            segment_id = segments[0]['segmentation_id']
            db.create_network(tenant_id, network_id, segment_id, segment_type)
        LOG.info(_("Create network postcommit end."))

    def update_network_precommit(self, context):
        pass

    def update_network_postcommit(self, context):
        pass

    def delete_network_precommit(self, context):
        pass

    def delete_network_postcommit(self, context):
        """ Delete network information from database."""
        LOG.info(_("Delete network begin."))
        network = context.current
        network_id = network['id']
        tenant_id = network['tenant_id']
        if db.is_network_created(tenant_id, network_id):
            LOG.info(_("Delete network %s from database."), network_id)
            db.delete_network(tenant_id, network_id)
        LOG.info(_("Delete network end."))

    def collect_create_config(self, network_id, host_id, vlan_id):
        device_config_dict = {}
        vlan_list = db.get_vlanlist_byhost(host_id)
        if vlan_id not in vlan_list:
            vlan_list.append(vlan_id)

        host_list = db.get_host_list(network_id)
        # Find which leaf device connects to the host_id.
        leaf_need_configure = []
        leaf_generator = tools.topology_generator(self.leaf_topology)
        leaf_ip_ref = {}
        for leaf_ip, topology in leaf_generator:
            leaf_host = topology['host']
            if leaf_host in host_list:
                leaf_ip_ref.setdefault(leaf_ip, set([]))
                leaf_ip_ref[leaf_ip] |= set(db.get_vlanlist_byhost(leaf_host))
            if leaf_host == host_id:
                leaf_ip_ref[leaf_ip] |= set([vlan_id])
                device_config_dict.setdefault(leaf_ip, {})
                device_config_dict[leaf_ip].setdefault('port_vlan', [])
                device_config_dict[leaf_ip]['vlan_create'] = vlan_list
                device_config_dict[leaf_ip]['port_vlan'].\
                    append((topology['ports'], vlan_list))
                leaf_need_configure.append(leaf_ip)

        LOG.info(_("Starting collecting spine's configs with leaf %s."),
                 str(leaf_need_configure))
        # Find which spine device connects to the leaf device
        # which is configured above.
        spine_generator = tools.topology_generator(self.spine_topology)
        for spine_ip, topology in spine_generator:
            leaf_ip = topology['leaf_ip']
            if leaf_ip in leaf_need_configure:
                spine_vlan_list = list(leaf_ip_ref[leaf_ip])
                if spine_ip not in device_config_dict:
                    device_config_dict.setdefault(spine_ip, {})
                    device_config_dict[spine_ip].setdefault('port_vlan', [])
                    device_config_dict[spine_ip]['vlan_create'] = vlan_list
                    device_config_dict[spine_ip]['port_vlan'].\
                        append((topology['spine_ports'], spine_vlan_list))
                if leaf_ip in device_config_dict:
                    device_config_dict[leaf_ip]['port_vlan'].\
                        append((topology['leaf_ports'], spine_vlan_list))

        LOG.info(_("Collect device configuration: %s"), device_config_dict)

        return device_config_dict

    def create_port_precommit(self, context):
        pass

    def _create_vlan_network(self, network_id, host_id, vlan_id):
        """Do real configuration in our physical devices.
        :param network_id. The uuid of network.
        :param host_id. The host where the port created.
        :param vlan_id. Segmentation ID
        """
        device_config_list = self.collect_create_config(network_id,
                                                        host_id,
                                                        vlan_id)
        # Execute configuration in physical devices.
        for dev_ip in device_config_list:
            vlan_list = device_config_list[dev_ip]['vlan_create']
            port_vlan_tuple_list = device_config_list[dev_ip]['port_vlan']
            rpc_client = self._get_client(dev_ip)
            if rpc_client is not None:
                LOG.info(_("Begin create vlan network: device %s, "
                           "create vlan %s, port trunk list %s"),
                         dev_ip, vlan_list, port_vlan_tuple_list)
                result = rpc_client.create_vlan_bulk(vlan_list)
                if result is True:
                    result = rpc_client.port_trunk_bulk(port_vlan_tuple_list)
                    if result is True:
                        LOG.info(_("Create vlan config successful for"
                                   " %s."), dev_ip)
                    LOG.info(_("End create vlan network"))
                else:
                    LOG.warn(_("Failed to create vlan network"))

    def create_port_postcommit(self, context):
        """Create network and port on physical device."""
        LOG.info(_("Create port begin."))

        # Here we only process virtual machine and DHCP server's port.
        port = context.current
        device_owner = port['device_owner']
        if not device_owner.startswith('compute') and \
                device_owner != n_const.DEVICE_OWNER_DHCP:
            LOG.info(_("Ignore port owner %s when creating port."),
                     device_owner)
            return

        device_id = port['device_id']
        host_id = context.host
        port_id = port['id']
        tenant_id = port['tenant_id']
        network_id = port['network_id']

        with self.sync_lock:
            if db.is_vm_created(device_id, host_id,
                                port_id, network_id, tenant_id):
                LOG.info(_("The port %s of virtual machine %s has "
                           "already inserted into the network %s."),
                         str(port_id), str(device_id), str(network_id))
                return

            LOG.info(_("Insert port %s's information into database."),
                     str(port_id))

            db.create_vm(device_id, host_id, port_id, network_id, tenant_id)
            # Get the count of port that created in the same network and host.
            port_count = db.get_vm_count(network_id, host_id)
            if port_count == 1:
                segments = context.network.network_segments
                segment_type = segments[0]['network_type']
                if segment_type == 'vlan':
                    vlan_id = int(segments[0]['segmentation_id'])
                    self._create_vlan_network(network_id, host_id, vlan_id)
                else:
                    LOG.info(_("Not supported network type %s"), segment_type)
            else:
                LOG.info(_("Physical switch has already configured. "
                           "There are %d VMs in network %s."),
                         port_count, network_id)
        LOG.info(_("Create port end."))

    def update_port_precommit(self, context):
        pass

    def update_port_postcommit(self, context):
        """Just process the migration of virtual machine."""
        port = context.current
        device_owner = port['device_owner']
        LOG.info(_("Update port begin. Device owner is %s."), device_owner)
        if not (device_owner.startswith('compute') or
                device_owner == n_const.DEVICE_OWNER_DHCP):
            LOG.info(_("Ignore port owner %s when update port."),
                     device_owner)
            return

        device_id = port['device_id']
        port_id = port['id']
        tenant_id = port['tenant_id']
        network_id = port['network_id']
        old_host_id = db.get_vm_host(device_id, port_id,
                                     network_id, tenant_id)
        if old_host_id is None or old_host_id == context.host:
            LOG.info(_("update port postcommit: No changed."))
            return

        # Migration is happen.
        LOG.info(_("Migration is begin."))
        segments = context.network.network_segments
        self.delete_port(old_host_id, port, segments)
        self.create_port_postcommit(context)
        LOG.info(_("Migration is end."))

    def collect_delete_config(self, network_id, host_id, vlan_id):
        vlan_list = db.get_vlanlist_byhost(host_id)
        if vlan_id in vlan_list:
            vlan_list.remove(vlan_id)
        leaf_generator = tools.topology_generator(self.leaf_topology)
        host_list = db.get_host_list(network_id)
        LOG.info(_("Delete vlan host list %s"), host_list)
        # It is the counter of host that connects to the same
        # device specified by ip address.
        leaf_ref_vlans = {}
        leaf_ref_host = {}
        delete_config = {}
        for leaf_ip, topology in leaf_generator:
            leaf_ref_vlans.setdefault(leaf_ip, set([]))
            leaf_ref_host.setdefault(leaf_ip, False)
            host = topology['host']
            host_vlan = db.get_vlanlist_byhost(host)
            if host in host_list:
                leaf_ref_vlans[leaf_ip] |= set(host_vlan)
            if host == host_id:
                delete_config.setdefault(leaf_ip, {})
                delete_config[leaf_ip].setdefault('port_vlan', [])
                delete_config[leaf_ip]['port_vlan'].\
                    append((topology['ports'], vlan_list))
                delete_config[leaf_ip]['vlan_del'] = []
                if host in host_list:
                    host_list.remove(host)
            else:
                if len(set([vlan_id]) & set(host_vlan)) > 0:
                    leaf_ref_host[leaf_ip] = True

        # If there is no host connects to leaf in the same network,
        # we will remove the configuration in the spine device.
        # And remove the vlan configuration in the leaf device.
        for leaf_ip in leaf_ref_vlans:
            if leaf_ref_host[leaf_ip] is False and leaf_ip in delete_config:
                leaf_ref_vlans[leaf_ip] -= set([vlan_id])
                delete_config[leaf_ip]['vlan_del'] = [vlan_id]

        # Check which spine device connects to above leafs.
        # We need remove this spine's configuration.
        spine_generator = tools.topology_generator(self.spine_topology)
        # This dict is used to count the host number in same network
        # with leafs connected to spine.
        spine_delete_score = {}
        for spine_ip, topology in spine_generator:
            leaf_ip = topology['leaf_ip']
            if leaf_ip in leaf_ref_vlans:
                spine_delete_score.setdefault(spine_ip, 0)
                if leaf_ref_host[leaf_ip] is True:
                    spine_delete_score[spine_ip] += 1
            if leaf_ip in delete_config:
                vlan_list = list(leaf_ref_vlans[leaf_ip])
                delete_config[spine_ip] = {}
                delete_config[spine_ip].setdefault('port_vlan', [])
                delete_config[spine_ip]['port_vlan'].\
                    append((topology['spine_ports'], vlan_list))
                delete_config[spine_ip]['vlan_del'] = []
                if len(delete_config[leaf_ip]['vlan_del']) != 0:
                    delete_config[leaf_ip]['port_vlan'].\
                        append((topology['leaf_ports'], vlan_list))
        # Check does spine need to delete vlan.
        for spine_ip in spine_delete_score:
            if spine_delete_score[spine_ip] == 0 \
                    and spine_ip in delete_config:
                delete_config[spine_ip]['vlan_del'] = [vlan_id]
        LOG.info(_("Delete configuration : %s"), delete_config)
        return delete_config

    def delete_vlan_config(self, network_id, host_id, vlan_id):
        """Delete vlan configuration from physical devices."""
        delete_config = self.collect_delete_config(network_id,
                                                   host_id,
                                                   vlan_id)
        for dev_ip in delete_config:
            rpc_client = self._get_client(dev_ip)
            port_vlan_tuple_list = delete_config[dev_ip]['port_vlan']
            vlan_del_list = delete_config[dev_ip]['vlan_del']
            if rpc_client is not None:
                if rpc_client.port_trunk_bulk(port_vlan_tuple_list) is True:
                    if rpc_client.delete_vlan_bulk(vlan_del_list) is True:
                        LOG.info(_("Delete vlan config %s success for %s."),
                                 port_vlan_tuple_list, dev_ip)
                    else:
                        LOG.warn(_("Failed to delete vlan %s for %s."),
                                 vlan_del_list, dev_ip)
                else:
                    LOG.warn(_("Failed to port trunk %s for %s"),
                             port_vlan_tuple_list, dev_ip)

    def delete_port_precommit(self, context):
        pass

    def delete_port(self, host_id, ports, segments):
        with self.sync_lock:
            network_id = ports['network_id']
            device_id = ports['device_id']
            port_id = ports['id']
            tenant_id = ports['tenant_id']
            if not db.is_vm_created(device_id, host_id,
                                    port_id, network_id, tenant_id):
                LOG.info(_("No such vm in database, ignore it"))
                return

            # Delete configuration in device
            # only if it is the last vm of host in this network
            vm_count = db.get_vm_count(network_id, host_id)
            if vm_count == 1:
                LOG.info(_("Delete physical port configuration: "
                           "All VMs of host %s in network %s is deleted. "),
                         host_id, network_id)
                segment_type = segments[0]['network_type']
                segment_id = segments[0]['segmentation_id']
                if segment_type == 'vlan':
                    vlan_id = int(segment_id)
                    self.delete_vlan_config(network_id, host_id, vlan_id)
                else:
                    LOG.info(_("Not supported network type %s."),
                             str(segment_type))
            else:
                LOG.info(_("The network %s still have %d vms, "
                           "ignore this operation."),
                         network_id, vm_count)
            db.delete_vm(device_id, host_id, port_id, network_id, tenant_id)

    def delete_port_postcommit(self, context):
        """Delete real configuration from our physical devices."""
        LOG.info(_("Delete port post-commit begin."))

        # Only process virtual machine device and DHCP port
        port = context.current
        device_owner = port['device_owner']
        if not device_owner.startswith('compute') and\
                device_owner != n_const.DEVICE_OWNER_DHCP:
            LOG.info(_("Ignore port owner %s when deleting port."),
                     device_owner)
            return

        segments = context.network.network_segments
        self.delete_port(context.host, port, segments)

        LOG.info(_("Delete port post-commit end."))
