*** Settings ***
Library     Process
Library     Collections
Resource    async_resources.robot
Test Setup     Setup protocol, nodes, and define templates
Test teardown    Teardown rammbock and increment port numbers
Force tags    regression
Test timeout    60s

*** Test cases ***
Register an auto reply
    Load Template   sample
    Reset received messages
    Set client handler  my_handler.handle_sample     header_filter=messageType
    Server sends sample message
    Server sends another message
    Client receives another message
    Handler should have been called with '1' sample messages
    Message cache should be empty
Respond to an asynchronous message
    Load Template   sample
    Reset received messages
    Set client handler  my_handler.respond_to_sample    header_filter=messageType
    Server sends sample message
    Server sends another message
    Client receives another message
    Server should receive response to sample
Multiple clients
    [Setup]   Setup protocol, server, two clients, and define templates
    Load Template   sample
    Reset received messages
    Set client handler  my_handler.respond_to_sample    name=ExampleClient2    header_filter=messageType
    Server sends sample message   Connection1
    Server sends another message  Connection1
    Client receives another message    name=ExampleClient1
    Sample message should be in cache   name=ExampleClient1
    Server sends sample message   Connection2
    Server sends another message  Connection2
    Client receives another message    name=ExampleClient2
    Server should receive response to sample
Asynchronous messages on background
    [Setup]    Setup protocol, one client, background server, and define templates      Serve on background
    Load Template   sample
    Reset received messages
    Set client handler  my_handler.respond_to_sample     header_filter=messageType
    Load template    another
    client sends message
    Wait until keyword succeeds     2s  0.1s  Handler should have been called with '1' sample messages
    client receives message    header_filter=messageType
    [Teardown]     Get background results and reset
100 asynchronous messages on background
    [Documentation]     This test is rather slow, so run with --exclude slow to skip this.
    [Tags]     slow
    [Setup]    Setup protocol, one client, background server, and define templates      Loop on background
    Load Template   sample
    Reset received messages
    Set client handler  my_handler.respond_to_sample     header_filter=messageType     interval=0.01
    Repeat keyword   100    Send receive another
    Wait until keyword succeeds     20s  0.5s  Handler should have been called with '101' sample messages
    [Teardown]     Get background results and reset
Register an auto reply to work on background
    Load Template   sample
    Reset received messages
    Set client handler  my_handler.handle_sample    header_filter=messageType
    Server sends sample message
    Wait until keyword succeeds   2s  0.1s   Handler should have been called with '1' sample messages
    Message cache should be empty
Timeout at background
    [timeout]    4s
    [Setup]    Setup protocol, one client, background server, and define templates  Send 10 messages every 0.5 seconds
    Load Template   sample
    Reset received messages
    Set client handler  my_handler.respond_to_sample    header_filter=messageType
    Load Template   another
    Run keyword and expect error  Timeout*  Client receives message   header_filter=messageType   timeout=0.6
    [Teardown]     Get background results and reset
Two clients handling same message asynchronously without any effect from main message 
    [Documentation]     This test is rather slow will handle multiple messages related to two clients at a time, so run with --exclude slow to skip this.
    [Setup]    Setup protocol, two clients, background server, and define templates  Send 10 messages every 0.5 seconds using given connection
    Load Template   sample
    Reset received messages
    Set client handler  my_handler.respond_to_sample    name=client1    header_filter=messageType
    Set client handler  my_handler.respond_to_sample    name=client2    header_filter=messageType
    Load Template   sample response
    Client receives message   name=client2    header_filter=messageType   timeout=10
    Client receives message   name=client1    header_filter=messageType   timeout=10
    Client receives message   name=client2    header_filter=messageType   timeout=10
    Client receives message   name=client1    header_filter=messageType   timeout=10
    Client receives message   name=client2    header_filter=messageType   timeout=10
    sleep   2
    [Teardown]     Get background results and reset
Get message using get message template keyword and perform send and receive operations with validation
    [Setup]    Setup protocol, server, two clients, and define templates
    ${message_and_fields}=    Get Message Template   sample
    client sends given message    ${message_and_fields}    name=ExampleClient1
    client sends given message    ${message_and_fields}    name=ExampleClient1
    ${message_and_fields}=    Get Message Template   sample response
    Run Keyword And Expect Error    timeout: timed out    server receives given message    ${message_and_fields}    alias=Connection1    header_filter=messageType    timeout=0.2
    ${message_and_fields}=    Get Message Template   sample
    Set To Dictionary    ${message_and_fields[1]}    foo    12
    Run Keyword And Expect Error    Value of field foo does not match 0x0001!=12    server receives given message    ${message_and_fields}    alias=Connection1    header_filter=messageType
    ${message_and_fields}=    Get Message Template   sample
    server receives given message    ${message_and_fields}    alias=Connection1    header_filter=messageType
    ${message_and_fields}=    Get Message Template   sample response
    server sends given message    ${message_and_fields}    connection=Connection2
    server sends given message    ${message_and_fields}    connection=Connection2
    ${message_and_fields}=    Get Message Template   sample
    Run Keyword And Expect Error    timeout: timed out    client receives given message    ${message_and_fields}    name=ExampleClient2    header_filter=messageType    timeout=0.2
    ${message_and_fields}=    Get Message Template   sample response
    Set To Dictionary    ${message_and_fields[1]}    bar    12
    Run Keyword And Expect Error    Value of field bar does not match 0x0064!=12    client receives given message    ${message_and_fields}    name=ExampleClient2    header_filter=messageType
    ${message_and_fields}=    Get Message Template   sample response
    client receives given message    ${message_and_fields}    name=ExampleClient2    header_filter=messageType


*** Variables ***
${SOURCEDIR}=   ${CURDIR}${/}..${/}..${/}src
${BACKGROUND FILE}=    ${CURDIR}${/}background_server.robot
${PORT2}=    44488
*** Keywords ***


Send receive another
    Load template    another
    client sends message
    client receives message     header_filter=messageType
Get background results and reset
    ${res}=    Terminate Process
    Log    STDOUT:\n${res.stdout}\nSTDERR:\n${res.stderr}
    log handler messages
    Teardown rammbock and increment port numbers
Setup protocol, one client, background server, and define templates
    [Arguments]    ${background operation}
    Define Example protocol
    Define templates
    Remove File     ${SIGNAL FILE}
    Start background process    ${background operation}
    Start TCP client    127.0.0.1   45555   name=client   protocol=Example
    Wait Until Created    ${SIGNAL FILE}     timeout=10 seconds
    sleep   0.2s     # Just to make sure we dont get inbetween keywordcalls
    Connect     127.0.0.1   ${SERVER PORT}

Setup protocol, two clients, background server, and define templates
    [Arguments]    ${background operation}
    Define Example protocol
    Define templates
    Remove File     ${SIGNAL FILE}
    Start background process    ${background operation}
    sleep  0.1
    Start TCP client    127.0.0.1   ${CLIENT 1 PORT}   name=client1   protocol=Example
    Wait Until Created    ${SIGNAL FILE}     timeout=10 seconds
    Connect     127.0.0.1   ${PORT2}
    Start TCP client    127.0.0.1   ${CLIENT 2 PORT}   name=client2   protocol=Example
    Connect     127.0.0.1   ${PORT2}
        
Setup protocol, server, two clients, and define templates
    Define protocol, start tcp server and two clients    protocol=Example
    Define templates
Setup protocol, nodes, and define templates
    Setup protocol, TCP server, and client
    Define Templates
Server sends sample message    [Arguments]    ${connection}=
    Load Template   sample
    Server sends message    connection=${connection}
Server sends another message   [Arguments]    ${connection}=
    Load Template   another
    Server sends message    connection=${connection}
Client receives another message
    [Arguments]     ${name}=
    Load Template   another
    Client receives message   name=${name}  header_filter=messageType
Server should receive response to sample
    Load Template   sample response
    Server receives message     timeout=1
Message cache should be empty
    ${my_count}=     Get Client Unread Messages Count
    Should be Equal as integers     ${my_count}     0
Sample message should be in cache
    [Arguments]     ${name}=
    ${my_count}=     Get Client Unread Messages Count   ${name}
    Should be Equal as integers     ${my_count}     1
Start background process
    [Arguments]     ${name}
    ${process}=    Start process  python  -m  robot.run  --test  ${name}  --loglevel   DEBUG
    ...            --variable  BACKGROUND:True   --variable  PORT:${SERVER PORT}  --pythonpath  ${SOURCEDIR}
    ...            --outputdir  ${TEMPDIR}  ${BACKGROUND FILE}
    [Return]    ${process}