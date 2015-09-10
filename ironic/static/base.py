

"""
Abstract base class for static providers.
"""

import abc

import six


@six.add_metaclass(abc.ABCMeta)
class BaseStatic(object):
    """Base class for Static provider APIs."""

    @abc.abstractmethod
    def create_port(self, port_dict):
        """create_port ."""
        pass

    @abc.abstractmethod
    def bind_port_to_segment(self, port_dict):
        """bind_port_to_segment ."""
        pass

    @abc.abstractmethod
    def update_port(self, port_dict):
        """update_port ."""
        pass

    @abc.abstractmethod
    def delete_port(self, port_id):
        """delete_port ."""
        pass

    @abc.abstractmethod
    def get_port(self, port_id, token=None):
        """get_port ."""
        pass

