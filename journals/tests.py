from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from .models import Journal


class JournalSlugFallbackTests(TestCase):
    """Non-Latin journal names must never produce an empty (or colliding) slug."""

    def test_arabic_name_gets_a_valid_unique_slug(self):
        a = Journal.objects.create(name='مجلة البحث العلمي')
        b = Journal.objects.create(name='مجلة البحث العلمي')
        self.assertTrue(a.slug)
        self.assertTrue(b.slug)
        self.assertNotEqual(a.slug, b.slug)
        self.assertEqual(reverse('dashboard:journal_detail', args=[a.slug]), f'/app/journals/{a.slug}/')