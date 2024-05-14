from dataclasses import dataclass, field

from omu.address import Address

from omuserver.directories import Directories


@dataclass(slots=True)
class Config:
    address: Address = Address(
        host="0.0.0.0",
        port=26423,
        secure=False,
    )
    debug: bool = False
    strict_origin: bool = True
    directories: Directories = field(default_factory=Directories.default)
    dashboard_token: str | None = None
