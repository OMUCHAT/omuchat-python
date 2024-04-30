from __future__ import annotations

import json
import sqlite3
import time
from typing import TYPE_CHECKING, Dict, List

from omu.extension.dashboard.dashboard import PermissionRequest
from omu.extension.permission import PermissionType
from omu.extension.permission.permission_extension import (
    PERMISSION_GRANT_PACKET,
    PERMISSION_REGISTER_PACKET,
    PERMISSION_REQUEST_ENDPOINT,
    PERMISSION_REQUIRE_PACKET,
)
from omu.identifier import Identifier
from omu.network.packet.packet_types import DisconnectType

from omuserver.session import Session

if TYPE_CHECKING:
    from omuserver.server import Server


class PermissionExtension:
    def __init__(self, server: Server) -> None:
        server.packet_dispatcher.register(
            PERMISSION_REGISTER_PACKET,
            PERMISSION_REQUIRE_PACKET,
            PERMISSION_GRANT_PACKET,
        )
        server.packet_dispatcher.add_packet_handler(
            PERMISSION_REGISTER_PACKET,
            self.handle_register,
        )
        server.packet_dispatcher.add_packet_handler(
            PERMISSION_REQUIRE_PACKET,
            self.handle_require,
        )
        server.endpoints.bind_endpoint(
            PERMISSION_REQUEST_ENDPOINT,
            self.handle_request,
        )
        self.server = server
        self.request_id = 0
        self.permission_registry: Dict[Identifier, PermissionType] = {}
        self.session_permissions: Dict[str, List[Identifier]] = {}
        permission_dir = server.directories.get("permissions")
        permission_dir.mkdir(parents=True, exist_ok=True)
        self.permission_db = sqlite3.connect(permission_dir / "permissions.db")
        self.permission_db.execute(
            """
            CREATE TABLE IF NOT EXISTS permissions (
                id TEXT PRIMARY KEY,
                value BLOB
            )
            """
        )
        self.permission_db.commit()
        self.load_permissions()

    def register(self, permission: PermissionType) -> None:
        if permission.id in self.permission_registry:
            raise ValueError(f"Permission {permission.id} already registered")
        self.permission_registry[permission.id] = permission

    async def handle_register(
        self, session: Session, permissions: List[PermissionType]
    ) -> None:
        for permission in permissions:
            if not permission.id.is_subpart_of(session.app.identifier):
                raise ValueError(
                    f"Permission identifier {permission.id} "
                    f"is not a subpart of app identifier {session.app.identifier}"
                )
            self.permission_registry[permission.id] = permission

    def load_permissions(self) -> None:
        cursor = self.permission_db.cursor()
        cursor.execute("SELECT id, value FROM permissions")
        for row in cursor:
            token = row[0]
            permissions = json.loads(row[1])
            self.session_permissions[token] = [
                Identifier.from_key(key) for key in permissions
            ]

    def store_permissions(self) -> None:
        cursor = self.permission_db.cursor()
        for token, permissions in self.session_permissions.items():
            permission_keys = [permission.key() for permission in permissions]
            permissions = json.dumps(permission_keys)
            cursor.execute(
                "INSERT OR REPLACE INTO permissions VALUES (?, ?)",
                (token, permissions),
            )
        self.permission_db.commit()

    def set_permissions(self, token: str, permissions: List[Identifier]) -> None:
        self.session_permissions[token] = permissions
        self.store_permissions()

    async def handle_require(
        self, session: Session, permission_identifiers: List[Identifier]
    ):
        if set(permission_identifiers) == set(
            self.session_permissions.get(session.token, {})
        ):
            return

        ready_task = await session.create_ready_task(
            f"handle_request({permission_identifiers})"
        )

        request_id = self._get_next_request_id()
        permissions: List[PermissionType] = []
        for identifier in permission_identifiers:
            permission = self.permission_registry.get(identifier)
            if permission is None:
                raise ValueError(f"Permission {identifier} not registered")
            permissions.append(permission)
        accepted = await self.server.dashboard.request_permissions(
            PermissionRequest(request_id, session.app, permissions)
        )
        if accepted:
            self.set_permissions(session.token, [p.id for p in permissions])
            if not session.closed:
                await session.send(PERMISSION_GRANT_PACKET, permissions)
            ready_task.set()
        else:
            await session.disconnect(
                DisconnectType.PERMISSION_DENIED,
                f"Permission request denied (id={request_id})",
            )

    async def handle_request(
        self, session: Session, permission_identifiers: List[Identifier]
    ):
        request_id = self._get_next_request_id()
        permissions: List[PermissionType] = []
        for identifier in permission_identifiers:
            permission = self.permission_registry.get(identifier)
            if permission is not None:
                permissions.append(permission)

        accepted = await self.server.dashboard.request_permissions(
            PermissionRequest(request_id, session.app, permissions)
        )
        if accepted:
            self.set_permissions(session.token, [p.id for p in permissions])
            if not session.closed:
                await session.send(PERMISSION_GRANT_PACKET, permissions)
        else:
            await session.disconnect(
                DisconnectType.PERMISSION_DENIED,
                f"Permission request denied (id={request_id})",
            )

    def _get_next_request_id(self) -> str:
        self.request_id += 1
        return f"{self.request_id}-{time.time_ns()}"

    def has_permission(self, session: Session, permission_id: Identifier) -> bool:
        if session.is_dashboard:
            return True
        return permission_id in self.session_permissions.get(session.token, {})
