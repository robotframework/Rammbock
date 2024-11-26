*** Settings ***
Suite teardown    Run keywords   log handler messages    Reset Rammbock
Resource     async_resources.robot
Force tags   background



*** Variables ***
${BACKGROUND}=    ${False}
${PORT}=          44455
${PORT2}=         44488

*** Test Cases ***
Serve on background
    Run keyword if   ${BACKGROUND}     Serve
    ...              ELSE              Set test documentation    Skipped because not run on background.
Loop on background
    Run keyword if   ${BACKGROUND}     Serve on loop
    ...              ELSE              Set test documentation    Skipped because not run on background.
Send 10 messages every 0.5 seconds
    Run keyword if   ${BACKGROUND}     Send 10 messages every 0.5 seconds
    ...              ELSE              Set test documentation    Skipped because not run on background.
Send 10 messages every 0.5 seconds using given connection
    Run keyword if   ${BACKGROUND}     Send 10 messages every 0.5 seconds using given connection
    ...              ELSE              Set test documentation    Skipped because not run on background.
*** Keywords ***
Serve on loop
    Setup connection
    Send   sample
    Load Template   another
    Set server handler     my_handler.server_respond_to_another_max_100     header_filter=messageType   interval=0.01
    Load template   sample response
    Set server handler     my_handler.server_respond_to_sample_response_max_100     header_filter=messageType    interval=0.01
    Wait until keyword succeeds   30s  0.5s    Handler should have been called with '200' times with logging

Serve
    Setup connection
    Receive   another
    Send sample receive sample
    Send  another
    Sleep    10

Send 10 messages every 0.5 seconds
    Setup connection
    :FOR  ${i}  IN RANGE  10
    \   Send sample receive sample
    \   Sleep   0.5

Setup connection
    Define example protocol
    Define Templates
    Start TCP server    127.0.0.1    ${PORT}    name=ExampleServer    protocol=Example
    Touch    ${SIGNAL FILE}
    Accept connection

Send sample receive sample
    Send   sample
    Receive  sample response

Send   [arguments]    ${message}
    Load template    ${message}
    Server sends message

Receive   [arguments]    ${message}
    Load template    ${message}
    Server receives message     header_filter=messageType

Setup connection with two clients
    Define example protocol
    Define Templates
    Start TCP server    127.0.0.1    ${PORT2}    name=ExampleServer    protocol=Example
    Touch    ${SIGNAL FILE}
    Accept connection    alias=Connection1
    Accept connection    alias=Connection2

Send 10 messages every 0.5 seconds using given connection
    Setup connection with two clients
    load template  sample response
    server sends message   connection=Connection2
    :FOR  ${i}  IN RANGE  10
    \   Send sample and receive sample using connection1
    \   Sleep   0.01
    load template  sample response
    server sends message   connection=Connection1
    :FOR  ${i}  IN RANGE  10
    \   Send sample and receive sample using connection2
    \   Sleep   0.01
    load template  sample response
    server sends message   connection=Connection2
    :FOR  ${i}  IN RANGE  10
    \   Send sample and receive sample using connection2
    \   Sleep   0.01
    load template  sample response
    server sends message   connection=Connection1
    :FOR  ${i}  IN RANGE  10
    \   Send sample and receive sample using connection1
    \   Sleep   0.01
    load template  sample response
    server sends message   connection=Connection2

Send sample and receive sample using connection1
    Send message using given connection   sample    Connection1
    Receive message using given connection  sample response    Connection1

Send sample and receive sample using connection2
    Send message using given connection   sample    Connection2
    Receive message using given connection  sample response    Connection2

Send message using given connection  [arguments]    ${message}   ${connection}
    ${data}=    get message template    ${message}
    Server sends given message    ${data}    connection=${connection}

Receive message using given connection   [arguments]    ${message}   ${connection}
    ${data}=    get message template    ${message}
    Server receives given message    ${data}    alias=${connection}    header_filter=messageType
