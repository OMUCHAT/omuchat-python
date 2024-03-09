from __future__ import annotations

import abc
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omu.app import App
    from omu.extension import ExtensionRegistry
    from omu.extension.endpoint import EndpointExtension
    from omu.extension.message import MessageExtension
    from omu.extension.registry import RegistryExtension
    from omu.extension.server import ServerExtension
    from omu.extension.table import TableExtension
    from omu.network import Connection
    from omu.network.packet import PacketDispatcher, PacketType


class ClientListener:
    async def on_initialized(self) -> None: ...

    async def on_started(self) -> None: ...

    async def on_stopped(self) -> None: ...


class Client(abc.ABC):
    @property
    @abc.abstractmethod
    def app(self) -> App: ...

    @property
    @abc.abstractmethod
    def loop(self) -> asyncio.AbstractEventLoop: ...

    @property
    @abc.abstractmethod
    def connection(self) -> Connection: ...

    @property
    @abc.abstractmethod
    def events(self) -> PacketDispatcher: ...

    @property
    @abc.abstractmethod
    def extensions(self) -> ExtensionRegistry: ...

    @property
    @abc.abstractmethod
    def endpoints(self) -> EndpointExtension: ...

    @property
    @abc.abstractmethod
    def tables(self) -> TableExtension: ...

    @property
    @abc.abstractmethod
    def registry(self) -> RegistryExtension: ...

    @property
    @abc.abstractmethod
    def message(self) -> MessageExtension: ...

    @property
    @abc.abstractmethod
    def server(self) -> ServerExtension: ...

    @property
    @abc.abstractmethod
    def running(self) -> bool: ...

    @abc.abstractmethod
    def run(self) -> None: ...

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...

    @abc.abstractmethod
    async def send[T](self, type: PacketType[T], data: T) -> None: ...

    @abc.abstractmethod
    def add_listener[T: ClientListener](self, listener: T) -> T: ...

    @abc.abstractmethod
    def remove_listener[T: ClientListener](self, listener: T) -> T: ...
