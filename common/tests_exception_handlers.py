from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from common.exception_handlers import api_exception_handler
from common.exceptions import APIError


class APIExceptionHandlerTests(SimpleTestCase):
    def test_api_error_details_preserve_request_id(self):
        request = APIRequestFactory().post("/api/v1/otp/phone/request/", {})
        request.request_id = "req-localized-error"

        response = api_exception_handler(
            APIError(
                "sms_send_rate_limited",
                code=42902,
                status_code=429,
                details={"error_type": "sms_send_rate_limited", "reason": "isv.BUSINESS_LIMIT_CONTROL:触发天级流控Permits:10"},
            ),
            {"request": request},
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["msg"], "sms_send_rate_limited")
        self.assertEqual(response.data["data"]["error_type"], "sms_send_rate_limited")
        self.assertEqual(response.data["data"]["reason"], "isv.BUSINESS_LIMIT_CONTROL:触发天级流控Permits:10")
        self.assertEqual(response.data["data"]["request_id"], "req-localized-error")
