"""Integration with asw service."""
from dataclasses import dataclass

import boto3
from botocore.client import BaseClient


@dataclass
class AWS:
    """Class stores app aws configuration and provides usefull methods."""

    access_key: str
    secret_key: str
    bucket: str
    endpoint: str = None

    def client_factory(self, service: str) -> BaseClient:
        """Build client for requested service."""
        kwargs = dict(  # noqa C408
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )

        if self.endpoint:
            kwargs["endpoint_url"] = self.endpoint

        return boto3.client(service, **kwargs)
