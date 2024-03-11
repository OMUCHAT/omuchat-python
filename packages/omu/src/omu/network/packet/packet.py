from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List

from omu.serializer import Serializer

if TYPE_CHECKING:
    from omu.app import App
    from omu.extension import ExtensionType
    from omu.serializer import Serializable


@dataclass
class PacketData:
    type: str
    data: bytes


@dataclass
class Packet[T]:
    packet_type: PacketType
    packet_data: T


class PacketType[T](abc.ABC):
    @property
    @abc.abstractmethod
    def type(self) -> str: ...

    @property
    @abc.abstractmethod
    def serializer(self) -> Serializable[T, bytes]: ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.type})"


type Jsonable = str | int | float | bool | None | Dict[str, Jsonable] | List[Jsonable]


class JsonPacketType[T](PacketType[T]):
    def __init__(
        self, owner: str, name: str, serializer: Serializable[T, Any] | None = None
    ):
        self._type = f"{owner}:{name}"
        self._serializer = (
            Serializer.noop()
            .pipe(serializer or Serializer.noop())
            .pipe(Serializer.json())
        )

    @property
    def type(self) -> str:
        return self._type

    @property
    def serializer(self) -> Serializable[T, bytes]:
        return self._serializer

    @classmethod
    def of(cls, app: App, name: str) -> JsonPacketType[T]:
        return cls(
            owner=app.key(),
            name=name,
            serializer=Serializer.noop(),
        )

    @classmethod
    def of_extension(
        cls,
        extension: ExtensionType,
        name: str,
        serializer: Serializable[T, Any] | None = None,
    ) -> JsonPacketType[T]:
        return cls(
            owner=extension.name,
            name=name,
            serializer=serializer,
        )


class SerializedPacketType[T](PacketType[T]):
    def __init__(self, owner: str, name: str, serializer: Serializable[T, bytes]):
        self._type = f"{owner}:{name}"
        self._serializer = serializer

    @property
    def type(self) -> str:
        return self._type

    @property
    def serializer(self) -> Serializable[T, bytes]:
        return self._serializer

    @classmethod
    def of(
        cls, app: App, name: str, serializer: Serializable[T, bytes]
    ) -> SerializedPacketType[T]:
        return cls(
            owner=app.key(),
            name=name,
            serializer=serializer,
        )

    @classmethod
    def of_extension(
        cls, extension: ExtensionType, name: str, serializer: Serializable[T, bytes]
    ) -> SerializedPacketType[T]:
        return cls(
            owner=extension.name,
            name=name,
            serializer=serializer,
        )
