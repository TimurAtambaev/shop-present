"""Classes to handle operations in zendesk."""
from datetime import datetime

from zenpy import Zenpy
from zenpy.lib.api_objects import CustomField, Ticket, TicketAudit
from zenpy.lib.api_objects import User as BaseUser


class User(BaseUser):
    """Class represents user in zendesk."""


class ZenDesk:
    """Class represents zendesk operations required for app."""

    def __init__(
        self,
        email: str = None,
        token: str = None,
        subdomain: str = None,
        is_test: bool = False,
    ) -> None:
        """Set variables and checks settings."""
        self.is_test = is_test

        if self.is_test:
            return

        assert (  # noqa PT018
            token and subdomain and email
        ), "Token, email and sub domain must be provided if not in test mode"

        self.__client: Zenpy = Zenpy(
            email=email, token=token, subdomain=subdomain
        )

    async def create_ticket(
        self, user: User, text: str, user_id: int = None, dream_id: int = None
    ) -> str:
        """Create ticket in zendesk panel."""
        if self.is_test:
            return datetime.utcnow().strftime("%Y%m%d%H%M%S")

        ticket: TicketAudit = self.__client.tickets.create(
            Ticket(
                description=text,
                custom_fields=[
                    CustomField(id="360008453958", value=str(user_id)),
                    CustomField(id="360008519978", value=str(dream_id)),
                ],
                requester=user,
            )
        )

        return str(ticket.ticket.id)
