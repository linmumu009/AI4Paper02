from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.network_target_guard import OutboundURLRejected  # noqa: E402


class LlmClientFactorySafetyTests(unittest.TestCase):
    def test_build_rejects_private_target_before_client_creation(self) -> None:
        from services.llm_client_factory import build_llm_client

        with (
            patch("services.llm_client_factory.OpenAI") as openai,
            self.assertRaises(OutboundURLRejected),
        ):
            build_llm_client(
                {
                    "llm_api_key": "not-a-real-key",
                    "llm_base_url": "https://169.254.169.254/latest/meta-data",
                    "llm_model": "example-model",
                }
            )
        openai.assert_not_called()

    def test_build_uses_normalized_public_target(self) -> None:
        from services.llm_client_factory import build_llm_client

        with (
            patch(
                "services.llm_client_factory.validate_user_llm_base_url",
                return_value="https://api.example.com/v1",
            ) as validate,
            patch("services.llm_client_factory.OpenAI") as openai,
        ):
            build_llm_client(
                {
                    "llm_api_key": "not-a-real-key",
                    "llm_base_url": " HTTPS://API.Example.COM/v1/ ",
                    "llm_model": "example-model",
                }
            )
        validate.assert_called_once_with("HTTPS://API.Example.COM/v1/")
        openai.assert_called_once_with(
            api_key="not-a-real-key",
            base_url="https://api.example.com/v1",
        )


if __name__ == "__main__":
    unittest.main()
