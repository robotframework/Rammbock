from unittest import TestCase, main
from .tools import MockStream
import socket
from Rammbock.templates.message_stream import MessageStream
from Rammbock.templates import Protocol, MessageTemplate, UInt, PDU
from Rammbock.binary_tools import to_bin
import threading


class TestProtocolMessageReceiving(TestCase):

    def setUp(self):
        self._protocol = Protocol('Test')
        self._protocol.add(UInt(1, 'id', 1))
        self._protocol.add(UInt(2, 'length', None))
        self._protocol.add(PDU('length-2'))

    def test_read_header_and_pdu(self):
        stream = MockStream(to_bin('0xff0004cafe'))
        header, data = self._protocol.read(stream)
        self.assertEquals(header.id.hex, '0xff')
        self.assertEquals(data, '\xca\xfe')


class TestMessageStream(TestCase):

    def setUp(self):
        self._protocol = Protocol('Test')
        self._protocol.add(UInt(1, 'id', 1))
        self._protocol.add(UInt(2, 'length', None))
        self._protocol.add(PDU('length-2'))
        self._msg = MessageTemplate('FooRequest', self._protocol, {'id': '0xaa'})
        self._msg.add(UInt(1, 'field_1', None))
        self._msg.add(UInt(1, 'field_2', None))
        byte_stream = MockStream(to_bin('0xff0004cafe aa0004dead dd0004beef'))
        self._msg_stream = MessageStream(byte_stream, self._protocol, threading.RLock())

    def test_get_message(self):
        msg = self._msg_stream.get(self._msg, header_filter='id')
        self.assertEquals(msg.field_1.hex, '0xde')

    def test_get_message_from_cache(self):
        _ = self._msg_stream.get(self._msg, header_filter='id')
        self._msg.header_parameters = {'id': '0xdd'}
        msg = self._msg_stream.get(self._msg, header_filter='id')
        self.assertEquals(msg.field_1.hex, '0xbe')

    def test_empty_message_stream(self):
        _ = self._msg_stream.get(self._msg, header_filter='id')
        self._msg_stream.empty()
        self.assertRaises(socket.timeout, self._msg_stream.get, self._msg, timeout=0.1)

    def test_filter_by_unset_field_fails(self):
        self._msg.header_parameters = {}
        self.assertRaises(AssertionError, self._msg_stream.get, self._msg, header_filter='id')

    def test_timeout_goes_to_stream(self):
        self._msg.header_parameters = {'id': '0x00'}
        self.assertRaises(socket.timeout, self._msg_stream.get, self._msg, timeout=0.1, header_filter='id')

    def test_get_messages_count_from_cache_two_messages(self):
        _ = self._msg_stream.get(self._msg, header_filter='id')
        self._msg.header_parameters = {'id': '0xdd'}
        count = self._msg_stream.get_messages_count_in_cache()
        self.assertEquals(count, 2)

    def test_get_messages_count_from_cache_three_messages(self):
        count = self._msg_stream.get_messages_count_in_cache()
        self.assertEquals(count, 3)


if __name__ == '__main__':
    main()
