from json import loads
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

from django.test import SimpleTestCase, override_settings

from accounts.services.web_apple_identity_service import WebAppleIdentityService


@override_settings(
    APPLE_WEB_SERVICE_IDS=["cn.Zhaodk.Health.web"],
    APPLE_WEB_ALLOWED_REDIRECT_URIS=["https://chat.dreamwhale.com/api/auth/apple/callback"],
)
class WebAppleCodeExchangeTests(SimpleTestCase):
    @patch.object(WebAppleIdentityService, "_build_client_secret", return_value="signed-client-secret")
    @patch("accounts.services.web_apple_identity_service.urlopen")
    def test_exchange_uses_form_encoded_body(self, mock_urlopen, _mock_client_secret):
        response = MagicMock()
        response.read.return_value = b'{"id_token":"exchanged-id-token"}'
        context_manager = MagicMock()
        context_manager.__enter__.return_value = response
        mock_urlopen.return_value = context_manager

        result = WebAppleIdentityService.exchange_authorization_code(
            authorization_code="one-time-code",
            service_id="cn.Zhaodk.Health.web",
            redirect_uri="https://chat.dreamwhale.com/api/auth/apple/callback",
        )

        self.assertEqual(result, loads('{"id_token":"exchanged-id-token"}'))
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertEqual(
            parse_qs(request.data.decode("ascii")),
            {
                "client_id": ["cn.Zhaodk.Health.web"],
                "client_secret": ["signed-client-secret"],
                "code": ["one-time-code"],
                "grant_type": ["authorization_code"],
                "redirect_uri": ["https://chat.dreamwhale.com/api/auth/apple/callback"],
            },
        )
