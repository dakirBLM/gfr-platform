from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from .models import MemberRole, Project, ProjectApplication, ProjectMembership, ProjectSection, ReviewStatus, Task, TaskStatus


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


class ProjectCanvasTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('canvas-owner', 'owner@example.com', 'password', role=Role.PROFESSOR)
        self.member = User.objects.create_user('canvas-member', 'member@example.com', 'password', role=Role.RESEARCHER)
        self.outsider = User.objects.create_user('canvas-outsider', 'outsider@example.com', 'password', role=Role.RESEARCHER)
        self.project = Project.objects.create(title='Canvas study', description='A map of our work.', created_by=self.owner)
        self.owner_membership = ProjectMembership.objects.create(project=self.project, user=self.owner, role=MemberRole.OWNER)
        self.member_membership = ProjectMembership.objects.create(project=self.project, user=self.member, role=MemberRole.MEMBER)
        self.task = Task.objects.create(project=self.project, title='Map the cohort', assigned_to=self.member, status=TaskStatus.IN_PROGRESS)

    def test_canvas_is_member_only_and_contains_owner_and_work(self):
        canvas_url = reverse('dashboard:project_canvas', args=[self.project.slug])
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(canvas_url).status_code, 404)

        self.client.force_login(self.owner)
        response = self.client.get(canvas_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Project Canvas')
        self.assertContains(response, 'canvas-owner')
        self.assertContains(response, 'Map the cohort')

    def test_canvas_position_is_saved_for_project_members_only(self):
        url = reverse('dashboard:project_canvas_position', args=[self.project.slug, self.member.pk])
        self.client.force_login(self.member)
        response = self.client.post(url, data=json.dumps({'x': 31.5, 'y': 68.25}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.canvas_x, 31.5)
        self.assertEqual(self.member_membership.canvas_y, 68.25)

        owner_url = reverse('dashboard:project_canvas_position', args=[self.project.slug, self.owner.pk])
        response = self.client.post(owner_url, data=json.dumps({'x': 44, 'y': 52}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.canvas_x, 44)

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(url, data=json.dumps({'x': 45, 'y': 50}), content_type='application/json').status_code, 404)


class TaskCloseReopenGuardTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user('mgr', 'mgr@example.com', 'password', role=Role.PROFESSOR)
        self.member = User.objects.create_user('member', 'member@example.com', 'password', role=Role.RESEARCHER)
        self.project = Project.objects.create(title='Guard study', description='A study', created_by=self.manager)
        ProjectMembership.objects.create(project=self.project, user=self.manager, role=MemberRole.OWNER)
        ProjectMembership.objects.create(project=self.project, user=self.member, role=MemberRole.MEMBER)
        self.task = Task.objects.create(project=self.project, title='Survey', assigned_to=self.member)

    def test_completed_task_cannot_be_reopened_by_approve_checkmark(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.manager)
        response = self.client.post(reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_completed_task_toggle_posts_are_ignored(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.manager)
        for _ in range(3):
            self.client.post(reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_toggle_task_requires_post(self):
        self.client.force_login(self.manager)
        url = reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)

    def test_open_task_can_still_be_marked_done_by_manager(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('dashboard:project_toggle_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_reopen_task_route_reopens_completed_task(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.manager)
        response = self.client.post(reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)
        self.assertEqual(response.status_code, 302)

    def test_reopen_task_clears_approval_badge(self):
        self.task.status = TaskStatus.DONE
        self.task.review_status = ReviewStatus.APPROVED
        self.task.save(update_fields=['status', 'review_status'])
        self.client.force_login(self.manager)
        self.client.post(reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)
        self.assertEqual(self.task.review_status, ReviewStatus.NONE)

    def test_reopen_task_only_for_completed_tasks(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.TODO)

    def test_reopen_task_requires_manager(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.member)
        response = self.client.post(reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk]))
        self.assertEqual(response.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)

    def test_reopen_task_requires_post(self):
        self.task.status = TaskStatus.DONE
        self.task.save(update_fields=['status'])
        self.client.force_login(self.manager)
        url = reverse('dashboard:project_reopen_task', args=[self.project.slug, self.task.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DONE)
