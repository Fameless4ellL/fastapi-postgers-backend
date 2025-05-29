from typing import Any

from fastapi_storages.integrations.sqlalchemy import FileType as _FileType
from fastapi_storages import FileSystemStorage


class FileType(_FileType):
    cache_ok = True

    def __init__(
        self,
        storage=FileSystemStorage(path='/tmp'),
        *args: Any,
        **kwargs: Any
    ) -> None:
        super().__init__(storage=storage, *args, **kwargs)