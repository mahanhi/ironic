__author__ = 'mnachiappan'

import signal
import socket

from neutronclient.common import exceptions as neutron_client_exc
from neutronclient.v2_0 import client as clientv20
from oslo_config import cfg

from ironic.static import base
from ironic.common import exception
from ironic.common.i18n import _
from ironic.common import keystone
from ironic.openstack.common import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt('my_ip', 'ironic.netconf')

static_provider_opts = [
    cfg.StrOpt('static_provider',
               default=None,
               help='Static provider to use. "neutron" uses Neutron, and '
               '"none" uses a no-op provider.'),
]
CONF.register_opts(static_provider_opts)

neutron_opts = [
    cfg.StrOpt('url',
               default='http://$my_ip:9696',
               help='URL for connecting to neutron.'),
    cfg.IntOpt('url_timeout',
               default=30,
               help='Timeout value for connecting to neutron in seconds.'),
    cfg.IntOpt('retries',
               default=3,
               help='Client retries in the case of a failed request.'),
    cfg.StrOpt('auth_strategy',
               default='keystone',
               help='Default authentication strategy to use when connecting '
                    'to neutron. Can be either "keystone" or "noauth". '
                    'Running neutron in noauth mode (related to but not '
                    'affected by this setting) is insecure and should only be '
                    'used for testing.')
    ]



CONF.register_opts(neutron_opts, group='neutron')
LOG = logging.getLogger(__name__)


def _build_client(token=None):
    """Utility function to create Neutron client."""
    params = {
        'timeout': CONF.neutron.url_timeout,
        'retries': CONF.neutron.retries,
        'insecure': CONF.keystone_authtoken.insecure,
        'ca_cert': CONF.keystone_authtoken.certfile,
    }

    if CONF.neutron.auth_strategy not in ['noauth', 'keystone']:
        raise exception.ConfigInvalid(_('Neutron auth_strategy should be '
                                        'either "noauth" or "keystone".'))

    if CONF.neutron.auth_strategy == 'noauth':
        params['endpoint_url'] = CONF.neutron.url
        params['auth_strategy'] = 'noauth'
    elif (CONF.neutron.auth_strategy == 'keystone' and
          token is None):
        params['endpoint_url'] = (CONF.neutron.url or
                                  keystone.get_service_url('neutron'))
        params['username'] = CONF.keystone_authtoken.admin_user
        params['tenant_name'] = CONF.keystone_authtoken.admin_tenant_name
        params['password'] = CONF.keystone_authtoken.admin_password
        params['auth_url'] = (CONF.keystone_authtoken.auth_uri or '')
        if CONF.keystone.region_name:
            params['region_name'] = CONF.keystone.region_name
    else:
        params['token'] = token
        params['endpoint_url'] = CONF.neutron.url
        params['auth_strategy'] = None

    return clientv20.Client(**params)

class NetworkStaticProvider(base.BaseStatic):

    def get_port(self, port_uuid, token):
        """get_port ."""
        """Get a port dict.

        :param port_uuid: Neutron port id.
        :param client: Neutron client instance.
        :returns: Neutron port dict.
        :raises: PortNotFound
        """
        port = None
        try:
            client = _build_client(token)
            neutron_port = client.show_port(port_uuid).get('port')
        except neutron_client_exc.NeutronClientException:
            LOG.exception(_LE("Failed to Get IP address on Neutron port %s."),
                          port_uuid)
            raise exception.PortNotFound(port_id=port_uuid)

        return neutron_port
