# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack Foundation
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

from tempest import clients
from tempest.common import isolated_creds
from tempest import exceptions
from tempest.openstack.common import log as logging
import tempest.test

LOG = logging.getLogger(__name__)


class BaseVolumeTest(tempest.test.BaseTestCase):

    """Base test case class for all Cinder API tests."""

    @classmethod
    def setUpClass(cls):
        super(BaseVolumeTest, cls).setUpClass()
        cls.isolated_creds = isolated_creds.IsolatedCreds(cls.__name__)

        if not cls.config.service_available.cinder:
            skip_msg = ("%s skipped as Cinder is not available" % cls.__name__)
            raise cls.skipException(skip_msg)

        if cls.config.compute.allow_tenant_isolation:
            creds = cls.isolated_creds.get_primary_creds()
            username, tenant_name, password = creds
            os = clients.Manager(username=username,
                                 password=password,
                                 tenant_name=tenant_name,
                                 interface=cls._interface)
        else:
            os = clients.Manager(interface=cls._interface)

        cls.os = os
        cls.volumes_client = os.volumes_client
        cls.snapshots_client = os.snapshots_client
        cls.servers_client = os.servers_client
        cls.image_ref = cls.config.compute.image_ref
        cls.flavor_ref = cls.config.compute.flavor_ref
        cls.build_interval = cls.config.volume.build_interval
        cls.build_timeout = cls.config.volume.build_timeout
        cls.snapshots = []
        cls.volumes = []
        cls.fixed_network_name = cls.config.compute.fixed_network_name
        cls.networks_client = cls.os.network_client

        cls.volumes_client.keystone_auth(cls.os.username,
                                         cls.os.password,
                                         cls.os.auth_url,
                                         cls.volumes_client.service,
                                         cls.os.tenant_name)

    @classmethod
    def tearDownClass(cls):
        cls.clear_snapshots()
        cls.clear_volumes()
        cls.isolated_creds.clear_isolated_creds()
        super(BaseVolumeTest, cls).tearDownClass()

    @classmethod
    def get_default_networks(cls):
        """Utility that returns a network structure for creating a server"""
        if cls.fixed_network_name:
            try:
                networks = cls.networks_client.list_networks()[1].get('networks')
                for network in networks:
                    if network['name'] == cls.fixed_network_name:
                        uuid = {'uuid': network['id']}
                        return [uuid]
                else:
                    raise exceptions.NotFound()
            except exceptions.NotFound:
                # In a number of legitimate situations, such as tenant
                # isolation, we may not be able to see the configured network.
                LOG.info('Unable to find network %s. '
                         'Starting instance without specifying a network.' %
                         cls.fixed_network_name)
            except exceptions.EndpointNotFound:
                # NOTE(bnemec): With nova-network we have no network endpoint
                # so we can't retrieve the network id to use here, at least
                # not without adding a Tempest client to retrieve it from
                # nova.  This means Tempest won't be able to run against
                # nova-network with multiple networks available.
                pass

        return None

    @classmethod
    def create_snapshot(cls, volume_id=1, **kwargs):
        """Wrapper utility that returns a test snapshot."""
        resp, snapshot = cls.snapshots_client.create_snapshot(volume_id,
                                                              **kwargs)
        assert 200 == resp.status
        cls.snapshots.append(snapshot)
        cls.snapshots_client.wait_for_snapshot_status(snapshot['id'],
                                                      'available')
        return snapshot

    # NOTE(afazekas): these create_* and clean_* could be defined
    # only in a single location in the source, and could be more general.

    @classmethod
    def create_volume(cls, size=1, **kwargs):
        """Wrapper utility that returns a test volume."""
        resp, volume = cls.volumes_client.create_volume(size, **kwargs)
        assert 200 == resp.status
        cls.volumes.append(volume)
        cls.volumes_client.wait_for_volume_status(volume['id'], 'available')
        return volume

    @classmethod
    def clear_volumes(cls):
        for volume in cls.volumes:
            try:
                cls.volumes_client.delete_volume(volume['id'])
            except Exception:
                pass

        for volume in cls.volumes:
            try:
                cls.volumes_client.wait_for_resource_deletion(volume['id'])
            except Exception:
                pass

    @classmethod
    def clear_snapshots(cls):
        for snapshot in cls.snapshots:
            try:
                cls.snapshots_client.delete_snapshot(snapshot['id'])
            except Exception:
                pass

        for snapshot in cls.snapshots:
            try:
                cls.snapshots_client.wait_for_resource_deletion(snapshot['id'])
            except Exception:
                pass

    def wait_for(self, condition):
        """Repeatedly calls condition() until a timeout."""
        start_time = int(time.time())
        while True:
            try:
                condition()
            except Exception:
                pass
            else:
                return
            if int(time.time()) - start_time >= self.build_timeout:
                condition()
                return
            time.sleep(self.build_interval)


class BaseVolumeAdminTest(BaseVolumeTest):
    """Base test case class for all Volume Admin API tests."""
    @classmethod
    def setUpClass(cls):
        super(BaseVolumeAdminTest, cls).setUpClass()
        cls.adm_user = cls.config.identity.admin_username
        cls.adm_pass = cls.config.identity.admin_password
        cls.adm_tenant = cls.config.identity.admin_tenant_name
        if not all((cls.adm_user, cls.adm_pass, cls.adm_tenant)):
            msg = ("Missing Volume Admin API credentials "
                   "in configuration.")
            raise cls.skipException(msg)
        if cls.config.compute.allow_tenant_isolation:
            creds = cls.isolated_creds.get_admin_creds()
            admin_username, admin_tenant_name, admin_password = creds
            cls.os_adm = clients.Manager(username=admin_username,
                                         password=admin_password,
                                         tenant_name=admin_tenant_name,
                                         interface=cls._interface)
        else:
            cls.os_adm = clients.AdminManager(interface=cls._interface)
        cls.client = cls.os_adm.volume_types_client
