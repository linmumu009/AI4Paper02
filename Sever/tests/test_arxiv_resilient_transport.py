from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from requests.adapters import HTTPAdapter


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller import http_session  # noqa: E402


def _prepared(url: str, method: str = "GET"):
    return requests.Request(method, url, headers={"User-Agent": "test"}).prepare()


def _response(status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.url = "https://arxiv.org/list/cs.AI/new"
    return response


class ArxivResilientTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        http_session._reset_arxiv_circuit_for_tests()

    def tearDown(self) -> None:
        http_session._reset_arxiv_circuit_for_tests()

    def test_connection_failure_opens_circuit_and_next_request_skips_direct(self) -> None:
        adapter = http_session.ArxivResilientAdapter(max_retries=0)
        fallback_response = _response()
        fallback_response.ai4papers_transport = "fastly_verified"
        with (
            patch.object(
                HTTPAdapter,
                "send",
                side_effect=requests.exceptions.ConnectionError("tls reset"),
            ) as direct,
            patch.object(
                adapter,
                "_send_via_verified_fastly",
                return_value=fallback_response,
            ) as fallback,
        ):
            first = adapter.send(_prepared("https://arxiv.org/list/cs.AI/new"))
            second = adapter.send(_prepared("https://oaipmh.arxiv.org/oai?verb=Identify"))

        self.assertEqual(first.ai4papers_transport, "fastly_verified")
        self.assertEqual(second.ai4papers_transport, "fastly_verified")
        self.assertEqual(direct.call_count, 1)
        self.assertEqual(fallback.call_count, 2)
        self.assertTrue(http_session._circuit_is_open())

    def test_http_error_response_does_not_open_transport_circuit(self) -> None:
        adapter = http_session.ArxivResilientAdapter(max_retries=0)
        response_429 = _response(429)
        with (
            patch.object(HTTPAdapter, "send", return_value=response_429),
            patch.object(adapter, "_send_via_verified_fastly") as fallback,
        ):
            result = adapter.send(_prepared("https://arxiv.org/list/cs.AI/new"))

        self.assertEqual(result.status_code, 429)
        fallback.assert_not_called()
        self.assertFalse(http_session._circuit_is_open())

    def test_unrelated_hosts_never_use_arxiv_fallback(self) -> None:
        adapter = http_session.ArxivResilientAdapter(max_retries=0)
        with (
            patch.object(
                HTTPAdapter,
                "send",
                side_effect=requests.exceptions.ConnectionError("offline"),
            ),
            patch.object(adapter, "_send_via_verified_fastly") as fallback,
        ):
            with self.assertRaises(requests.exceptions.ConnectionError):
                adapter.send(_prepared("https://example.com/data"))
        fallback.assert_not_called()

    def test_verified_route_pins_tls_name_and_encrypts_original_host_header(self) -> None:
        adapter = http_session.ArxivResilientAdapter(max_retries=0)
        raw = Mock()
        raw.status = 200
        raw.headers = {"Content-Type": "text/xml"}
        raw.reason = "OK"
        pool = Mock()
        pool.urlopen.return_value = raw
        request = _prepared(
            "https://oaipmh.arxiv.org/oai?verb=Identify&metadataPrefix=arXiv"
        )

        with (
            patch.object(
                http_session,
                "_resolved_fastly_ips",
                return_value=["151.101.3.42"],
            ),
            patch.object(
                http_session.urllib3,
                "HTTPSConnectionPool",
                return_value=pool,
            ) as pool_factory,
        ):
            response = adapter._send_via_verified_fastly(
                request,
                timeout=60,
                verify=True,
            )

        args, kwargs = pool_factory.call_args
        self.assertEqual(args[0], "151.101.3.42")
        self.assertEqual(kwargs["cert_reqs"], "CERT_REQUIRED")
        self.assertEqual(
            kwargs["assert_hostname"],
            "s.sni-810-default.ssl.fastly.net",
        )
        self.assertEqual(
            kwargs["server_hostname"],
            "s.sni-810-default.ssl.fastly.net",
        )
        _, target = pool.urlopen.call_args.args[:2]
        request_kwargs = pool.urlopen.call_args.kwargs
        self.assertEqual(
            target,
            "/oai?verb=Identify&metadataPrefix=arXiv",
        )
        self.assertEqual(request_kwargs["headers"]["Host"], "oaipmh.arxiv.org")
        self.assertFalse(request_kwargs["redirect"])
        self.assertEqual(response.ai4papers_transport, "fastly_verified")

    def test_verified_route_refuses_disabled_certificate_validation(self) -> None:
        adapter = http_session.ArxivResilientAdapter(max_retries=0)
        with self.assertRaises(requests.exceptions.SSLError):
            adapter._send_via_verified_fastly(
                _prepared("https://arxiv.org/list/cs.AI/new"),
                timeout=60,
                verify=False,
            )

    def test_build_session_does_not_delete_process_proxy_environment(self) -> None:
        with (
            patch.dict(
                http_session.os.environ,
                {"HTTPS_PROXY": "http://proxy.invalid:8080"},
                clear=False,
            ),
            patch.object(http_session, "PROXIES", None),
            patch.object(http_session, "RESPECT_ENV_PROXIES", False),
        ):
            session = http_session.build_session()
            self.assertFalse(session.trust_env)
            self.assertEqual(
                http_session.os.environ["HTTPS_PROXY"],
                "http://proxy.invalid:8080",
            )


if __name__ == "__main__":
    unittest.main()
