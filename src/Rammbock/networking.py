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


import socket
import time
from .logger import logger
from .synchronization import SynchronizedType
from .binary_tools import to_hex
import threading

try:
    from sctp import sctpsocket_tcp
    SCTP_ENABLED = True
except ImportError:
    SCTP_ENABLED = False

UDP_BUFFER_SIZE = 65536
TCP_BUFFER_SIZE = 1000000
TCP_MAX_QUEUED_CONNECTIONS = 5


def get_family(family):
    if not family:
        family = 'ipv4'
    return {'ipv4': socket.AF_INET, 'ipv6': socket.AF_INET6}[family.lower()]


class _WithTimeouts(object):

    _default_timeout = 10

    def _get_timeout(self, timeout):
        if timeout in (None, '') or str(timeout).lower() == 'none':
            return self._default_timeout
        elif str(timeout).lower() == 'blocking':
            return None
        return float(timeout)

    def _set_default_timeout(self, timeout):
        self._default_timeout = self._get_timeout(timeout)


class _NetworkNode(_WithTimeouts):

    __metaclass__ = SynchronizedType

    _message_stream = None
    parent = None
    name = '<not set>'

    def __init__(self):
        self._lock = threading.RLock()

    def set_handler(self, msg_template, handler_func, header_filter, alias=None, interval=None):
        if alias:
            raise AssertionError('Named connections not supported.')
        self._message_stream.set_handler(msg_template, handler_func, header_filter, interval)

    def get_own_address(self):
        return self._socket.getsockname()[:2]

    def get_peer_address(self, alias=None):
        if alias:
            raise AssertionError('Named connections not supported.')
        return self._socket.getpeername()[:2]

    def close(self):
        if self._is_connected:
            self._is_connected = False
            self._socket.close()
            if self._message_stream:
                self._message_stream.close()
            self._message_stream = None

    # TODO: Rename to _get_new_message_stream
    def _get_message_stream(self):
        if not self._protocol:
            return None
        return self._protocol.get_message_stream(BufferedStream(self, self._default_timeout), self._lock)

    def get_message(self, message_template, timeout=None, header_filter=None, latest=None):
        if not self._protocol:
            raise AssertionError('Can not receive messages without protocol. Initialize network node with "protocol=<protocl name>"')
        if self._protocol != message_template._protocol:
            raise AssertionError('Template protocol does not match network node protocol %s!=%s' % (self.protocol_name, message_template._protocol.name))
        return self._get_from_stream(message_template, self._message_stream, timeout=timeout, header_filter=header_filter, latest=latest)

    def _get_from_stream(self, message_template, stream, timeout, header_filter, latest):
        return stream.get(message_template, timeout=timeout, header_filter=header_filter, latest=latest)

    def log_send(self, binary, ip, port):
        logger.debug("Send %d bytes: %s to %s:%s over %s" % (len(binary), to_hex(binary), ip, port, self._transport_layer_name))

    def log_receive(self, binary, ip, port):
        logger.trace("Trying to read %d bytes: %s from %s:%s over %s" % (len(binary), to_hex(binary), ip, port, self._transport_layer_name))

    def empty(self):
        result = True
        try:
            while result:
                result = self.receive(timeout=0.0)
        except (socket.timeout, socket.error):
            pass
        if self._message_stream:
            self._message_stream.empty()

    def receive(self, timeout=None, alias=None):
        return self.receive_from(timeout, alias)[0]

    def receive_from(self, timeout=None, alias=None):
        self._raise_error_if_alias_given(alias)
        timeout = self._get_timeout(timeout)
        self._socket.settimeout(timeout)
        return self._receive_msg_ip_port()

    def _receive_msg_ip_port(self):
        msg = self._socket.recv(self._size_limit)
        ip, port = self._socket.getpeername()[:2]
        self.log_receive(msg, ip, port)
        return msg, ip, port

    def send(self, msg, alias=None):
        self._raise_error_if_alias_given(alias)
        ip, port = self.get_peer_address()
        self.log_send(msg, ip, port)
        self._sendall(msg)

    def _sendall(self, msg):
        self._socket.sendall(msg)

    def _raise_error_if_alias_given(self, alias):
        if alias:
            raise AssertionError('Connection aliases not supported.')

    @property
    def protocol_name(self):
        return self._protocol.name if self._protocol else None

    def get_messages_count_in_buffer(self):
        return self._message_stream.get_messages_count_in_cache()


class _TCPNode(object):

    _transport_layer_name = 'TCP'
    _size_limit = TCP_BUFFER_SIZE

    def _init_socket(self, family):
        self._socket = socket.socket(get_family(family), socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


class _UDPNode(object):

    _transport_layer_name = 'UDP'
    _size_limit = UDP_BUFFER_SIZE

    def _init_socket(self, family):
        self._socket = socket.socket(get_family(family), socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


class _SCTPNode(object):

    _transport_layer_name = 'SCTP'
    _size_limit = TCP_BUFFER_SIZE

    def _init_socket(self, family):
        if not SCTP_ENABLED:
            raise Exception("SCTP Not enabled. Is pysctp installed? https://github.com/philpraxis/pysctp")
        self._socket = sctpsocket_tcp(get_family(family))


class _Server(_NetworkNode):

    def __init__(self, ip, port, timeout=None):
        self._ip = ip
        self._port = int(port)
        self._set_default_timeout(timeout)
        _NetworkNode.__init__(self)

    def _bind_socket(self):
        try:
            self._socket.bind((self._ip, self._port))
        except socket.error, e:
            raise Exception("error: [Errno %d] %s for address %s:%d" % (e[0], e[1], self._ip, self._port))
        self._is_connected = True


class UDPServer(_Server, _UDPNode):

    def __init__(self, ip, port, timeout=None, protocol=None, family=None):
        _Server.__init__(self, ip, port, timeout)
        self._protocol = protocol
        self._last_client = None
        self._init_socket(family)
        self._bind_socket()
        self._message_stream = self._get_message_stream()

    def _receive_msg_ip_port(self):
        msg, address = self._socket.recvfrom(self._size_limit)
        ip, port = address[:2]
        self.log_receive(msg, ip, port)
        self._last_client = (ip, int(port))
        return msg, ip, port

    def _check_no_alias(self, alias):
        if alias:
            raise Exception('Connection aliases are not supported on UDP Servers')

    def send_to(self, msg, ip, port):
        self._last_client = (ip, int(port))
        self.send(msg)

    def _sendall(self, msg):
        self._socket.sendto(msg, self.get_peer_address())

    def get_peer_address(self, alias=None):
        self._check_no_alias(alias)
        if not self._last_client:
            raise Exception('Server has no default client, because it has not received messages from clients yet.')
        return self._last_client


class StreamServer(_Server):

    def __init__(self, ip, port, timeout=None, protocol=None, family=None):
        _Server.__init__(self, ip, port, timeout)
        self._init_socket(family)
        self._bind_socket()
        self._socket.listen(TCP_MAX_QUEUED_CONNECTIONS)
        self._protocol = protocol
        self._init_connection_cache()

    def _init_connection_cache(self):
        self._connections = _NamedCache('connection', "No connections accepted!")

    def set_handler(self, msg_template, handler_func, header_filter, alias=None, interval=None):
        connection = self._connections.get(alias)
        connection.set_handler(msg_template, handler_func, header_filter, interval=interval)

    def receive_from(self, timeout=None, alias=None):
        connection = self._connections.get(alias)
        return connection.receive_from(timeout=timeout)

    def accept_connection(self, alias=None, timeout=0):
        timeout = self._get_timeout(timeout)
        if timeout > 0:
            self._socket.settimeout(timeout)
        connection, client_address = self._socket.accept()
        self._connections.add(_TCPConnection(self, connection, protocol=self._protocol), alias)
        return client_address

    def send(self, msg, alias=None):
        connection = self._connections.get(alias)
        connection.send(msg)

    def send_to(self, *args):
        raise Exception("Stream server cannot send to a specific address.")

    def close(self):
        if self._is_connected:
            self._is_connected = False
            for connection in self._connections:
                connection.close()
            self._socket.close()
            self._init_connection_cache()

    def close_connection(self, alias=None):
        raise Exception("Not yet implemented")

    def get_message(self, message_template, timeout=None, alias=None, header_filter=None):
        connection = self._connections.get(alias)
        return connection.get_message(message_template, timeout=timeout, header_filter=header_filter)

    def empty(self):
        for connection in self._connections:
            connection.empty()

    def get_peer_address(self, alias=None):
        connection = self._connections.get(alias)
        return connection.get_peer_address()


class _TCPConnection(_NetworkNode, _TCPNode):

    def __init__(self, parent, socket, protocol=None):
        _NetworkNode.__init__(self)
        self.parent = parent
        self._socket = socket
        self._protocol = protocol
        self._message_stream = self._get_message_stream()
        self._is_connected = True


class SCTPServer(StreamServer, _SCTPNode):
    pass


class TCPServer(StreamServer, _TCPNode):
    pass


class _Client(_NetworkNode):

    def __init__(self, timeout=None, protocol=None, family=None):
        _NetworkNode.__init__(self)
        self._is_connected = False
        self._init_socket(family)
        self._set_default_timeout(timeout)
        self._protocol = protocol
        self._message_stream = None

    def set_own_ip_and_port(self, ip=None, port=None):
        if ip and port:
            self._socket.bind((ip, int(port)))
        elif ip:
            self._socket.bind((ip, 0))
        elif port:
            self._socket.bind(("", int(port)))
        else:
            raise Exception("You must specify host or port")

    def connect_to(self, server_ip, server_port):
        if self._is_connected:
            raise Exception('Client already connected!')
        self._server_ip = server_ip
        self._socket.connect((server_ip, int(server_port)))
        self._message_stream = self._get_message_stream()
        self._is_connected = True
        return self


class UDPClient(_Client, _UDPNode):
    pass


class TCPClient(_Client, _TCPNode):
    pass


class SCTPClient(_Client, _SCTPNode):
    pass


class _NamedCache(object):

    def __init__(self, basename, miss_error):
        self._basename = basename
        self._counter = 0
        self._cache = {}
        self._current = None
        self._miss_error = miss_error

    def add(self, value, name=None):
        name = name or self._next_name()
        self._cache[name] = value
        value.name = name
        self._current = name

    def _next_name(self):
        self._counter += 1
        return self._basename + str(self._counter)

    def get_with_name(self, name=None):
        if not name:
            name = self._current
            if not name:
                raise AssertionError(self._miss_error)
            logger.debug("Choosing %s by default" % self._current)
        return self._cache[name], name

    def get(self, name=None):
        return self.get_with_name(name)[0]

    def __iter__(self):
        return self._cache.itervalues()

    def set_current(self, name):
        if name in self._cache:
            self._current = name
        else:
            raise KeyError("Name %s unknown." % name)


class BufferedStream(_WithTimeouts):

    def __init__(self, connection, default_timeout):
        self._connection = connection
        self._buffer = ''
        self._default_timeout = default_timeout

    def read(self, size, timeout=None):
        result = ''
        timeout = float(timeout if timeout else self._default_timeout)
        cutoff = time.time() + timeout
        while time.time() < cutoff:
            result += self._get(size - len(result))
            if self._size_full(result, size):
                return result
            self._fill_buffer(timeout)
        raise AssertionError('Timeout %fs exceeded.' % timeout)

    def _size_full(self, result, size):
        return len(result) == size or (size == -1 and len(result))

    def return_data(self, data):
        if data:
            self._buffer = data + self._buffer

    def _get(self, size):
        if size == -1:
            size = len(self._buffer)
        if not self._buffer:
            return ''
        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result

    def _fill_buffer(self, timeout):
        self._buffer += self._connection.receive(timeout=timeout)

    def empty(self):
        self._buffer = ''
