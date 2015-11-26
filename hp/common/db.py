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

import sqlalchemy as sa

from neutron import context as nctx
import neutron.db.api as db
from neutron.db import db_base_plugin_v2
from neutron.db import model_base
from neutron.db import models_v2
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

VLAN_SEGMENTATION = 'vlan'

UUID_LEN = 36
STR_LEN = 255
SEGTYPE_LEN = 12


class HPRelatedNetworks(model_base.BASEV2,
                        models_v2.HasId,
                        models_v2.HasTenant):
    """ Representation for table comware_related_nets
        A network id corresponding a segmentation ID.
    """
    __tablename__ = 'hp_related_nets'

    network_id = sa.Column(sa.String(UUID_LEN))
    segmentation_id = sa.Column(sa.Integer)
    segmentation_type = sa.Column(sa.String(SEGTYPE_LEN))

    def hp_network_representation(self, segmentation_type):
        return {u'network_id': self.network_id,
                u'segmentation_id': self.segmentation_id,
                u'segmentation_type': segmentation_type}


class HPRelatedVms(model_base.BASEV2, models_v2.HasId, models_v2.HasTenant):
    """ Representation for table comware_related_vms
        This table stores all the VM informations.
    """
    __tablename__ = 'hp_related_vms'

    device_id = sa.Column(sa.String(STR_LEN))
    host_id = sa.Column(sa.String(STR_LEN))
    port_id = sa.Column(sa.String(UUID_LEN))
    network_id = sa.Column(sa.String(UUID_LEN))

    def hp_vm_representation(self):
        return {u'device_id': self.device_id,
                u'host': self.host_id,
                u'ports': {self.port_id: [{u'port_id': self.port_id,
                                          u'network_id': self.network_id}]}}

    def hp_port_representation(self):
        return {u'device_id': self.device_id,
                u'host': self.host_id,
                u'port_id': self.port_id,
                u'network_id': self.network_id}


def get_network_count():
    session = db.get_session()
    with session.begin():
        q = session.query(HPRelatedNetworks)
        nets_cnt = int(q.count())
        return nets_cnt


def create_network(tenant_id, network_id, segmentation_id, segment_type):
    """ Store a network relationship in db. """
    session = db.get_session()
    with session.begin():
        network = HPRelatedNetworks(tenant_id=tenant_id,
                                    network_id=network_id,
                                    segmentation_id=segmentation_id,
                                    segmentation_type=segment_type)
        session.add(network)


def delete_network(tenant_id, network_id):
    """ Remove a network relationship from comware db. """
    session = db.get_session()
    with session.begin():
        (session.query(HPRelatedNetworks).
         filter_by(network_id=network_id).delete())


def create_vm(device_id, host_id, port_id, network_id, tenant_id):
    """ Relate a vm with comware. """
    session = db.get_session()
    with session.begin():
        vm = HPRelatedVms(device_id=device_id,
                          host_id=host_id,
                          port_id=port_id,
                          network_id=network_id,
                          tenant_id=tenant_id)
        session.add(vm)


def delete_vm(device_id, host_id, port_id, network_id, tenant_id):
    """Removes all relevant information about a VM from repository.
    """
    LOG.info(_("break vm begin"))
    session = db.get_session()
    with session.begin():
        (session.query(HPRelatedVms).
         filter_by(device_id=device_id, host_id=host_id,
                   port_id=port_id, tenant_id=tenant_id,
                   network_id=network_id).delete())
        LOG.info(_("Break vm end"))


def get_segmentation_id(tenant_id, network_id):
    session = db.get_session()
    with session.begin():
        net = (session.query(HPRelatedNetworks).
               filter_by(tenant_id=tenant_id,
                         network_id=network_id).first())
        return net and net.segmentation_id or None


def is_vm_created(device_id, host_id, port_id,
                  network_id, tenant_id):
    """Checks if a VM is already known to comware. """
    session = db.get_session()
    num_vm = 0
    with session.begin():
        num_vm = (session.query(HPRelatedVms).
                  filter_by(tenant_id=tenant_id,
                            device_id=device_id,
                            port_id=port_id,
                            network_id=network_id,
                            host_id=host_id).count())
    return num_vm > 0


def get_distinct_vms():
    session = db.get_session()
    with session.begin():
        vms = (session.query(HPRelatedVms.host_id,
                             HPRelatedVms.network_id).distinct())
        return vms
    return None


def get_segment_id_by_net_id(net_id, net_type):
    session = db.get_session()
    with session.begin():
        net = session.query(HPRelatedNetworks).\
            filter_by(network_id=net_id, segmentation_type=net_type).first()
        if net is not None:
            return net.segmentation_id
        else:
            return None


def is_network_created(tenant_id, network_id, seg_id=None):
    """Checks if a networks is already known to COMWARE."""
    session = db.get_session()
    with session.begin():
        if not seg_id:
            num_nets = (session.query(HPRelatedNetworks).
                        filter_by(tenant_id=tenant_id,
                                  network_id=network_id).count())
        else:
            num_nets = (session.query(HPRelatedNetworks).
                        filter_by(tenant_id=tenant_id,
                                  network_id=network_id,
                                  segmentation_id=seg_id).count())
        LOG.info(_("num_nets %s"), str(num_nets))
        return num_nets > 0


def created_nets_count(tenant_id):
    """Returns number of networks for a given tenant. """
    session = db.get_session()
    with session.begin():
        return (session.query(HPRelatedNetworks).
                filter_by(tenant_id=tenant_id).count())


def get_vm_count(network_id, host_id):
    """ Return the number vm in the same network. """
    session = db.get_session()
    with session.begin():
        return (session.query(HPRelatedVms).
                filter_by(network_id=network_id, host_id=host_id).count())


def get_networks():
    session = db.get_session()
    with session.begin():
        model = HPRelatedNetworks
        all_nets = session.query(model)
        res = dict(
            (net.network_id, net.hp_network_representation(
                VLAN_SEGMENTATION))
            for net in all_nets
        )
        return res


def get_vms(tenant_id):
    session = db.get_session()
    with session.begin():
        model = HPRelatedVms
        none = None
        all_vms = (session.query(model).
                   filter(model.tenant_id == tenant_id,
                          model.host_id != none,
                          model.device_id != none,
                          model.network_id != none,
                          model.port_id != none))
        res = dict(
            (vm.device_id, vm.hp_vm_representation())
            for vm in all_vms
        )
        return res


def get_vm_host(device_id, port_id,
                network_id, tenant_id):
    session = db.get_session()
    with session.begin():
        qry = (session.query(HPRelatedVms).
               filter_by(tenant_id=tenant_id,
                         device_id=device_id,
                         port_id=port_id,
                         network_id=network_id))
        for one in qry:
            return one['host_id']

    return None


def get_host_list(network_id):
    host_list = []
    session = db.get_session()
    with session.begin():
        qry = (session.query(HPRelatedVms).
               filter_by(network_id=network_id))
        for one in qry:
            host_list.append(one['host_id'])
    return host_list


def get_ports(tenant_id):
    session = db.get_session()
    with session.begin():
        model = HPRelatedVms
        none = None
        all_ports = (session.query(model).
                     filter(model.tenant_id == tenant_id,
                            model.host_id != none,
                            model.device_id != none,
                            model.network_id != none,
                            model.port_id != none))
        res = dict(
            (port.port_id, port.hp_port_representation())
            for port in all_ports
        )
        return res


def get_host_vlan():
    vms = get_distinct_vms()
    host_vlan = {}
    for vm in vms:
        seg_id = get_segment_id_by_net_id(vm.network_id, 'vlan')
        if seg_id is None:
            continue
        host_id = vm.host_id
        LOG.info(_("host %s seg_id %s"), host_id, str(seg_id))
        if host_id in host_vlan:
            if seg_id not in host_vlan[host_id]:
                host_vlan[host_id].append(seg_id)
        else:
            host_vlan[host_id] = [seg_id]
        LOG.info(_("Host vlan: %s"), str(host_vlan))

    return host_vlan


def get_vlanlist_byhost(host_id):
    host_vlan = get_host_vlan()
    vlanlist = host_vlan.get(host_id, None)
    return vlanlist or []
