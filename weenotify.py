"""
    WeeNotify

    A minimalist Weechat client using the Weechat relay protocol to
    retrieve notifications from a bouncer and display them locally.

    ---
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import argparse
import logging
import os
import socket
import subprocess
import sys

import packetRead

##################### CONFIGURATION ##########################
DEFAULT_CONF=(os.path.expanduser("~"))+'/.weenotifrc'
##################### END CONFIGURATION ######################

def expandPaths(path):
    return os.path.expanduser(path)

def safeCall(callArray):
    if(len(callArray) == 0):
        logging.error("Trying to call an unspecified external program.")
        return
    try:
        subprocess.call(callArray)
    except:
        logging.error("Could not execute "+callArray[0])

def gotHighlight(message, nick, conf):
    if not 'highlight-action' in conf or not conf['highlight-action']:
        return # No action defined: do nothing.

    highlightProcessCmd = expandPaths(conf['highlight-action'])
    safeCall([highlightProcessCmd, message, nick])

def gotPrivMsg(message, nick, conf):
    if not 'privmsg-action' in conf or not conf['privmsg-action']:
        return # No action defined: do nothing.

    privmsgProcessCmd = expandPaths(conf['privmsg-action'])
    safeCall([privmsgProcessCmd, message, nick])

def getResponse(sock, conf):
    READ_AT_ONCE=4096
    sockBytes = sock.recv(READ_AT_ONCE)
    if not sockBytes:
        return False # Connection closed
    
    if(len(sockBytes) < 5):
        logging.warning("Packet shorter than 5 bytes received. Ignoring.")
        return True

    if sockBytes[4] != 0:
        logging.warning("Received compressed message. Ignoring.")
        return True
    
    mLen,_ = packetRead.read_int(sockBytes)
    lastPacket = sockBytes
    while(len(sockBytes) < mLen):
        if(len(lastPacket) < READ_AT_ONCE):
            logging.warning("Incomplete packet received. Ignoring.")
            return True
        lastPacket = sock.recv(READ_AT_ONCE)
        sockBytes += lastPacket

    body = sockBytes[5:]
    ident,body = packetRead.read_str(body)
    if ident != "_buffer_line_added":
        return True
    logging.debug("Received buffer line.")

    dataTyp,body = packetRead.read_typ(body)
    if(dataTyp != "hda"):
        logging.warning("Unknown buffer_line_added format. Ignoring.")
        return True
    hdaData,body = packetRead.read_hda(body)

    for hda in hdaData:
        msg=hda['message']
        nick=""
        for tag in hda['tags_array']:
            if tag.startswith('nick_'):
                nick = tag[5:]

        if hda['highlight'] > 0:
            gotHighlight(msg, nick, conf)
            continue
        for tag in hda['tags_array']:
            if tag.startswith('notify_'):
                notifLevel = tag[7:]
                if notifLevel == 'private':
                    gotPrivMsg(msg, nick, conf)
                    break

    return True

CONFIG_ITEMS = [
    ('-c','config', 'Use the given configuration file.'),
    ('-s','server', 'Address of the Weechat relay.'),
    ('-p','port', 'Port of the Weechat relay.'),
    ('-a','highlight-action', 'Program to invoke when highlighted.'),
    ('','privmsg-action', 'Program to invoke when receiving a private message.'),
    ('','log-file', 'Log file. If omitted, the logs will be directly printed.')
    ]
    
def readConfig(path, createIfAbsent=False):
    outDict = dict()
    try:
        with open(path,'r') as handle:
            confOpts = [ x[1] for x in CONFIG_ITEMS ]
            for line in handle:
                if '#' in line:
                    line = line[:line.index('#')].strip()
                if(line == ''):
                    continue

                if '=' in line:
                    eqPos = line.index('=')
                    attr = line[:eqPos].strip()
                    arg = line[eqPos+1:].strip()
                    if(attr in confOpts): # Valid option
                        outDict[attr] = arg
                    else:
                        logging.warning('Unknown option: '+attr+'.')
            handle.close()
    except FileNotFoundError:
        if(createIfAbsent):
            with open(path, 'x') as touchHandle:
                pass
        else:
            logging.error("The configuration file '"+path+"' does not exists.")
    except IOError:
        logging.error("Could not read the configuration file at '"+path+"'.")
    return outDict


def readCommandLine():
    parser = argparse.ArgumentParser(description="WeeChat client to get "+\
        "highlight notifications from a distant bouncer.")
    parser.add_argument('-v', action='store_true')
    for (shortOpt,longOpt,helpMsg) in CONFIG_ITEMS:
        if shortOpt == '':
            parser.add_argument('--'+longOpt, dest=longOpt, help=helpMsg)
        else:
            parser.add_argument(shortOpt, '--'+longOpt, dest=longOpt,\
                help=helpMsg)
    parsed = parser.parse_args()
    
    parsedTable = vars(parsed)
    if(parsed.config != None):
        parsedTable.update(readConfig(parsed.config))

    return parsedTable


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',\
        datefmt='%I:%M:%S')

    conf = readCommandLine()
    if (not 'config' in conf) or (not conf['config']):
        conf.update(readConfig(DEFAULT_CONF,True))
    
    if('v' in conf and conf['v']): # Verbose
        logging.basicConfig(level = logging.DEBUG)
    if('log-file' in conf):
        logging.basicConfig(filename=conf['log-file'])

    if not 'server' in conf or not conf['server'] or\
            not 'port' in conf or not conf['port']:
        print("Missing argument(s): server address and/or port.")
        exit(1)

    sock = socket.socket()
    sock.connect((conf['server'], int(conf['port'])))
    sock.sendall(b'init compression=off\n')
    sock.sendall(b'sync *\n')
    while getResponse(sock,conf):
        pass

if __name__=='__main__':
    main()
