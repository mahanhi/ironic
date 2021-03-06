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

from ironic.common import exception
from ironic.db import api as db_api
from ironic.objects import base
from ironic.objects import fields as object_fields


class Node(base.IronicObject):
    # Version 1.0: Initial version
    # Version 1.1: Added instance_info
    # Version 1.2: Add get() and get_by_id() and make get_by_uuid()
    #              only work with a uuid
    # Version 1.3: Add create() and destroy()
    # Version 1.4: Add get_by_instance_uuid()
    # Version 1.5: Add list()
    # Version 1.6: Add reserve() and release()
    # Version 1.7: Add conductor_affinity
    # Version 1.8: Add maintenance_reason
    # Version 1.9: Add driver_internal_info
    # Version 1.10: Add name and get_by_name()
    # Version 1.11: Add clean_step
    # Version 1.12: Add raid_config and target_raid_config
    # Version 1.13: Add touch_provisioning()
    VERSION = '1.13'

    dbapi = db_api.get_instance()

    fields = {
        'id': object_fields.IntegerField(),

        'uuid': object_fields.UUIDField(nullable=True),
        'name': object_fields.StringField(nullable=True),
        'chassis_id': object_fields.IntegerField(nullable=True),
        'instance_uuid': object_fields.UUIDField(nullable=True),

        'driver': object_fields.StringField(nullable=True),
        'driver_info': object_fields.FlexibleDictField(nullable=True),
        'driver_internal_info': object_fields.FlexibleDictField(nullable=True),

        # A clean step dictionary, indicating the current clean step
        # being executed, or None, indicating cleaning is not in progress
        # or has not yet started.
        'clean_step': object_fields.FlexibleDictField(nullable=True),

        'raid_config': object_fields.FlexibleDictField(nullable=True),
        'target_raid_config': object_fields.FlexibleDictField(nullable=True),

        'instance_info': object_fields.FlexibleDictField(nullable=True),
        'properties': object_fields.FlexibleDictField(nullable=True),
        'reservation': object_fields.StringField(nullable=True),
        # a reference to the id of the conductor service, not its hostname,
        # that has most recently performed some action which could require
        # local state to be maintained (eg, built a PXE config)
        'conductor_affinity': object_fields.IntegerField(nullable=True),

        # One of states.POWER_ON|POWER_OFF|NOSTATE|ERROR
        'power_state': object_fields.StringField(nullable=True),

        # Set to one of states.POWER_ON|POWER_OFF when a power operation
        # starts, and set to NOSTATE when the operation finishes
        # (successfully or unsuccessfully).
        'target_power_state': object_fields.StringField(nullable=True),

        'provision_state': object_fields.StringField(nullable=True),
        'provision_updated_at': object_fields.DateTimeField(nullable=True),
        'target_provision_state': object_fields.StringField(nullable=True),

        'maintenance': object_fields.BooleanField(),
        'maintenance_reason': object_fields.StringField(nullable=True),
        'console_enabled': object_fields.BooleanField(),

        # Any error from the most recent (last) asynchronous transaction
        # that started but failed to finish.
        'last_error': object_fields.StringField(nullable=True),

        'inspection_finished_at': object_fields.DateTimeField(nullable=True),
        'inspection_started_at': object_fields.DateTimeField(nullable=True),

        'extra': object_fields.FlexibleDictField(nullable=True),
    }

    @staticmethod
    def _from_db_object(node, db_node):
        """Converts a database entity to a formal object."""
        for field in node.fields:
            node[field] = db_node[field]
        node.obj_reset_changes()
        return node

    @base.remotable_classmethod
    def get(cls, context, node_id):
        """Find a node based on its id or uuid and return a Node object.

        :param node_id: the id *or* uuid of a node.
        :returns: a :class:`Node` object.
        """
        if strutils.is_int_like(node_id):
            return cls.get_by_id(context, node_id)
        elif uuidutils.is_uuid_like(node_id):
            return cls.get_by_uuid(context, node_id)
        else:
            raise exception.InvalidIdentity(identity=node_id)

    @base.remotable_classmethod
    def get_by_id(cls, context, node_id):
        """Find a node based on its integer id and return a Node object.

        :param node_id: the id of a node.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_id(node_id)
        node = Node._from_db_object(cls(context), db_node)
        return node

    @base.remotable_classmethod
    def get_by_uuid(cls, context, uuid):
        """Find a node based on uuid and return a Node object.

        :param uuid: the uuid of a node.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_uuid(uuid)
        node = Node._from_db_object(cls(context), db_node)
        return node

    @base.remotable_classmethod
    def get_by_name(cls, context, name):
        """Find a node based on name and return a Node object.

        :param name: the logical name of a node.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_name(name)
        node = Node._from_db_object(cls(context), db_node)
        return node

    @base.remotable_classmethod
    def get_by_instance_uuid(cls, context, instance_uuid):
        """Find a node based on the instance uuid and return a Node object.

        :param uuid: the uuid of the instance.
        :returns: a :class:`Node` object.
        """
        db_node = cls.dbapi.get_node_by_instance(instance_uuid)
        node = Node._from_db_object(cls(context), db_node)
        return node

    @base.remotable_classmethod
    def list(cls, context, limit=None, marker=None, sort_key=None,
             sort_dir=None, filters=None):
        """Return a list of Node objects.

        :param context: Security context.
        :param limit: maximum number of resources to return in a single result.
        :param marker: pagination marker for large data sets.
        :param sort_key: column to sort results by.
        :param sort_dir: direction to sort. "asc" or "desc".
        :param filters: Filters to apply.
        :returns: a list of :class:`Node` object.

        """
        db_nodes = cls.dbapi.get_node_list(filters=filters, limit=limit,
                                           marker=marker, sort_key=sort_key,
                                           sort_dir=sort_dir)
        return [Node._from_db_object(cls(context), obj) for obj in db_nodes]

    @base.remotable_classmethod
    def reserve(cls, context, tag, node_id):
        """Get and reserve a node.

        To prevent other ManagerServices from manipulating the given
        Node while a Task is performed, mark it reserved by this host.

        :param context: Security context.
        :param tag: A string uniquely identifying the reservation holder.
        :param node_id: A node id or uuid.
        :raises: NodeNotFound if the node is not found.
        :returns: a :class:`Node` object.

        """
        db_node = cls.dbapi.reserve_node(tag, node_id)
        node = Node._from_db_object(cls(context), db_node)
        return node

    @base.remotable_classmethod
    def release(cls, context, tag, node_id):
        """Release the reservation on a node.

        :param context: Security context.
        :param tag: A string uniquely identifying the reservation holder.
        :param node_id: A node id or uuid.
        :raises: NodeNotFound if the node is not found.

        """
        cls.dbapi.release_node(tag, node_id)

    @base.remotable
    def create(self, context=None):
        """Create a Node record in the DB.

        Column-wise updates will be made based on the result of
        self.what_changed(). If target_power_state is provided,
        it will be checked against the in-database copy of the
        node before updates are made.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Node(context)

        """
        values = self.obj_get_changes()
        db_node = self.dbapi.create_node(values)
        self._from_db_object(self, db_node)

    @base.remotable
    def destroy(self, context=None):
        """Delete the Node from the DB.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Node(context)
        """
        self.dbapi.destroy_node(self.uuid)
        self.obj_reset_changes()

    @base.remotable
    def save(self, context=None):
        """Save updates to this Node.

        Column-wise updates will be made based on the result of
        self.what_changed(). If target_power_state is provided,
        it will be checked against the in-database copy of the
        node before updates are made.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Node(context)
        """
        updates = self.obj_get_changes()
        if 'driver' in updates and 'driver_internal_info' not in updates:
            # Clean driver_internal_info when changes driver
            self.driver_internal_info = {}
            updates = self.obj_get_changes()
        self.dbapi.update_node(self.uuid, updates)
        self.obj_reset_changes()

    @base.remotable
    def refresh(self, context=None):
        """Refresh the object by re-fetching from the DB.

        :param context: Security context. NOTE: This should only
                        be used internally by the indirection_api.
                        Unfortunately, RPC requires context as the first
                        argument, even though we don't use it.
                        A context should be set when instantiating the
                        object, e.g.: Node(context)
        """
        current = self.__class__.get_by_uuid(self._context, self.uuid)
        self.obj_refresh(current)

    @base.remotable
    def touch_provisioning(self, context=None):
        """Touch the database record to mark the provisioning as alive."""
        self.dbapi.touch_node_provisioning(self.id)
