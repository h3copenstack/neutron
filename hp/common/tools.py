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

import copy
from oslo_log import log as logging


LOG = logging.getLogger(__name__)


def get_vlan_commastr(vlan_list):
    vlans = ""
    if vlan_list is not None:
        vlan_list_len = len(vlan_list)
        index = 0
        for vlan in vlan_list:
            vlans += str(vlan)
            index += 1
            if index != vlan_list_len:
                vlans += ","
        vlans.rstrip(',')
    return vlans


def topology_generator(dev_topology):
    """ Generate one topology every time.
    :param spine or leaf topology. Format as following:
    """
    for dev in dev_topology:
        for topology in dev['connections']:
            new_topology = copy.deepcopy(topology)
            LOG.info(_("Topology owner ip is %s, content is %s."),
                     dev['ip'], new_topology)
            yield dev['ip'], new_topology
