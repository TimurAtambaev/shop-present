"""Integration requirements for external systems."""
from abc import ABCMeta, abstractmethod
from typing import Dict, Iterable, List

from aiohttp import ClientSession

from dataset.core.graphql import build_gql_request
from dataset.core.log import LOGGER


class ProductData:
    """Data class that represents product data from integration endpoint."""

    def __init__(
        self, profile_id: str, level_number: int, product_id: str
    ) -> None:
        """Class init."""
        super().__init__()
        self.profile_id = self.user_id = profile_id
        self.level_number = self.level = level_number
        self.product_id = product_id.rjust(6, "0")
        self.blacklist = []


class BaseExternalApplication:
    """Basic external application operations."""

    def __init__(self, url: str, token: str) -> None:
        """Class init."""
        self.__url__: str = url
        self.__token__: str = token

    def __session_factory__(self) -> ClientSession:
        """Create preconfigured ClientSession object."""
        return ClientSession(headers={"Authorization": self.__token__})

    async def query(self, gql: str, variables: Dict = None) -> Dict:
        """Make graphql_ query."""
        async with self.__session_factory__() as session:
            response = await session.post(
                self.__url__, json=await build_gql_request(gql, variables)
            )

            try:
                assert response.status == 200
            except AssertionError:
                data = await response.json()
                LOGGER.error(
                    "External application request failed with result %d: %s",
                    response.status,
                    data,
                )
                raise

            data = await response.json()

            if "errors" in data:
                error = ", ".join(
                    [e.get("message") for e in data.get("errors")]
                )
                raise RuntimeError(error)

            return data.get("data", {})


class Validator:
    """Ticket validator abstract class."""

    __metaclass__ = ABCMeta

    @abstractmethod
    async def validate(
        self,
        app: BaseExternalApplication,
        product_id: int,
        blacklist: List[str] = None,
    ) -> List[ProductData]:
        """Validate product id."""

    @abstractmethod
    async def reserve(
        self,
        app: BaseExternalApplication,
        product_id: str,
        profile_id: str,
        blacklist: List[str] = None,
    ) -> List[ProductData]:
        """Reserve product id."""


class TicketValidator(Validator):
    """Ticket validator. Makes query to external application."""

    async def validate(
        self,
        app: BaseExternalApplication,
        product_id: int,
        blacklist: List[str] = None,
    ) -> List[ProductData]:
        """Validate product id."""
        v_data = await app.query(
            """mutation Validate($input:TicketCheckInput!){
                productCheck(input: $input){
                    result {
                        profileId
                        levelNumber
                        productId
                    }
                }
            }""",
            {"productId": product_id, "blackList": blacklist or []},
        )

        return [
            ProductData(
                p.get("profileId"), p.get("levelNumber"), p.get("productId")
            )
            for p in v_data.get("productCheck", {}).get("result", [])
        ]

    async def reserve(
        self,
        app: BaseExternalApplication,
        product_id: str,
        profile_id: str,
        blacklist: List[str] = None,
    ) -> List[ProductData]:
        """Reserve product id."""
        v_data = await app.query(
            """mutation Reserve($input:TicketReserveInput!){
                productReserve(input: $input){
                    result {
                        profileId
                        levelNumber
                        productId
                    }
                }
            }""",
            {
                "productId": product_id,
                "profileId": profile_id,
                "blackList": blacklist or [],
            },
        )

        return [
            ProductData(
                p.get("profileId"), p.get("levelNumber"), p.get("productId")
            )
            for p in v_data.get("productReserve", {}).get("result", [])
        ]


class TestTicketValidator(Validator):
    """Test ticket validator. Returns static data."""

    @staticmethod
    def get_referal(blacklist: Iterable[str]) -> ProductData:
        """Return referal data.

        Returns one of two users depending on is_blacklist argument.
        """
        result = ProductData(
            product_id="986223", profile_id="5", level_number=0
        )
        no_payment_data = ProductData(
            product_id="021155", profile_id="1", level_number=0
        )
        no_order = ProductData(
            product_id="000002", profile_id="3", level_number=0
        )
        inactive_user = ProductData(
            product_id="492211", profile_id="6", level_number=0
        )

        if no_payment_data.profile_id not in blacklist:
            result = no_payment_data
        elif no_order.profile_id not in blacklist:
            result = no_order
        elif inactive_user.profile_id not in blacklist:
            result = inactive_user
        elif "5" in blacklist:
            result = ProductData(
                product_id="026881", profile_id="9", level_number=0
            )

        return result  # noqa R504

    async def validate(
        self,
        app: BaseExternalApplication,
        product_id: str,
        blacklist: List[str] = None,
    ) -> List[ProductData]:
        """Validate product id."""
        return [self.get_referal(blacklist)]

    async def reserve(
        self,
        app: BaseExternalApplication,
        product_id: str,
        profile_id: str,
        blacklist: List[str] = None,
    ) -> List[ProductData]:
        """Reserve product id."""
        if product_id == "test1111":
            return [
                ProductData(
                    product_id="005377", profile_id="11", level_number=1
                )
            ]

        return [
            self.get_referal(blacklist),
            ProductData(product_id="005377", profile_id="11", level_number=1),
            ProductData(product_id="032257", profile_id="8", level_number=2),
            ProductData(product_id="593019", profile_id="2", level_number=3),
        ]


class ExternalApplication(BaseExternalApplication):
    """Class handles integrated application operations."""

    def __init__(self, url: str, token: str) -> None:
        """Class init."""
        super().__init__(url, token)
        self.__validator: Validator = TicketValidator()

    @property
    def validator(self) -> None:
        """Validate."""
        return

    @validator.setter
    def validator(self, validator: Validator) -> None:
        self.__validator = validator

    async def validate(
        self, product_id: int, blacklist: List[str] = None
    ) -> List[ProductData]:
        """Validate product id."""
        return await self.__validator.validate(self, product_id, blacklist)

    async def reserve(
        self, product_id: str, profile_id: str, blacklist: List[str] = None
    ) -> List[ProductData]:
        """Reserve product id."""
        return await self.__validator.reserve(
            self, product_id, profile_id, blacklist
        )

    async def release(self, product_id: str) -> None:
        """Release product id."""
        v_data = await self.query(
            """mutation Release($input:TicketReleaseInput!){
                productRelease(input: $input){
                    result
                }
            }""",
            {
                "productId": product_id,
            },
        )

        assert v_data.get("productCheck", {}).get("result")

    async def prepare_for_payment(self, product_id: str) -> None:
        """Prepare for payment product id."""
        v_data = await self.query(
            """mutation productPrepareForPayment($input: TicketPrepareForPaymentInput!){
                productPrepareForPayment(input: $input){
                    result
                }
            }""",
            {
                "productId": product_id,
            },
        )
        assert v_data.get("productPrepareForPayment", {}).get("result")

    async def product_certificates(self, product_id: str) -> List:
        """Product certificates by product id."""
        v_data = await self.query(
            """query ProductCertificates($input:ProductIdInput!) {
                productCertificates(input: $input){
                    productId
                    status
                }
            }""",
            {
                "productId": product_id,
            },
        )

        return v_data.get("productCertificates", [])
