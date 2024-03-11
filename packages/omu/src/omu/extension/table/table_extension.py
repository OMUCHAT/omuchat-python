from typing import (
    AsyncGenerator,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    TypedDict,
)

from omu.client import Client
from omu.extension import Extension, ExtensionType
from omu.extension.endpoint import JsonEndpointType, SerializeEndpointType
from omu.helper import AsyncCallback, Coro
from omu.identifier import Identifier
from omu.interface import Keyable
from omu.network.bytebuffer import ByteReader, ByteWriter
from omu.network.packet import JsonPacketType, SerializedPacketType
from omu.serializer import JsonSerializable, Serializable, Serializer

from .table import (
    Table,
    TableConfig,
    TableListener,
    TableType,
)

type ModelType[T: Keyable, D] = JsonSerializable[T, D]


class TableExtension(Extension):
    def __init__(self, client: Client):
        self._client = client
        self._tables: Dict[Identifier, Table] = {}
        client.network.register_packet(
            TableConfigSetEvent,
            TableListenEvent,
            TableProxyListenEvent,
            TableProxyEvent,
            TableItemAddEvent,
            TableItemUpdateEvent,
            TableItemRemoveEvent,
            TableItemClearEvent,
        )

    def create[T](
        self,
        identifier: Identifier,
        serializer: Serializable[T, bytes],
        key_function: Callable[[T], str],
    ) -> Table[T]:
        if self.has(identifier):
            raise ValueError(f"Table with identifier {identifier} already exists")
        table = TableImpl(
            self._client,
            identifier=identifier,
            serializer=serializer,
            key_function=key_function,
        )
        self._tables[identifier] = table
        return table

    def get[T](self, type: TableType[T]) -> Table[T]:
        if self.has(type.identifier):
            return self._tables[type.identifier]
        return self.create(type.identifier, type.serializer, type.key_func)

    def model[T: Keyable, D](
        self, identifier: Identifier, name: str, type: type[ModelType[T, D]]
    ) -> Table[T]:
        identifier = identifier / name
        if self.has(identifier):
            return self._tables[identifier]
        return self.create(
            identifier,
            Serializer.model(type).pipe(Serializer.json()),
            lambda item: item.key(),
        )

    def has(self, identifier: Identifier) -> bool:
        return identifier in self._tables


TableExtensionType = ExtensionType(
    "table", lambda client: TableExtension(client), lambda: []
)


class TableEventData(TypedDict):
    type: str


class TableItemsData(TableEventData):
    items: Dict[str, bytes]


class TableKeysData(TableEventData):
    keys: List[str]


class TableProxyData(TableItemsData):
    key: int


class TableItemsSerielizer(Serializable[TableItemsData, bytes]):
    def serialize(self, item: TableItemsData) -> bytes:
        writer = ByteWriter()
        writer.write_string(item["type"])
        writer.write_int(len(item["items"]))
        for key, value in item["items"].items():
            writer.write_string(key)
            writer.write_byte_array(value)
        return writer.finish()

    def deserialize(self, data: bytes) -> TableItemsData:
        with ByteReader(data) as reader:
            type = reader.read_string()
            item_count = reader.read_int()
            items = {}
            for _ in range(item_count):
                key = reader.read_string()
                value = reader.read_byte_array()
                items[key] = value
        return {"type": type, "items": items}


class TableProxySerielizer(Serializable[TableProxyData, bytes]):
    def serialize(self, item: TableProxyData) -> bytes:
        writer = ByteWriter()
        writer.write_string(item["type"])
        writer.write_int(item["key"])
        writer.write_int(len(item["items"]))
        for key, value in item["items"].items():
            writer.write_string(key)
            writer.write_byte_array(value)
        return writer.finish()

    def deserialize(self, data: bytes) -> TableProxyData:
        with ByteReader(data) as reader:
            type = reader.read_string()
            key = reader.read_int()
            item_count = reader.read_int()
            items = {}
            for _ in range(item_count):
                item_key = reader.read_string()
                value = reader.read_byte_array()
                items[item_key] = value
        return {"type": type, "key": key, "items": items}


class SetConfigReq(TypedDict):
    type: str
    config: TableConfig


TableConfigSetEvent = JsonPacketType[SetConfigReq].of_extension(
    TableExtensionType, "config_set"
)
TableListenEvent = JsonPacketType[str].of_extension(TableExtensionType, name="listen")
TableProxyListenEvent = JsonPacketType[str].of_extension(
    TableExtensionType, "proxy_listen"
)
TableProxyEvent = SerializedPacketType[TableProxyData].of_extension(
    TableExtensionType,
    "proxy",
    serializer=TableProxySerielizer(),
)
TableProxyEndpoint = SerializeEndpointType[TableProxyData, int].of_extension(
    TableExtensionType,
    "proxy",
    request_serializer=TableProxySerielizer(),
    response_serializer=Serializer.json(),
)


TableItemAddEvent = SerializedPacketType[TableItemsData].of_extension(
    TableExtensionType, "item_add", TableItemsSerielizer()
)
TableItemUpdateEvent = SerializedPacketType[TableItemsData].of_extension(
    TableExtensionType, "item_update", TableItemsSerielizer()
)
TableItemRemoveEvent = SerializedPacketType[TableItemsData].of_extension(
    TableExtensionType, "item_remove", TableItemsSerielizer()
)
TableItemClearEvent = JsonPacketType[TableEventData].of_extension(
    TableExtensionType, "item_clear"
)


TableItemGetEndpoint = SerializeEndpointType[
    TableKeysData, TableItemsData
].of_extension(
    TableExtensionType,
    "item_get",
    request_serializer=Serializer.json(),
    response_serializer=TableItemsSerielizer(),
)


class TableFetchReq(TypedDict):
    type: str
    before: int | None
    after: int | None
    cursor: str | None


TableItemFetchEndpoint = SerializeEndpointType[
    TableFetchReq, TableItemsData
].of_extension(
    TableExtensionType,
    "item_fetch",
    request_serializer=Serializer.json(),
    response_serializer=TableItemsSerielizer(),
)
TableItemSizeEndpoint = JsonEndpointType[TableEventData, int].of_extension(
    TableExtensionType, "item_size"
)


class TableImpl[T](Table[T]):
    def __init__(
        self,
        client: Client,
        identifier: Identifier,
        serializer: Serializable[T, bytes],
        key_function: Callable[[T], str],
    ):
        self._client = client
        self._identifier = identifier
        self._serializer = serializer
        self._key_function = key_function
        self._cache: Dict[str, T] = {}
        self._listeners: List[TableListener[T]] = []
        self._proxies: List[Coro[[T], T | None]] = []
        self._chunk_size = 100
        self._cache_size = 1000
        self._listening = False
        self._config: TableConfig | None = None
        self.key = identifier.key()

        client.network.add_packet_handler(TableProxyEvent, self._on_proxy)
        client.network.add_packet_handler(TableItemAddEvent, self._on_item_add)
        client.network.add_packet_handler(TableItemUpdateEvent, self._on_item_update)
        client.network.add_packet_handler(TableItemRemoveEvent, self._on_item_remove)
        client.network.add_packet_handler(TableItemClearEvent, self._on_item_clear)
        client.network.listeners.connected += self.on_connected

    @property
    def cache(self) -> Dict[str, T]:
        return self._cache

    async def get(self, key: str) -> T | None:
        if key in self._cache:
            return self._cache[key]
        res = await self._client.endpoints.call(
            TableItemGetEndpoint, TableKeysData(type=self.key, keys=[key])
        )
        items = self._parse_items(res["items"])
        self._cache.update(items)
        if key in items:
            return items[key]
        return None

    async def add(self, *items: T) -> None:
        data = self._serialize_items(items)
        await self._client.send(
            TableItemAddEvent, TableItemsData(type=self.key, items=data)
        )

    async def update(self, *items: T) -> None:
        data = self._serialize_items(items)
        await self._client.send(
            TableItemUpdateEvent, TableItemsData(type=self.key, items=data)
        )

    async def remove(self, *items: T) -> None:
        data = self._serialize_items(items)
        await self._client.send(
            TableItemRemoveEvent, TableItemsData(type=self.key, items=data)
        )

    async def clear(self) -> None:
        await self._client.send(TableItemClearEvent, TableEventData(type=self.key))

    async def fetch_items(
        self,
        before: int | None = None,
        after: int | None = None,
        cursor: str | None = None,
    ) -> Dict[str, T]:
        items_response = await self._client.endpoints.call(
            TableItemFetchEndpoint,
            TableFetchReq(type=self.key, before=before, after=after, cursor=cursor),
        )
        items = self._parse_items(items_response["items"])
        self._cache.update(items)
        for listener in self._listeners:
            await listener.on_cache_update(self._cache)
        return items

    async def iterate(
        self,
        backward: bool = False,
        cursor: str | None = None,
    ) -> AsyncGenerator[T, None]:
        items = await self.fetch_items(
            before=self._chunk_size if backward else None,
            after=self._chunk_size if not backward else None,
            cursor=cursor,
        )
        for item in items.values():
            yield item
        while len(items) > 0:
            cursor = next(iter(items.keys()))
            items = await self.fetch_items(
                before=self._chunk_size if backward else None,
                after=self._chunk_size if not backward else None,
                cursor=cursor,
            )
            for item in items.values():
                yield item
            items.pop(cursor, None)

    async def size(self) -> int:
        res = await self._client.endpoints.call(
            TableItemSizeEndpoint, TableEventData(type=self.key)
        )
        return res

    def listen(
        self, callback: AsyncCallback[Mapping[str, T]] | None = None
    ) -> Callable[[], None]:
        self._listening = True
        listener = TableListener(on_cache_update=callback)
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def proxy(self, callback: Coro[[T], T | None]) -> Callable[[], None]:
        self._proxies.append(callback)
        return lambda: self._proxies.remove(callback)

    def set_config(self, config: TableConfig) -> None:
        self._config = config

    async def on_connected(self) -> None:
        if self._config is not None:
            await self._client.send(
                TableConfigSetEvent, SetConfigReq(type=self.key, config=self._config)
            )
        if self._listening:
            await self._client.send(TableListenEvent, self.key)
        if len(self._proxies) > 0:
            await self._client.send(TableProxyListenEvent, self.key)

    async def _on_proxy(self, event: TableProxyData) -> None:
        if event["type"] != self.key:
            return
        items = self._parse_items(event["items"])
        for proxy in self._proxies:
            for key, item in list(items.items()):
                updated_item = await proxy(item)
                if updated_item is None:
                    del items[key]
                else:
                    items[key] = updated_item
        serialized_items = self._serialize_items(items.values())
        await self._client.endpoints.call(
            TableProxyEndpoint,
            TableProxyData(
                type=self.key,
                key=event["key"],
                items=serialized_items,
            ),
        )

    async def _on_item_add(self, event: TableItemsData) -> None:
        if event["type"] != self.key:
            return
        items = self._parse_items(event["items"])
        self._cache.update(items)
        for listener in self._listeners:
            await listener.on_add(items)
            await listener.on_cache_update(self._cache)

    async def _on_item_update(self, event: TableItemsData) -> None:
        if event["type"] != self.key:
            return
        items = self._parse_items(event["items"])
        self._cache.update(items)
        for listener in self._listeners:
            await listener.on_update(items)
            await listener.on_cache_update(self._cache)

    async def _on_item_remove(self, event: TableItemsData) -> None:
        if event["type"] != self.key:
            return
        items = self._parse_items(event["items"])
        for key in items.keys():
            if key not in self._cache:
                continue
            del self._cache[key]
        for listener in self._listeners:
            await listener.on_remove(items)
            await listener.on_cache_update(self._cache)

    async def _on_item_clear(self, event: TableEventData) -> None:
        if event["type"] != self.key:
            return
        self._cache.clear()
        for listener in self._listeners:
            await listener.on_clear()
            await listener.on_cache_update(self._cache)

    def _parse_items(self, items: Dict[str, bytes]) -> Dict[str, T]:
        parsed_items: Dict[str, T] = {}
        for key, item_bytes in items.items():
            item = self._serializer.deserialize(item_bytes)
            if item is None:
                raise ValueError(f"Failed to deserialize item with key: {key}")
            parsed_items[key] = item
        return parsed_items

    def _serialize_items(self, items: Iterable[T]) -> Dict[str, bytes]:
        serialized_items: Dict[str, bytes] = {}
        for item in items:
            key = self._key_function(item)
            serialized_items[key] = self._serializer.serialize(item)
        return serialized_items

    def set_cache_size(self, size: int) -> None:
        self._cache_size = size

    def add_listener(self, listener: TableListener[T]) -> None:
        self._listeners.append(listener)
        self._listening = True

    def remove_listener(self, listener: TableListener[T]) -> None:
        self._listeners.remove(listener)
