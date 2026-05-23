"""SMTP backend that uses certifi's CA bundle for TLS verification."""

from __future__ import annotations

import ssl

import certifi
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend
from django.utils.functional import cached_property


class EmailBackend(DjangoSMTPBackend):
    """
    Django's default SMTP backend relies on ssl.create_default_context(), which on
    macOS Python.org builds often lacks trusted CAs. Use certifi for verification.
    """

    @cached_property
    def ssl_context(self):
        if self.ssl_certfile or self.ssl_keyfile:
            ssl_context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)
            return ssl_context
        return ssl.create_default_context(cafile=certifi.where())
