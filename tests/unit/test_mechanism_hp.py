# -*- coding: utf-8 -*-
#
#  H3C Technologies Co., Limited Copyright 2003-2015, All rights reserved.
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

import sys
import mock
from neutron.tests.unit import testlib_api
from neutron.extensions import portbindings

with mock.patch.dict(sys.modules,
                     {'hp': mock.Mock(),
                      'hp.common': mock.Mock()}):
    from neutron.plugins.ml2.drivers.hp import mechanism_hp


class HPDriverTestCase(testlib_api.SqlTestCase):
    """Main test cases for HP Mechanism driver.

    Tests all mechanism driver APIs supported by HP Driver.
    """
    def setUp(self):
        super(HPDriverTestCase, self).setUp()
        self.mock = mock.MagicMock()
        mechanism_hp.db = self.mock
        self.driver = mechanism_hp.HPDriver(self.mock)
        self.driver.initialize()

    def tearDown(self):
        super(HPDriverTestCase, self).tearDown()

    def _get_network_context(self, tenant_id, net_id, seg_id, shared):
        network = {'id': net_id,
                   'tenant_id': tenant_id,
                   'name': 'test-net',
                   'shared': shared}
        network_segments = [{
                             'segmentation_id': seg_id,
                             'network_type': 'vlan'
                             }]
        return FakeNetworkContext(network, network_segments, network)

    def _get_port_context(self, tenant_id, net_id, vm_id, network):
        port = {'device_id': vm_id,
                'device_owner': 'compute',
                'binding:host_id': 'ubuntu1',
                'name': 'test-port',
                'tenant_id': tenant_id,
                'id': 101,
                'network_id': net_id
                }
        return FakePortContext(port, port, network)

    def test_create_network_postcommit(self):
        tenant_id = 'tennet1'
        network_id = 'network1'
        segmentation_id = 101

        network_context = self._get_network_context(tenant_id,
                                                    network_id,
                                                    segmentation_id,
                                                    False)
        mechanism_hp.db.is_network_created.return_value = False

        self.driver.create_network_postcommit(network_context)

        segments = network_context.network_segments
        segment_type = segments[0]['network_type']
        segment_id = segments[0]['segmentation_id']

        expected_calls = [
            mock.call.is_network_created(tenant_id, network_id),
            mock.call.create_network(tenant_id, network_id,
                                     segment_id, segment_type),
        ]

        mechanism_hp.db.assert_has_calls(expected_calls)

    def test_delete_network_postcommit(self):
        tenant_id = 'tennet1'
        network_id = 'network1'
        segmentation_id = 101

        network_context = self._get_network_context(tenant_id,
                                                    network_id,
                                                    segmentation_id,
                                                    False)
        mechanism_hp.db.is_network_created.return_value = True

        self.driver.delete_network_postcommit(network_context)
        expected_calls = [
            mock.call.delete_network(tenant_id, network_id),
        ]

        mechanism_hp.db.assert_has_calls(expected_calls)

    def test_create_port_postcommit(self):
        tenant_id = 'tennet1'
        network_id = 'network1'
        segmentation_id = 101
        vm_id = 'vm1'

        network_context = self._get_network_context(tenant_id,
                                                    network_id,
                                                    segmentation_id,
                                                    False)
        port_context = self._get_port_context(tenant_id,
                                              network_id,
                                              vm_id,
                                              network_context)
        mechanism_hp.db.is_vm_created.return_value = False
        mechanism_hp.db.get_vm_count.return_value = 1

        port = port_context.current
        device_id = port['device_id']
        host_id = port['binding:host_id']
        port_id = port['id']

        self.driver.create_port_postcommit(port_context)

        expected_calls = [
            mock.call.is_vm_created(device_id, host_id,
                                    port_id, network_id, tenant_id),
            mock.call.create_vm(device_id, host_id, port_id,
                                network_id, tenant_id),
            mock.call.get_vm_count(network_id, host_id),
        ]

        mechanism_hp.db.assert_has_calls(expected_calls)

    def test_delete_port_postcommit(self):
        tenant_id = 'tennet1'
        network_id = 'network1'
        segmentation_id = 101
        vm_id = 'vm1'

        network_context = self._get_network_context(tenant_id,
                                                    network_id,
                                                    segmentation_id,
                                                    False)

        port_context = self._get_port_context(tenant_id,
                                              network_id,
                                              vm_id,
                                              network_context)
        mechanism_hp.db.is_vm_created.return_value = True
        mechanism_hp.db.get_vm_count.return_value = 1

        self.driver.delete_port_postcommit(port_context)

        host_id = port_context.current['binding:host_id']
        port_id = port_context.current['id']
        device_id = port_context.current['device_id']
        expected_calls = [
            mock.call.is_vm_created(device_id, host_id,
                                    port_id, network_id, tenant_id),
            mock.call.get_vm_count(network_id, host_id),
        ]

        mechanism_hp.db.assert_has_calls(expected_calls)


class FakeNetworkContext(object):
    """To generate network context for testing purposes only."""

    def __init__(self, network, segments=None, original_network=None):
        self._network = network
        self._original_network = original_network
        self._segments = segments

    @property
    def current(self):
        return self._network

    @property
    def original(self):
        return self._original_network

    @property
    def network_segments(self):
        return self._segments


class FakePortContext(object):
    """To generate port context for testing purposes only."""

    def __init__(self, port, original_port, network):
        self._port = port
        self._original_port = original_port
        self._network_context = network

    @property
    def current(self):
        return self._port

    @property
    def original(self):
        return self._original_port

    @property
    def network(self):
        return self._network_context

    @property
    def host(self):
        return self._port.get(portbindings.HOST_ID)

    @property
    def original_host(self):
        return self._original_port.get(portbindings.HOST_ID)
