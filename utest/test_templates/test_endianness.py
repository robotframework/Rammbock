from unittest import TestCase
from Rammbock.templates.containers import Protocol, MessageTemplate
from Rammbock.templates.primitives import UInt, PDU
from Rammbock.binary_tools import to_bin
from .tools import *
from Rammbock.templates.message_stream import MessageStream
import threading


class TestLittleEndian(TestCase):

    def test_little_endian_struct_decode(self):
        pair = get_pair()
        decoded = pair.decode(to_bin('0xcafebabe'), little_endian=True)
        self.assertEquals(decoded.first.hex, '0xfeca')
        self.assertEquals(decoded.second.hex, '0xbeba')

    def test_little_endian_struct_encode(self):
        pair = get_pair()
        encoded = pair.encode({}, little_endian=True)
        self.assertEquals(encoded.first.hex, '0x0001')
        self.assertEquals(encoded.first._raw, to_bin('0x0100'))
        self.assertEquals(encoded.second.hex, '0x0002')
        self.assertEquals(encoded.second._raw, to_bin('0x0200'))

    def test_little_endian_list_encode(self):
        struct_list = get_struct_list()
        encoded = struct_list.encode({}, None, little_endian=True)
        self.assertEquals(encoded[0].first.hex, '0x0001')
        self.assertEquals(encoded[0].first._raw, to_bin('0x0100'))
        self.assertEquals(encoded[0].second.hex, '0x0002')
        self.assertEquals(encoded[0].second._raw, to_bin('0x0200'))


class TestLittleEndianProtocol(TestCase):

    def setUp(self):
        self._protocol = Protocol('TestProtocol', little_endian=True)
        self._protocol.add(UInt(2, 'msgId', 5))
        self._protocol.add(UInt(2, 'length', None))
        self._protocol.add(PDU('length-4'))
        self.tmp = MessageTemplate('FooRequest', self._protocol, {})
        self.tmp.add(UInt(2, 'field_1', '0xcafe'))
        self.tmp.add(UInt(2, 'field_2', '0xbabe'))

    def test_encode_little_endian_header(self):
        encoded = self.tmp.encode({}, {})
        self.assertEquals(encoded._header.msgId.hex, '0x0005')
        self.assertEquals(encoded._header.length.hex, '0x0008')
        self.assertEquals(encoded._header.msgId._raw, to_bin('0x0500'))
        self.assertEquals(encoded._header.length._raw, to_bin('0x0800'))

    def test_decode_little_endian_header(self):
        byte_stream = MockStream(to_bin('0x0500 0800 cafe babe'))
        self._msg_stream = MessageStream(byte_stream, self._protocol, threading.RLock())
        decoded = self._msg_stream.get(self.tmp)
        self.assertEquals(decoded._header.msgId.hex, '0x0005')
        self.assertEquals(decoded._header.msgId._raw, to_bin('0x0500'))
        self.assertEquals(decoded.field_1.hex, '0xcafe')
        self.assertEquals(decoded.field_1._raw, to_bin('0xcafe'))
        self.assertEquals(decoded.field_2.hex, '0xbabe')
        self.assertEquals(decoded.field_2._raw, to_bin('0xbabe'))
