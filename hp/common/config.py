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


""" HP ML2 Mechanism driver specific configuration knobs.
    Following are user configurable options for HP ML2 Mechanism driver.
"""
HP_DRIVER_OPTS = [
    cfg.StrOpt('sync_time',
               default=300,
               help=_('Set the interval for synchronizing port and network '
                      'configuration from the network server to physical '
                      'devices, in seconds.')),
    cfg.BoolOpt('sync_overlap',
                default=False,
                help=_('Does synchronized configuration forcibly overwrite '
                       'the physical devices configurations?')),
    cfg.StrOpt('oem',
               default='hp',
               help=_('Specify the OEM for all physical devices.'
                      'Supported OEMs are HP and H3C.')),
    cfg.StrOpt('schema',
               default='https',
               help=_('Specify the encapsulation protocol for NETCONF,'
                      ' which can be HTTPS and HTTP.')),
    cfg.StrOpt('username',
               default='',
               help=_('Specify the username and password used for '
                      'establishing NETCONF and RESTful connections '
                      'with physical devices. ')),
    cfg.StrOpt('password',
               default='',
               help=_('Specify the username and password used for '
                      'establishing NETCONF and RESTful connections '
                      'with physical devices. ')),
    cfg.StrOpt('rpc_backend',
               default='netconf',
               help=_('Specify a method for assigning configuration.'
                      ' Supported backends are NETCONF and RESTful.'))
]

cfg.CONF.register_opts(HP_DRIVER_OPTS, "ml2_hp")


class HPML2Config(object):
    """ML2 Mechanism Driver HP Configuration class.
    leaf_topology:
        [
          {
            'ip': 'x.x.x.x',
            'oem': 'hp',
            'connections' :
                [
                   {
                      'host' : 'ubuntu-136',
                      'ports' : ['g1/0/1', 'g1/0/2']
                   },
                   {
                      'host' : 'ubuntu-134',
                      'ports': ['g1/0/3']
                   }
                ]
          },
          ...
        ]
    spine_topology:
        [
          {
             'ip': 'x.x.x.x',
             'oem': 'hp',
             'connections' :
                [
                   {
                      'leaf_ip' : 1.1.1.1,
                       'leaf_ports': ['G1/0/1'],
                       'spine_ports':['G1/0/1'],
                   },
                   {
                      'leaf_ip' : 1.1.1.2,
                       'leaf_ports': ['G1/0/2'],
                       'spine_ports':['G1/0/2'],
                   }
                ]
          },
          ...
        ]
    """
    leaf_topology = []
    spine_topology = []

    def __init__(self):
        self._create_hp_config()

    def _create_leaf_config(self, leaf_ip, items):
        leaf_in_use = None
        for leaf in self.leaf_topology:
            if leaf['ip'] == leaf_ip:
                leaf_in_use = leaf
                break
        if leaf_in_use is None:
            new_leaf = {}
            new_leaf.setdefault('ip', leaf_ip)
            new_leaf.setdefault('connections', [])
            new_leaf.setdefault('oem', '')
            self.leaf_topology.append(new_leaf)
        else:
            new_leaf = leaf_in_use
        for key, value in items:
            if key.lower() == 'oem':
                new_leaf['oem'] = value[0].lower()
                continue
            new_host = {}
            new_host.setdefault('host', key)
            port_list = []
            if value[0] != "":
                port_list = [v.strip()
                             for v in value[0].split(",")]
            new_host.setdefault('ports', port_list)
            new_leaf['connections'].append(new_host)

    def _create_spine_config(self, ip_pair, items):
        spine_ip, sep, leaf_ip = ip_pair.partition(':')
        spine_in_use = None
        for spine in self.spine_topology:
            if spine['ip'] == spine_ip:
                spine_in_use = spine
                break
        if spine_in_use is None:
            new_spine = {}
            new_spine.setdefault('ip', spine_ip)
            new_spine.setdefault('connections', [])
            new_spine.setdefault('oem', '')
            self.spine_topology.append(new_spine)
        else:
            new_spine = spine_in_use
        new_leaf = {}
        new_leaf.setdefault('leaf_ip', leaf_ip)
        new_leaf.setdefault('spine_ports', [])
        new_leaf.setdefault('leaf_ports', [])
        spine_oem = ''
        for key, value in items:
            if key.lower() != 'oem':
                new_leaf['spine_ports'].append(key.strip().replace('#', ':'))
                new_leaf['leaf_ports'].append(value[0].strip())
            else:
                spine_oem = value[0].lower()
        new_spine['oem'] = spine_oem
        new_spine['connections'].append(new_leaf)

    def _create_hp_config(self):
        multi_parser = cfg.MultiConfigParser()
        read_ok = multi_parser.read(cfg.CONF.config_file)

        if len(read_ok) != len(cfg.CONF.config_file):
            raise cfg.Error(_("Some config files were not parsed properly."))

        for parsed_file in multi_parser.parsed:
            for parsed_item in parsed_file.keys():
                config_id, sep, ip = parsed_item.partition(':')
                config_key = config_id.lower()
                key_items = parsed_file[parsed_item].items()
                if config_key == 'ml2_hp_leaf':
                    self._create_leaf_config(ip, key_items)
                elif config_key == 'ml2_hp_spine':
                    self._create_spine_config(ip, key_items)
