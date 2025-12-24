#!/usr/bin/python3
#
# this tester depends on PyCryptodom. install with:
#   pip install pycryptodome
#

import asyncio
import sys
import struct
import array
import signal
import ssl
import argparse
import binascii

from abc import ABC, abstractmethod
from collections import namedtuple
from Crypto.Cipher import DES
from Crypto.Util.Padding import pad, unpad
from typing import BinaryIO, Tuple, Union


#
# version check >= 3.7
#
if sys.version_info < (3, 7):
    raise AssertionError('python version must be 3.7 or above')

#
# default values.
#
DEFAULT_CA_CRT = "ca.crt"
DEFAULT_ORCH_CRT = "orch.crt"
DEFAULT_ORCH_KEY = "orch.key"
DEFAULT_CLIENT_CRT_FMT = "client-{0}-{1}.crt"
DEFAULT_CLIENT_KEY_FMT = "client-{0}-{1}.key"
DEFAULT_JSON_STR_FMT = '{"queueSize": 1024,"queueBytes": 16777216,"criteria": [{"field": "msgType","from": %d, "to": %d},{"field": "customerId", "from": %d, "to": %d},{"field": "clientId", "from": %d, "to": %d}]}\0'

#
# HexDumper: the hex dump class.
#
class HexDumper:
    def __init__(self, width: int=16, indent: str='') -> None:
        self._width = width
        self._indent = indent

    def _text_line(self, offset: int, data: bytes) -> str:
        line = '{0}{1:04x} -'.format(self._indent, offset)
        datastr = data.hex()
        for n in range(0, len(datastr), 2):
            line = line + ' ' + datastr[n : n + 2]
        n = len(datastr) // 2
        if self._width > n:
            line = line + (self._width - n) * '   '
        line = line + '  '
        for b in data:
            c = chr(b)
            line = line + (c if c.isprintable() else '.')
        return line

    def dump(self, data: bytes) -> None:
        if data is not None:
            cnt = len(data)
            if cnt > 0:
                for n in range(0, cnt, self._width):
                    print(self._text_line(n, data[n : n + self._width]))
            else:
                print(self._indent + '<EMPTY>')
        else:
            print(self._indent + '<NONE>')

    @staticmethod
    def hex(data: bytes, maxbytes: int=-1, sep: str=' ') -> str:
        if data is None:
            s = 'None'
        else:
            dlen = len(data)
            if maxbytes < 0 or maxbytes > dlen:
                maxbytes = dlen
            if maxbytes > 0:
                s = data[0 : 1].hex()
                for i in range(1, maxbytes):
                    s = s + sep + data[i : i + 1].hex()
                if maxbytes < dlen:
                    s = s + sep + '...'
            else:
                s = ''
        return s

# define a default hex dumper for debugging purposes.
dumper = HexDumper()


#
# constants.
#
DES_BLOCK_SIZE = 8
def des_roundup(n: int) -> int:
    return (n + DES_BLOCK_SIZE - 1) // DES_BLOCK_SIZE * DES_BLOCK_SIZE

#
# define LW_MSG_HEADER* structures.
#
LW_MSG_HEADER_V3 = namedtuple(
    'LW_MSG_HEADER_V3',
    'Version, Reserved, Checksum, CustomerId, ClientId, OrchId, Type, Len, TransactionId'
    )
LW_MSG_HEADER_V3.__new__.__defaults__ = (0,) * len(LW_MSG_HEADER_V3._fields)
LW_MSG_HEADER_V3_FMT = '!BBHLLHHLL'
LW_MSG_HEADER_V3_PACKER = struct.Struct(LW_MSG_HEADER_V3_FMT)
LW_MSG_HEADER_V3_LEN = LW_MSG_HEADER_V3_PACKER.size

LW_MSG_HEADER_V2 = namedtuple(
    'LW_MSG_HEADER_V2',
    'VerMagic, OrchId, CustomerId, ClientId, Type, Len, TransactionId'
    )
LW_MSG_HEADER_V2.__new__.__defaults__ = (0,) * len(LW_MSG_HEADER_V2._fields)
LW_MSG_HEADER_V2_FMT = '!HHLHHLL'
LW_MSG_HEADER_V2_PACKER = struct.Struct(LW_MSG_HEADER_V2_FMT)
LW_MSG_HEADER_V2_LEN = LW_MSG_HEADER_V2_PACKER.size
LW_MSG_HEADER_V2_LEN_ENC = des_roundup(LW_MSG_HEADER_V2_LEN)

MSGV3 = 0x30
MSGV2 = 202


def header_checksum(header: bytearray) -> None:
    header[2:4] = [0, 0]
    s = sum(array.array('H', header))
    s = (s & 0xffff) + (s >> 16)
    s = (s & 0xffff) + (s >> 16)
    s ^= 0xffff
    header[2:4] = [s & 0xff, s >> 8]


def header_checksum_set(header: bytearray, chksum: int) -> None:
    header[2:4] = [(chksum >> 8) & 0xff, chksum & 0xff]


def header_checksum_verify(header: bytearray) -> bool:
    s = sum(array.array('H', header))
    s = (s & 0xffff) + (s >> 16)
    s = (s & 0xffff) + (s >> 16)
    s ^= 0xffff
    return s == 0


#
# define our own exception.
#
class LWTestError(RuntimeError):
    pass

class BadFormatError(LWTestError):
    pass

class InvalidVersionError(LWTestError):
    pass


#
# the LW message classes
#
class LWMsg:
    def __init__(self, Version: int=MSGV3) -> None:
        self.Version = Version
        self.CustomerId = 0
        self.ClientId = 0
        self.OrchId = 0
        self.Type = 0
        self.TransactionId = 0
        self.ForceChksum = 0

    def serialize_v3(self, Len: int) -> bytes:
        hdr = LW_MSG_HEADER_V3(
            Version=self.Version,
            CustomerId=self.CustomerId,
            ClientId=self.ClientId,
            OrchId=self.OrchId,
            Type=self.Type,
            Len=Len,
            TransactionId=self.TransactionId
            )
        bs = bytearray(LW_MSG_HEADER_V3_PACKER.pack(*hdr))
        header_checksum(bs) if self.ForceChksum == 0 else header_checksum_set(bs, self.ForceChksum)
        return bytes(bs)

    def serialize_v2(self, Len: int) -> bytes:
        hdr = LW_MSG_HEADER_V2(
            VerMagic=self.Version,
            OrchId=self.OrchId,
            CustomerId=self.CustomerId,
            ClientId=self.ClientId,
            Type=self.Type,
            Len=Len,
            TransactionId=self.TransactionId
            )
        bs = LW_MSG_HEADER_V2_PACKER.pack(*hdr)
        return LWMsg.encrypt(bs)

    @staticmethod
    def parse_header_v3(hdata: bytes) -> LW_MSG_HEADER_V3:
        if len(hdata) == LW_MSG_HEADER_V3_LEN and header_checksum_verify(hdata):
            hdrv3 = LW_MSG_HEADER_V3(*LW_MSG_HEADER_V3_PACKER.unpack(hdata))
            if hdrv3.Version == MSGV3:
                return hdrv3
        raise BadFormatError()

    @staticmethod
    def parse_header_v2(enchdata: bytes) -> LW_MSG_HEADER_V2:
        if len(enchdata) == LW_MSG_HEADER_V2_LEN_ENC:
            hdata = LWMsg.decrypt(enchdata)
            hdrv2 = LW_MSG_HEADER_V2(*LW_MSG_HEADER_V2_PACKER.unpack(hdata))
            if hdrv2.VerMagic == MSGV2:
                return hdrv2
        raise BadFormatError()

    _key = b'appexnet'
    _iv = b'lightwan'

    @staticmethod
    def encrypt(plain: bytes) -> bytes:
        en = DES.new(key=LWMsg._key, mode=DES.MODE_CBC, iv=LWMsg._iv)
        return en.encrypt(pad(plain, en.block_size))

    @staticmethod
    def decrypt(cipher: bytes) -> bytes:
        de = DES.new(key=LWMsg._key, mode=DES.MODE_CBC, iv=LWMsg._iv)
        return unpad(de.decrypt(cipher), de.block_size)


class LWMsgClient(LWMsg):
    def __init__(
        self,
        CustomerId: int,
        ClientId: int,
        Version: int=MSGV3,
        OrchId: int=0,
        Type: int=0,
        TransactionId: int=0
        ) -> None:
        super().__init__(Version=Version)
        self.CustomerId = CustomerId
        self.ClientId = ClientId
        self.OrchId = OrchId
        self.Type = Type
        self.TransactionId = TransactionId
        self._data = None

    def payload_string(self, val: str) -> None:
        self._data = val.encode()

    def payload_seq(self, count: int, step: int=0, start: int=0) -> None:
        self._data = None if count == 0 else \
            bytes([((start + n * step) & 0xff) for n in range(count)])

    def serialize_v3(self, ForceLen: int=0) -> bytes:
        data = self._data if self._data is not None else b''
        datalen = len(data) if ForceLen == 0 else ForceLen
        hdr = super().serialize_v3(datalen)
        return hdr + data

    def serialize_v2(self, ForceLen: int=0) -> bytes:
        encdata = LWMsg.encrypt(self._data) if self._data is not None else b''
        datalen = len(encdata) if ForceLen == 0 else ForceLen
        hdr = super().serialize_v2(datalen)
        return hdr + encdata

    def serialize(self, ForceLen: int=0) -> bytes:
        if self.Version == MSGV3: return self.serialize_v3(ForceLen)
        if self.Version == MSGV2: return self.serialize_v2(ForceLen)
        raise InvalidVersionError()

    def __str__(self) -> str:
        dlen = 0 if self._data is None else len(self._data)
        s = type(self).__name__ + \
            ('' if self.Version == MSGV3 else '*' if self.Version == MSGV2 else '?') + \
            '({0}:{1} Orch:{2} Type:{3} Transaction:{4:08d} Len:{5})'.format(
                self.CustomerId,
                self.ClientId,
                self.OrchId,
                self.Type,
                self.TransactionId,
                dlen
                )
        if dlen != 0:
            s += ': ' + HexDumper.hex(self._data, 8)
        return s

    @staticmethod
    def deserialize(header: Union[LW_MSG_HEADER_V3, LW_MSG_HEADER_V2], data: bytes=None) -> LWMsg:
        ver = MSGV3 if isinstance(header, LW_MSG_HEADER_V3) else MSGV2
        # 'Len' field in v2 header is the cipher text size, may not equal to the plain text size.
        if ver == MSGV2 or \
            (data is None and header.Len == 0) or \
            (data is not None and header.Len == len(data)):
            msg = LWMsgClient(
                Version=ver,
                CustomerId=header.CustomerId,
                ClientId=header.ClientId,
                OrchId=header.OrchId,
                Type=header.Type,
                TransactionId=header.TransactionId
                )
            msg._data = data
            return msg
        else:
            raise BadFormatError()


class LWMsgSubscribe(LWMsg):
    def __init__(self, msgTypeStart: int, msgTypeEnd: int, customerIdStart: int, customerIdEnd: int, clientIdStart: int, clientIdEnd: int, OrchId: int=0) -> None:
        super().__init__()
        self.OrchId = OrchId
        self._msgTypestart = msgTypeStart
        self._msgTypeEnd = msgTypeEnd
        self._customerIdStart = customerIdStart
        self._customerIdEnd = customerIdEnd
        self._clientIdStart = clientIdStart
        self._clientIdEnd = clientIdEnd

    def serialize(self, ForceLen: int=0) -> bytes:
        json = DEFAULT_JSON_STR_FMT%(self._msgTypestart, self._msgTypeEnd, self._customerIdStart, self._customerIdEnd, self._clientIdStart, self._clientIdEnd);
        json_bytes = json.encode('UTF-8')
        #json_bytes += b'\0'
        hdr = super().serialize_v3(json.__len__() if ForceLen == 0 else ForceLen)
        return hdr + json_bytes
        
#
# used to launch openssl s_client to do the SSL connection. but there appears to be
# a bug in it in that when we push too quickly into its stdin pipe, s_client could
# fail and stop. since python SSL support is not too complicated to use, just switch
# to pure python tester here.
#
class LWStream:
    def __init__(self, host: str, ca: str, cert: str, key: str) -> None:
        try:
            addr, port = host.rsplit(':', 1)
            port = int(port)
        except ValueError:
            raise ValueError('invalid server address: \'{0}\''.format(host))
        if ca is not None and cert is not None and key is not None:
            sslctx = ssl.SSLContext()
            sslctx.verify_mode = ssl.CERT_REQUIRED
            sslctx.check_hostname = False
            sslctx.load_verify_locations(ca)
            sslctx.load_cert_chain(cert, key)
        else:
            sslctx = False
        self._host = addr
        self._port = port
        self._sslctx = sslctx

    # enter/exit to support 'with ... as ...' context management.
    async def __aenter__(self) -> None:
        self.reader, self.writer = await asyncio.open_connection(
            host=self._host,
            port=self._port,
            ssl=self._sslctx
            )
        return self

    async def __aexit__(self, *args) -> None:
        self.writer.close()
        await self.writer.wait_closed()


#
# TLS client socket runner abstract base class.
#
class LWStreamRunner(ABC):
    def __init__(self, host: str, ca: str, cert: str, key: str, legacy: bool) -> None:
        self._host = host
        self._ca = None if legacy else ca
        self._cert = None if legacy else cert
        self._key = None if legacy else key

    @abstractmethod
    async def _async_run(self, stream: LWStream) -> None:
        raise NotImplementedError()

    async def async_run(self) -> None:
        async with LWStream(host=self._host, ca=self._ca, cert=self._cert, key=self._key) as strm:
            await self._async_run(strm)

    @staticmethod
    async def async_readmsg_v3(stream: LWStream) -> Tuple[LWMsgClient, bytes]:
        hdata = await stream.reader.readexactly(LW_MSG_HEADER_V3_LEN)
        hdr = LWMsg.parse_header_v3(hdata)
        payload = await stream.reader.readexactly(hdr.Len) if hdr.Len != 0 else b''
        msg = LWMsgClient.deserialize(hdr, payload)
        data = hdata + payload
        return (msg, data)

    @staticmethod
    async def async_readmsg_v2(stream: LWStream) -> Tuple[LWMsgClient, bytes]:
        enchdata = await stream.reader.readexactly(LW_MSG_HEADER_V2_LEN_ENC)
        hdr = LWMsg.parse_header_v2(enchdata)
        if hdr.Len != 0:
            encpayload = await stream.reader.readexactly(hdr.Len)
            payload = LWMsg.decrypt(encpayload)
        else:
            encpayload = b''
            payload = None
        msg = LWMsgClient.deserialize(hdr, payload)
        encdata = enchdata + encpayload
        return (msg, encdata)


#
# orchestrator classes.
#
class LWOrch(LWStreamRunner):
    def __init__(
        self,
        id: int,
        host: str,
        ca: str=None,
        cert: str=None,
        key: str=None,
        legacy: bool=False
        ) -> None:
        super().__init__(
            host=host,
            ca=DEFAULT_CA_CRT if ca is None else ca,
            cert=DEFAULT_ORCH_CRT if cert is None else cert,
            key=DEFAULT_ORCH_KEY if key is None else key,
            legacy=legacy
            )
        self._id = id


#
# the echo orch replies back exactly what the client sent.
#
class LWOrchEcho(LWOrch):
    def __init__(
        self,
        id: int,
        msgTypeStart: int,
        msgTypeEnd: int,
        customerIdStart: int,
        customerIdEnd: int,
        clientIdStart: int,
        clientIdEnd: int,
        host: str,
        ca: str=None,
        cert: str=None,
        key: str=None,
        legacy: bool=False,
        show: bool=False
        ) -> None:
        super().__init__(id=id, host=host, ca=ca, cert=cert, key=key, legacy=legacy)
        self._msgTypestart = msgTypeStart
        self._msgTypeEnd = msgTypeEnd
        self._customerIdStart = customerIdStart
        self._customerIdEnd = customerIdEnd
        self._clientIdStart = clientIdStart
        self._clientIdEnd = clientIdEnd
        self._show = show

    async def _async_send(self, stream: LWStream, queue: asyncio.Queue) -> None:
        while True:
            data = await queue.get()
            if data is None: break
            stream.writer.write(data)
            await stream.writer.drain()
            queue.task_done()

    async def _async_recv(self, stream: LWStream, queue: asyncio.Queue) -> None:
        while True:
            msg, data = await LWStreamRunner.async_readmsg_v3(stream)
            if self._show: print(msg)
            try:
                # MUST keep consuming inbound data, discard message if we have to.
                queue.put_nowait(data)
            except asyncio.QueueFull:
                print('ERROR: queue full, message discarded!', file=sys.stderr)
        # put a None to signal quit.
        await queue.put(None)

    async def _async_run(self, stream: LWStream) -> None:
        # subscribe type range first.
        sub = LWMsgSubscribe(msgTypeStart=self._msgTypestart, msgTypeEnd=self._msgTypeEnd, customerIdStart=self._customerIdStart, customerIdEnd=self._customerIdEnd, clientIdStart=self._clientIdStart, clientIdEnd=self._clientIdEnd, OrchId=self._id)
        stream.writer.write(sub.serialize())
        await stream.writer.drain()
        queue = asyncio.Queue()
        await asyncio.gather(self._async_send(stream, queue), self._async_recv(stream, queue))


#
# client classes.
#
class LWClient(LWStreamRunner):
    def __init__(
        self,
        customerid: int,
        clientid: int,
        host: str,
        ca: str=None,
        cert: str=None,
        key: str=None,
        legacy: bool=False
        ) -> None:
        super().__init__(
            host=host,
            ca=DEFAULT_CA_CRT if ca is None else ca,
            cert=DEFAULT_CLIENT_CRT_FMT.format(customerid, clientid) if cert is None else cert,
            key=DEFAULT_CLIENT_KEY_FMT.format(customerid, clientid) if key is None else key,
            legacy=legacy
            )
        self._customerid = customerid
        self._clientid = clientid


#
# the crazy client keeps sending messages nonstop.
#
class LWClientCrazy(LWClient):
    def __init__(
        self,
        customerid: int,
        clientid: int,
        host: str,
        type: int,
        size: int,
        count: int,
        startseq: int=0,
        ca: str=None,
        cert: str=None,
        key: str=None,
        legacy: bool=False,
        gap: float=None,
        payload_file: str=None,
        payload_hex: str=None,
        payload_text: str=None
        ) -> None:
        super().__init__(
            customerid=customerid,
            clientid=clientid,
            host=host,
            ca=ca,
            cert=cert,
            key=key,
            legacy=legacy
            )
        self._type = type
        self._size = size
        self._count = count
        self._transaction = startseq
        self._gap = gap
        self._version = MSGV2 if legacy else MSGV3
        self._async_read = LWStreamRunner.async_readmsg_v2 \
            if legacy else LWStreamRunner.async_readmsg_v3
        self._payload_bytes = None

        # payload override (priority: file > hex > text)
        if payload_file:
            with open(payload_file, 'rb') as f:
                self._payload_bytes = f.read()
        elif payload_hex:
            hx = payload_hex.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            self._payload_bytes = binascii.unhexlify(hx)
        elif payload_text is not None:
            self._payload_bytes = payload_text.encode('utf-8')

    async def _async_send(self, stream: LWStream) -> None:
        cnt = 0
        while self._count < 0 or cnt < self._count:
            msg = LWMsgClient(
                Version=self._version,
                CustomerId=self._customerid,
                ClientId=self._clientid,
                Type=self._type,
                TransactionId=self._transaction
                )
            self._transaction += 1
            if self._payload_bytes is not None:
                msg._data = self._payload_bytes
            else:
                msg.payload_seq(count=self._size, step=self._transaction & 0xff)
            data = msg.serialize()
            stream.writer.write(data)
            # XXX: in cygwin python3.7 _async_recv() seems to be starved without this sleep(0) !!
            # it could be cause by the send buffer size, though.
            if self._gap is not None: await asyncio.sleep(self._gap)
            await stream.writer.drain()
            cnt += 1

    async def _async_recv(self, stream: LWStream) -> None:
        while True:
            msg, data = await self._async_read(stream)

    async def _async_run(self, stream: LWStream) -> None:
        if self._count != 0:
            await asyncio.gather(self._async_send(stream), self._async_recv(stream))


#
# executable main entry
#
if __name__ == "__main__":

    ap = argparse.ArgumentParser(description='CommServer TLS tester.')
    g0 = ap.add_argument_group('tester and connection')
    g0.add_argument('tester', choices=['client', 'orch'], metavar='{client | orch}',
        help='(REQUIRED) run tester as.')
    g0.add_argument('host', metavar='<server-addr>:<port>',
        help='(REQUIRED) the CommServer addr and port to connect.')
    g1 = ap.add_argument_group('client-specific options')
    g1.add_argument('--customer-id', type=int, metavar='<n>',
        help='(REQUIRED) the customer id.')
    g1.add_argument('--client-id', type=int, metavar='<n>',
        help='(REQUIRED) the client id.')
    g1.add_argument('--type', type=int, default=384, metavar='<n>',
        help='the message type (default: 384).')
    g1.add_argument('--len', type=int, default=16384, metavar='<n>',
        help='the message length (default: 16384).')
    g1.add_argument('--count', type=int, default=-1, metavar='<n>',
        help='the number of messages (default: infinite).')
    g1.add_argument('--gap', type=float, metavar='<secs>',
        help='the seconds to wait btw messages, e.g., 0.01')
    g1.add_argument('--payload-file', metavar='<path>',
        help='use exact payload bytes from file (overrides --len/payload_seq).')
    g1.add_argument('--payload-hex', metavar='<hex>',
        help='use exact payload bytes from hex string (overrides --len/payload_seq).')
    g1.add_argument('--payload-text', metavar='<text>',
        help='use exact payload text (utf-8) (overrides --len/payload_seq).')
    g2 = ap.add_argument_group('orch-specific options')
    g2.add_argument('--range', type=int, nargs=6, metavar='<n>',
        help='(REQUIRED) the range of msgType/customerId/clientId to subscribe for.')
    g2.add_argument('--orch-id', type=int, default=0, metavar='<n>',
        help='the orchestrator id.')
    g2.add_argument('--show', default=False, action='store_true',
        help='display messages received.')
    g3 = ap.add_argument_group('common options (optional)')
    g3.add_argument('--ca', metavar='<certfile>',
        help='the CA certificate to authenticate CommServer.')
    g3.add_argument('--cert', metavar='<certfile>',
        help='the certificate to authenticate self.')
    g3.add_argument('--key', metavar='<keyfile>',
        help='the private key to authenticate self.')
    g3.add_argument('--legacy', default=False, action='store_true',
        help='use legacy non-TLS connection.')
    args = ap.parse_args()

    if (args.tester == 'client' and (args.customer_id is None or args.client_id is None)) or \
       (args.tester == 'orch' and args.range is None):
        ap.error('missing required arguments for \'{0}\'.'.format(args.tester))

    # enable CTRL-C breaking program for Windows.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    if args.tester == 'client':
        payload_opts = [args.payload_file is not None, args.payload_hex is not None, args.payload_text is not None]
        if sum(payload_opts) > 1:
            ap.error('only one of --payload-file/--payload-hex/--payload-text can be specified.')
        runner = LWClientCrazy(
            customerid=args.customer_id,
            clientid=args.client_id,
            host=args.host,
            type=args.type,
            size=args.len,
            count=args.count,
            ca=args.ca,
            cert=args.cert,
            key=args.key,
            legacy=args.legacy,
            gap=args.gap,
            payload_file=args.payload_file,
            payload_hex=args.payload_hex,
            payload_text=args.payload_text
            )
    else:
        runner = LWOrchEcho(
            id=args.orch_id,
            msgTypeStart=args.range[0],
            msgTypeEnd=args.range[1],
            customerIdStart=args.range[2],
            customerIdEnd=args.range[3],
            clientIdStart=args.range[4],
            clientIdEnd=args.range[5],
            host=args.host,
            ca=args.ca,
            cert=args.cert,
            key=args.key,
            legacy=args.legacy,
            show=args.show
            )

    asyncio.run(runner.async_run())
