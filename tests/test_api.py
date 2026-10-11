"""Exercise protocol, renewal, malformed responses and credential redaction."""
import importlib
import sys
import types
import unittest
from pathlib import Path

# Load the independent API client without importing Home Assistant's setup module.
package = types.ModuleType("mroad")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/mroad")]
sys.modules["mroad"] = package
api = importlib.import_module("mroad.api")


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self, **kwargs):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


ROW = {"contract_id": "123", "contract_num": "456", "remainder": "1234.56", "status": "Active", "status_ref": "1"}


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_and_balance(self):
        session = Session([Response({"return": "secret-token"}), Response({"return": [ROW]})])
        client = api.MRoadClient(session, "user", "secret-password")
        accounts = await client.async_accounts()
        self.assertEqual(accounts["123"]["balance"], 1234.56)
        login = session.calls[0]["params"]
        self.assertEqual(login["pass"], "secret-password")
        self.assertNotIn("pass_", login)
        self.assertEqual(login["realm"], "nqr.client")
        self.assertEqual(session.calls[1]["params"]["auth_token"], "secret-token")

    async def test_session_expiry_reauthenticates_once(self):
        session = Session([Response("first"), Response({}, 401), Response("second"), Response([ROW])])
        client = api.MRoadClient(session, "user", "password")
        self.assertIn("123", await client.async_accounts())
        self.assertEqual(len(session.calls), 4)

    async def test_rejected_new_credentials_stop(self):
        session = Session([Response("first"), Response({}, 403), Response({"error": {"code": 401}})])
        with self.assertRaises(api.MRoadAuthError):
            await api.MRoadClient(session, "user", "password").async_accounts()
        self.assertEqual(len(session.calls), 3)

    async def test_api_error_renews_session(self):
        session = Session([Response("first"), Response({"error": {"code": "401"}}), Response("second"), Response([])])
        self.assertEqual(await api.MRoadClient(session, "user", "password").async_accounts(), {})

    async def test_error_does_not_expose_credentials(self):
        session = Session([api.aiohttp.ClientError("https://example/?pass=secret-password")])
        with self.assertRaises(api.MRoadError) as raised:
            await api.MRoadClient(session, "user", "secret-password").async_accounts()
        self.assertNotIn("secret-password", str(raised.exception))
        self.assertTrue(raised.exception.__suppress_context__)

    async def test_non_json_response(self):
        session = Session([Response(ValueError("invalid JSON"))])
        with self.assertRaises(api.MRoadError):
            await api.MRoadClient(session, "user", "password").async_accounts()

    async def test_pagination(self):
        first = [{**ROW, "contract_id": str(i)} for i in range(500)]
        session = Session([Response("token"), Response(first), Response([{**ROW, "contract_id": "last"}])])
        result = await api.MRoadClient(session, "user", "password").async_accounts()
        self.assertEqual(len(result), 501)
        self.assertEqual(session.calls[-1]["params"]["rows_skip"], 500)


class PayloadTests(unittest.TestCase):
    def test_missing_or_nonfinite_balance_is_not_zero(self):
        for value in [None, "NaN", "Infinity", "invalid"]:
            with self.subTest(value=value), self.assertRaises(api.MRoadError):
                api.normalize_accounts([{**ROW, "remainder": value}])
        with self.assertRaises(api.MRoadError):
            api.normalize_accounts([{"contract_id": 1}])

    def test_negative_balance(self):
        self.assertEqual(api.normalize_accounts([{**ROW, "remainder": "-50.25"}])["123"]["balance"], -50.25)

    def test_unknown_envelope_is_error(self):
        with self.assertRaises(api.MRoadError):
            api.unwrap({"unexpected": []})
