import io
import json
import urllib.error
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.management import call_command
from habits.services import (
    query_semantic_intent_classifier,
    query_gemini_intent_classifier,
    query_groq_intent_classifier,
    query_ollama_intent_classifier,
    find_matching_predefined_template,
)


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


class CloudAndLocalAISemanticTests(TestCase):
    """Tests multi-provider cloud AI (Gemini Flash, Groq) and local Ollama semantic intent classifiers."""

    def setUp(self):
        self.fake_template = MagicMock()
        self.fake_template.name = "Consistent Morning Wake-Up"
        self.fake_template.category = "Health"
        self.fake_template.description = "Wake up at a set time"

    @override_settings(GEMINI_API_KEY="test-gemini-key")
    @patch("urllib.request.urlopen")
    def test_gemini_flash_classifier_success(self, mock_urlopen):
        mock_res = MagicMock()
        mock_res.read.return_value = json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "matches": True,
                            "matched_name": "Consistent Morning Wake-Up",
                            "confidence": 0.95,
                            "reason": "Rising early is waking up early."
                        })
                    }]
                }
            }]
        }).encode("utf-8")
        mock_res.__enter__.return_value = mock_res
        mock_urlopen.return_value = mock_res

        matched, conf, reason = query_gemini_intent_classifier(
            "Rise early tomorrow", active_templates=[self.fake_template]
        )

        self.assertIsNotNone(matched)
        self.assertEqual(matched.name, "Consistent Morning Wake-Up")
        self.assertGreaterEqual(conf, 0.9)
        # Verify URL calls Gemini 1.5 Flash endpoint
        req = mock_urlopen.call_args[0][0]
        self.assertIn("gemini-1.5-flash", req.full_url)
        self.assertIn("key=test-gemini-key", req.full_url)

    @override_settings(GEMINI_API_KEY="", GROQ_API_KEY="test-groq-key")
    @patch("urllib.request.urlopen")
    def test_groq_classifier_success(self, mock_urlopen):
        mock_res = MagicMock()
        mock_res.read.return_value = json.dumps({
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "matches": True,
                        "matched_name": "Consistent Morning Wake-Up",
                        "confidence": 0.92,
                        "reason": "Recognized as morning wake up."
                    })
                }
            }]
        }).encode("utf-8")
        mock_res.__enter__.return_value = mock_res
        mock_urlopen.return_value = mock_res

        matched, conf, reason = query_groq_intent_classifier(
            "Up at dawn", active_templates=[self.fake_template]
        )

        self.assertIsNotNone(matched)
        self.assertEqual(matched.name, "Consistent Morning Wake-Up")
        # Verify URL calls Groq API with Bearer token
        req = mock_urlopen.call_args[0][0]
        self.assertIn("api.groq.com", req.full_url)
        self.assertEqual(req.headers.get("Authorization"), "Bearer test-groq-key")

    @override_settings(GEMINI_API_KEY="", GROQ_API_KEY="", OLLAMA_BASE_URL="http://custom-ollama:11434")
    @patch("urllib.request.urlopen")
    def test_fallback_to_ollama_when_no_cloud_keys(self, mock_urlopen):
        mock_res = MagicMock()
        mock_res.read.return_value = json.dumps({
            "response": json.dumps({
                "matches": True,
                "matched_name": "Consistent Morning Wake-Up",
                "confidence": 0.88,
                "reason": "Ollama local match"
            })
        }).encode("utf-8")
        mock_res.__enter__.return_value = mock_res
        mock_urlopen.return_value = mock_res

        matched, conf, reason = query_semantic_intent_classifier(
            "Rise early at 5", active_templates=[self.fake_template]
        )

        self.assertIsNotNone(matched)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://custom-ollama:11434/api/generate")

    def test_tier_2_rise_early_synonym_without_any_ai(self):
        """Tests that Tier 2 regex instantly matches 'rise early' without calling any AI."""
        from habits.models import Habit
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(username="test_user_ai", password="password123")

        template = Habit.objects.create(
            name="Wake up early",
            created_by=user,
            is_template=True,
            is_active=True,
            category="Personal Development",
        )

        # use_ai=False to guarantee it is matched entirely by Tier 2 regex patterns
        matched = find_matching_predefined_template("rise early", use_ai=False)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.pk, template.pk)
