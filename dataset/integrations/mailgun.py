"""Mailgun related code and Mailer class."""
import re

import aiohttp
import trafaret as T  # noqa N812
from aiohttp import BasicAuth, ClientSession, ContentTypeError

from dataset.core.constants import R_EMAIL_PATTERN, TRUE_VALUES
from dataset.core.log import LOGGER
from dataset.core.mail import Mailer as BaseMailer
from dataset.core.mail import Message


class Mailgun(BaseMailer):
    """Mailgun mailer."""

    DSN_PATTERN = re.compile(
        r"^mailgun://(?P<api_key>[a-z0-9-]+)@"
        r"(?P<url>api.([a-z]{2}.|)mailgun.net/v3/(?P<domain>[a-z][a-z0-9\.]+))"
        r"(\?(?P<extra_vars>[^?]+)|)$",
        re.I,
    )

    def __init__(
        self,
        dsn: str,
        public_domain: str,
        app_domain: str,
        support_email: str,
        landing_domain: str,
    ) -> None:
        """Class init."""
        self.__api_key__: str
        self.__url__: str
        self.__domain__: str
        self.__mail_from__: str
        self.__mail_is_test__: bool
        self.__session__: aiohttp.ClientSession

        super().__init__(
            dsn, public_domain, app_domain, support_email, landing_domain
        )

    def __parse_dsn__(self, dsn: str) -> None:
        """Read mailgun connection options from dsn string."""
        dsn_match = self.DSN_PATTERN.match(dsn.strip())

        assert dsn_match is not None

        params = dsn_match.groupdict()

        self.__api_key__ = params.get("api_key")
        self.__url__ = "https://" + params.get("url")
        self.__domain__ = params.get("domain")

        extra_vars = self.__parse_extra_vars__(params.get("extra_vars"))

        self.__mail_from__ = extra_vars.get("from")

        if not self.__mail_from__:
            domain = ".".join(self.__domain__.split(".")[-2:])
            self.__mail_from__ = f"noreply@{domain}"

        self.__mail_is_test__ = extra_vars.get("test") in TRUE_VALUES

    @staticmethod
    def __parse_extra_vars__(raw_vars: str) -> dict:
        """Parse extra vars."""
        result = {}

        trafaret = T.Dict(
            {
                T.Key("from", optional=True): T.Regexp(R_EMAIL_PATTERN, re.I),
                T.Key("test", optional=True): T.Regexp(
                    re.compile("^(%s)$" % "|".join(TRUE_VALUES), re.I)
                ),
            }
        )

        if raw_vars:
            result = dict(
                [i.split("=") for i in raw_vars.split("&") if i and "=" in i]
            )

        return trafaret.check(result)

    def __build_url__(self, endpoint: str) -> str:
        """Build url for api requests."""
        return f"{self.__url__}/{endpoint}"

    def __session_factory__(self) -> ClientSession:
        """Client session factory."""
        return aiohttp.ClientSession(
            auth=BasicAuth("api", self.__api_key__, "utf8")
        )

    async def send(self, message: Message) -> str:
        """Handle api requests to mailgun for sending mail."""
        await message.build()

        async with self.__session_factory__() as session:
            try:
                is_test = self.__mail_is_test__ or message.is_test
                html = await message.html()
                message_vars = {
                    **message.variables,
                    **self.__vars__,
                    "sender": message.sender.split()[0],
                }
                for key, value in message_vars.items():
                    html = html.replace("{{%s}}" % key, str(value))

                resp = await session.post(
                    self.__build_url__("messages"),
                    data={
                        **{
                            "from": message.sender or self.__mail_from__,
                            "to": message.recipient,
                            "subject": await message.subject(),
                            "html": html,
                            "o:tag": message.tags,
                            "o:testmode": "true" if is_test else "false",
                        },
                    },
                )
                try:
                    data = await resp.json()
                except ContentTypeError:
                    data = await resp.text()

                if not resp.status == 200:
                    raise RuntimeError(f"{resp.status}: {data}")

                LOGGER.debug(
                    "Mail to %s send successfully. Response: %s",
                    message.recipient,
                    data,
                )

                return data.get("id").strip("<>")
            except Exception:
                LOGGER.error("Mail to %s is not sent. ", message.recipient)
                raise

    async def get_events_message_by_id(self, message_id: int) -> dict:
        """Return events related to message id.

        Added for debugging and testing purposes
        """
        async with self.__session_factory__() as session:
            resp = await session.get(
                self.__build_url__("events"), params={"message-id": message_id}
            )

            data = await resp.json()

            if not resp.status == 200:
                raise RuntimeError(f"{resp.status}: {data}")

            return data
