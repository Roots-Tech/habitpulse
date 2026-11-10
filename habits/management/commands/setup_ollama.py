import json
import urllib.request
import urllib.error
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Verifies Ollama connectivity and pulls/verifies the required local AI model on the server."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pull",
            action="store_true",
            default=False,
            help="Automatically pull the model if not already present in Ollama.",
        )
        parser.add_argument(
            "--model",
            type=str,
            default="",
            help="Target model to check/pull (defaults to OLLAMA_MODEL setting).",
        )
        parser.add_argument(
            "--test",
            action="store_true",
            default=False,
            help="Run a sample classification query against Ollama.",
        )

    def handle(self, *args, **options):
        ollama_base = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        target_model = options["model"] or getattr(settings, "OLLAMA_MODEL", "llama3.2:1b")
        should_pull = options["pull"]
        run_test = options["test"]

        self.stdout.write(self.style.NOTICE(f"Connecting to Ollama at: {ollama_base}"))
        self.stdout.write(self.style.NOTICE(f"Target model: {target_model}"))

        # 1. Check server health
        tags_url = f"{ollama_base}/api/tags"
        try:
            req = urllib.request.Request(tags_url)
            with urllib.request.urlopen(req, timeout=5.0) as res:
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.URLError as e:
            self.stdout.write(
                self.style.ERROR(f"Unable to connect to Ollama ({e}). Ensure Ollama service/container is running.")
            )
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error checking Ollama status: {e}"))
            return

        available_models = [m.get("name", "") for m in data.get("models", [])]
        self.stdout.write(self.style.SUCCESS(f"Connected to Ollama! Available models: {available_models or 'None'}"))

        # 2. Check if model exists
        model_exists = any(target_model in m or m.startswith(target_model) for m in available_models)

        if not model_exists:
            if should_pull:
                self.stdout.write(self.style.WARNING(f"Model '{target_model}' not found locally. Initiating pull..."))
                pull_url = f"{ollama_base}/api/pull"
                pull_payload = json.dumps({"name": target_model, "stream": False}).encode("utf-8")
                try:
                    req_pull = urllib.request.Request(
                        pull_url,
                        data=pull_payload,
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req_pull, timeout=300.0) as pull_res:
                        pull_data = json.loads(pull_res.read().decode("utf-8"))
                        status = pull_data.get("status", "completed")
                        self.stdout.write(self.style.SUCCESS(f"Pull completed: {status}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to pull model '{target_model}': {e}"))
                    return
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Model '{target_model}' is not pulled yet. Run with --pull to download it into Ollama."
                    )
                )
                return
        else:
            self.stdout.write(self.style.SUCCESS(f"Model '{target_model}' is present and ready."))

        # 3. Optional test classification
        if run_test:
            self.stdout.write(self.style.NOTICE("Executing sample intent classification test..."))
            from habits.services import query_ollama_intent_classifier

            matched, conf, reason = query_ollama_intent_classifier("Guzzle 2L water", timeout=10.0)
            if matched:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Classification Successful! Matched: '{matched.name}' (Confidence: {conf:.2f}, Reason: {reason})"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING("Test ran but no template matched (or catalog empty)."))
