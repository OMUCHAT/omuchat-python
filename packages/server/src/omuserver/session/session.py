from __future__ import annotations

import abc
from typing import TYPE_CHECKING
from omu.event_emitter import EventEmitter
from omu.network.packet import Packet
from omu.network.connection import PacketMapper
from omu.network.packet import PACKET_TYPES
from omu.network.packet.packet_types import ConnectPacket
from omu.network.packet.packet import PacketType
from omuserver.server.server import Server

if TYPE_CHECKING:
    from omu import App

    from omuserver.security import Permission


class SessionConnection(abc.ABC):
    @abc.abstractmethod
    async def send(self, packet: Packet, packet_mapper: PacketMapper) -> None: ...

    @abc.abstractmethod
    async def receive(self, packet_mapper: PacketMapper) -> Packet: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @property
    @abc.abstractmethod
    def closed(self) -> bool: ...


class Session:
    def __init__(
        self,
        packet_mapper: PacketMapper,
        app: App,
        permissions: Permission,
        connection: SessionConnection,
    ) -> None:
        self.serializer = packet_mapper
        self.app = app
        self.permissions = permissions
        self._connection = connection
        self._listeners = SessionListeners()

    @classmethod
    async def from_connection(
        cls,
        server: Server,
        packet_mapper: PacketMapper,
        connection: SessionConnection,
    ) -> Session:
        data = await connection.receive(packet_mapper)
        if data is None:
            raise RuntimeError("Socket closed before connect")
        if data.packet_type != PACKET_TYPES.Connect:
            raise RuntimeError(
                f"Expected {PACKET_TYPES.Connect.type} but got {data.packet_type}"
            )
        event: ConnectPacket = data.packet_data
        permissions, token = await server.security.authenticate_app(
            event.app, event.token
        )
        session = Session(packet_mapper, event.app, permissions, connection)
        await session.send(PACKET_TYPES.Token, token)
        return session

    @property
    def closed(self) -> bool:
        return self._connection.closed

    async def disconnect(self) -> None:
        await self._connection.close()

    async def listen(self) -> None:
        while not self._connection.closed:
            packet = await self._connection.receive(self.serializer)
            await self.listeners.packet.emit(self, packet)

    async def send[T](self, packet_type: PacketType[T], data: T) -> None:
        await self._connection.send(Packet(packet_type, data), self.serializer)

    @property
    def listeners(self) -> SessionListeners:
        return self._listeners


class SessionListeners:
    def __init__(self) -> None:
        self.packet = EventEmitter[Session, Packet]()
        self.disconnected = EventEmitter[Session]()
