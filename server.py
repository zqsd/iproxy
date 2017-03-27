import datetime
import signal
import sys
import SocketServer
import re
import select
import socket
import base64
import json
from urlparse import urlparse

if not hasattr(socket, 'IP_FREEBIND'):
    socket.IP_FREEBIND = 15


with open('./config.json') as f:
    config = json.load(f)

def ip_version(ip):
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
        return 4
    elif re.match(r"^([a-zA-Z0-9]{1,4}(?::[a-zA-Z0-9]{1,4}){0,7})$", ip):
        return 6
    else:
        return False

class MyRequestHandlerWithStreamRequestHandler(SocketServer.StreamRequestHandler):
    def parseHeaders(self):
        request_msg = self.rfile.readline(65536).strip()
        print('%s' % (request_msg))
        m = re.search(re.compile(ur'^(\w+) (.+) HTTP/((\d\.)*\d)$'), request_msg)
        if m is None:
            self.connection.send("HTTP/1.0 500 Invalid request\n\n")
            return False
        method, url, httpVersion = m.group(1, 2, 3)
        self.method = method
        self.url = url
        self.httpVersion = httpVersion

        o = urlparse(url)
        # o.scheme : '', 'http', 'https'
        if o.hostname is None:
            p = re.compile(ur'^(.+):(\d+)$')
            m = re.search(p, url)
            if m:
                self.host = m.group(1)
                self.port = int(m.group(2))
        else:
            self.host = o.hostname
            self.port = 80 if o.port is None else o.port

        self.request_headers = {}
        while True:
            msg = self.rfile.readline(65536).strip()
            if msg == '':
                break
            p = re.compile(ur'^(.+):(.+)$')
            m = re.search(p, msg)
            if m:
                self.request_headers[m.group(1)] = m.group(2).strip()
        return True


    def handle(self):
        if not self.parseHeaders():
            self.connection.close()
            return

        if not 'Proxy-Authorization' in self.request_headers:
            print('not authorized')
            self.connection.send('HTTP/1.0 407 Proxy Authentication Required\nProxy-Authenticate: Basic realm="hack"\n\nAuthentification required\n')
            self.connection.close()
            return

        p = re.compile(ur'^Basic (.+)$')
        m = re.search(p, self.request_headers['Proxy-Authorization'])
        auth = m.group(1).decode('base64')

        p = re.compile(r"^(.+):(.+?)$")
        m = re.search(p, auth)
        ip = m.group(1)
        self.ipv = ip_version(ip)
        password = m.group(2)
        if password != config['key']:
            print('Request with wrong auth %s:%s' % (ip, password))
            self.connection.send("HTTP/1.0 403 Invalid Proxy Key\n\n")
            self.connection.close()
            return
        self.ip = ip

        if self.method == 'CONNECT':
            self.handleConnect()
        elif self.method in ['GET', 'POST', 'PUT', 'OPTIONS', 'DELETE']:
            self.handleHttp()
        else:
            self.connection.send("HTTP/1.0 500 Unknown method\n\n")
            self.connection.close()
            return

        print('%s %s done\n' % (self.method, self.url))


    def handleHttp(self):
        # connect to server
        if self.ipv == 4:
            clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self.ipv == 6:
            clientSocket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        clientSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        clientSocket.setsockopt(socket.SOL_IP, socket.IP_FREEBIND, 1)
        clientSocket.bind((self.ip, 0))
        try:
            clientSocket.connect_ex((self.host, self.port))
        except Exception, ex:
            self.connection.send("HTTP/1.0 500 Remote server not found\n\nCouldn't connect to remote server %s at port %d\n" % (self.host, self.port))
            self.connection.close()
            return

        # send headers
        clientSocket.send('%s %s HTTP/1.0\n' % (self.method, self.url))
        for key, value in self.request_headers.iteritems():
            if key != 'Proxy-Authorization':
                clientSocket.send('%s: %s\n' % (key, value))
        clientSocket.send('\n')

        # send body if any
        if 'Content-Length' in self.request_headers:
            size = int(self.request_headers['Content-Length'])
            for i in range(0, size, 4096):
                data = self.rfile.read(min(4096, size - i))
                if not data:
                    break
                clientSocket.send(data)

        # receive response
        while True:
            data = clientSocket.recv(4096)
            if not data:
                break
            self.connection.send(data)
        self.connection.close() # TODO: manage keep alive


    def handleConnect(self):
        if self.ipv == 4:
            clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self.ipv == 6:
            clientSocket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        clientSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        clientSocket.setsockopt(socket.SOL_IP, socket.IP_FREEBIND, 1)
        clientSocket.bind((self.ip, 0))
        clientSocket.connect_ex((self.host, self.port))
        self.connection.send("HTTP/1.1 200 Connection established\r\n\r\n")

        read_list = [clientSocket, self.connection]
        run = True
        try:
            while run:
                rd, wd, ed = select.select(read_list, [], [])
                for s in rd:
                    if s is clientSocket:
                        data = clientSocket.recv(1024)
                        if not data:
                            run = False
                        else:
                            self.connection.send(data)
                    if s is self.connection:
                        data = self.connection.recv(1024)
                        if not data:
                            run = False
                        else:
                            clientSocket.send(data)
        except:
            print('fail for %s' % (self.url))
            pass

        self.connection.close()
        clientSocket.close()

def simple_tcp_server():
    server = SocketServer.ThreadingTCPServer(
        ("0.0.0.0", 4239),
        RequestHandlerClass=MyRequestHandlerWithStreamRequestHandler,
        bind_and_activate=False)
 
    server.allow_reuse_address = True
    server.server_bind()
    server.server_activate()

    print('started')
    server.serve_forever()

def signal_handler(signal, frame):
    print('You pressed Ctrl+C!')
    server.shutdown()
    server.server_close()
    #sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    simple_tcp_server()
