"""Read-only client for the API used by the official web account."""
import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from .const import API_URL, APP_KEY


class MRoadError(Exception):
    """Connection or response error, with no credentials in its message."""


class MRoadAuthError(MRoadError):
    """Credentials or session rejected."""


def unwrap(payload: Any) -> Any:
    """Unwrap ONYMA's return envelope and reject API errors."""
    if isinstance(payload, dict):
        if "error" in payload:
            error = payload["error"]
            code = str(error.get("code", "")) if isinstance(error, dict) else ""
            if code in {"401", "403"}:
                raise MRoadAuthError("Authentication rejected")
            raise MRoadError("API returned an error")
        if "return" not in payload:
            raise MRoadError("Unexpected response envelope")
        return payload["return"]
    return payload


def normalize_accounts(rows: Any) -> dict[str, dict[str, Any]]:
    """Validate account records rather than turning missing balances into zero."""
    if not isinstance(rows, list):
        raise MRoadError("Unexpected account response")
    accounts = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("contract_id") is None:
            raise MRoadError("Missing account identifier")
        try:
            amount = Decimal(str(row["remainder"]))
            if not amount.is_finite():
                raise InvalidOperation
        except (KeyError, InvalidOperation, ValueError):
            raise MRoadError("Invalid balance in account response") from None
        account_id = str(row["contract_id"])
        accounts[account_id] = {
            "id": account_id,
            "number": str(row.get("contract_num") or account_id),
            "balance": float(amount),
            "status": str(row.get("status") or ""),
            "status_id": str(row.get("status_ref") or ""),
        }
    return accounts


class MRoadClient:
    """Keep the authentication token only in memory."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str):
        self.session = session
        self.username = username
        self.password = password
        self.token: str | None = None

    async def _request(self, function: str, **params: Any) -> Any:
        if "pass_" in params:
            params["pass"] = params.pop("pass_")
        query = {"function": function, "__app_key__": APP_KEY, **params}
        if self.token:
            query["auth_token"] = self.token
        try:
            async with self.session.get(
                API_URL, params=query, timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=False,
            ) as response:
                if response.status in (401, 403):
                    raise MRoadAuthError("Authentication rejected")
                if response.status != 200:
                    raise MRoadError(f"API HTTP status {response.status}")
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            # aiohttp exceptions can contain a URL with the password/token.
            raise MRoadError("Cannot read API response") from None
        return unwrap(payload)

    async def async_login(self) -> None:
        self.token = None
        result = await self._request(
            "open_session", user=self.username, pass_=self.password,
            realm="nqr.client",
        )
        if not isinstance(result, str) or not result.strip():
            raise MRoadAuthError("Unexpected login response")
        self.token = result

    async def _accounts(self) -> dict[str, dict[str, Any]]:
        rows = []
        for offset in range(0, 50000, 500):
            page = await self._request(
                "onm_api_nqr_api_contract_info", type_ref='{"ne":2}',
                rows_limit=500, rows_skip=offset,
            )
            if not isinstance(page, list):
                raise MRoadError("Unexpected account response")
            rows.extend(page)
            if len(page) < 500:
                return normalize_accounts(rows)
        raise MRoadError("Account pagination limit exceeded")

    async def async_accounts(self) -> dict[str, dict[str, Any]]:
        if not self.token:
            await self.async_login()
        try:
            return await self._accounts()
        except MRoadAuthError:
            await self.async_login()
            return await self._accounts()
