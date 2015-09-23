__author__ = 'mnachiappan'

from ironic.db import api as dbapi

from ironic import objects

import argparse
import base64
import contextlib
import gzip
import json
import os
import shutil
import subprocess
import tempfile

from ironic.common import exception
from ironic.common.i18n import _
from ironic.common import utils
from ironic.openstack.common import log
from netaddr import *

LOG = log.getLogger(__name__)

class ConfigDrive(object):

    def set_config_drive(self, context, node_uuid, configdrive=None):

        if os.path.isdir(configdrive):
            configdrive = self.make_configdrive(configdrive)

        return configdrive

    def create_meta_data(self, node_uuid, context):
        #create /openstack/latest/meta_data.json
        #create /openstack/content/0000
        #network_config (IP Address, gateway, cidr, mac, dns, domain)
        #uuid, hostname, name, public_keys
        node_ident = objects.Node.get_by_uuid(context,node_uuid)
        ports = objects.Port.list_by_node_id(context, node_ident._id)
        LOG.debug('Got all the ports for %s, [%s]' %(node_uuid, ports))
        with utils.tempdir() as config_drive:
            LOG.debug('Created temp directory %s, %s' %(node_uuid , config_drive))
            meta_dir = self.create_dir(config_drive)
            count = 0
            content_dir = meta_dir['content']+'/0000'
            content_fd = os.open(content_dir ,os.O_RDWR|os.O_CREAT)
            content = "auto lo" + '\n'
            content += "iface lo inet loopback" + '\n\n'
            for port in ports:
                interface = 'eth'+str(count)
                LOG.debug('Creating %s' %(interface))
                content += 'auto '+interface+'\n'
                content += 'iface '+interface+' inet static' +'\n'
                cidr = IPNetwork(port['_extra']['cidr'])
                content += 'address %s' %port['_extra']['ip'] + '\n'
                content += 'netmask %s' %(cidr.netmask) + '\n'
                content += 'gateway %s' %cidr.ip + '\n\n'
                count +=1
            LOG.debug('Content  %s' %(content))
            os.write(content_fd, content)
            os.close(content_fd)
            meta_data = {}
            meta_data["availability_zone"] = ""
            meta_data["hostname"] = node_ident._name
            meta_data["network_config"] = {"content_path": "/content/0000", "name": "network_config"}
            meta_data["meta"] = {}
            meta_data["public_keys"] = {"mykey":""}
            meta_data["uuid"] = node_ident._uuid
            meta_fd = os.open(config_drive + meta_dir["meta_json"]+"/meta_data.json",os.O_RDWR|os.O_CREAT)
            LOG.debug('metadata_json  %s' %(meta_data))
            os.write(meta_fd, str(meta_data))
            os.close(meta_fd)
            config_drive_data = self.make_configdrive(config_drive)
            LOG.debug('config_drive_data  %s' %(config_drive_data))
            return config_drive_data

    def create_dir(self, path):
        latest = path + "/openstack/latest"
        content = path + "/openstack/content/"
        os.makedirs(latest)
        os.makedirs(content)
        meta_info = {"meta_json": latest, "content":content}
        return meta_info

    def make_configdrive(path):
        """Make the config drive file.
        :param path: The directory containing the config drive files.
        :returns: A gzipped and base64 encoded configdrive string.
        """
        # Make sure path it's readable
        if not os.access(path, os.R_OK):
            raise Exception(_('The directory "%s" is not readable') % path)

        with tempfile.NamedTemporaryFile() as tmpfile:
            with tempfile.NamedTemporaryFile() as tmpzipfile:
                publisher = 'ironic-configdrive 0.1'
                try:
                    p = subprocess.Popen(['genisoimage', '-o', tmpfile.name,
                                          '-ldots', '-allow-lowercase',
                                          '-allow-multidot', '-l',
                                          '-publisher', publisher,
                                          '-quiet', '-J',
                                          '-r', '-V', 'config-2',
                                          path],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                except OSError as e:
                    raise Exception(
                        _('Error generating the config drive. Make sure the '
                          '"genisoimage" tool is installed. Error: %s') % e)

                stdout, stderr = p.communicate()
                if p.returncode != 0:
                    raise Exception(
                        _('Error generating the config drive.'
                          'Stdout: "%(stdout)s". Stderr: %(stderr)s') %
                        {'stdout': stdout, 'stderr': stderr})

                # Compress file
                tmpfile.seek(0)
                g = gzip.GzipFile(fileobj=tmpzipfile, mode='wb')
                shutil.copyfileobj(tmpfile, g)
                g.close()

                tmpzipfile.seek(0)
                return base64.b64encode(tmpzipfile.read())

