import mimetypes
import os
import uuid
from datetime import timedelta
from typing import BinaryIO

import urllib3
from fastapi_storages.base import BaseStorage
from minio import Minio
from minio.error import S3Error, MinioException
from settings import aws, settings


class MinioStorage(BaseStorage):
    OVERWRITE_EXISTING_FILES = True

    def __init__(
        self,
        bucket: str,
        path: str = None,
        public: bool = False
    ):
        self.client = Minio(
            aws.minio.endpoint,
            access_key=aws.minio.access_key,
            secret_key=aws.minio.secret_key,
            region=aws.region,
            secure=aws.minio.secure,
            http_client=urllib3.ProxyManager(
                "http://minio:9000",
                timeout=urllib3.Timeout.DEFAULT_TIMEOUT,
                retries=urllib3.Retry(
                    total=5,
                    backoff_factor=0.2,
                    status_forcelist=[500, 502, 503, 504],
                ),
            ),
        )
        self.bucket = bucket
        self.path = path
        self.public = public

        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def get_name(self, name: str) -> str:
        if self.path and not name.startswith(self.path):
            return self.path + '/' + name
        return name

    def reupload_from_static(self, local_path: str):
        with open(local_path, 'rb') as file:
            file.seek(0, 2)
            length = file.tell()
            file.seek(0)
            content_type, _ = mimetypes.guess_type(local_path)
            self.client.put_object(
                self.bucket,
                file.name.replace('static/', ''),
                data=file,
                length=length,
                content_type=content_type or "application/octet-stream"
            )

    def get_path(self, name: str) -> str:
        local_path = 'static/' + self.path + '/' + name
        if os.path.exists(local_path):
            self.reupload_from_static(local_path)
            os.remove(local_path)

        if self.public:
            return f"{settings.back_url}/v1/file/{self.bucket}?path={self.get_name(name)}"

        return self.client.presigned_get_object(
            bucket_name=self.bucket,
            object_name=self.get_name(name),
            expires=timedelta(days=7)
        )

    def get_size(self, name: str) -> int:
        stat = self.client.stat_object(self.bucket, self.get_name(name))
        return stat.size

    def open(self, name: str) -> BinaryIO:
        try:
            return self.client.get_object(self.bucket, self.get_name(name))
        except (MinioException, S3Error) as e:
            raise FileNotFoundError(f"Object '{name}' not found in bucket '{self.bucket}'") from e

    def write(self, file: BinaryIO, name: str) -> str:
        filename = self.get_name(name)
        if not self.OVERWRITE_EXISTING_FILES:
            filename = self.generate_new_filename(self.get_name(name))

        file.seek(0, 2)
        length = file.tell()
        file.seek(0)
        content_type, _ = mimetypes.guess_type(filename)
        self.client.put_object(
            self.bucket,
            filename,
            data=file,
            length=length,
            content_type=content_type or "application/octet-stream"
        )
        return filename

    def generate_new_filename(self, filename: str) -> str:
        root, ext = os.path.splitext(filename)
        return f"{root}_{uuid.uuid4().hex}{ext}"
