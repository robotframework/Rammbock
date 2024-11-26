*** Settings ***
Library           Rammbock
Variables         ports.py

*** Variables ***
${TEST MACHINE}    127.0.0.1
${SERVER}         ${TEST MACHINE}
${CLIENT}         ${TEST MACHINE}

*** Keywords ***
Define example protocol
    [Arguments]    ${name}=Example
    New protocol    ${name}
    u8    version    0x01
    u8    reserved    0x00
    u16    messageType    # Empty on purpose, each message template defines the type for it
    u16    length    # Empty on purpose, the length is pdu length
    u16    flags    0x0000
    pdu    length-8
    End protocol

Define simple protocol
    New protocol    Example
    uint    1    field    16
    pdu    4
    End protocol

Receiver
    [Arguments]    ${name}
    New Struct    Receiver    ${name}
    u16    board
    u16    process
    End Struct

Define protocol with struct in header
    New protocol    StructProtocol
    u16    length
    Receiver    receiver
    pdu    length-6
    End protocol

Setup protocol with struct in header, Udp server and client
    Define protocol with struct in header
    Setup UDP server and client    StructProtocol

Setup TCP server and client
    [Arguments]    ${protocol}=
    Start TCP server    ${SERVER}    ${SERVER PORT}    name=ExampleServer    protocol=${protocol}
    Start TCP client    name=ExampleClient    protocol=${protocol}
    connect    ${SERVER}    ${SERVER PORT}    name=ExampleClient
    Accept connection    name=ExampleServer

Define protocol, start tcp server and two clients
    [Arguments]    ${protocol}=
    Define example protocol
    Start TCP server    ${SERVER}    ${SERVER PORT}    name=ExampleServer    protocol=${protocol}
    Start TCP client    name=ExampleClient1    protocol=${protocol}
    Start TCP client    name=ExampleClient2    protocol=${protocol}
    connect    ${SERVER}    ${SERVER PORT}    name=ExampleClient1
    Accept connection    alias=Connection1
    connect    ${SERVER}    ${SERVER PORT}    name=ExampleClient2
    Accept connection    alias=Connection2

Setup UDP server and client
    [Arguments]    ${protocol}=
    Start udp server    ${SERVER}    ${SERVER PORT}    name=ExampleServer    protocol=${protocol}    timeout=1
    Start udp client    name=ExampleClient    protocol=${protocol}    timeout=1
    connect    ${SERVER}    ${SERVER PORT}    name=ExampleClient

Setup protocol, UDP server, and client
    Define example protocol
    Setup UDP server and client    protocol=Example

Setup protocol, TCP server, and client
    Define example protocol
    Setup TCP server and client    protocol=Example

Start two udp clients
    Start udp client    ${CLIENT}    ${CLIENT 1 PORT}    Client_1
    Start udp client    ${CLIENT}    ${CLIENT 2 PORT}    Client_2

Start two tcp clients
    Start tcp client    ${CLIENT}    ${CLIENT 1 PORT}    Client_1
    Start tcp client    ${CLIENT}    ${CLIENT 2 PORT}    Client_2

Connect two clients
    [Arguments]    ${server port 1}    ${server port 2}
    connect    ${SERVER}    ${server port 1}    Client_1
    connect    ${SERVER}    ${server port 2}    Client_2

Connect two clients and accept connections
    [Arguments]    ${server 1}=    ${server port 1}=${SERVER PORT}    ${server 2}=    ${server port 2}=${SERVER PORT}
    Connect    ${SERVER}    ${server port 1}    name=Client_1
    Accept connection    name=${server 1}    alias=Connection_1
    Connect    ${SERVER}    ${server port 2}    name=Client_2
    Accept connection    name=${server 2}    alias=Connection_2

Two clients send foo and bar
    Client Sends binary    foo    name=Client_1
    Client Sends binary    bar    name=Client_2

Verify server gets hex
    [Arguments]    ${expected hex}
    ${msg} =    Server receives binary
    Binary should equal hex    ${msg}    ${expected hex}

Verify client gets hex
    [Arguments]    ${expected hex}
    ${msg} =    Client receives binary
    Binary should equal hex    ${msg}    ${expected hex}

Server '${server}' should get '${msg}' from '${ip}':'${port}'
    Verify server gets from    ${ip}    ${port}    ${msg}    ${server}

'${connection}' on '${server}' should get '${msg}' from '${ip}':'${port}'
    Verify server gets from    ${ip}    ${port}    ${msg}    ${server}    ${connection}

Verify server gets from
    [Arguments]    ${ip}    ${port}    ${expected}    ${server}    ${connection}=
    ${msg}    ${from ip}    ${from port} =    Server receives binary from    name=${server}    connection=${connection}
    Should be equal    ${msg}    ${expected}
    Should be equal    ${from ip}    ${ip}
    Should be equal as integers    ${from port}    ${port}

Binary should equal hex
    [Arguments]    ${binary}    ${expected hex}
    ${binary in hex} =    bin to hex    ${binary}
    ${expected normalized} =    Normalize hex    ${expected hex}
    Should be equal    ${binary in hex}    ${expected normalized}

Normalize hex
    [Arguments]    ${hex}
    ${bin} =    Hex to bin    ${hex}
    ${normalized}    Bin to hex    ${bin}
    [Return]    ${normalized}

Client Sends hex
    [Arguments]    ${hex}    @{params}
    ${binary} =    Hex to bin    ${hex}
    Client Sends binary    ${binary}    @{params}

Teardown rammbock and increment port numbers
    Reset Rammbock
    Increment ports

Increment ports
    Increment port    SERVER PORT
    Increment port    SERVER PORT 2
    Increment port    CLIENT 1 PORT
    Increment port    CLIENT 2 PORT

Increment port
    [Arguments]    ${name}
    ${new} =    Evaluate    ${${name}}+2
    Set global variable    ${${name}}    ${new}

Should fail
    [Arguments]    @{args}
    run keyword and expect error    *    @{args}

Setup SCTP server and client
    [Arguments]    ${protocol}=
    Start SCTP Server    ${SERVER}    ${SERVER PORT}    name=ExampleServer    protocol=${protocol}
    Start SCTP client    name=ExampleClient    protocol=${protocol}
    connect    ${SERVER}    ${SERVER PORT}    name=ExampleClient
    Accept connection    name=ExampleServer

Close client '${client_original}' and switch to client '${alternate_client}'
   Close Client   name=${client_original}
   Switch Client   name=${alternate_client}

Close server '${original_server}' and switch to server '${alternate_server}'
   Close Server   name=${original_server}
   Switch Server   name=${alternate_server}
