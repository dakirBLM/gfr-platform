from django.test import TestCase
from django.urls import reverse

from .models import Conference


class ConferenceSlugFallbackTests(TestCase):
    """Non-Latin conference titles must never produce an empty (or colliding) slug."""

    def test_arabic_title_gets_a_valid_unique_slug(self):
        a = Conference.objects.create(
            title='مؤتمر الابتكار العلمي', description='x',
            start_date='2026-09-01', end_date='2026-09-03',
        )
        b = Conference.objects.create(
            title='مؤتمر الابتكار العلمي', description='y',
            start_date='2026-10-01', end_date='2026-10-03',
        )
        self.assertTrue(a.slug)
        self.assertTrue(b.slug)
        self.assertNotEqual(a.slug, b.slug)
        self.assertEqual(reverse('dashboard:conference_detail', args=[a.slug]), f'/app/conferences/{a.slug}/')