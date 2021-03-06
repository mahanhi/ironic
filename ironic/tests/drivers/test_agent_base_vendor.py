# -*- coding: utf-8 -*-
#
# Copyright 2015 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import time
import types

import mock

from ironic.common import boot_devices
from ironic.common import exception
from ironic.common import states
from ironic.conductor import manager
from ironic.conductor import task_manager
from ironic.conductor import utils as manager_utils
from ironic.drivers.modules import agent_base_vendor
from ironic.drivers.modules import agent_client
from ironic.drivers.modules import deploy_utils
from ironic.drivers.modules import fake
from ironic import objects
from ironic.tests.conductor import utils as mgr_utils
from ironic.tests.db import base as db_base
from ironic.tests.db import utils as db_utils
from ironic.tests.objects import utils as object_utils

INSTANCE_INFO = db_utils.get_test_agent_instance_info()
DRIVER_INFO = db_utils.get_test_agent_driver_info()
DRIVER_INTERNAL_INFO = db_utils.get_test_agent_driver_internal_info()


class TestBaseAgentVendor(db_base.DbTestCase):

    def setUp(self):
        super(TestBaseAgentVendor, self).setUp()
        mgr_utils.mock_the_extension_manager(driver="fake_agent")
        self.passthru = agent_base_vendor.BaseAgentVendor()
        n = {
            'driver': 'fake_agent',
            'instance_info': INSTANCE_INFO,
            'driver_info': DRIVER_INFO,
            'driver_internal_info': DRIVER_INTERNAL_INFO,
        }
        self.node = object_utils.create_test_node(self.context, **n)

    def test_validate(self):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            method = 'heartbeat'
            self.passthru.validate(task, method)

    def test_driver_validate(self):
        kwargs = {'version': '2'}
        method = 'lookup'
        self.passthru.driver_validate(method, **kwargs)

    def test_driver_validate_invalid_paremeter(self):
        method = 'lookup'
        kwargs = {'version': '1'}
        self.assertRaises(exception.InvalidParameterValue,
                          self.passthru.driver_validate,
                          method, **kwargs)

    def test_driver_validate_missing_parameter(self):
        method = 'lookup'
        kwargs = {}
        self.assertRaises(exception.MissingParameterValue,
                          self.passthru.driver_validate,
                          method, **kwargs)

    def test_lookup_version_not_found(self):
        kwargs = {
            'version': '999',
        }
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              self.passthru.lookup,
                              task.context,
                              **kwargs)

    @mock.patch('ironic.drivers.modules.agent_base_vendor.BaseAgentVendor'
                '._find_node_by_macs', autospec=True)
    def test_lookup_v2(self, find_mock):
        kwargs = {
            'version': '2',
            'inventory': {
                'interfaces': [
                    {
                        'mac_address': 'aa:bb:cc:dd:ee:ff',
                        'name': 'eth0'
                    },
                    {
                        'mac_address': 'ff:ee:dd:cc:bb:aa',
                        'name': 'eth1'
                    }

                ]
            }
        }
        find_mock.return_value = self.node
        with task_manager.acquire(self.context, self.node.uuid) as task:
            node = self.passthru.lookup(task.context, **kwargs)
        self.assertEqual(self.node.as_dict(), node['node'])

    def test_lookup_v2_missing_inventory(self):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              self.passthru.lookup,
                              task.context)

    def test_lookup_v2_empty_inventory(self):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.InvalidParameterValue,
                              self.passthru.lookup,
                              task.context,
                              inventory={})

    def test_lookup_v2_empty_interfaces(self):
        with task_manager.acquire(self.context, self.node.uuid) as task:
            self.assertRaises(exception.NodeNotFound,
                              self.passthru.lookup,
                              task.context,
                              version='2',
                              inventory={'interfaces': []})

    @mock.patch.object(objects.Node, 'get_by_uuid')
    def test_lookup_v2_with_node_uuid(self, mock_get_node):
        kwargs = {
            'version': '2',
            'node_uuid': 'fake uuid',
            'inventory': {
                'interfaces': [
                    {
                        'mac_address': 'aa:bb:cc:dd:ee:ff',
                        'name': 'eth0'
                    },
                    {
                        'mac_address': 'ff:ee:dd:cc:bb:aa',
                        'name': 'eth1'
                    }

                ]
            }
        }
        mock_get_node.return_value = self.node
        with task_manager.acquire(self.context, self.node.uuid) as task:
            node = self.passthru.lookup(task.context, **kwargs)
        self.assertEqual(self.node.as_dict(), node['node'])
        mock_get_node.assert_called_once_with(mock.ANY, 'fake uuid')

    @mock.patch.object(objects.port.Port, 'get_by_address',
                       spec_set=types.FunctionType)
    def test_find_ports_by_macs(self, mock_get_port):
        fake_port = object_utils.get_test_port(self.context)
        mock_get_port.return_value = fake_port

        macs = ['aa:bb:cc:dd:ee:ff']

        with task_manager.acquire(
                self.context, self.node['uuid'], shared=True) as task:
            ports = self.passthru._find_ports_by_macs(task, macs)
        self.assertEqual(1, len(ports))
        self.assertEqual(fake_port.uuid, ports[0].uuid)
        self.assertEqual(fake_port.node_id, ports[0].node_id)

    @mock.patch.object(objects.port.Port, 'get_by_address',
                       spec_set=types.FunctionType)
    def test_find_ports_by_macs_bad_params(self, mock_get_port):
        mock_get_port.side_effect = exception.PortNotFound(port="123")

        macs = ['aa:bb:cc:dd:ee:ff']
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=True) as task:
            empty_ids = self.passthru._find_ports_by_macs(task, macs)
        self.assertEqual([], empty_ids)

    @mock.patch('ironic.objects.node.Node.get_by_id',
                spec_set=types.FunctionType)
    @mock.patch('ironic.drivers.modules.agent_base_vendor.BaseAgentVendor'
                '._get_node_id', autospec=True)
    @mock.patch('ironic.drivers.modules.agent_base_vendor.BaseAgentVendor'
                '._find_ports_by_macs', autospec=True)
    def test_find_node_by_macs(self, ports_mock, node_id_mock, node_mock):
        ports_mock.return_value = object_utils.get_test_port(self.context)
        node_id_mock.return_value = '1'
        node_mock.return_value = self.node

        macs = ['aa:bb:cc:dd:ee:ff']
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=True) as task:
            node = self.passthru._find_node_by_macs(task, macs)
        self.assertEqual(node, node)

    @mock.patch('ironic.drivers.modules.agent_base_vendor.BaseAgentVendor'
                '._find_ports_by_macs', autospec=True)
    def test_find_node_by_macs_no_ports(self, ports_mock):
        ports_mock.return_value = []

        macs = ['aa:bb:cc:dd:ee:ff']
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=True) as task:
            self.assertRaises(exception.NodeNotFound,
                              self.passthru._find_node_by_macs,
                              task,
                              macs)

    @mock.patch('ironic.objects.node.Node.get_by_uuid',
                spec_set=types.FunctionType)
    @mock.patch('ironic.drivers.modules.agent_base_vendor.BaseAgentVendor'
                '._get_node_id', autospec=True)
    @mock.patch('ironic.drivers.modules.agent_base_vendor.BaseAgentVendor'
                '._find_ports_by_macs', autospec=True)
    def test_find_node_by_macs_nodenotfound(self, ports_mock, node_id_mock,
                                            node_mock):
        port = object_utils.get_test_port(self.context)
        ports_mock.return_value = [port]
        node_id_mock.return_value = self.node['uuid']
        node_mock.side_effect = [self.node,
                                 exception.NodeNotFound(node=self.node)]

        macs = ['aa:bb:cc:dd:ee:ff']
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=True) as task:
            self.assertRaises(exception.NodeNotFound,
                              self.passthru._find_node_by_macs,
                              task,
                              macs)

    def test_get_node_id(self):
        fake_port1 = object_utils.get_test_port(self.context,
                                                node_id=123,
                                                address="aa:bb:cc:dd:ee:fe")
        fake_port2 = object_utils.get_test_port(self.context,
                                                node_id=123,
                                                id=42,
                                                address="aa:bb:cc:dd:ee:fb",
                                                uuid='1be26c0b-03f2-4d2e-ae87-'
                                                     'c02d7f33c782')

        node_id = self.passthru._get_node_id([fake_port1, fake_port2])
        self.assertEqual(fake_port2.node_id, node_id)

    def test_get_node_id_exception(self):
        fake_port1 = object_utils.get_test_port(self.context,
                                                node_id=123,
                                                address="aa:bb:cc:dd:ee:fc")
        fake_port2 = object_utils.get_test_port(self.context,
                                                node_id=321,
                                                id=42,
                                                address="aa:bb:cc:dd:ee:fd",
                                                uuid='1be26c0b-03f2-4d2e-ae87-'
                                                     'c02d7f33c782')

        self.assertRaises(exception.NodeNotFound,
                          self.passthru._get_node_id,
                          [fake_port1, fake_port2])

    def test_get_interfaces(self):
        fake_inventory = {
            'interfaces': [
                {
                    'mac_address': 'aa:bb:cc:dd:ee:ff',
                    'name': 'eth0'
                }
            ]
        }
        interfaces = self.passthru._get_interfaces(fake_inventory)
        self.assertEqual(fake_inventory['interfaces'], interfaces)

    def test_get_interfaces_bad(self):
        self.assertRaises(exception.InvalidParameterValue,
                          self.passthru._get_interfaces,
                          inventory={})

    def test_heartbeat(self):
        kwargs = {
            'agent_url': 'http://127.0.0.1:9999/bar'
        }
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=True) as task:
            self.passthru.heartbeat(task, **kwargs)

    def test_heartbeat_bad(self):
        kwargs = {}
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=True) as task:
            self.assertRaises(exception.MissingParameterValue,
                              self.passthru.heartbeat, task, **kwargs)

    @mock.patch.object(agent_base_vendor.BaseAgentVendor, 'deploy_has_started',
                       autospec=True)
    @mock.patch.object(deploy_utils, 'set_failed_state', autospec=True)
    @mock.patch.object(agent_base_vendor.BaseAgentVendor, 'deploy_is_done',
                       autospec=True)
    @mock.patch.object(agent_base_vendor.LOG, 'exception', autospec=True)
    def test_heartbeat_deploy_done_fails(self, log_mock, done_mock,
                                         failed_mock, deploy_started_mock):
        deploy_started_mock.return_value = True
        kwargs = {
            'agent_url': 'http://127.0.0.1:9999/bar'
        }
        done_mock.side_effect = iter([Exception('LlamaException')])
        with task_manager.acquire(
                self.context, self.node['uuid'], shared=True) as task:
            task.node.provision_state = states.DEPLOYWAIT
            task.node.target_provision_state = states.ACTIVE
            self.passthru.heartbeat(task, **kwargs)
            failed_mock.assert_called_once_with(task, mock.ANY)
        log_mock.assert_called_once_with(
            'Asynchronous exception for node '
            '1be26c0b-03f2-4d2e-ae87-c02d7f33c123: Failed checking if deploy '
            'is done. exception: LlamaException')

    @mock.patch.object(objects.node.Node, 'touch_provisioning', autospec=True)
    @mock.patch.object(manager, 'set_node_cleaning_steps', autospec=True)
    @mock.patch.object(agent_base_vendor.BaseAgentVendor,
                       '_notify_conductor_resume_clean', autospec=True)
    def test_heartbeat_resume_clean(self, mock_notify, mock_set_steps,
                                    mock_touch):
        kwargs = {
            'agent_url': 'http://127.0.0.1:9999/bar'
        }
        self.node.clean_step = {}
        for state in (states.CLEANWAIT, states.CLEANING):
            self.node.provision_state = state
            self.node.save()
            with task_manager.acquire(
                    self.context, self.node.uuid, shared=True) as task:
                self.passthru.heartbeat(task, **kwargs)

            mock_touch.assert_called_once_with(mock.ANY)
            mock_notify.assert_called_once_with(mock.ANY, task)
            mock_set_steps.assert_called_once_with(task)
            # Reset mocks for the next interaction
            mock_touch.reset_mock()
            mock_notify.reset_mock()
            mock_set_steps.reset_mock()

    @mock.patch.object(objects.node.Node, 'touch_provisioning', autospec=True)
    @mock.patch.object(agent_base_vendor.BaseAgentVendor,
                       'continue_cleaning', autospec=True)
    def test_heartbeat_continue_cleaning(self, mock_continue, mock_touch):
        kwargs = {
            'agent_url': 'http://127.0.0.1:9999/bar'
        }
        self.node.clean_step = {
            'priority': 10,
            'interface': 'deploy',
            'step': 'foo',
            'reboot_requested': False
        }
        for state in (states.CLEANWAIT, states.CLEANING):
            self.node.provision_state = state
            self.node.save()
            with task_manager.acquire(
                    self.context, self.node.uuid, shared=True) as task:
                self.passthru.heartbeat(task, **kwargs)

            mock_touch.assert_called_once_with(mock.ANY)
            mock_continue.assert_called_once_with(mock.ANY, task, **kwargs)
            # Reset mocks for the next interaction
            mock_touch.reset_mock()
            mock_continue.reset_mock()

    @mock.patch('ironic.conductor.manager.cleaning_error_handler')
    @mock.patch.object(agent_base_vendor.BaseAgentVendor,
                       'continue_cleaning', autospec=True)
    def test_heartbeat_continue_cleaning_fails(self, mock_continue,
                                               mock_handler):
        kwargs = {
            'agent_url': 'http://127.0.0.1:9999/bar'
        }
        self.node.clean_step = {
            'priority': 10,
            'interface': 'deploy',
            'step': 'foo',
            'reboot_requested': False
        }

        mock_continue.side_effect = Exception()

        for state in (states.CLEANWAIT, states.CLEANING):
            self.node.provision_state = state
            self.node.save()
            with task_manager.acquire(
                    self.context, self.node.uuid, shared=True) as task:
                self.passthru.heartbeat(task, **kwargs)

            mock_continue.assert_called_once_with(mock.ANY, task, **kwargs)
            mock_handler.assert_called_once_with(task, mock.ANY)
            mock_handler.reset_mock()
            mock_continue.reset_mock()

    @mock.patch.object(agent_base_vendor.BaseAgentVendor, 'continue_deploy',
                       autospec=True)
    @mock.patch.object(agent_base_vendor.BaseAgentVendor, 'reboot_to_instance',
                       autospec=True)
    @mock.patch.object(agent_base_vendor.BaseAgentVendor,
                       '_notify_conductor_resume_clean', autospec=True)
    def test_heartbeat_noops_maintenance_mode(self, ncrc_mock, rti_mock,
                                              cd_mock):
        """Ensures that heartbeat() no-ops for a maintenance node."""
        kwargs = {
            'agent_url': 'http://127.0.0.1:9999/bar'
        }
        self.node.maintenance = True
        for state in (states.AVAILABLE, states.DEPLOYWAIT, states.DEPLOYING,
                      states.CLEANING):
            self.node.provision_state = state
            self.node.save()
            with task_manager.acquire(
                    self.context, self.node['uuid'], shared=True) as task:
                self.passthru.heartbeat(task, **kwargs)

        self.assertEqual(0, ncrc_mock.call_count)
        self.assertEqual(0, rti_mock.call_count)
        self.assertEqual(0, cd_mock.call_count)

    @mock.patch.object(objects.node.Node, 'touch_provisioning', autospec=True)
    @mock.patch.object(agent_base_vendor.BaseAgentVendor, 'deploy_has_started',
                       autospec=True)
    def test_heartbeat_touch_provisioning(self, mock_deploy_started,
                                          mock_touch):
        mock_deploy_started.return_value = True
        kwargs = {
            'agent_url': 'http://127.0.0.1:9999/bar'
        }

        self.node.provision_state = states.DEPLOYWAIT
        self.node.save()
        with task_manager.acquire(
                self.context, self.node.uuid, shared=True) as task:
            self.passthru.heartbeat(task, **kwargs)

        mock_touch.assert_called_once_with(mock.ANY)

    def test_vendor_passthru_vendor_routes(self):
        expected = ['heartbeat']
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            vendor_routes = task.driver.vendor.vendor_routes
            self.assertIsInstance(vendor_routes, dict)
            self.assertEqual(expected, list(vendor_routes))

    def test_vendor_passthru_driver_routes(self):
        expected = ['lookup']
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            driver_routes = task.driver.vendor.driver_routes
            self.assertIsInstance(driver_routes, dict)
            self.assertEqual(expected, list(driver_routes))

    @mock.patch.object(time, 'sleep', lambda seconds: None)
    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(fake.FakePower, 'get_power_state',
                       spec=types.FunctionType)
    @mock.patch.object(agent_client.AgentClient, 'power_off',
                       spec=types.FunctionType)
    def test_reboot_and_finish_deploy(self, power_off_mock,
                                      get_power_state_mock,
                                      node_power_action_mock):
        self.node.provision_state = states.DEPLOYING
        self.node.target_provision_state = states.ACTIVE
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            get_power_state_mock.side_effect = [states.POWER_ON,
                                                states.POWER_OFF]
            self.passthru.reboot_and_finish_deploy(task)
            power_off_mock.assert_called_once_with(task.node)
            self.assertEqual(2, get_power_state_mock.call_count)
            node_power_action_mock.assert_called_once_with(
                task, states.POWER_ON)
            self.assertEqual(states.ACTIVE, task.node.provision_state)
            self.assertEqual(states.NOSTATE, task.node.target_provision_state)

    @mock.patch.object(time, 'sleep', lambda seconds: None)
    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(fake.FakePower, 'get_power_state',
                       spec=types.FunctionType)
    @mock.patch.object(agent_client.AgentClient, 'power_off',
                       spec=types.FunctionType)
    def test_reboot_and_finish_deploy_soft_poweroff_doesnt_complete(
            self, power_off_mock, get_power_state_mock,
            node_power_action_mock):
        self.node.provision_state = states.DEPLOYING
        self.node.target_provision_state = states.ACTIVE
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            get_power_state_mock.return_value = states.POWER_ON
            self.passthru.reboot_and_finish_deploy(task)
            power_off_mock.assert_called_once_with(task.node)
            self.assertEqual(7, get_power_state_mock.call_count)
            node_power_action_mock.assert_called_once_with(
                task, states.REBOOT)
            self.assertEqual(states.ACTIVE, task.node.provision_state)
            self.assertEqual(states.NOSTATE, task.node.target_provision_state)

    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'power_off',
                       spec=types.FunctionType)
    def test_reboot_and_finish_deploy_soft_poweroff_fails(
            self, power_off_mock, node_power_action_mock):
        power_off_mock.side_effect = iter([RuntimeError("boom")])
        self.node.provision_state = states.DEPLOYING
        self.node.target_provision_state = states.ACTIVE
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            self.passthru.reboot_and_finish_deploy(task)
            power_off_mock.assert_called_once_with(task.node)
            node_power_action_mock.assert_called_once_with(
                task, states.REBOOT)
            self.assertEqual(states.ACTIVE, task.node.provision_state)
            self.assertEqual(states.NOSTATE, task.node.target_provision_state)

    @mock.patch.object(time, 'sleep', lambda seconds: None)
    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(fake.FakePower, 'get_power_state',
                       spec=types.FunctionType)
    @mock.patch.object(agent_client.AgentClient, 'power_off',
                       spec=types.FunctionType)
    def test_reboot_and_finish_deploy_get_power_state_fails(
            self, power_off_mock, get_power_state_mock,
            node_power_action_mock):
        self.node.provision_state = states.DEPLOYING
        self.node.target_provision_state = states.ACTIVE
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            get_power_state_mock.side_effect = iter([RuntimeError("boom")])
            self.passthru.reboot_and_finish_deploy(task)
            power_off_mock.assert_called_once_with(task.node)
            self.assertEqual(7, get_power_state_mock.call_count)
            node_power_action_mock.assert_called_once_with(
                task, states.REBOOT)
            self.assertEqual(states.ACTIVE, task.node.provision_state)
            self.assertEqual(states.NOSTATE, task.node.target_provision_state)

    @mock.patch.object(time, 'sleep', lambda seconds: None)
    @mock.patch.object(manager_utils, 'node_power_action', autospec=True)
    @mock.patch.object(fake.FakePower, 'get_power_state',
                       spec=types.FunctionType)
    @mock.patch.object(agent_client.AgentClient, 'power_off',
                       spec=types.FunctionType)
    def test_reboot_and_finish_deploy_power_action_fails(
            self, power_off_mock, get_power_state_mock,
            node_power_action_mock):
        self.node.provision_state = states.DEPLOYING
        self.node.target_provision_state = states.ACTIVE
        self.node.save()
        with task_manager.acquire(self.context, self.node.uuid,
                                  shared=True) as task:
            get_power_state_mock.return_value = states.POWER_ON
            node_power_action_mock.side_effect = iter([RuntimeError("boom")])
            self.assertRaises(exception.InstanceDeployFailure,
                              self.passthru.reboot_and_finish_deploy,
                              task)
            power_off_mock.assert_called_once_with(task.node)
            self.assertEqual(7, get_power_state_mock.call_count)
            node_power_action_mock.assert_has_calls([
                mock.call(task, states.REBOOT),
                mock.call(task, states.POWER_OFF)])
            self.assertEqual(states.DEPLOYFAIL, task.node.provision_state)
            self.assertEqual(states.ACTIVE, task.node.target_provision_state)

    @mock.patch.object(agent_client.AgentClient, 'install_bootloader',
                       autospec=True)
    @mock.patch.object(deploy_utils, 'try_set_boot_device', autospec=True)
    def test_configure_local_boot(self, try_set_boot_device_mock,
                                  install_bootloader_mock):
        install_bootloader_mock.return_value = {
            'command_status': 'SUCCESS', 'command_error': None}
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            task.node.driver_internal_info['is_whole_disk_image'] = False
            self.passthru.configure_local_boot(task,
                                               root_uuid='some-root-uuid')
            try_set_boot_device_mock.assert_called_once_with(
                task, boot_devices.DISK)
            install_bootloader_mock.assert_called_once_with(
                mock.ANY, task.node, root_uuid='some-root-uuid',
                efi_system_part_uuid=None)

    @mock.patch.object(agent_client.AgentClient, 'install_bootloader',
                       autospec=True)
    @mock.patch.object(deploy_utils, 'try_set_boot_device', autospec=True)
    def test_configure_local_boot_uefi(self, try_set_boot_device_mock,
                                       install_bootloader_mock):
        install_bootloader_mock.return_value = {
            'command_status': 'SUCCESS', 'command_error': None}
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            task.node.driver_internal_info['is_whole_disk_image'] = False
            self.passthru.configure_local_boot(
                task, root_uuid='some-root-uuid',
                efi_system_part_uuid='efi-system-part-uuid')
            try_set_boot_device_mock.assert_called_once_with(
                task, boot_devices.DISK)
            install_bootloader_mock.assert_called_once_with(
                mock.ANY, task.node, root_uuid='some-root-uuid',
                efi_system_part_uuid='efi-system-part-uuid')

    @mock.patch.object(deploy_utils, 'try_set_boot_device', autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'install_bootloader',
                       autospec=True)
    def test_configure_local_boot_whole_disk_image(
            self, install_bootloader_mock, try_set_boot_device_mock):
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            self.passthru.configure_local_boot(task)
            self.assertFalse(install_bootloader_mock.called)
            try_set_boot_device_mock.assert_called_once_with(
                task, boot_devices.DISK)

    @mock.patch.object(deploy_utils, 'try_set_boot_device', autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'install_bootloader',
                       autospec=True)
    def test_configure_local_boot_no_root_uuid(
            self, install_bootloader_mock, try_set_boot_device_mock):
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            task.node.driver_internal_info['is_whole_disk_image'] = False
            self.passthru.configure_local_boot(task)
            self.assertFalse(install_bootloader_mock.called)
            try_set_boot_device_mock.assert_called_once_with(
                task, boot_devices.DISK)

    @mock.patch.object(agent_client.AgentClient, 'install_bootloader',
                       autospec=True)
    def test_configure_local_boot_boot_loader_install_fail(
            self, install_bootloader_mock):
        install_bootloader_mock.return_value = {
            'command_status': 'FAILED', 'command_error': 'boom'}
        self.node.provision_state = states.DEPLOYING
        self.node.target_provision_state = states.ACTIVE
        self.node.save()
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            task.node.driver_internal_info['is_whole_disk_image'] = False
            self.assertRaises(exception.InstanceDeployFailure,
                              self.passthru.configure_local_boot,
                              task, root_uuid='some-root-uuid')
            install_bootloader_mock.assert_called_once_with(
                mock.ANY, task.node, root_uuid='some-root-uuid',
                efi_system_part_uuid=None)
            self.assertEqual(states.DEPLOYFAIL, task.node.provision_state)
            self.assertEqual(states.ACTIVE, task.node.target_provision_state)

    @mock.patch.object(deploy_utils, 'try_set_boot_device', autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'install_bootloader',
                       autospec=True)
    def test_configure_local_boot_set_boot_device_fail(
            self, install_bootloader_mock, try_set_boot_device_mock):
        install_bootloader_mock.return_value = {
            'command_status': 'SUCCESS', 'command_error': None}
        try_set_boot_device_mock.side_effect = iter([RuntimeError('error')])
        self.node.provision_state = states.DEPLOYING
        self.node.target_provision_state = states.ACTIVE
        self.node.save()
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            task.node.driver_internal_info['is_whole_disk_image'] = False
            self.assertRaises(exception.InstanceDeployFailure,
                              self.passthru.configure_local_boot,
                              task, root_uuid='some-root-uuid')
            install_bootloader_mock.assert_called_once_with(
                mock.ANY, task.node, root_uuid='some-root-uuid',
                efi_system_part_uuid=None)
            try_set_boot_device_mock.assert_called_once_with(
                task, boot_devices.DISK)
            self.assertEqual(states.DEPLOYFAIL, task.node.provision_state)
            self.assertEqual(states.ACTIVE, task.node.target_provision_state)

    @mock.patch.object(agent_base_vendor.BaseAgentVendor,
                       '_notify_conductor_resume_clean', autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'get_commands_status',
                       autospec=True)
    def test_continue_cleaning(self, status_mock, notify_mock):
        # Test a successful execute clean step on the agent
        self.node.clean_step = {
            'priority': 10,
            'interface': 'deploy',
            'step': 'erase_devices',
            'reboot_requested': False
        }
        self.node.save()
        status_mock.return_value = [{
            'command_status': 'SUCCEEDED',
            'command_name': 'execute_clean_step',
            'command_result': {
                'clean_step': self.node.clean_step
            }
        }]
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            self.passthru.continue_cleaning(task)
            notify_mock.assert_called_once_with(mock.ANY, task)

    @mock.patch.object(agent_base_vendor.BaseAgentVendor,
                       '_notify_conductor_resume_clean', autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'get_commands_status',
                       autospec=True)
    def test_continue_cleaning_old_command(self, status_mock, notify_mock):
        # Test when a second execute_clean_step happens to the agent, but
        # the new step hasn't started yet.
        self.node.clean_step = {
            'priority': 10,
            'interface': 'deploy',
            'step': 'erase_devices',
            'reboot_requested': False
        }
        self.node.save()
        status_mock.return_value = [{
            'command_status': 'SUCCEEDED',
            'command_name': 'execute_clean_step',
            'command_result': {
                'priority': 20,
                'interface': 'deploy',
                'step': 'update_firmware',
                'reboot_requested': False
            }
        }]
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            self.passthru.continue_cleaning(task)
            self.assertFalse(notify_mock.called)

    @mock.patch.object(agent_base_vendor.BaseAgentVendor,
                       '_notify_conductor_resume_clean', autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'get_commands_status',
                       autospec=True)
    def test_continue_cleaning_running(self, status_mock, notify_mock):
        # Test that no action is taken while a clean step is executing
        status_mock.return_value = [{
            'command_status': 'RUNNING',
            'command_name': 'execute_clean_step',
            'command_result': None
        }]
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            self.passthru.continue_cleaning(task)
            self.assertFalse(notify_mock.called)

    @mock.patch('ironic.conductor.manager.cleaning_error_handler',
                autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'get_commands_status',
                       autospec=True)
    def test_continue_cleaning_fail(self, status_mock, error_mock):
        # Test the a failure puts the node in CLEANFAIL
        status_mock.return_value = [{
            'command_status': 'FAILED',
            'command_name': 'execute_clean_step',
            'command_result': {}
        }]
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            self.passthru.continue_cleaning(task)
            error_mock.assert_called_once_with(task, mock.ANY)

    @mock.patch('ironic.conductor.manager.set_node_cleaning_steps',
                autospec=True)
    @mock.patch.object(agent_base_vendor.BaseAgentVendor,
                       '_notify_conductor_resume_clean', autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'get_commands_status',
                       autospec=True)
    def test_continue_cleaning_clean_version_mismatch(
            self, status_mock, notify_mock, steps_mock):
        # Test that cleaning is restarted if there is a version mismatch
        status_mock.return_value = [{
            'command_status': 'CLEAN_VERSION_MISMATCH',
            'command_name': 'execute_clean_step',
            'command_result': {}
        }]
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            self.passthru.continue_cleaning(task)
            steps_mock.assert_called_once_with(task)
            notify_mock.assert_called_once_with(mock.ANY, task)

    @mock.patch('ironic.conductor.manager.cleaning_error_handler',
                autospec=True)
    @mock.patch.object(agent_client.AgentClient, 'get_commands_status',
                       autospec=True)
    def test_continue_cleaning_unknown(self, status_mock, error_mock):
        # Test that unknown commands are treated as failures
        status_mock.return_value = [{
            'command_status': 'UNKNOWN',
            'command_name': 'execute_clean_step',
            'command_result': {}
        }]
        with task_manager.acquire(self.context, self.node['uuid'],
                                  shared=False) as task:
            self.passthru.continue_cleaning(task)
            error_mock.assert_called_once_with(task, mock.ANY)
