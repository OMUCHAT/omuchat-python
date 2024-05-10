from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import (
    AsyncGenerator,
    Callable,
    Dict,
    Mapping,
    NotRequired,
    TypedDict,
)

from omu.event_emitter import EventEmitter, Unlisten
from omu.helper import AsyncCallback, Coro
from omu.identifier import Identifier
from omu.interface import Keyable
from omu.serializer import JsonSerializable, Serializable, Serializer


class TableConfig(TypedDict):
    cache_size: NotRequired[int]


class Table[T](abc.ABC):
    @property
    @abc.abstractmethod
    def cache(self) -> Mapping[str, T]: ...

    @abc.abstractmethod
    def set_cache_size(self, size: int) -> None: ...

    @abc.abstractmethod
    async def get(self, key: str) -> T | None: ...

    @abc.abstractmethod
    async def get_many(self, *keys: str) -> Dict[str, T]: ...

    @abc.abstractmethod
    async def add(self, *items: T) -> None: ...

    @abc.abstractmethod
    async def update(self, *items: T) -> None: ...

    @abc.abstractmethod
    async def remove(self, *items: T) -> None: ...

    @abc.abstractmethod
    async def clear(self) -> None: ...

    @abc.abstractmethod
    async def fetch_items(
        self,
        before: int | None = None,
        after: int | None = None,
        cursor: str | None = None,
    ) -> Mapping[str, T]: ...

    @abc.abstractmethod
    async def fetch_all(self) -> Dict[str, T]: ...

    @abc.abstractmethod
    async def iterate(
        self,
        backward: bool = False,
        cursor: str | None = None,
    ) -> AsyncGenerator[T, None]: ...

    @abc.abstractmethod
    async def size(self) -> int: ...

    @abc.abstractmethod
    def listen(
        self, listener: AsyncCallback[Mapping[str, T]] | None = None
    ) -> Unlisten: ...

    @abc.abstractmethod
    def proxy(self, callback: Coro[[T], T | None]) -> Unlisten: ...

    @abc.abstractmethod
    def set_config(self, config: TableConfig) -> None: ...

    @property
    @abc.abstractmethod
    def event(self) -> TableEvents[T]: ...


class TableEvents[T]:
    def __init__(
        self,
        table: Table[T],
    ) -> None:
        self.unlisten: Unlisten | None = None

        def listen():
            self.unlisten = table.listen()

        def unlisten():
            if self.unlisten:
                self.unlisten()

        self.add: EventEmitter[Mapping[str, T]] = EventEmitter(
            on_subscribe=listen, on_empty=unlisten
        )
        self.update: EventEmitter[Mapping[str, T]] = EventEmitter(
            on_subscribe=listen, on_empty=unlisten
        )
        self.remove: EventEmitter[Mapping[str, T]] = EventEmitter(
            on_subscribe=listen, on_empty=unlisten
        )
        self.clear: EventEmitter[[]] = EventEmitter(
            on_subscribe=listen, on_empty=unlisten
        )
        self.cache_update: EventEmitter[Mapping[str, T]] = EventEmitter(
            on_subscribe=listen, on_empty=unlisten
        )


type ModelEntry[T: Keyable, D] = JsonSerializable[T, D]


@dataclass(frozen=True)
class TablePermissions:
    all: Identifier | None = None
    read: Identifier | None = None
    write: Identifier | None = None
    remove: Identifier | None = None
    proxy: Identifier | None = None


@dataclass(frozen=True)
class TableType[T]:
    id: Identifier
    serializer: Serializable[T, bytes]
    key_function: Callable[[T], str]
    permissions: TablePermissions | None = None

    @classmethod
    def create_model[_T: Keyable, _D](
        cls,
        identifier: Identifier,
        name: str,
        model_type: type[ModelEntry[_T, _D]],
        permissions: TablePermissions | None = None,
    ) -> TableType[_T]:
        return TableType(
            id=identifier / name,
            serializer=Serializer.model(model_type).to_json(),
            key_function=lambda item: item.key(),
            permissions=permissions,
        )

    @classmethod
    def create_serialized[_T: Keyable](
        cls,
        identifier: Identifier,
        name: str,
        serializer: Serializable[_T, bytes],
        permissions: TablePermissions | None = None,
    ) -> TableType[_T]:
        return TableType(
            id=identifier / name,
            serializer=serializer,
            key_function=lambda item: item.key(),
            permissions=permissions,
        )
