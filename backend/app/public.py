"""Public mode: daily limits on live provider calls, and a cost ceiling for each call.

A hosted demo lets strangers reach the server's own provider keys, so every live call is counted
against two in-memory allowances that reset at 00:00 UTC: one shared by everyone (the real guard,
since forwarded headers can be spoofed) and one per client address. A call whose worst-case cost
is above ``public_max_call_usd`` is refused before it is sent. Previews never come here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import HTTPException, status

from app.benchmarks.costs import worst_case_call_usd
from app.config import Settings
from app.learned.router import prompt_token_estimate


def _utc_today() -> date:
    return datetime.now(UTC).date()


@dataclass(frozen=True)
class LiveCall:
    """One provider request about to be sent."""

    model_name: str
    prompt: str
    max_tokens: int
    prompt_price_per_token: Decimal | None
    completion_price_per_token: Decimal | None

    def worst_case_usd(self) -> Decimal:
        # The benchmark estimate counts 4 characters per token; assume 2, so a prompt of
        # unusual text (code, other scripts) is not undercounted. Retries are included.
        return worst_case_call_usd(
            2 * prompt_token_estimate(self.prompt),
            self.max_tokens,
            self.prompt_price_per_token,
            self.completion_price_per_token,
        )


class PublicGuard:
    def __init__(
        self, settings: Settings, today: Callable[[], date] = _utc_today
    ) -> None:
        self.enabled = settings.public_mode
        self.shared_limit = settings.public_daily_live_calls
        self.client_limit = settings.public_client_daily_live_calls
        self.max_call_usd = settings.public_max_call_usd
        self._today = today
        self._day = today()
        self._shared_used = 0
        self._client_used: dict[str, int] = {}

    def _roll_over(self) -> None:
        if self._today() != self._day:
            self._day = self._today()
            self._shared_used = 0
            self._client_used = {}

    def shared_left(self) -> int:
        self._roll_over()
        return max(self.shared_limit - self._shared_used, 0)

    def client_left(self, client: str) -> int:
        """Calls this client can still make today: its own allowance, capped by the shared one."""
        used = self._client_used.get(client, 0)
        return min(max(self.client_limit - used, 0), self.shared_left())

    def admit(self, client: str, calls: Sequence[LiveCall]) -> None:
        """Refuse the calls (403 over the cost ceiling, 429 over a limit) or count them."""
        if not self.enabled:
            return
        for call in calls:
            cost = call.worst_case_usd()
            if cost > self.max_call_usd:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"{call.model_name} could cost up to ${cost:.3f} for this prompt, above "
                        f"the public demo's ${self.max_call_usd} limit per call, so it was not "
                        "called. The preview still shows the decision."
                    ),
                )
        needed = len(calls)
        if self.shared_left() < needed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"The public demo has used its {self.shared_limit} live calls for today. "
                    "Previews are unlimited, and live calls return at 00:00 UTC."
                ),
            )
        if self.client_left(client) < needed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"This needs {needed} live call{'s' if needed != 1 else ''}, and you have "
                    f"{self.client_left(client)} of your {self.client_limit} left today. "
                    "Previews are unlimited, and live calls return at 00:00 UTC."
                ),
            )
        self._shared_used += needed
        self._client_used[client] = self._client_used.get(client, 0) + needed
