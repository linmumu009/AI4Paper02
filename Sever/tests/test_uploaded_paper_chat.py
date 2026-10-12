import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from routers import paper_router as router


class UploadedPaperChatTests(unittest.TestCase):
    def test_owned_upload_reaches_chat_stream(self):
        with patch.object(router.user_paper_service, "get_paper", return_value={"paper_id": "up_owned"}) as uploaded, patch.object(router.data_service, "get_paper_detail") as feed, patch.object(router.entitlement_service, "reserve_quota", return_value={}) as quota, patch.object(router.chat_service, "stream_chat", return_value=iter([])) as stream:
            response = router.api_post_paper_chat("up_owned", router.PaperChatBody(message="Explain"), {"id": 7})
            self.assertEqual(response.media_type, "text/event-stream")
            uploaded.assert_called_once_with(7, "up_owned")
            feed.assert_not_called()
            quota.assert_called_once_with(7, "chat")
            self.assertEqual(stream.call_args.args[:3], (7, "up_owned", "Explain"))

    def test_missing_or_other_users_upload_does_not_charge_or_fallback(self):
        with patch.object(router.user_paper_service, "get_paper", return_value=None) as uploaded, patch.object(router.data_service, "get_paper_detail") as feed, patch.object(router.entitlement_service, "reserve_quota") as quota, patch.object(router.chat_service, "stream_chat") as stream:
            with self.assertRaises(HTTPException) as error:
                router.api_post_paper_chat("up_private", router.PaperChatBody(message="Explain"), {"id": 8})
            self.assertEqual(error.exception.status_code, 404)
            uploaded.assert_called_once_with(8, "up_private")
            feed.assert_not_called()
            quota.assert_not_called()
            stream.assert_not_called()

    def test_regular_paper_keeps_existing_lookup(self):
        with patch.object(router.user_paper_service, "get_paper") as uploaded, patch.object(router.data_service, "get_paper_detail", return_value={}) as feed, patch.object(router.entitlement_service, "reserve_quota", return_value={}), patch.object(router.chat_service, "stream_chat", return_value=iter([])):
            router.api_post_paper_chat("2601.12345", router.PaperChatBody(message="Explain"), {"id": 7})
            feed.assert_called_once_with("2601.12345", user_id=7)
            uploaded.assert_not_called()


if __name__ == "__main__":
    unittest.main()
