import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import telegram_bot


class TelegramBotTest(unittest.TestCase):
    def test_partir_en_bloques_quita_html_y_respeta_limite(self) -> None:
        bloques = telegram_bot._partir_en_bloques("<b>Título</b>\n" + "x" * 15, 10)

        self.assertEqual(bloques, ["Título", "xxxxxxxxxx", "xxxxx"])
        self.assertTrue(all(len(bloque) <= 10 for bloque in bloques))

    @patch.dict(
        os.environ,
        {
            "RESPONDI_API_URL": "https://monia.example/",
            "RESPONDI_API_KEY": "rsp_test",
            "RESPONDI_CHANNEL_ID": "11111111-1111-4111-8111-111111111111",
            "TELEGRAM_CHAT_ID": "42",
        },
        clear=True,
    )
    @patch("telegram_bot.requests.get")
    @patch("telegram_bot.requests.post")
    def test_enviar_mensaje_espera_confirmacion(
        self, post: Mock, get: Mock
    ) -> None:
        post.return_value.json.return_value = {
            "messageId": "22222222-2222-4222-8222-222222222222"
        }
        get.return_value.json.side_effect = [
            {"deliveryStatus": "queued"},
            {"deliveryStatus": "sent"},
        ]

        with patch("telegram_bot.time.sleep"):
            telegram_bot.enviar_mensaje("<b>Resumen</b>")

        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["json"]["content"]["text"], "Resumen")
        self.assertEqual(get.call_count, 2)
        post.return_value.raise_for_status.assert_called_once()
        self.assertEqual(get.return_value.raise_for_status.call_count, 2)

    @patch.dict(
        os.environ,
        {
            "RESPONDI_API_URL": "https://monia.example",
            "RESPONDI_API_KEY": "rsp_test",
            "RESPONDI_CHANNEL_ID": "11111111-1111-4111-8111-111111111111",
            "TELEGRAM_CHAT_ID": "42",
        },
        clear=True,
    )
    @patch("telegram_bot.requests.get")
    @patch("telegram_bot.requests.post")
    def test_enviar_mensaje_falla_si_respondi_reporta_fallo(
        self, post: Mock, get: Mock
    ) -> None:
        post.return_value.json.return_value = {
            "messageId": "22222222-2222-4222-8222-222222222222"
        }
        get.return_value.json.return_value = {"deliveryStatus": "failed"}

        with self.assertRaises(RuntimeError):
            telegram_bot.enviar_mensaje("Resumen")


if __name__ == "__main__":
    unittest.main()
