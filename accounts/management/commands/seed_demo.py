"""
Creates demo researcher accounts so the directory has content to browse.
Safe to run multiple times (skips existing usernames).
"""
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from accounts.models import ResearchInterest, Role, User

DEMO_USERS = [
    {
        'username': 'omar_ibrahim',
        'first_name': 'Omar', 'last_name': 'Ibrahim',
        'email': 'omar@demo.gfr', 'role': Role.PROFESSOR,
        'affiliation': 'Cairo University', 'country': 'Egypt',
        'headline': 'Professor of Artificial Intelligence and Decision Systems',
        'biography': 'My research focuses on AI applications in healthcare diagnostics and resource-constrained settings.',
        'interests': ['Artificial Intelligence', 'Healthcare Informatics', 'Decision Systems'],
        'orcid': '0000-0001-2345-6789',
    },
    {
        'username': 'lena_vogel',
        'first_name': 'Lena', 'last_name': 'Vogel',
        'email': 'lena@demo.gfr', 'role': Role.RESEARCHER,
        'affiliation': 'Max Planck Institute', 'country': 'Germany',
        'headline': 'Computational neuroscientist studying neural coding',
        'biography': 'I develop probabilistic models of sensory perception in the visual cortex.',
        'interests': ['Computational Neuroscience', 'Machine Learning', 'Vision Science'],
    },
    {
        'username': 'juan_reyes',
        'first_name': 'Juan', 'last_name': 'Reyes',
        'email': 'juan@demo.gfr', 'role': Role.RESEARCHER,
        'affiliation': 'Universidad Nacional de Colombia', 'country': 'Colombia',
        'headline': 'Climate scientist and sustainable agriculture researcher',
        'biography': 'Studying the effects of extreme weather events on Andean agricultural systems.',
        'interests': ['Climate Science', 'Sustainable Agriculture', 'Remote Sensing'],
    },
    {
        'username': 'fatima_nasser',
        'first_name': 'Fatima', 'last_name': 'Nasser',
        'email': 'fatima@demo.gfr', 'role': Role.REVIEWER,
        'affiliation': 'King Abdullah University of Science and Technology', 'country': 'Saudi Arabia',
        'headline': 'Materials scientist and peer reviewer',
        'biography': 'Research in 2D nanomaterials and their energy storage applications.',
        'interests': ['Nanomaterials', 'Energy Storage', 'Materials Science'],
        'orcid': '0000-0003-5678-9012',
    },
    {
        'username': 'yuki_tanaka',
        'first_name': 'Yuki', 'last_name': 'Tanaka',
        'email': 'yuki@demo.gfr', 'role': Role.PROFESSOR,
        'affiliation': 'University of Tokyo', 'country': 'Japan',
        'headline': 'Quantum computing and cryptography researcher',
        'biography': 'Working on post-quantum cryptographic protocols and their formal verification.',
        'interests': ['Quantum Computing', 'Cryptography', 'Formal Methods'],
    },
    {
        'username': 'sofia_rossi',
        'first_name': 'Sofia', 'last_name': 'Rossi',
        'email': 'sofia@demo.gfr', 'role': Role.STUDENT,
        'affiliation': 'Politecnico di Milano', 'country': 'Italy',
        'headline': 'PhD candidate in urban mobility and autonomous systems',
        'biography': 'Exploring multi-agent reinforcement learning for urban traffic optimization.',
        'interests': ['Reinforcement Learning', 'Urban Mobility', 'Multi-agent Systems'],
    },
    {
        'username': 'kwame_asante',
        'first_name': 'Kwame', 'last_name': 'Asante',
        'email': 'kwame@demo.gfr', 'role': Role.RESEARCHER,
        'affiliation': 'University of Ghana', 'country': 'Ghana',
        'headline': 'Epidemiologist studying infectious disease dynamics in West Africa',
        'biography': 'Building computational models for malaria and dengue fever spread in tropical climates.',
        'interests': ['Epidemiology', 'Infectious Diseases', 'Public Health', 'Bioinformatics'],
    },
    {
        'username': 'mei_lin',
        'first_name': 'Mei', 'last_name': 'Lin',
        'email': 'mei@demo.gfr', 'role': Role.EDITOR,
        'affiliation': 'Tsinghua University', 'country': 'China',
        'headline': 'Journal editor — Natural Language Processing and Computational Linguistics',
        'biography': 'Research in cross-lingual transfer learning and low-resource NLP for under-represented languages.',
        'interests': ['Natural Language Processing', 'Machine Learning', 'Computational Linguistics'],
        'orcid': '0000-0002-8765-4321',
    },
]


class Command(BaseCommand):
    help = 'Create demo researcher accounts for browsing the directory.'

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        password = make_password('Demo!2024gfr')

        for data in DEMO_USERS:
            interests = data.pop('interests', [])
            orcid = data.pop('orcid', '')

            if User.objects.filter(username=data['username']).exists():
                skipped += 1
                self.stdout.write(f"  skip  {data['username']}")
                data['interests'] = interests
                data['orcid'] = orcid
                continue

            user = User(**data, password=password, accepted_ethics_code=True)
            if orcid:
                user.orcid = orcid
            user.save()

            interest_objs = []
            for name in interests:
                obj = ResearchInterest.get_or_create_by_name(name)
                if obj:
                    interest_objs.append(obj)
            user.interests.set(interest_objs)

            created += 1
            self.stdout.write(f"  create {user.username}")

        self.stdout.write(self.style.SUCCESS(
            f'\nDone — {created} created, {skipped} skipped.'
        ))
