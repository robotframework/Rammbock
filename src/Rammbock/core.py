#  Copyright 2014 Nokia Siemens Networks Oyj
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import with_statement
import copy
from contextlib import contextmanager
from .logger import logger
from .synchronization import SynchronizedType
from .templates.containers import BagTemplate, CaseTemplate
from .message import _StructuredElement
from .networking import (TCPServer, TCPClient, UDPServer, UDPClient, SCTPServer,
                         SCTPClient, _NamedCache)
from .message_sequence import MessageSequence
from .templates import (Protocol, UInt, Int, PDU, MessageTemplate, Char, Binary,
                        TBCD, StructTemplate, ListTemplate, UnionTemplate,
                        BinaryContainerTemplate, ConditionalTemplate,
                        TBCDContainerTemplate)
from .binary_tools import to_0xhex, to_bin


class RammbockCore(object):

    ROBOT_LIBRARY_SCOPE = 'GLOBAL'

    __metaclass__ = SynchronizedType

    def __init__(self):
        self._init_caches()

    def _init_caches(self):
        self._protocol_in_progress = None
        self._protocols = {}
        self._servers = _NamedCache('server', "No servers defined!")
        self._clients = _NamedCache('client', "No clients defined!")
        self._message_stack = []
        self._header_values = {}
        self._field_values = {}
        self._message_sequence = MessageSequence()
        self._message_templates = {}
        self.reset_handler_messages()

    @property
    def _current_container(self):
        return self._message_stack[-1]

    def reset_handler_messages(self):
        logger.reset_background_messages()

    def log_handler_messages(self):
        logger.log_background_messages()

    def set_client_handler(self, handler_func, name=None, header_filter=None, interval=0.5):
        """Sets an automatic handler for the type of message template currently loaded.

        This feature allows users to set a python handler function which is called
        automatically by the Rammbock message queue when message matches the expected
        template. The optional name argument defines the client node to which the
        handler will be bound. Otherwise the default client will be used.

        The header_filter defines which header field will be used to identify the
        message defined in template. (Otherwise all incoming messages will match!)

        The interval defines the interval in seconds on which the handler will
        be called on background. By default the incoming messages are checked
        every 0.5 seconds.

        The handler function will be called with two arguments: the rammbock library
        instance and the received message.

        Example:
        | Load template      | SomeMessage |
        | Set client handler | my_module.respond_to_sample |

        my_module.py:
        | def respond_to_sample(rammbock, msg):
        |     rammbock.save_template("__backup_template", unlocked=True)
        |     try:
        |         rammbock.load_template("sample response")
        |         rammbock.client_sends_message()
        |     finally:
        |         rammbock.load_template("__backup_template")
        """
        msg_template = self._get_message_template()
        client, client_name = self._clients.get_with_name(name)
        client.set_handler(msg_template, handler_func, header_filter=header_filter, interval=interval)

    def set_server_handler(self, handler_func, name=None, header_filter=None, alias=None, interval=0.5):
        """Sets an automatic handler for the type of message template currently loaded.

        This feature allows users to set a python handler function which is called
        automatically by the Rammbock message queue when message matches the expected
        template. The optional name argument defines the server node to which the
        handler will be bound. Otherwise the default server will be used.

        The header_filter defines which header field will be used to identify the
        message defined in template. (Otherwise all incoming messages will match!)

        The interval defines the interval in seconds on which the handler will
        be called on background. By default the incoming messages are checked
        every 0.5 seconds.

        The alias is the alias for the connection. By default the current active
        connection will be used.

        The handler function will be called with two arguments: the rammbock library
        instance and the received message.

        Example:
        | Load template      | SomeMessage |
        | Set server handler | my_module.respond_to_sample | messageType |

        my_module.py:
        | def respond_to_sample(rammbock, msg):
        |     rammbock.save_template("__backup_template", unlocked=True)
        |     try:
        |         rammbock.load_template("sample response")
        |         rammbock.server_sends_message()
        |     finally:
        |         rammbock.load_template("__backup_template")
        """
        msg_template = self._get_message_template()
        server, server_name = self._servers.get_with_name(name)
        server.set_handler(msg_template, handler_func, header_filter=header_filter, alias=alias, interval=interval)

    def reset_rammbock(self):
        """Closes all connections, deletes all servers, clients, and protocols.

        You should call this method before exiting your test run. This will
        close all the connections and the ports will therefore be available for
        reuse faster.
        """
        for client in self._clients:
            client.close()
        for server in self._servers:
            server.close()
        self._init_caches()

    def clear_message_streams(self):
        """ Resets streams and sockets of incoming messages.

        You can use this method to reuse the same connections for several
        consecutive test cases.
        """
        for client in self._clients:
            client.empty()
        for server in self._servers:
            server.empty()

    def new_protocol(self, protocol_name, little_endian=False):
        """Start defining a new protocol template.

        All messages sent and received from a connection that uses a protocol
        have to conform to this protocol template.
        """
        if self._protocol_in_progress:
            raise Exception('Can not start a new protocol definition in middle of old.')
        if protocol_name in self._protocols:
            raise Exception('Protocol %s already defined' % protocol_name)
        self._init_new_message_stack(Protocol(protocol_name, little_endian, library=self))
        self._protocol_in_progress = True

    def end_protocol(self):
        """End protocol definition."""
        protocol = self._get_message_template()
        self._protocols[protocol.name] = protocol
        self._protocol_in_progress = False

    def start_udp_server(self, ip, port, name=None, timeout=None, protocol=None, family='ipv4'):
        """Starts a new UDP server to given `ip` and `port`.

        Server can be given a `name`, default `timeout` and a `protocol`.
        `family` can be either ipv4 (default) or ipv6.

        Examples:
        | Start UDP server | 10.10.10.2 | 53 |
        | Start UDP server | 10.10.10.2 | 53 | Server1 |
        | Start UDP server | 10.10.10.2 | 53 | name=Server1 | protocol=GTPV2 |
        | Start UDP server | 10.10.10.2 | 53 | timeout=5 |
        | Start UDP server | 0:0:0:0:0:0:0:1 | 53 | family=ipv6 |
        """
        self._start_server(UDPServer, ip, port, name, timeout, protocol, family)

    def start_tcp_server(self, ip, port, name=None, timeout=None, protocol=None, family='ipv4'):
        """Starts a new TCP server to given `ip` and `port`.

        Server can be given a `name`, default `timeout` and a `protocol`.
        `family` can be either ipv4 (default) or ipv6. Notice that you have to
        use `Accept Connection` keyword for server to receive connections.

        Examples:
        | Start TCP server | 10.10.10.2 | 53 |
        | Start TCP server | 10.10.10.2 | 53 | Server1 |
        | Start TCP server | 10.10.10.2 | 53 | name=Server1 | protocol=GTPV2 |
        | Start TCP server | 10.10.10.2 | 53 | timeout=5 |
        | Start TCP server | 0:0:0:0:0:0:0:1 | 53 | family=ipv6 |
        """
        self._start_server(TCPServer, ip, port, name, timeout, protocol, family)

    def start_sctp_server(self, ip, port, name=None, timeout=None, protocol=None, family='ipv4'):
        """Starts a new STCP server to given `ip` and `port`.

        `family` can be either ipv4 (default) or ipv6.

        pysctp (https://github.com/philpraxis/pysctp) need to be installed your system.
        Server can be given a `name`, default `timeout` and a `protocol`.
        Notice that you have to use `Accept Connection` keyword for server to
        receive connections.

        Examples:
        | Start STCP server | 10.10.10.2 | 53 |
        | Start STCP server | 10.10.10.2 | 53 | Server1 |
        | Start STCP server | 10.10.10.2 | 53 | name=Server1 | protocol=GTPV2 |
        | Start STCP server | 10.10.10.2 | 53 | timeout=5 |
        """
        self._start_server(SCTPServer, ip, port, name, timeout, protocol, family)

    def _start_server(self, server_class, ip, port, name, timeout, protocol, family):
        protocol = self._get_protocol(protocol)
        server = server_class(ip=ip, port=port, timeout=timeout, protocol=protocol, family=family)
        return self._servers.add(server, name)

    def start_udp_client(self, ip=None, port=None, name=None, timeout=None, protocol=None, family='ipv4'):
        """Starts a new UDP client.

        Client can be optionally given `ip` and `port` to bind to, as well as
        `name`, default `timeout` and a `protocol`.  `family` can be either
        ipv4 (default) or ipv6.

        You should use `Connect` keyword to connect client to a host.

        Examples:
        | Start UDP client |
        | Start UDP client | name=Client1 | protocol=GTPV2 |
        | Start UDP client | 10.10.10.2 | 53 | name=Server1 | protocol=GTPV2 |
        | Start UDP client | timeout=5 |
        | Start UDP client | 0:0:0:0:0:0:0:1 | 53 | family=ipv6 |
        """
        self._start_client(UDPClient, ip, port, name, timeout, protocol, family)

    def start_tcp_client(self, ip=None, port=None, name=None, timeout=None, protocol=None, family='ipv4'):
        """Starts a new TCP client.

        Client can be optionally given `ip` and `port` to bind to, as well as
        `name`, default `timeout` and a `protocol`. `family` can be either
        ipv4 (default) or ipv6.

        You should use `Connect` keyword to connect client to a host.

        Examples:
        | Start TCP client |
        | Start TCP client | name=Client1 | protocol=GTPV2 |
        | Start TCP client | 10.10.10.2 | 53 | name=Server1 | protocol=GTPV2 |
        | Start TCP client | timeout=5 |
        | Start TCP client | 0:0:0:0:0:0:0:1 | 53 | family=ipv6 |
        """
        self._start_client(TCPClient, ip, port, name, timeout, protocol, family)

    def start_sctp_client(self, ip=None, port=None, name=None, timeout=None, protocol=None, family='ipv4'):
        """Starts a new SCTP client.

        Client can be optionally given `ip` and `port` to bind to, as well as
        `name`, default `timeout` and a `protocol`.  `family` can be either
        ipv4 (default) or ipv6.

        You should use `Connect` keyword to connect client to a host.

        Examples:
        | Start TCP client |
        | Start TCP client | name=Client1 | protocol=GTPV2 |
        | Start TCP client | 10.10.10.2 | 53 | name=Server1 | protocol=GTPV2 |
        | Start TCP client | timeout=5 |
        """
        self._start_client(SCTPClient, ip, port, name, timeout, protocol, family)

    def _start_client(self, client_class, ip, port, name, timeout, protocol, family):
        protocol = self._get_protocol(protocol)
        client = client_class(timeout=timeout, protocol=protocol, family=family)
        if ip or port:
            client.set_own_ip_and_port(ip=ip, port=port)
        return self._clients.add(client, name)

    def _get_protocol(self, protocol):
        try:
            protocol = self._protocols[protocol] if protocol else None
        except KeyError:
            raise Exception("No protocol '%s' defined!" % protocol)
        return protocol

    def get_client_protocol(self, name=None):
        """Returns name of the protocol client uses or empty if client does not
        use a protocol.
        """
        return self._clients.get(name).protocol_name or ''

    def accept_connection(self, name=None, alias=None, timeout=0):
        """Accepts a connection to server identified by `name` or the latest
        server if `name` is empty.

        If given an `alias`, the connection is named and can be later referenced
        with that name.

        If `timeout` is > 0, the connection times out after the time specified.
        `timeout` defaults to 0 which will wait indefinitely.
        Empty value or None will use socket default timeout.

        Examples:
        | Accept connection |
        | Accept connection | Server1 | my_connection |
        | Accept connection | Server1 | my_connection | timeout=5 |
        """
        server = self._servers.get(name)
        server.accept_connection(alias, timeout)

    def connect(self, host, port, name=None):
        """Connects a client to given `host` and `port`. If client `name` is not
        given then connects the latest client.

        Examples:
        | Connect | 127.0.0.1 | 8080 |
        | Connect | 127.0.0.1 | 8080 | Client1 |
        """
        client = self._clients.get(name)
        client.connect_to(host, port)

    def _register_send(self, sender, label, name, connection=None):
        self._message_sequence.send(name, sender.get_own_address(), sender.get_peer_address(alias=connection),
                                    sender.protocol_name, label)

    def _register_receive(self, receiver, label, name, error='', connection=None):
        self._message_sequence.receive(name, receiver.get_own_address(), receiver.get_peer_address(alias=connection),
                                       receiver.protocol_name, label, error)

    def client_sends_binary(self, message, name=None, label=None):
        """Send raw binary `message`.

        If client `name` is not given, uses the latest client. Optional message
        `label` is shown on logs.

        Examples:
        | Client sends binary | Hello! |
        | Client sends binary | ${some binary} | Client1 | label=DebugMessage |
        """
        client, name = self._clients.get_with_name(name)
        client.send(message)
        self._register_send(client, label, name)

    # FIXME: support "send to" somehow. A new keyword?
    def server_sends_binary(self, message, name=None, connection=None, label=None):
        """Send raw binary `message`.

        If server `name` is not given, uses the latest server. Optional message
        `label` is shown on logs.

        Examples:
        | Server sends binary | Hello! |
        | Server sends binary | ${some binary} | Server1 | label=DebugMessage |
        | Server sends binary | ${some binary} | connection=my_connection |
        """
        server, name = self._servers.get_with_name(name)
        server.send(message, alias=connection)
        self._register_send(server, label, name, connection=connection)

    def client_receives_binary(self, name=None, timeout=None, label=None):
        """Receive raw binary message.

        If client `name` is not given, uses the latest client. Optional message
        `label` is shown on logs.

        Examples:
        | ${binary} = | Client receives binary |
        | ${binary} = | Client receives binary | Client1 | timeout=5 |
        """
        client, name = self._clients.get_with_name(name)
        msg = client.receive(timeout=timeout)
        self._register_receive(client, label, name)
        return msg

    def server_receives_binary(self, name=None, timeout=None, connection=None, label=None):
        """Receive raw binary message.

        If server `name` is not given, uses the latest server. Optional message
        `label` is shown on logs.

        Examples:
        | ${binary} = | Server receives binary |
        | ${binary} = | Server receives binary | Server1 | connection=my_connection | timeout=5 |
        """
        return self.server_receives_binary_from(name, timeout, connection=connection, label=label)[0]

    def server_receives_binary_from(self, name=None, timeout=None, connection=None, label=None):
        """Receive raw binary message. Returns message, ip, and port.

        If server `name` is not given, uses the latest server. Optional message
        `label` is shown on logs.

        Examples:
        | ${binary} | ${ip} | ${port} = | Server receives binary from |
        | ${binary} | ${ip} | ${port} = | Server receives binary from | Server1 | connection=my_connection | timeout=5 |
        """
        server, name = self._servers.get_with_name(name)
        msg, ip, port = server.receive_from(timeout=timeout, alias=connection)
        self._register_receive(server, label, name, connection=connection)
        return msg, ip, port

    def _init_new_message_stack(self, message, fields=None, header_fields=None):
        self._field_values = fields if fields else {}
        self._header_values = header_fields if header_fields else {}
        self._message_stack = [message]

    def new_message(self, message_name, protocol=None, *parameters):
        """Define a new message template with `message_name`.

        `protocol` has to be defined earlier with `Start Protocol Description`.
        Optional parameters are default values for message header separated with
        colon.

        Examples:
        | New message | MyMessage | MyProtocol | header_field:value |
        """
        proto = self._get_protocol(protocol)
        if not proto:
            raise Exception("Protocol not defined! Please define a protocol before creating a message!")
        if self._protocol_in_progress:
            raise Exception("Protocol definition in progress. Please finish it before starting to define a message.")
        configs, fields, header_fields = self._parse_parameters(parameters)
        self._raise_error_if_configs_or_fields(configs, fields, 'New message')
        self._init_new_message_stack(MessageTemplate(message_name, proto, header_fields))

    def _raise_error_if_configs_or_fields(self, configs, fields, function):
        if configs or fields:
            raise AssertionError('Cannot set configs or pdu fields in %s' % function)

    def save_template(self, name, unlocked=False):
        """Save a message template for later use with `Load template`.

        If saved template is marked as unlocked, then changes can be made to it
        afterwards. By default tempaltes are locked.

        Examples:
        | Save Template | MyMessage |
        | Save Template | MyOtherMessage | unlocked=True |
        """
        if isinstance(unlocked, basestring):
            unlocked = unlocked.lower() != 'false'
        template = self._get_message_template()
        if not unlocked:
            template.set_as_saved()
        self._message_templates[name] = (template, self._field_values)

    def load_template(self, name, *parameters):
        """Load a message template saved with `Save template`.
        Optional parameters are default values for message header separated with
        colon.

        Examples:
        | Load Template | MyMessage | header_field:value |
        """
        template, fields, header_fields = self._set_templates_fields_and_header_fields(name, parameters)
        self._init_new_message_stack(template, fields, header_fields)

    def load_copy_of_template(self, name, *parameters):
        """Load a copy of message template saved with `Save template` when originally saved values need to be preserved
        from test to test.
        Optional parameters are default values for message header separated with
        colon.

        Examples:
        | Load Copy Of Template | MyMessage | header_field:value |
        """
        template, fields, header_fields = self._set_templates_fields_and_header_fields(name, parameters)
        copy_of_template = copy.deepcopy(template)
        copy_of_fields = copy.deepcopy(fields)
        self._init_new_message_stack(copy_of_template, copy_of_fields, header_fields)

    def _set_templates_fields_and_header_fields(self, name, parameters):
        configs, fields, header_fields = self._parse_parameters(parameters)
        self._raise_error_if_configs_or_fields(configs, fields, 'Load template')
        template, fields = self._message_templates[name]
        return template, fields, header_fields

    def get_message(self, *parameters):
        """Get encoded message.

        * Send Message -keywords are convenience methods, that will call this to
        get the message object and then send it. Optional parameters are message
        field values separated with colon.

        Examples:
        | ${msg} = | Get message |
        | ${msg} = | Get message | field_name:value |
        """
        _, message_fields, header_fields = self._get_parameters_with_defaults(parameters)
        return self._encode_message(message_fields, header_fields)

    def _encode_message(self, message_fields, header_fields):
        msg = self._get_message_template().encode(message_fields, header_fields)
        logger.debug('%s' % repr(msg))
        return msg

    def _get_message_template(self):
        if len(self._message_stack) != 1:
            raise Exception('Message definition not complete. %s not completed.' % self._current_container.name)
        return self._message_stack[0]

    # FIXME: how to support kwargs from new robot versions?
    def client_sends_message(self, *parameters):
        """Send a message defined with `New Message`.

        Optional parameters are client `name` separated with equals and message
        field values separated with colon. Protocol header values can be set
        with syntax header:header_field_name:value.

        Examples:
        | Client sends message |
        | Client sends message | field_name:value | field_name2:value |
        | Client sends message | name=Client1 | header:message_code:0x32 |
        """
        self._send_message(self.client_sends_binary, parameters)

    # FIXME: support "send to" somehow. A new keyword?
    def server_sends_message(self, *parameters):
        """Send a message defined with `New Message`.

        Optional parameters are server `name` and possible `connection` alias
        separated with equals and message field values separated with colon.
        Protocol header values can be set with syntax header:header_field_name:value.

        Examples:
        | Server sends message |
        | Server sends message | field_name:value | field_name2:value |
        | Server sends message | name=Server1 | connection=my_connection | header:message_code:0x32 |
        """
        self._send_message(self.server_sends_binary, parameters)

    def _send_message(self, callback, parameters):
        configs, message_fields, header_fields = self._get_parameters_with_defaults(parameters)
        msg = self._encode_message(message_fields, header_fields)
        callback(msg._raw, label=self._current_container.name, **configs)

    def client_receives_message(self, *parameters):
        """Receive a message with template defined using `New Message` and
        validate field values.

        Message template has to be defined with `New Message` before calling
        this.

        Optional parameters:
        - `name` the client name (default is the latest used) example: `name=Client 1`
        - `timeout` for receiving message. example: `timeout=0.1`
        - `latest` if set to True, get latest message from buffer instead first. Default is False. Example: `latest=True`
        -  message field values for validation separated with colon. example: `some_field:0xaf05`

        Examples:
        | ${msg} = | Client receives message |
        | ${msg} = | Client receives message | name=Client1 | timeout=5 |
        | ${msg} = | Client receives message | message_field:(0|1) |
        """
        with self._receive(self._clients, *parameters) as (msg, message_fields, header_fields):
            self._validate_message(msg, message_fields, header_fields)
            return msg

    def client_receives_without_validation(self, *parameters):
        """Receive a message with template defined using `New Message`.

        Message template has to be defined with `New Message` before calling
        this.

        Optional parameters:
        - `name` the client name (default is the latest used) example: `name=Client 1`
        - `timeout` for receiving message. example: `timeout=0.1`
        - `latest` if set to True, get latest message from buffer instead first. Default is False. Example: `latest=True`

        Examples:
        | ${msg} = | Client receives without validation |
        | ${msg} = | Client receives without validation | name=Client1 | timeout=5 |
        """
        with self._receive(self._clients, *parameters) as (msg, _, _):
            return msg

    def server_receives_message(self, *parameters):
        """Receive a message with template defined using `New Message` and
        validate field values.

        Message template has to be defined with `New Message` before calling
        this.

        Optional parameters:
        - `name` the client name (default is the latest used) example: `name=Client 1`
        - `connection` alias. example: `connection=connection 1`
        - `timeout` for receiving message. example: `timeout=0.1`
        - `latest` if set to True, get latest message from buffer instead first. Default is False. Example: `latest=True`
        -  message field values for validation separated with colon. example: `some_field:0xaf05`

        Optional parameters are server `name`, `connection` alias and
        possible `timeout` separated with equals and message field values for
        validation separated with colon.

        Examples:
        | ${msg} = | Server receives message |
        | ${msg} = | Server receives message | name=Server1 | alias=my_connection | timeout=5 |
        | ${msg} = | Server receives message | message_field:(0|1) |
        """
        with self._receive(self._servers, *parameters) as (msg, message_fields, header_fields):
            self._validate_message(msg, message_fields, header_fields)
            return msg

    def server_receives_without_validation(self, *parameters):
        """Receive a message with template defined using `New Message`.

        Message template has to be defined with `New Message` before calling
        this.

        Optional parameters:
        - `name` the client name (default is the latest used) example: `name=Client 1`
        - `connection` alias. example: `connection=connection 1`
        - `timeout` for receiving message. example: `timeout=0.1`
        - `latest` if set to True, get latest message from buffer instead first. Default is False. Example: `latest=True`

        Examples:
        | ${msg} = | Server receives without validation |
        | ${msg} = | Server receives without validation | name=Server1 | alias=my_connection | timeout=5 |
        """
        with self._receive(self._servers, *parameters) as (msg, _, _):
            return msg

    def validate_message(self, msg, *parameters):
        """Validates given message using template defined with `New Message` and
        field values given as optional arguments.

        Examples:
        | Validate message | ${msg} |
        | Validate message | ${msg} | status:0 |
        """
        _, message_fields, header_fields = self._get_parameters_with_defaults(parameters)
        self._validate_message(msg, message_fields, header_fields)

    def _validate_message(self, msg, message_fields, header_fields):
        errors = self._get_message_template().validate(msg, message_fields, header_fields)
        if errors:
            logger.info("Validation failed for %s" % repr(msg))
            logger.info('\n'.join(errors))
            raise AssertionError(errors[0])

    @contextmanager
    def _receive(self, nodes, *parameters):
        configs, message_fields, header_fields = self._get_parameters_with_defaults(parameters)
        node, name = nodes.get_with_name(configs.pop('name', None))
        msg = node.get_message(self._get_message_template(), **configs)
        try:
            yield msg, message_fields, header_fields
            self._register_receive(node, self._current_container.name, name)
            logger.debug("Received %s" % repr(msg))
        except AssertionError, e:
            self._register_receive(node, self._current_container.name, name, error=e.args[0])
            raise e

    def uint(self, length, name, value=None, align=None):
        """Add an unsigned integer to template.

        `length` is given in bytes and `value` is optional. `align` can be used
        to align the field to longer byte length.

        Examples:
        | uint | 2 | foo |
        | uint | 2 | foo | 42 |
        | uint | 2 | fourByteFoo | 42 | align=4 |
        """
        self._add_field(UInt(length, name, value, align=align))

    def int(self, length, name, value=None, align=None):
        """Add an signed integer to template.

        `length` is given in bytes and `value` is optional. `align` can be used
        to align the field to longer byte length.
        Signed integer uses twos-complement with bits numbered in big-endian.

        Examples:
        | int | 2 | foo |
        | int | 2 | foo | 42 |
        | int | 2 | fourByteFoo | 42 | align=4 |
        """
        self._add_field(Int(length, name, value, align=align))

    def chars(self, length, name, value=None, terminator=None):
        """Add a char array to template.

        `length` is given in bytes and can refer to earlier numeric fields in
        template. Special value '*' in length means that length is encoded to
        length of value and decoded as all available bytes.

        `value` is optional.
        `value` could be either a "String" or a "Regular Expression" and
        if it is a Regular Expression it must be prefixed by 'REGEXP:'.

        Examples:
        | chars | 16 | field | Hello World! |

        | u8 | charLength |
        | chars | charLength | field |

        | chars | * | field | Hello World! |
        | chars | * | field | REGEXP:^{[a-zA-Z ]+}$ |
        """

        self._add_field(Char(length, name, value, terminator))

    def _add_field(self, field):
        if self._current_container.is_saved:
            raise AssertionError('Adding fields to message loaded with Load template is not allowed')
        self._current_container.add(field)

    def new_struct(self, type, name, *parameters):
        """Defines a new struct to template.

        You must call `End Struct` to end struct definition. `type` is the name
        for generic type and `name` is the field name in containing structure.
        Possible parameters are values for struct fields separated with colon
        and optional struct length defined with `length=`. Length can be used in
        receiveing to validate that struct matches predfeined length. When
        sending, the struct length can refer to other message field which will
        then be set dynamically.

        Examples:
        | New struct | Pair | myPair |
        | u8     | first |
        | u8     | second |
        | End Struct |
        """
        configs, parameters, _ = self._get_parameters_with_defaults(parameters)
        self._add_struct_name_to_params(name, parameters)
        self._message_stack.append(StructTemplate(type, name, self._current_container, parameters, length=configs.get('length'), align=configs.get('align')))

    def _add_struct_name_to_params(self, name, parameters):
        for param_key in parameters.keys():
            parameters[name + '.' + param_key] = parameters.pop(param_key)

    def end_struct(self):
        """End struct definition. See `New Struct`."""
        struct = self._message_stack.pop()
        self._add_field(struct)

    def _new_list(self, size, name):
        """Defines a new list to template of `size` and with `name`.

        List type must be given after this keyword by defining one field. Then
        the list definition has to be closed using `End List`.

        Special value '*' in size means that list will decode values as long as
        data is available. This free length value is not supported on encoding.

        Examples:
        | New list | 5 | myIntList |
        | u16 |
        | End List |

        | u8 | listLength |
        | New list | listLength | myIntList |
        | u16 |
        | End List |

        | New list | * | myIntList |
        | u16 |
        | End List |
        """
        self._message_stack.append(ListTemplate(size, name, self._current_container))

    def _end_list(self):
        """End list definition. See `New List`.
        """
        list = self._message_stack.pop()
        self._add_field(list)

    def new_binary_container(self, name):
        """Defines a new binary container to template.

        Binary container can only contain binary fields defined with `Bin`
        keyword.

        Examples:
        | New binary container | flags |
        | bin | 2 | foo |
        | bin | 6 | bar |
        | End binary container |
        """
        self._message_stack.append(BinaryContainerTemplate(name, self._current_container))

    def new_tbcd_container(self, name):
        self._message_stack.append(TBCDContainerTemplate(name, self._current_container))

    def end_binary_container(self):
        """End binary container. See `New Binary Container`.
        """
        binary_container = self._message_stack.pop()
        binary_container.verify()
        self._add_field(binary_container)

    def end_tbcd_container(self):
        tbcd_container = self._message_stack.pop()
        self._add_field(tbcd_container)

    def bin(self, size, name, value=None):
        """Add new binary field to template.

        This keyword has to be called within a binary container. See `New Binary
        Container`.
        """
        self._add_field(Binary(size, name, value))

    def tbcd(self, size, name, value=None):
        self._add_field(TBCD(size, name, value))

    def new_union(self, type, name):
        """Defines a new union to template of `type` and `name`.

        Fields inside the union are alternatives and the length of the union is
        the length of its longest field.

        Example:
        | New union | IntOrAddress | foo |
        | Chars | 16 | ipAddress |
        | u32   | int |
        | End union |
        """
        self._message_stack.append(UnionTemplate(type, name, self._current_container))

    def end_union(self):
        """End union definition. See `New Union`.
        """
        union = self._message_stack.pop()
        self._add_field(union)

    def start_bag(self, name):
        """Bags are sets of optional elements with an optional count.

        The optional elements are given each as a `Case` with the accepted count
        as first argument. The received elements are matched from the list of
        cases in order. If the the received value does not validate against the
        case (for example a value of a field does not match expected), then the
        next case is tried until a match is found. Note that although the received
        elements are matched in order that the cases are given, the elements dont
        need to arrive in the same order as the cases are.


        This example would match int value 42 0-1 times and in value 1 0-2 times.
        For example 1, 42, 1 would match, as would 1, 1:
        | Start bag | intBag |
        | case | 0-1 | u8 | foo | 42 |
        | case | 0-2 | u8 | bar | 1 |
        | End bag |


        A more real world example, where each AVP entry has a type field with a
        value that is used for matching:
        | Start bag | avps |
        | Case | 1 | AVP | result | Result-Code |
        | Case | 1 | AVP | originHost | Origin-Host |
        | Case | 1 | AVP | originRealm | Origin-Realm |
        | Case | 1 | AVP | hostIP | Host-IP-Address |
        | Case | * | AVP | appId | Vendor-Specific-Application-Id |
        | Case | 0-1 | AVP | originState | Origin-State |
        | End bag |

        For a more complete example on bags, see the
        [https://github.com/robotframework/Rammbock/blob/master/atest/diameter.robot|diameter.robot]
        file from Rammbock's acceptance tests.
        """
        self._message_stack.append(BagTemplate(name, self._current_container))

    def end_bag(self):
        """Ends a bag started with `Start Bag`.
        """
        bag = self._message_stack.pop()
        self._add_field(bag)

    def _start_bag_case(self, size):
        self._message_stack.append(CaseTemplate(size, self._current_container))

    def _end_bag_case(self):
        case = self._message_stack.pop()
        self._add_field(case)

    def pdu(self, length):
        """Defines the message in protocol template.

        Length must be the name of a previous field in template definition or a
        static value for fixed length protocols.

        Examples:
        | pdu | 5 |

        | u8  | length |
        | pdu | length - 1 |
        """
        self._add_field(PDU(length))

    def hex_to_bin(self, hex_value):
        """Converts given hex value to binary.

        Examples:
        | ${bin} = | Hex to bin | 0xcafe |
        """
        return to_bin(hex_value)

    def bin_to_hex(self, bin_value):
        """Converts given binary to hex string.

        Examples:
        | ${hex} = | Bin to hex | Hello! |
        | ${hex} = | Bin to hex | ${binary} |
        """
        return to_0xhex(bin_value)

    def _get_parameters_with_defaults(self, parameters):
        config, fields, headers = self._parse_parameters(parameters)
        fields = self._populate_defaults(fields, self._field_values)
        headers = self._populate_defaults(headers, self._header_values)
        return config, fields, headers

    def _populate_defaults(self, fields, default_values):
        ret_val = default_values
        ret_val.update(fields)
        return ret_val

    def value(self, name, value):
        """Defines a default `value` for a template field identified by `name`.

        Default values for header fields can be set with header:field syntax.

        Examples:
        | Value | foo | 42 |
        | Value | struct.sub_field | 0xcafe |
        | Value | header:version | 0x02 |
        """
        if isinstance(value, _StructuredElement):
            self._struct_fields_as_values(name, value)
        elif name.startswith('header:'):
            self._header_values[name.partition(':')[-1]] = value
        else:
            self._field_values[name] = value

    def _struct_fields_as_values(self, name, value):
        for field_name in value._fields:
            self.value('%s.%s' % (name, field_name), value._fields[field_name])

    def _parse_parameters(self, parameters):
        configs, fields = [], []
        for parameter in parameters:
            self._parse_entry(parameter, configs, fields)
        headers, fields = self._get_headers(fields)
        return self._to_dict(configs, fields, headers)

    def _get_headers(self, fields):
        headers = []
        indices = []
        for index, (name, value) in enumerate(fields):
            if name == 'header' and ':' in value:
                headers.append(self._name_and_value(':', value))
                indices.append(index)
        fields = (field for index, field in enumerate(fields)
                  if index not in indices)
        return headers, fields

    def _to_dict(self, *lists):
        return (dict(list) for list in lists)

    def _parse_entry(self, param, configs, fields):
        colon_index = param.find(':')
        equals_index = param.find('=')
        # TODO: Cleanup. There must be a cleaner way.
        # Luckily test_rammbock.py has unit tests covering all paths.
        if colon_index == equals_index == -1:
            raise Exception('Illegal parameter %s' % param)
        elif equals_index == -1:
            fields.append(self._name_and_value(':', param))
        elif colon_index == -1 or colon_index > equals_index:
            configs.append(self._name_and_value('=', param))
        else:
            fields.append(self._name_and_value(':', param))

    def _name_and_value(self, separator, parameter):
        index = parameter.find(separator)
        try:
            key = str(parameter[:index].strip())
        except UnicodeError:
            raise Exception("Only ascii characters are supported in parameters.")
        return key, parameter[index + 1:].strip()

    def conditional(self, condition, name):
        """Defines a 'condition' when conditional element of 'name' exists if `condition` is true.

        `condition` can contain multiple conditions combined together using Logical Expressions(&&,||).

        Example:
        | Conditional | mycondition == 1 | foo |
        | u8   | myelement | 42 |
        | End conditional |

        | Conditional | condition1 == 1 && condition2 != 2 | bar |
        | u8   | myelement | 8 |
        | End condtional |
        """
        self._message_stack.append(ConditionalTemplate(condition, name, self._current_container))

    def end_conditional(self):
        """End conditional definition. See `Conditional`.
        """
        conditional = self._message_stack.pop()
        self._add_field(conditional)

    def get_client_unread_messages_count(self, client_name=None):
        """Gets count of unread messages from client
        """
        client = self._clients.get_with_name(client_name)[0]
        return client.get_messages_count_in_buffer()

    def get_server_unread_messages_count(self, server_name=None):
        """Gets count of unread messages from server
        """
        server = self._servers.get(server_name)
        return server.get_messages_count_in_buffer()

    def close_client(self, name=None):
        """Closes the client connection based on the `client_name`.

        If no name provided it will close the current active connection.
        You have to explicitly `Switch Client` after close when sending or
        receiving any message without explicitly passing the client name.

        Example:
        | Close Client | client |
        """
        self._clients.get(name).close()

    def close_server(self, name=None):
        """Closes the Server connection based on the `server_name`.

        If no name provided it will close the current active connection.
        You have to explicitly `Switch Server` after close when sending or
        receiving any message without explicitly passing the server
        name.

        Example:
        | Close Server | server |
        """
        self._servers.get(name).close()

    def switch_client(self, name):
        """ Switches the current active client to the `client_name` specified.

        Example:
        | Switch Client | client |
        """
        self._clients.set_current(name)

    def switch_server(self, name):
        """ Switches the current active server to the `server_name` specified.

        Example:
        | Switch Server | server |
        """
        self._servers.set_current(name)
