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
import time
import threading
import traceback
import re

from Rammbock.logger import logger
from Rammbock.binary_tools import to_bin, to_int


class MessageStream(object):

    def __init__(self, stream, protocol, lock):
        self._cache = []
        self._stream = stream
        self._protocol = protocol
        self._handlers = []
        self._handler_thread = None
        self._running = True
        self._interval = 0.5
        self._lock = lock

    def close(self):
        self._running = False
        self.empty()

    def set_handler(self, msg_template, handler_func, header_filter, interval):
        self._handlers.append((msg_template, handler_func, header_filter))
        if interval:
            self._interval = float(interval)
        if not self._handler_thread:
            self._handler_thread = threading.Thread(target=self.match_handlers_periodically, name="Background handler")
            self._handler_thread.daemon = True
            self._handler_thread.start()

    def get(self, message_template, timeout=None, header_filter=None, latest=None):
        header_fields = message_template.header_parameters
        logger.trace("Get message with params %s" % header_fields)
        if latest:
            self._fill_cache()
        msg = self._get_from_cache(message_template, header_fields, header_filter, latest)
        if msg:
            logger.trace("Cache hit. Cache currently has %s messages" % len(self._cache))
            return msg
        cutoff = time.time() + float(timeout if timeout else 0)
        while not timeout or time.time() < cutoff:
            with self._lock:
                header, pdu_bytes = self._protocol.read(self._stream, timeout=timeout)
                if self._matches(header, header_fields, header_filter):
                    return self._to_msg(message_template, header, pdu_bytes)
                else:
                    self._match_or_cache(header, pdu_bytes)
        raise AssertionError('Timeout %fs exceeded in message stream.' % float(timeout))

    def _match_or_cache(self, header, pdu_bytes):
        for template, func, handler_filter in self._handlers:
            if self._matches(header, template.header_parameters, handler_filter):
                msg_to_be_sent = self._to_msg(template, header, pdu_bytes)
                logger.debug("Calling handler %s for message %s" % (func, msg_to_be_sent))
                self._call_handler_function(func, msg_to_be_sent)
                return
        self._cache.append((header, pdu_bytes))

    def _get_call_handler(self, handler_name):
        module, function = handler_name.split('.')
        mod = __import__(module)
        return getattr(mod, function)

    def _get_from_cache(self, template, fields, header_filter, latest):
        indexes = range(len(self._cache))
        for index in indexes if not latest else reversed(indexes):
            header, pdu = self._cache[index]
            if self._matches(header, fields, header_filter):
                self._cache.pop(index)
                return self._to_msg(template, header, pdu)
        return None

    def _to_msg(self, template, header, pdu_bytes):
        if template.only_header:
            return header
        msg = template.decode(pdu_bytes, parent=header)
        msg._add_header(header)
        return msg

    def _matches(self, header, fields, header_filter):
        if header_filter:
            if header_filter not in fields:
                raise AssertionError('Trying to filter messages by header field %s, but no value has been set for %s' %
                                     (header_filter, header_filter))
            field = header[header_filter]
            if field._type == 'chars':
                if fields[header_filter].startswith('REGEXP:'):
                    try:
                        regexp = fields[header_filter].split(':')[1].strip()
                        return bool(re.match(regexp, field.ascii))
                    except re.error as e:
                        raise Exception("Invalid RegEx Error : " + str(e))
                return field.ascii == fields[header_filter]
            if field._type == 'uint':
                return field.uint == to_int(fields[header_filter])
            if header[header_filter].bytes != to_bin(fields[header_filter]):
                return False
        return True

    def empty(self):
        self._cache = []
        self._stream.empty()

    def get_messages_count_in_cache(self):
        self._fill_cache()
        for msg in self._cache:
            logger.info(msg)
        return len(self._cache)

    def _fill_cache(self):
        try:
            while True:
                header, pdu_bytes = self._protocol.read(self._stream, timeout=0.2)
                self._cache.append((header, pdu_bytes))
        except:
            pass

    def match_handlers_periodically(self):
        while self._running:
            time.sleep(self._interval)
            self.match_handlers()

    def match_handlers(self):
        try:
            while True:
                with self._lock:
                    self._try_matching_cached_to_templates()
                    header, pdu_bytes = self._protocol.read(self._stream, timeout=0.01)
                    self._match_or_cache(header, pdu_bytes)
        except Exception:
            logger.debug("failure in matching cache %s" % traceback.format_exc())

    # FIXME: Is this actually necessary? Wouldnt we always match before caching?
    # Unless of course the handler was set after caching happened...
    def _try_matching_cached_to_templates(self):
        if not self._cache:
            return
        for template, func, handler_filter in self._handlers:
            msg = self._get_from_cache(template, template.header_parameters, handler_filter, False)
            if msg:
                logger.debug("Calling handler %s for cached message %s" % (func, msg))
                self._call_handler_function(func, msg)

    def _call_handler_function(self, func, msg):
        func = self._get_call_handler(func)
        node, connection = self._get_node_and_connection()
        args = func.func_code.co_argcount
        if args == 3:
            return func(self._protocol.library, msg, node)
        if args == 4:
            return func(self._protocol.library, msg, node, connection)
        return func(self._protocol.library, msg)

    def _get_node_and_connection(self):
        connection = self._stream._connection
        if connection.parent:
            return connection.parent, connection
        return connection, None
