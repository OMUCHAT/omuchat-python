from __future__ import annotations

import aiohttp
from aiohttp import web

from omu.client.client import Client
from omu.network import Address
from omu.network.bytebuffer import ByteReader, ByteWriter
from omu.network.connection import Connection, PacketSerializer
from omu.network.packet import PacketData
from omu.network.packet.packet import Packet


class WebsocketsConnection(Connection):
    def __init__(self, client: Client, address: Address):
        self._client = client
        self._address = address
        self._connected = False
        self._socket: aiohttp.ClientWebSocketResponse | None = None
        self._session = aiohttp.ClientSession()

    @property
    def _ws_endpoint(self) -> str:
        protocol = "wss" if self._address.secure else "ws"
        return f"{protocol}://{self._address.host}:{self._address.port}/ws"

    async def connect(self) -> None:
        if self._socket and not self._socket.closed:
            raise RuntimeError("Already connected")
        self._socket = await self._session.ws_connect(self._ws_endpoint)
        self._connected = True

    async def receive(self, serializer: PacketSerializer) -> Packet:
        if not self._socket or self._socket.closed:
            raise RuntimeError("Not connected")
        msg = await self._socket.receive()
        if msg.type in {
            web.WSMsgType.CLOSE,
            web.WSMsgType.CLOSED,
            web.WSMsgType.CLOSING,
            web.WSMsgType.ERROR,
        }:
            raise RuntimeError(f"Socket {msg.type.name.lower()}")
        if msg.data is None:
            raise RuntimeError("Received empty message")
        if msg.type == web.WSMsgType.TEXT:
            raise RuntimeError("Received text message")
        elif msg.type == web.WSMsgType.BINARY:
            with ByteReader(msg.data) as reader:
                event_type = reader.read_string()
                event_data = reader.read_byte_array()
            packet_data = PacketData(event_type, event_data)
            return serializer.deserialize(packet_data)
        else:
            raise RuntimeError(f"Unknown message type {msg.type}")

    @property
    def closed(self) -> bool:
        return not self._socket or self._socket.closed

    async def close(self) -> None:
        if not self._socket or self._socket.closed:
            return
        if self._socket:
            try:
                await self._socket.close()
            except AttributeError:
                pass
        self._socket = None
        self._connected = False

    async def send(self, packet: Packet, serializer: PacketSerializer) -> None:
        if not self._socket or self._socket.closed or not self._connected:
            raise RuntimeError("Not connected")
        packet_data = serializer.serialize(packet)
        writer = ByteWriter()
        writer.write_string(packet_data.type)
        writer.write_byte_array(packet_data.data)
        await self._socket.send_bytes(writer.finish())
