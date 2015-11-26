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
import urllib2
import ssl
from string import Template
from xml.etree import ElementTree
from oslo_log import log as logging
from neutron.plugins.ml2.drivers.hp.common import tools


LOG = logging.getLogger(__name__)

MESSAGE_ID = "404"
LANGUAGE_CH = "zh-cn"
LANGUAGE_EN = "en"

NS_HELLO = "{http://www.%s.com/netconf/base:1.0}"
NS_DATA = "{http://www.%s.com/netconf/data:1.0}"
SESSION = """<env:Envelope
  xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Header>
    <auth:Authentication env:mustUnderstand="1"
    xmlns:auth="http://www.$OEM.com/netconf/base:1.0">
      <auth:AuthInfo>$AuthInfo</auth:AuthInfo>
      <auth:Language>$Language</auth:Language>
    </auth:Authentication>
  </env:Header>
  <env:Body>
    <rpc message-id="$messageid"
    xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
       <get-sessions/>
    </rpc>
   </env:Body>
</env:Envelope>
"""
HELLO = """<env:Envelope
 xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
   <env:Header>
      <auth:Authentication env:mustUnderstand="1"
      xmlns:auth="http://www.%s.com/netconf/base:1.0">
         <auth:UserName>%s</auth:UserName>
         <auth:Password>%s</auth:Password>
      </auth:Authentication>
   </env:Header>
   <env:Body>
      <hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
         <capabilities>
            <capability>urn:ietf:params:netconf:base:1.0</capability>
         </capabilities>
      </hello>
   </env:Body>
</env:Envelope>"""

CLOSE = """<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
   <env:Header>
      <auth:Authentication env:mustUnderstand="1"
      xmlns:auth="http://www.$OEM.com/netconf/base:1.0">
         <auth:AuthInfo>$AuthInfo</auth:AuthInfo>
         <auth:Language>$Language</auth:Language>
      </auth:Authentication>
   </env:Header>
   <env:Body>
     <rpc message-id="$messageid"
          xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
       <close-session/>
     </rpc>
   </env:Body>
</env:Envelope>"""

EDIT_HEAD = """<env:Envelope
xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Header>
    <auth:Authentication env:mustUnderstand="1"
     xmlns:auth="http://www.$OEM.com/netconf/base:1.0">
      <auth:AuthInfo>$AuthInfo</auth:AuthInfo>
      <auth:Language>$Language</auth:Language>
    </auth:Authentication>
  </env:Header>
  <env:Body>
    <rpc message-id="$messageid"
      xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
      <edit-config>
             <target>
          <running/>
        </target>
            <default-operation>merge</default-operation>
        <test-option>set</test-option>
        <error-option>continue-on-error</error-option>
        <config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0">
          <top xmlns="http://www.$OEM.com/netconf/config:1.0" >"""

EDIT_TAIL = """ </top>
        </config>
      </edit-config>
    </rpc>
  </env:Body>
</env:Envelope>"""

GET_HEADER = """<env:Envelope
  xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Header>
    <auth:Authentication env:mustUnderstand="1"
     xmlns:auth="http://www.$OEM.com/netconf/base:1.0">
      <auth:AuthInfo>$AuthInfo</auth:AuthInfo>
      <auth:Language>$Language</auth:Language>
    </auth:Authentication>
  </env:Header>
  <env:Body>
    <rpc message-id="$messageid"
    xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
      <get>
        <filter type="subtree">
          <top xmlns="http://www.$OEM.com/netconf/data:1.0"
          xmlns:h3c="http://www.$OEM.com/netconf/data:1.0"
          xmlns:base="http://www.$OEM.com/netconf/base:1.0"
          xmlns:netconf="urn:ietf:params:xml:ns:netconf:base:1.0">"""

GET_TAIL = """</top></filter>
         </get>
      </rpc>
   </env:Body>
</env:Envelope>"""

GET_BULK_HEADER = """<env:Envelope
xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Header>
    <auth:Authentication env:mustUnderstand="1"
    xmlns:auth="http://www.$OEM.com/netconf/base:1.0">
      <auth:AuthInfo>$AuthInfo</auth:AuthInfo>
      <auth:Language>$Language</auth:Language>
    </auth:Authentication>
  </env:Header>
  <env:Body>
    <rpc message-id="$messageid"
    xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
      <get-bulk>
        <filter type="subtree">
          <top xmlns="http://www.$OEM.com/netconf/data:1.0"
          xmlns:h3c="http://www.$OEM.com/netconf/data:1.0"
          xmlns:base="http://www.$OEM.com/netconf/base:1.0"
          xmlns:netconf="urn:ietf:params:xml:ns:netconf:base:1.0">"""

GET_BULK_TAIL = """</top></filter>
         </get-bulk>
      </rpc>
   </env:Body>
</env:Envelope>"""

CLI_EXEC_HEAD = """<env:Envelope
 xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
   <env:Header>
      <auth:Authentication env:mustUnderstand="1"
      xmlns:auth="http://www.$OEM.com/netconf/base:1.0">
         <auth:AuthInfo>$AuthInfo</auth:AuthInfo>
         <auth:Language>$Language</auth:Language>
      </auth:Authentication>
   </env:Header>
   <env:Body>
      <rpc message-id="$messageid"
      xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
         <CLI>
          <Execution>"""

CLI_EXEC_TAIL = """</Execution>
        </CLI>
      </rpc>
   </env:Body>
</env:Envelope>"""

CLI_CONF_HEAD = """<env:Envelope
 xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
   <env:Header>
      <auth:Authentication env:mustUnderstand="1"
       xmlns:auth="http://www.$OEM.com/netconf/base:1.0">
         <auth:AuthInfo>$AuthInfo</auth:AuthInfo>
         <auth:Language>$Language</auth:Language>
      </auth:Authentication>
   </env:Header>
   <env:Body>
      <rpc message-id="$messageid"
       xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
         <CLI>
          <Configuration>"""

CLI_CONF_TAIL = """</Configuration>
        </CLI>
      </rpc>
   </env:Body>
</env:Envelope>"""
NC_VLAN_GROUP = """<VLAN xc:operation='%s'>
                    <VLANs>%s</VLANs>
                 </VLAN>
              """
NC_VLAN = """<VLANID><ID>%s</ID></VLANID>"""

NC_TRUNK_INTERFACE = """<Interface>
                         <IfIndex>%s</IfIndex>
                         <PermitVlanList>%s</PermitVlanList>
                     </Interface>
                  """
NC_VLAN_TRUNK = """<VLAN><TrunkInterfaces>%s</TrunkInterfaces></VLAN>"""
NC_PORT = """<Port><Name>%s</Name><IfIndex></IfIndex></Port>"""
NC_IFINDEX = """<Ifmgr><Ports>%s</Ports></Ifmgr>"""
NC_LINKTYPE_INTERFACE = """<Interface>
                           <IfIndex>%s</IfIndex>
                           <LinkType>%s</LinkType>
                        </Interface>"""
NC_LINKTYPE = """<Ifmgr>
                 <Interfaces>%s</Interfaces>
               </Ifmgr>"""
SOAP_HTTPS_PORT = 832


class NetConfig(object):
    def __init__(self, oem='hp', ip='127.0.0.1',
                 schema='https', user_name='', password=''):
        url = '%s://%s:%d/soap/netconf/' % (schema, ip, SOAP_HTTPS_PORT)
        self.url = url
        self.oem = oem
        self.message_id = MESSAGE_ID
        self.language = LANGUAGE_EN
        self.ns_data = NS_DATA % oem
        self.user_name = user_name
        self.password = password
        self.auth_info = None
        self.schema = schema
        if schema.lower() == 'https':
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        else:
            self.ssl_context = None

    def request(self, req_msg):
        msg = Template(req_msg)
        MSG = msg.substitute(OEM=self.oem, Language=self.language,
                             messageid=self.message_id,
                             AuthInfo=self.auth_info)
        try:
            req = urllib2.Request(self.url, MSG)
            resp = urllib2.urlopen(req, context=self.ssl_context, timeout=3)
            buf = resp.read()
            return buf
        except urllib2.URLError, err:
            LOG.warn(_("Request failed: %s"), err)
            return

    def close_session(self):
        if self.auth_info is not None:
            close_template = Template(CLOSE)
            close_msg = close_template.substitute(AuthInfo=self.auth_info,
                                                  Language=self.language,
                                                  messageid=self.message_id)
            try:
                req = urllib2.Request(self.url, close_msg)
                resp = urllib2.urlopen(req, context=self.ssl_context)
                LOG.info("Session %s closed.", resp.read())
            except urllib2.URLError, err:
                LOG.warn(_("Close session failed: %s"), err)

    def get_session(self):
        if self.auth_info is not None:
            verify_msg = self.request(SESSION)
            if verify_msg is None:
                LOG.warn(_("Failed to get session."))
                return False
            root = ElementTree.fromstring(verify_msg)
            valid_session = True
            for element in root.iter("faultstring"):
                if element.text == 'Invalid session':
                    valid_session = False
                    break
            if valid_session is True:
                LOG.info(_("Current authorization info is still in use."))
                return True
        LOG.info(_("Get new session with %s"), self.url)
        hello_msg = HELLO % (self.oem, self.user_name, self.password)
        req_hello = urllib2.Request(self.url, hello_msg)
        try:
            resp_hello = urllib2.urlopen(req_hello,
                                         context=self.ssl_context, timeout=3)
        except urllib2.URLError, err:
            if hasattr(err, "reason"):
                LOG.warn(_('Failed to connect server %s, error:%s'),
                         self.url, err.reason)
            elif hasattr(err, "code"):
                LOG.warn('Request failed, error:%s', err.code)
            else:
                LOG.warn("urllib2 error:%s", err)
            self.close_session()
            return False

        buf_hello = resp_hello.read()
        root = ElementTree.fromstring(buf_hello)
        ns = NS_HELLO % self.oem
        for auth in root.iter(ns + "AuthInfo"):
            self.auth_info = auth.text
            break
        return True

    def get(self, body, *tags):
        if self.get_session() is not True:
            return
        get_msg_tmp = GET_HEADER + body + GET_TAIL
        buf_get = self.request(get_msg_tmp)
        if buf_get is None:
            return
        root = ElementTree.fromstring(buf_get)
        dict_ret = {}
        for element in tags:
            tag = self.ns_data + element
            for label in root.iter(tag):
                dict_ret[element] = label.text
                break
        return dict_ret

    def get_bulk(self, body, *tags):
        if self.get_session() is not True:
            return
        get_msg_tmp = GET_HEADER + body + GET_TAIL
        buf_get = self.request(get_msg_tmp)
        if buf_get is None:
            return
        root = ElementTree.fromstring(buf_get)
        dict_ret = {}
        for element in tags:
            tag = self.ns_data + element
            dict_ret.setdefault(element, [])
            for label in root.iter(tag):
                dict_ret[element].append(label.text)
        return dict_ret

    def get_next(self, body, *tags):
        if self.get_session() is not True:
            return
        getall_msg_tmp = GET_BULK_HEADER + body + GET_BULK_TAIL
        buf_get = self.request(getall_msg_tmp)
        if buf_get is None:
            return
        root = ElementTree.fromstring(buf_get)
        dict_ret = {}
        for element in tags:
            tag = self.ns_data + element
            for label in root.iter(tag):
                dict_ret[element] = label.text
                break
        return dict_ret

    def set(self, body):
        if self.get_session() is not True:
            return False
        set_msg_tmp = EDIT_HEAD + body + EDIT_TAIL
        result = self.request(set_msg_tmp)
        if result is not None and "ok/" in result:
            LOG.info(_("Edit config %s success."), body)
            result = True
        else:
            LOG.warn(_("Edit config %s failed. Result is %s"),
                     body, result)
            result = False
        return result

    def execute(self, cmd):
        if self.get_session() is not True:
            return
        exec_msg_tmp = CLI_EXEC_HEAD + cmd + CLI_EXEC_TAIL
        return self.request(exec_msg_tmp)

    def config(self, cmd):
        if self.get_session() is not True:
            return
        self.get_session()
        conf_msg_tmp = CLI_CONF_HEAD + cmd + CLI_CONF_TAIL
        return self.request(conf_msg_tmp)


class NetConfigClient(NetConfig):
    def __init__(self, oem, ip, schema, user_name, password):
        super(NetConfigClient, self).__init__(oem=oem,
                                              ip=ip,
                                              schema=schema,
                                              user_name=user_name,
                                              password=password)

    def port_link_type_bulk(self, port_list, link_type=2):
        port_link_xml = ""
        for port in port_list:
            port_link_xml += NC_LINKTYPE_INTERFACE % (port, link_type)
        result = True
        if len(port_list) > 0:
            port_link_bulk_xml = NC_LINKTYPE % port_link_xml
            result = self.set(port_link_bulk_xml)
            LOG.info(_("Change port %s type to trunk."), str(port_list))
        return result

    def create_vlan(self, vlan_id):
        vlan_xml = NC_VLAN_GROUP % ('merge', (NC_VLAN % vlan_id))
        result = self.set(vlan_xml)
        if result is True:
            LOG.info(_("Create vlan %s"), str(vlan_id))
        return result

    def create_vlan_bulk(self, vlan_list, overlap=False):
        vlan_xml_unit = ""
        for vlan_id in vlan_list:
            unit = NC_VLAN % vlan_id
            vlan_xml_unit += unit
        if overlap is True:
            operation = 'replace'
        else:
            operation = 'merge'
        vlan_xml = NC_VLAN_GROUP % (operation, vlan_xml_unit)
        return self.set(vlan_xml)

    def delete_vlan_bulk(self, vlan_list):
        if len(vlan_list) == 0:
            return True
        vlan_units = ""
        for vlan_id in vlan_list:
            vlan_units += NC_VLAN % vlan_id
        del_vlan_xml = NC_VLAN_GROUP % ('remove', vlan_units)
        return self.set(del_vlan_xml)

    def delete_vlan(self, vlan_id):
        vlan_unit = NC_VLAN % vlan_id
        del_vlan_xml = NC_VLAN_GROUP % ('remove', vlan_unit)
        LOG.info(_("Delete vlan %s"), str(vlan_id))
        return self.set(del_vlan_xml)

    def port_trunk_permit(self, port, vlan_list=[]):
        result = False
        if port is not None:
            self.port_link_type_bulk([port])
            vlan_str = tools.get_vlan_commastr(vlan_list)
            trunk_xml = NC_VLAN_TRUNK % \
                (NC_TRUNK_INTERFACE % (port, vlan_str))
            result = self.set(trunk_xml)
        return result

    def port_trunk_bulk(self, port_vlan_tuple_list):
        LOG.info(_("Port vlan tuple %s "), port_vlan_tuple_list)
        trunk_intf_xmls = ""
        trunk_port_list = []
        for (port_list, vlan_list) in port_vlan_tuple_list:
            vlans = tools.get_vlan_commastr(vlan_list)
            trunk_port_list.extend(port_list)
            for port in port_list:
                trunk_intf_xmls += NC_TRUNK_INTERFACE % (port, vlans)
        result = True
        if len(trunk_port_list) > 0:
            self.port_link_type_bulk(trunk_port_list)
            trunk_xml = NC_VLAN_TRUNK % trunk_intf_xmls
            result = self.set(trunk_xml)
        return result
