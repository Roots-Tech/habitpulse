import io
import json
import urllib.error
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.management import call_command
from habits.services import query_ollama_intent_classifier


class SetupOllamaCommandTests(TestCase):
    """Tests for setup_ollama management command and Ollama Docker integration."""

    @patch("urllib.request.urlopen")
    def test_setup_ollama_connection_error(self, mock_urlopen):
        """Tests setup_ollama gracefully handles unreachable Ollama instance."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        out = io.StringIO()
        call_command("setup_ollama", stdout=out)
        output = out.getvalue()

        self.assertIn("Connecting to Ollama at:", output)
        self.assertIn("Unable to connect to Ollama", output)

    @patch("urllib.request.urlopen")
    def test_setup_ollama_model_present(self, mock_urlopen):
        """Tests setup_ollama recognizes existing model."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "models": [{"name": "llama3.2:1b:latest"}]
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        out = io.StringIO()
        call_command("setup_ollama", stdout=out)
        output = out.getvalue()

        self.assertIn("Connected to Ollama!", output)
        self.assertIn("is present and ready", output)

    @patch("urllib.request.urlopen")
    def test_setup_ollama_pull_flag(self, mock_urlopen):
        """Tests setup_ollama --pull triggers pull request when model is missing."""
        mock_tags_res = MagicMock()
        mock_tags_res.read.return_value = json.dumps({"models": []}).encode("utf-8")
        mock_tags_res.__enter__.return_value = mock_tags_res

        mock_pull_res = MagicMock()
        mock_pull_res.read.return_value = json.dumps({"status": "success"}).encode("utf-8")
        mock_pull_res.__enter__.return_value = mock_pull_res

        mock_urlopen.side_effect = [mock_tags_res, mock_pull_res]

        out = io.StringIO()
        call_command("setup_ollama", pull=True, stdout=out)
        output = out.getvalue()

        self.assertIn("Model 'llama3.2:1b' not found locally. Initiating pull...", output)
        self.assertIn("Pull completed: success", output)


class OllamaSettingsAndDynamicUrlTests(TestCase):
    """Tests dynamic Ollama URL and model configuration in services."""

    @override_settings(OLLAMA_BASE_URL="http://custom-ollama-host:11434", OLLAMA_MODEL="custom-llama:1b")
    @patch("urllib.request.urlopen")
    def test_query_ollama_uses_dynamic_settings(self, mock_urlopen):
        mock_res = MagicMock()
        mock_res.read.return_value = json.dumps({
            "response": '{"matches": false}'
        }).encode("utf-8")
        mock_res.__enter__.return_value = mock_res
        mock_urlopen.return_value = mock_res

        fake_template = MagicMock()
        fake_template.name = "Daily Deep Hydration"
        fake_template.category = "Health"
        fake_template.description = "Drink water"

        query_ollama_intent_classifier("Some unusual habit", active_templates=[fake_template])

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://custom-ollama-host:11434/api/generate")

        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["model"], "custom-llama:1b")
