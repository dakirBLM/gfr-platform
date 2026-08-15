"""
Ask Gemini one throwaway question and report exactly what came back.

When Sandy answers "Sandy could not reply right now", the cause is upstream:
a missing or rejected key, a model name the key cannot use, or an exhausted
quota. This command surfaces that reason directly instead of leaving it in the
server log.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from dashboard.views import GEMINI_DEFAULT_MODEL, GeminiUnavailable, _gemini_generate


class Command(BaseCommand):
    help = 'Verify that the configured Gemini key and model can answer a request.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--message', default='Reply with the single word: ready.',
            help='Prompt to send instead of the default probe.',
        )

    def handle(self, *args, **options):
        model = getattr(settings, 'GEMINI_MODEL', '') or GEMINI_DEFAULT_MODEL
        key = settings.GEMINI_API_KEY or ''
        if not key:
            self.stdout.write(self.style.ERROR(
                'GEMINI_API_KEY is empty. Sandy chat will answer 503 until it is set.'
            ))
            return

        self.stdout.write(f'Model: {model}')
        self.stdout.write(f'Key:   {key[:4]}…{key[-4:]} ({len(key)} characters)')

        try:
            reply = _gemini_generate('You are a health check.', [], options['message'])
        except GeminiUnavailable as error:
            self.stdout.write(self.style.ERROR(f'Gemini call failed: {error}'))
            return

        self.stdout.write(self.style.SUCCESS(f'Gemini replied: {reply}'))
