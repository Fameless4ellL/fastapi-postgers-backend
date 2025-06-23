import mimetypes
import os
import uuid
from datetime import timedelta
from typing import BinaryIO

import urllib3
from fastapi_storages.base import BaseStorage
from minio import Minio
from minio.error import S3Error, MinioException
from settings import aws


class MinioStorage(BaseStorage):
    OVERWRITE_EXISTING_FILES = True

    def __init__(
        self,
        bucket: str,
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

        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def get_name(self, name: str) -> str:
        return name

    def get_path(self, name: str) -> str:
        return self.client.presigned_get_object(
            bucket_name=self.bucket,
            object_name=name,
            expires=timedelta(days=7)
        )
        # return f"{self.bucket}/{name}"

    def get_size(self, name: str) -> int:
        stat = self.client.stat_object(self.bucket, name)
        return stat.size

    def open(self, name: str) -> BinaryIO:
        try:
            return self.client.get_object(self.bucket, name)
        except (MinioException, S3Error) as e:
            raise FileNotFoundError(f"Object '{name}' not found in bucket '{self.bucket}'") from e

    def write(self, file: BinaryIO, name: str) -> str:
        filename = name
        if not self.OVERWRITE_EXISTING_FILES:
            filename = self.generate_new_filename(name)

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
