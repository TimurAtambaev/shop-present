"""Basic classes and helper functions.

For mailers and mail sending related basic code.
"""
from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple

from trafaret import Trafaret


class Template:
    """Message template class.

    When declaring new template must set as class level vars:
    __template_name__ - string value of name
    __template_subject__ - string value, supports formatting. Uses variables.
    __template_tags__ - tuple of string values to be used as tags for message
    trafarret method - trafarret validation rules fo template vars

    Variables are set with "template" prefix to avoid name mixing.
    """

    def __init__(self, **kwargs: Dict) -> None:
        """Get variables for template."""
        super().__init__()
        self.__template_variables__: Dict = self.__validate__(kwargs)
        self.__html__ = None
        self.__is_built__ = False

    @abstractmethod
    def trafarret(self) -> Trafaret:
        """Declare trafaret rules to validate provided variables."""

    def __check_is_built__(self) -> None:
        """Check build."""
        if not self.__is_built__:
            raise RuntimeError("Build before use")

    def __validate__(self, raw_vars: Any) -> Any:
        """Validate potential variables and return them with default values.

        If configured in trafarret method
        """
        return self.trafarret().check(raw_vars)

    def template_name(self) -> str:
        """Return template name."""
        self.__check_is_built__()
        return self.__template_name__

    def variables(self) -> Dict[str, str]:
        """Return variables."""
        self.__check_is_built__()
        return self.__template_variables__

    async def subject(self) -> str:
        """Return subject. Must be set as class var."""
        self.__check_is_built__()
        return self.__template_subject__.format(
            **self.__template_variables__,
        )

    async def html(self) -> str:
        """Return html body."""
        self.__check_is_built__()
        return self.__html__

    def tags(self) -> Tuple[str]:
        """Return list of template tags."""
        self.__check_is_built__()
        return self.__template_tags__

    async def build(self) -> None:
        """Designed to prepare template if required.

        Method designed to be overriden
        """
        self.__is_built__ = True


class Message:
    """Class represents mail message.

    Designed to unify mailers message creation.
    """

    def __init__(
        self,
        recipient: str,
        template: Template,
        _from: str = None,
        is_test: bool = False,
    ) -> None:
        """Set up object parameters.

        recipients will be converted to tuple.
        """
        super().__init__()

        assert isinstance(recipient, str)
        assert isinstance(template, Template)
        assert isinstance(_from, str) or _from is None
        assert isinstance(is_test, bool)

        self.__message_recipient__: str = recipient
        self.__message_template__ = template
        self.__message_sender__: Optional[str] = _from
        self.__message_is_test__: bool = is_test

    @property
    def sender(self) -> Optional[str]:
        """Return sender for FROM field."""
        return self.__message_sender__

    @property
    def recipient(self) -> str:
        """Return list of recipients."""
        return self.__message_recipient__

    async def subject(self) -> str:
        """Return set template subject."""
        return await self.__message_template__.subject()

    @property
    def tags(self) -> Tuple[str]:
        """Return tags list."""
        return self.__message_template__.tags()

    @property
    def variables(self) -> Dict[str, str]:
        """Return template variables."""
        return self.__message_template__.variables()

    @property
    def is_test(self) -> bool:
        """Return if message is supposed to be test."""
        return self.__message_is_test__

    async def html(self) -> str:
        """Return message html body."""
        return await self.__message_template__.html()

    async def build(self) -> None:
        """Prepare (builds) message."""
        await self.__message_template__.build()


class Mailer:
    """Mailer basic class.

    Working mailers must be children of this class
    """

    def __init__(
        self,
        dsn: str,
        public_domain: str,
        app_domain: str,
        support_email: str,
        landing_domain: str,
    ) -> None:
        """Mailer init."""
        super().__init__()
        self.__mail_is_test__ = False
        self.__mail_from__ = None
        self.__parse_dsn__(dsn)
        self.__vars__ = {
            "publicDomain": public_domain,
            "appDomain": app_domain,
            "supportEmail": support_email,
            "landingDomain": landing_domain,
        }

    @abstractmethod
    def __parse_dsn__(self, dsn: str) -> None:
        """Parse dsn string and set up object vars.

        Based on parse result
        """

    @property
    def is_test_mode(self) -> bool:
        """Return is mailer working in test mode."""
        return self.__mail_is_test__

    @abstractmethod
    async def send(self, message: Message) -> str:
        """Define send handling. Returns message id."""
