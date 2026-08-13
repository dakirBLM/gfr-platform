from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from .models import MemberRole, Project, ProjectApplication, ProjectMembership, ProjectSection, Task


class SlugFallbackTests(TestCase):
    """Non-Latin titles must never produce an empty (or colliding) slug."""

    def setUp(self):
        self.user = User.objects.create_user('slugger', 'slug@example.com', 'password', role=Role.PROFESSOR)

    def test_arabic_title_gets_a_valid_unique_slug(self):
        a = Project.objects.create(title='دراسة بحثية', description='x', created_by=self.user)
        b = Project.objects.create(title='دراسة بحثية', description='y', created_by=self.user)
        self.assertTrue(a.slug)
        self.assertTrue(b.slug)
        self.assertNotEqual(a.slug, b.slug)
        self.assertNotEqual(a.slug, '')
        self.assertNotEqual(b.slug, '')
        # Both URLs must resolve.
        self.assertEqual(reverse('dashboard:project_detail', args=[a.slug]), f'/app/projects/{a.slug}/')
        self.assertEqual(reverse('dashboard:project_detail', args=[b.slug]), f'/app/projects/{b.slug}/')


class GuarantorWorkflowTests(TestCase):
    def setUp(self):
        self.guarantor = User.objects.create_user('guarantor', 'g@example.com', 'password', role=Role.PROFESSOR)
        self.applicant = User.objects.create_user('applicant', 'a@example.com', 'password', role=Role.RESEARCHER)
        self.project = Project.objects.create(title='Structured study', description='A study', created_by=self.guarantor)
        ProjectMembership.objects.create(project=self.project, user=self.guarantor, role=MemberRole.OWNER)

    def test_application_requires_guarantor_acceptance_before_membership(self):
        self.client.force_login(self.applicant)
        response = self.client.post(reverse('dashboard:project_join', args=[self.project.slug]), {
            'message': 'I work in this area.', 'answer': 'I can analyse the data.',
        })
        self.assertRedirects(response, reverse('dashboard:project_detail', args=[self.project.slug]))
        application = ProjectApplication.objects.get(project=self.project, applicant=self.applicant)
        self.assertEqual(application.status, ProjectApplication.Status.PENDING)
        self.assertFalse(ProjectMembership.objects.filter(project=self.project, user=self.applicant).exists())

        self.client.force_login(self.guarantor)
        self.client.post(reverse('dashboard:project_review_application', args=[self.project.slug, application.pk, 'accept']))
        self.assertTrue(ProjectMembership.objects.filter(project=self.project, user=self.applicant).exists())
        application.refresh_from_db()
        self.assertEqual(application.status, ProjectApplication.Status.ACCEPTED)

    def test_task_belongs_to_a_guarantor_section(self):
        section = ProjectSection.objects.create(project=self.project, title='Data collection', order=1)
        task = Task.objects.create(project=self.project, section=section, title='Collect sources')
        self.assertEqual(task.section.title, 'Data collection')
