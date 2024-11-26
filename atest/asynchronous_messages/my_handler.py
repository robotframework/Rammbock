from Rammbock import logger
import sys


RECEIVED_MESSAGES = []
SERVER_SENT = {'sample': 0, 'another': 0}


def handle_sample(rammbock, msg):
    RECEIVED_MESSAGES.append(msg)


def reset_received_messages():
    while RECEIVED_MESSAGES:
        RECEIVED_MESSAGES.pop()


def respond_to_sample(rammbock, msg, client):
    RECEIVED_MESSAGES.append(msg)
    foo = "adding Extra Variable to replicate ArgCount bug"
    bar = "adding Extra Variable to replicate ArgCount bug"
    message_template = rammbock.get_message_template('sample response')
    rammbock.client_sends_given_message(message_template, client.name)


def server_respond_to_another_max_100(rammbock, msg, server, connection):
    RECEIVED_MESSAGES.append(msg)
    if SERVER_SENT['another'] < 100:
        SERVER_SENT['another'] = SERVER_SENT['another'] + 1
        message_template = rammbock.get_message_template('another')
        rammbock.server_sends_given_message(message_template, server.name, connection.name)
    else:
        logger.warn("Reached 100 in another")


def server_respond_to_sample_response_max_100(rammbock, msg):
    RECEIVED_MESSAGES.append(msg)
    if SERVER_SENT['sample'] < 100:
        SERVER_SENT['sample'] = SERVER_SENT['sample'] + 1
        message_template = rammbock.get_message_template('sample')
        rammbock.server_sends_given_message(message_template)
    else:
        logger.warn("Reached 100 in sample")


def get_rcvd_msg():
    return RECEIVED_MESSAGES
