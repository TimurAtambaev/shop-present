"""Модуль обработки и загрузки файлов."""
import base64
import tempfile
from datetime import datetime
from io import BytesIO
from mimetypes import guess_extension, guess_type
from typing import Union

import boto3
import requests
from botocore.exceptions import ClientError
from fastapi import HTTPException, Request
from nudenet import NudeClassifier
from PIL import Image
from pydantic import BaseModel
from starlette import status
from starlette.datastructures import UploadFile

from dataset.config import settings
from dataset.integrations.aws import AWS  # noqa N811
from dataset.middlewares import request_var
from dataset.rest.models.types import UploadFileOrLink


class UploadCloudModel(BaseModel):
    """Базовая модель пидантик с возможностью загружать файлы в aws."""

    @staticmethod
    def get_type() -> type:
        """Получаем тип."""
        return UploadFileOrLink(validator=UploadCloudModel.validate_picture)

    @staticmethod
    def validate_picture(
        value: Union[str, UploadFile], compress: bool = True
    ) -> Union[UploadFile, str]:
        """Валидация картинки."""
        type_image = ["image/jpeg", "image/jpg", "image/png"]
        if (content_type := getattr(value, "content_type", None)) is None:
            content_type = guess_type(value)[0]

        if content_type not in type_image:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            )

        UploadCloudModel.check_mature_content(value)

        funcs = {
            UploadFile: lambda: UploadCloudModel.upload_file(
                UploadCloudModel.compress_file(
                    value, settings.FILE_SIZE if compress else float("inf")
                )
            ),
            str: lambda: value,
        }
        if func := funcs.get(type(value)):
            return func()
        raise ValueError(f"The {type(value)} type is not supported")

    @staticmethod
    def check_mature_content(file: Union[str, UploadFile]) -> None:
        """Проверить файл ссылку на содержание взрослого контента."""
        if not file:
            return

        classifier = NudeClassifier()

        if isinstance(file, str):
            content = requests.get(file).content
        else:
            content = file.file.read()

        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(content)
            tmp.flush()
            scores = classifier.classify(f"/{tmp.name}")[f"/{tmp.name}"]

        if scores["unsafe"] > settings.NSFW_CENSOR_THRESHOLD:
            raise ValueError("This content is not allowed")

    @staticmethod
    def compress_file(file: UploadFile, x_size: int) -> UploadFile:
        """Сжать файл изображения."""
        image = Image.open(file.file).convert("RGB")
        if image.size[0] > x_size:
            y_size = int(image.size[1] / (image.size[0] / x_size))
            image = image.resize((x_size, y_size))
        image_io = BytesIO()
        image.save(image_io, "JPEG", optimize=True)
        file.file = image_io
        image_io.seek(0)
        return file

    @staticmethod
    def upload(
        s3_client: boto3, file: UploadFile, aws: AWS, new_filename: str
    ) -> str:
        """Переопределение метода загрузки файла в облако."""
        try:
            s3_client.upload_fileobj(
                file.file,
                aws.bucket,
                new_filename,
                ExtraArgs={
                    "ContentType": (
                        guess_type(file.filename)[0] or file.content_type
                    ),
                },
            )
        except ClientError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        return (
            f"https://{aws.bucket}.{settings.AWS_DEFAULT_REGION}"
            f".{settings.AWS_DOMAIN}/{new_filename}"
        )

    @staticmethod
    def upload_file(file: UploadFile) -> str:
        """Загрузить файл в облако."""

        def get_unique_name() -> str:
            """Получить уникальное имя."""
            user_id = -1
            if user := getattr(request, "user", None):
                user_id = user.id
            filename = bytes(
                f"{file.filename}_{datetime.now().timestamp()}_{user_id}",
                "utf-8",
            )
            filename = base64.b64encode(filename).decode("ascii")
            return f"{filename}==sep=={guess_extension(file.content_type)}"

        def check_file_existence(filename: str) -> bool:
            """Проверить существование файла в облаке."""
            try:
                s3_client.head_object(Bucket=aws.bucket, Key=filename)
            except ClientError:
                return False
            return True

        request: Request = request_var.get()
        if int(request.headers["content-length"]) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Превышен максимальный размер файла",
            )
        aws: AWS = request.app.state.aws
        s3_client = aws.client_factory("s3")

        new_filename = get_unique_name()

        if check_file_existence(new_filename):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT)
        return UploadCloudModel.upload(s3_client, file, aws, new_filename)


class MessageUploadCloudModel(UploadCloudModel):
    """Класс для загрузки файла в чате."""

    @classmethod
    def upload(
        cls, s3_client: boto3, file: UploadFile, aws: AWS, new_filename: str
    ) -> dict:
        """Загрузка файла."""
        try:
            s3_client.upload_fileobj(
                file.file,
                aws.bucket,
                new_filename,
                ExtraArgs={
                    "ContentType": (
                        guess_type(file.filename)[0] or "binary/octet-stream"
                    ),
                },
            )
        except ClientError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        return {
            file.filename: f"https://{aws.bucket}.{settings.AWS_DEFAULT_REGION}"
            f".{settings.AWS_DOMAIN}/{new_filename}"
        }


class ReceiptUploadCloudModel(UploadCloudModel):
    """Класс для загрузки квитанции при донате."""

    @classmethod
    def upload(
        cls, s3_client: boto3, file: UploadFile, aws: AWS, new_filename: str
    ) -> str:
        """Переопределение метода загрузки файла в облако."""
        try:
            s3_client.upload_fileobj(
                file.file,
                aws.bucket,
                new_filename,
                ExtraArgs={
                    "ContentType": (
                        guess_type(file.filename)[0] or "binary/octet-stream"
                    ),
                },
            )
        except ClientError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        return (
            f"https://{aws.bucket}.{settings.AWS_DEFAULT_REGION}"
            f".{settings.AWS_DOMAIN}/{new_filename}"
        )
