from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Callable

from omu.helper import Coro
from omu.identifier import Identifier
from omu.network.bytebuffer import ByteReader, ByteWriter, Flags
from omu.serializer import Serializable, Serializer


@dataclass(frozen=True)
class SignalPermissions:
    all: Identifier | None = None
    listen: Identifier | None = None
    send: Identifier | None = None

    def serialize(self, writer: ByteWriter) -> None:
        flags = Flags(length=3)
        flags.set(0, self.all is not None)
        flags.set(1, self.listen is not None)
        flags.set(2, self.send is not None)
        writer.write_byte(flags.value)
        if self.all is not None:
            writer.write_string(self.all.key())
        if self.listen is not None:
            writer.write_string(self.listen.key())
        if self.send is not None:
            writer.write_string(self.send.key())

    @classmethod
    def deserialize(cls, reader: ByteReader) -> SignalPermissions:
        flags = Flags(reader.read_byte())
        all = flags.if_set(0, lambda: Identifier.from_key(reader.read_string()))
        listen = flags.if_set(1, lambda: Identifier.from_key(reader.read_string()))
        send = flags.if_set(2, lambda: Identifier.from_key(reader.read_string()))
        return SignalPermissions(all=all, listen=listen, send=send)


@dataclass(frozen=True)
class SignalType[T]:
    identifier: Identifier
    serializer: Serializable[T, bytes]
    permissions: SignalPermissions = SignalPermissions()

    @classmethod
    def create_json(
        cls,
        identifier: Identifier,
        name: str,
        permissions: SignalPermissions | None = None,
    ):
        return cls(
            identifier=identifier / name,
            serializer=Serializer.json(),
            permissions=permissions or SignalPermissions(),
        )

    @classmethod
    def create_serialized(
        cls,
        identifier: Identifier,
        name: str,
        serializer: Serializable[T, bytes],
        permissions: SignalPermissions | None = None,
    ):
        return cls(
            identifier=identifier / name,
            serializer=serializer,
            permissions=permissions or SignalPermissions(),
        )


class Signal[T](abc.ABC):
    @abc.abstractmethod
    def listen(self, listener: Coro[[T], None]) -> Callable[[], None]: ...

    @abc.abstractmethod
    async def broadcast(self, body: T) -> None: ...
