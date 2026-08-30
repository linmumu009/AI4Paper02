from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import arxiv_metadata_service  # noqa: E402
from services.arxiv_rate_limit import RateLimitExhausted  # noqa: E402


def _record_payload() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
      <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
        <GetRecord><record><header>
          <identifier>oai:arXiv.org:2608.00001</identifier>
        </header><metadata>
          <arXiv xmlns="http://arxiv.org/OAI/arXiv/">
            <id>2608.00001</id><created>2026-08-27</created>
            <authors><author><keyname>Example</keyname><forenames>Alice</forenames>
              <affiliation>Example University</affiliation>
            </author></authors>
            <title>Reliable agents</title>
            <categories>cs.AI</categories>
            <abstract>Complete abstract.</abstract>
          </arXiv>
        </metadata></record></GetRecord>
      </OAI-PMH>
    """


def _missing_payload() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
      <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
        <error code="idDoesNotExist">missing</error>
      </OAI-PMH>
    """


class ArxivMetadataServiceTests(unittest.TestCase):
    @staticmethod
    def _session() -> MagicMock:
        session = MagicMock()
        session.__enter__.return_value = session
        return session

    def test_lookup_uses_oai_base_id_and_preserves_requested_version(self) -> None:
        session = self._session()
        with (
            patch.object(
                arxiv_metadata_service,
                "build_arxiv_api_session",
                return_value=session,
            ),
            patch.object(
                arxiv_metadata_service,
                "_request_oai_record",
                return_value=_record_payload(),
            ) as fetch,
        ):
            result = arxiv_metadata_service.fetch_arxiv_metadata("2608.00001v2")

        self.assertEqual(fetch.call_args.args[1], "2608.00001")
        self.assertEqual(result["arxiv_id"], "2608.00001v2")
        self.assertEqual(result["title"], "Reliable agents")
        self.assertEqual(result["institution"], "Example University")
        self.assertEqual(result["year"], 2026)

    def test_missing_oai_record_maps_to_public_404(self) -> None:
        with (
            patch.object(
                arxiv_metadata_service,
                "build_arxiv_api_session",
                return_value=self._session(),
            ),
            patch.object(
                arxiv_metadata_service,
                "_request_oai_record",
                return_value=_missing_payload(),
            ),
        ):
            with self.assertRaises(
                arxiv_metadata_service.ArxivMetadataLookupError
            ) as raised:
                arxiv_metadata_service.fetch_arxiv_metadata("2608.99999")
        self.assertEqual(raised.exception.status_code, 404)

    def test_network_details_are_not_exposed(self) -> None:
        private_error = requests.exceptions.ConnectionError(
            "private upstream token sk-secret-value"
        )
        with (
            patch.object(
                arxiv_metadata_service,
                "build_arxiv_api_session",
                return_value=self._session(),
            ),
            patch.object(
                arxiv_metadata_service,
                "_request_oai_record",
                side_effect=private_error,
            ),
        ):
            with self.assertRaises(
                arxiv_metadata_service.ArxivMetadataLookupError
            ) as raised:
                arxiv_metadata_service.fetch_arxiv_metadata("2608.00001")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("private", str(raised.exception))
        self.assertNotIn("sk-secret", str(raised.exception))

    def test_rate_limit_maps_to_retryable_503(self) -> None:
        with (
            patch.object(
                arxiv_metadata_service,
                "build_arxiv_api_session",
                return_value=self._session(),
            ),
            patch.object(
                arxiv_metadata_service,
                "_request_oai_record",
                side_effect=RateLimitExhausted(),
            ),
        ):
            with self.assertRaises(
                arxiv_metadata_service.ArxivMetadataLookupError
            ) as raised:
                arxiv_metadata_service.fetch_arxiv_metadata("2608.00001")
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
