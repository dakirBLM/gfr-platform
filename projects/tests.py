from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from .models import (
    MemberRole, Project, ProjectApplication, ProjectMembership,
    ProjectSection, ReviewStatus, Task, TaskStatus,
)


class GuarantorWorkflowTests(TestCase):
    def setUp(self):
        self.guarantor = User.objects.create_user('guarantor', 'g@example.com', 'password', role=Role.PROFESSOR)
        self.applicant = User.objects.create_user('applicant', 'a@example.com', 'password', role=Role.RESEARCHER)
        self.project = Project.objects.create(title='Structured study', description='A study', created_by=self.guarantor)
        ProjectMembership.objects.create(project=self.project, user=self.guarantor, role=MemberRole.OWNER)
        self.task = Task.objects.create(project=self.project, title='Collect sources')
        self.toggle_url = reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk])
        self.reopen_url = reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk])

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


class TaskCloseReopenGuardTests(GuarantorWorkflowTests):
    """A completed task must not be silently reopened via the approve checkmark."""

    def _make_done(self, review_status=ReviewStatus.NONE):
        self.task.status = TaskStatus.DONE
        self.task.review_status = review_status
        self.task.save(update_fields=['status', 'review_status'])
        self.client.force_login(self.guarantor)

    def test_toggle_closes_an_open_task(self):
        self.client.force_login(self.guarantor)
        self.client.post(self.toggle_url)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_toggle_cannot_reopen_a_done_task(self):
        self._make_done()
        self.client.post(self.toggle_url)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_toggle_ignores_get_requests(self):
        self.client.force_login(self.guarantor)
        response = self.client.get(self.toggle_url)
        self.assertEqual(response.status_code, 405)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)

    def test_reopen_resets_an_approved_task_to_todo(self):
        self._make_done(review_status=ReviewStatus.APPROVED)
        self.client.post(self.reopen_url)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)
        self.assertEqual(self.task.review_status, ReviewStatus.NONE)

    def test_reopen_keeps_unreviewed_done_task_as_none(self):
        self._make_done(review_status=ReviewStatus.NONE)
        self.client.post(self.reopen_url)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)
        self.assertEqual(self.task.review_status, ReviewStatus.NONE)

    def test_reopen_rejects_an_open_task(self):
        self.client.force_login(self.guarantor)
        self.client.post(self.reopen_url)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)

    def test_reopen_requires_manager(self):
        self._make_done()
        self.client.force_login(self.applicant)
        response = self.client.post(self.reopen_url)
        self.assertEqual(response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)
