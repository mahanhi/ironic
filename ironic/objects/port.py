# coding=utf-8
#
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

from oslo_utils import strutils
from oslo_utils import uuidutils
from oslo_config import cfg

from ironic.common import exception
from ironic.common import utils
from ironic.db import api as dbapi
from ironic.objects import base
from ironic.objects import utils as obj_utils

from ironic.static import network_services

from ironic.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class Port(base.IronicObject):
    # Version 1.0: Initial version
    # Version 1.1: Add get() and get_by_id() and get_by_address() and
    #              make get_by_uuid() only work with a uuid
    # Version 1.2: Add create() and destroy()
    # Version 1.3: Add list()
    # Version 1.4: Add list_by_node_id()
    VERSION = '1.4'

    dbapi = dbapi.get_instance()

    fields = {
        'id': int,
        'uuid': obj_utils.str_or_none,
        'node_id': obj_utils.int_or_none,
        'address': obj_utils.str_or_none,
        'extra': obj_utils.dict_or_none,
    }

    @staticmethod
    def _from_db_object(port, db_port):
        """Converts a database entity to a formal object."""
        for field in port.fields:
            port[field] = db_port[field]

        port.obj_reset_changes()
        return port

    @staticmethod
    def _from_db_object_list(db_objects, cls, context):
        """Converts a list of database entities to a list of formal objects."""
        return [Port._from_db_object(cls(context), obj) for obj in db_objects]

    @base.remotable_classmethod
    def get(cls, context, port_id):
        """Find a port based on its id or uuid and return a Port object.

        :param port_id: the id *or* uuid of a port.
        :returns: a :class:`Port` object.
        """
        if strutils.is_int_like(port_id):
            return cls.get_by_id(context, port_id)
        elif uuidutils.is_uuid_like(port_id):
            return cls.get_by_uuid(context, port_id)
        elif utils.is_valid_mac(port_id):
            return cls.get_by_address(context, port_id)
        else:
            raise exception.InvalidIdentity(identity=port_id)

    @base.remotable_classmethod
    def get_by_id(cls, context, port_id):
        """Find a port based on its integer id and return a Port object.

        :param port_id: the id of a port.
        :returns: a :class:`Port` object.
        """
        db_port = cls.dbapi.get_port_by_id(port_id)
        port = Port._from_db_object(cls(context), db_port)
        return port

    @base.remotable_classmethod
    def get_by_uuid(cls, context, uuid):
        """Find a port based on uuid and return a :class:`Port` object.

        :param uuid: the uuid of a port.
        :param context: Security context
        :returns: a :class:`Port` object.
        """
        db_port = cls.dbapi.get_port_by_uuid(uuid)
        port = Port._from_db_object(cls(context), db_port)
        return port

    @base.remotable_classmethod
    def get_by_address(cls, context, address):
        """Find a port based on address and return a :class:`Port` object.

        :param address: the address of a port.
        :param context: Security context
        :returns: a :class:`Port` object.
        """
        db_port = cls.dbapi.get_port_by_address(address)
        port = Port._from_db_object(cls(context), db_port)
        return port

    @base.remotable_classmethod
    def list(cls, context, limit=None, marker=None,
             sort_key=None, sort_dir=None):
        """Return a list of Port objects.

        :param context: Security context.
        :param limit: maximum number of resources to return in a single result.
        :param marker: pagination marker for large data sets.
        :param sort_key: column to sort results by.
        :param sort_dir: direction to sort. "asc" or "desc".
        :returns: a list of :class:`Port` object.

        """
        db_ports = cls.dbapi.get_port_list(limit=limit,
                                           marker=marker,
                                           sort_key=sort_key,
                                           sort_dir=sort_dir)
        return Port._from_db_object_list(db_ports, cls, context)

    @base.remotable_classmethod
    def list_by_node_id(cls, context, node_id, limit=None, marker=None,
                        sort_key=None, sort_dir=None):
        """Return a list of Port objects associated with a given node ID.

        :param context: Security context.
        :param node_id: the ID of the node.
        :param limit: maximum number of resources to return in a single result.
        :param marker: pagination marker for large data sets.
        :param sort_key: column to sort results by.
        :param sort_dir: direction to sort. "asc" or "desc".
        :returns: a list of :class:`Port` object.

        """
        db_ports = cls.dbapi.get_ports_by_node_id(node_id, limit=limit,
                                                  marker=marker,
                                                  sort_key=sort_key,
                                                  sort_dir=sort_dir)
        return Port._from_db_object_list(db_ports, cls, context)

    @base.remotable
    def create(self, context=None):
        """Create a Port record in the DB.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Port(context)

        """
        values = self.obj_get_changes()
        #Reade config, if static_provider is true get static IP from neutron
        #
        if not values['extra']:
            raise exception.NotAcceptable()
        net_uuid = values['extra']['net_uuid']
        if not net_uuid:
            raise exception.NotAcceptable()

        network_provider = network_services.NetworkStaticProvider()
        port_dict = self.prepare()
        port_dict['port']['mac_address'] = values['address']
        port_dict['port']['network_id'] = net_uuid
        port_dict['port']['name'] = 'metal-id-{}'.format(str(values['node_id']))
        port_dict['port']['device_id'] = str(values['node_id'])
        port_new = network_provider.create_port(port_dict,context.auth_token)
        #port_dict = network_provider.get_port(port_new['port'].get('id'),context.auth_token)
        fixed_ips = port_new.get('fixed_ips')
        if fixed_ips:
            ip_address = fixed_ips[0].get('ip_address', None)
            values['extra']['ip'] = ip_address
            values['uuid'] = port_new['port'].get('id')

        if ip_address:
            LOG.debug("IP Address =====>>>>  %s.", ip_address)

        db_port = self.dbapi.create_port(values)
        self._from_db_object(self, db_port)

    def prepare(self):
        port_dict = {
            "port": {
                "network_id": "",
                "name": "",
                "admin_state_up": True
            }
        }
        return port_dict

    @base.remotable
    def destroy(self, context=None):
        """Delete the Port from the DB.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Port(context)
        """
        self.dbapi.destroy_port(self.uuid)
        self.obj_reset_changes()

    @base.remotable
    def save(self, context=None):
        """Save updates to this Port.

        Updates will be made column by column based on the result
        of self.what_changed().

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Port(context)
        """
        updates = self.obj_get_changes()
        self.dbapi.update_port(self.uuid, updates)

        self.obj_reset_changes()

    @base.remotable
    def refresh(self, context=None):
        """Loads updates for this Port.

        Loads a port with the same uuid from the database and
        checks for updated attributes. Updates are applied from
        the loaded port column by column, if there are any updates.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Port(context)
        """
        current = self.__class__.get_by_uuid(self._context, uuid=self.uuid)
        for field in self.fields:
            if (hasattr(self, base.get_attrname(field)) and
                    self[field] != current[field]):
                self[field] = current[field]
