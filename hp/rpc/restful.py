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

import ssl
import urllib2
import base64
import json
import re

from oslo_log import log
from neutron.plugins.ml2.drivers.hp.common import tools

LOG = log.getLogger(__name__)


class REST(object):
    def __init__(self, ip, user, password):
        self.host = ip
        self.user = user
        self.password = password
        self.token = None
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        self.is_online = self.get_session()

    @property
    def online(self):
        return self.is_online

    def fillheader(self, headers):
        headers['Accept-Encoding'] = 'gzip,deflate'
        headers['Content-Type'] = 'application/json'
        headers['Host'] = self.host
        headers['Connection'] = 'Keep-Alive'
        headers['User-Agent'] = 'Apache-HttpClient/4.1.1 (java 1.5)'

    def request(self, url, body, headers, method):
        req = urllib2.Request(url, data=body, headers=headers)
        req.get_method = lambda: '%s' % method
        try:
            resp = urllib2.urlopen(req, context=self.ssl_context, timeout=3)
        except urllib2.URLError, e:
            if hasattr(e, "reason"):
                LOG.error("%s %s failed, reason:%s" % (method, url, e.reason))
            elif hasattr(e, "code"):
                LOG.error("Server couldn't fulfill the request, error:%s" %
                          e.code)
            return None
        buf = resp.read()
        return buf

    def get_session(self):
        headers = {}
        self.fillheader(headers)
        auth_str = "Basic %s" % base64.encodestring("%s:%s" %
                                                    (self.user,
                                                     self.password))
        headers['Authorization'] = auth_str.strip()
        headers['Content-Length'] = 0
        url = 'https://%s:443/api/v1//tokens HTTP/1.1' % self.host
        buf = self.request(url, None, headers, 'POST')
        if buf is None:
            LOG.error(_("Get session failed for url %s"), url)
            return False
        token = json.loads(buf)
        self.token = token['token-id'].encode()
        return True

    def post(self, table, body_dict):
        headers = {}
        self.fillheader(headers)
        headers['X-Auth-Token'] = self.token

        body = json.dumps(body_dict)
        headers['Content-Length'] = len(body)
        url = 'https://%s:443/api/v1/%s HTTP/1.1' % (self.host, table)

        req = urllib2.Request(url, data=body, headers=headers)
        method = 'POST'
        req.get_method = lambda: '%s' % method
        try:
            resp = urllib2.urlopen(req, context=self.ssl_context, timeout=3)
        except urllib2.URLError, e:
            if hasattr(e, "reason"):
                if e.reason == 'Unauthorized':
                    self.get_session()
                    headers['X-Auth-Token'] = self.token
                    self.request(url, body, headers, 'POST')
                    return
                else:
                    LOG.error("%s %s failed, reason:%s" %
                              (method, url, e.reason))
            elif hasattr(e, "code"):
                LOG.error("Server couldn't fulfill the request, error:%s" %
                          e.code)
        return

    def set(self, table_index, body, method):
        headers = {}
        self.fillheader(headers)
        headers['X-Auth-Token'] = self.token
        if body is not None:
            headers['Content-Length'] = len(body)

        index = table_index.find('index=') + 6
        table = table_index[index:]
        table = re.sub(r'=', '%3D', table)
        table = re.sub(r';', '%3B', table)
        url = ('https://%s:443/api/v1/%s HTTP/1.1' %
               (self.host, (table_index[:index] + table)))

        req = urllib2.Request(url, data=body, headers=headers)
        req.get_method = lambda: '%s' % method
        try:
            resp = urllib2.urlopen(req, context=self.ssl_context, timeout=3)
        except urllib2.URLError, e:
            if hasattr(e, "reason"):
                if e.reason == 'Unauthorized':
                    self.get_session()
                    headers['X-Auth-Token'] = self.token
                    return self.request(url, body, headers, method)
                else:
                    LOG.error("%s %s failed, reason:%s" %
                              (method, url, e.reason))
            elif hasattr(e, "code"):
                LOG.error("Server couldn't fulfill the request, Error:%s" %
                          e.code)
            return None

        buf = resp.read()
        return buf

    def put(self, table_index, body_dict):
        body = json.dumps(body_dict)
        if self.set(table_index, body, 'PUT') is None:
            return False
        else:
            return True

    def delete(self, table_index):
        if self.set(table_index, None, 'DELETE') is None:
            return False
        else:
            return True

    def get(self, table_index):
        buf = self.set(table_index, None, 'GET')
        return buf


class RestfulCfg(object):
    def __init__(self, ip_address, user_name, password):
        self.ip_address = ip_address
        self.user_name = user_name
        self.password = password

    def create_vlan_bulk(self, vlan_list, overlap=False):
        LOG.debug(_("Restful: create vlan bulk: vlan list %s, overlap %s"),
                  vlan_list, overlap)
        client = REST(self.ip_address, self.user_name, self.password)
        if client.online is not True:
            LOG.warn(_("Failed to create vlan list %s"), vlan_list)
            return False
        result = True
        for vlan_id in vlan_list:
            if self.create_vlan(vlan_id, client=client) is not True:
                result = False
                break
        return result

    def create_vlan(self, vlan_id, client=None):
        if client is None:
            client = REST(self.ip_address, self.user_name, self.password)
        if client.online is not True:
            LOG.warn(_("Failed to create vlan %s"), vlan_id)
            return False
        body_dict = {}
        body_dict['ID'] = vlan_id
        return client.put('VLAN/VLANs?index=ID=%s' % vlan_id, body_dict)

    def delete_vlan_bulk(self, vlan_list, client=None):
        if len(vlan_list) == 0:
            return True
        if client is None:
            client = REST(self.ip_address, self.user_name, self.password)
        if client.online is not True:
            LOG.warn(_("Failed to delete vlan %s"), vlan_list)
            return False
        result = True
        for vlan_id in vlan_list:
            if client.delete('VLAN/VLANs?index=ID=%s' % vlan_id) is not True:
                result = False
                break
        return result

    def delete_vlan(self, vlan_id, client=None):
        if client is None:
            client = REST(self.ip_address, self.user_name, self.password)
        if client.online is not True:
            LOG.warn(_("Failed to delete vlan %d"), vlan_id)
            return False
        resp_j = client.get('VLAN/VLANs?index=ID=%d' % vlan_id)
        if resp_j is None:
            return False
        resp = json.loads(resp_j)
        untagged_port_list = resp.get('UntaggedPortList')
        tagged_port_list = resp.get('TaggedPortList')
        if untagged_port_list or tagged_port_list:
            return True
        return client.delete('VLAN/VLANs?index=ID=%s' % vlan_id)

    def port_link_type(self, if_index_list, client=None):
        if client is None:
            client = REST(self.ip_address, self.user_name, self.password)
        if client.online is not True:
            LOG.warn(_("Change port %s link type failed."), if_index_list)
            return False
        for if_index in if_index_list:
            body_dict = {}
            body_dict['IfIndex'] = if_index
            body_dict['LinkType'] = 2
            body_dict['PortLayer'] = 1
            return client.put('Ifmgr/Interfaces?index=IfIndex=%s' %
                              if_index, body_dict)

    def port_trunk_bulk(self, port_vlan_tuple_list, client=None):
        if client is None:
            client = REST(self.ip_address, self.user_name, self.password)
        if client.online is not True:
            LOG.warn(_("Failed to set port trunk permit: %s."),
                     port_vlan_tuple_list)
            return False
        for port_list, vlan_list in port_vlan_tuple_list:
            if port_list is not None:
                if self.port_link_type(port_list, client=client) is False:
                    return False
                vlans = tools.get_vlan_commastr(vlan_list)
                for port in port_list:
                    LOG.debug(_('trunkInterface %s'), port)
                    body_dict = {}
                    body_dict['IfIndex'] = port
                    body_dict['PermitVlanList'] = vlans
                    result = client.put('VLAN/TrunkInterfaces?'
                                        'index=IfIndex=%s' % port, body_dict)
                    if result is False:
                        return result
            else:
                LOG.warn(_("Failed to get interface index list "
                           "from device %s with user %s password %s."),
                         self.ip_address, self.user_name, self.password)
        return True
