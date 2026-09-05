"""Strict TLS trust configuration for INCOIS services.

Some ``*.incois.gov.in`` hosts omit their issuing intermediate certificate.
The bundled certificate is the GlobalSign RSA OV SSL CA 2018 intermediate
advertised by those leaf certificates through AIA. It is added to the platform
trust store; hostname checking and certificate verification remain mandatory.
"""

from __future__ import annotations

import logging
import os
import ssl
from pathlib import Path

logger = logging.getLogger(__name__)

_BUNDLED_INTERMEDIATE = (
    Path(__file__).parent / "certs" / "globalsign-rsa-ov-ssl-ca-2018.pem"
)


def build_incois_ssl_context() -> ssl.SSLContext:
    """Return a verifying context augmented with the INCOIS intermediate.

    ``INCOIS_CA_BUNDLE`` may point to an additional operator-managed PEM bundle.
    A missing override logs a warning and retains the verified bundled
    intermediate; a present but invalid override fails closed.
    """
    # Import lazily so this low-level TLS module remains independently
    # importable while source adapters import it during package initialization.
    from .sources.base import SourceContractError

    context = ssl.create_default_context()
    try:
        context.load_verify_locations(cafile=str(_BUNDLED_INTERMEDIATE))
    except (OSError, ssl.SSLError) as exc:
        raise SourceContractError(
            "bundled INCOIS intermediate CA is missing or invalid"
        ) from exc

    configured = os.environ.get("INCOIS_CA_BUNDLE", "").strip()
    if configured:
        override = Path(configured).expanduser()
        if not override.is_file():
            logger.warning(
                "INCOIS_CA_BUNDLE=%s is not a file; using the verified bundled "
                "intermediate. TLS verification remains enabled.",
                override,
            )
        elif override.resolve() != _BUNDLED_INTERMEDIATE.resolve():
            try:
                context.load_verify_locations(cafile=str(override))
            except (OSError, ssl.SSLError) as exc:
                raise SourceContractError(
                    f"configured INCOIS_CA_BUNDLE is invalid: {override}"
                ) from exc

    # These are defaults from create_default_context; assert them explicitly so
    # a future refactor cannot silently weaken this source-specific trust path.
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise SourceContractError("INCOIS TLS context is not verification-enforcing")
    return context
