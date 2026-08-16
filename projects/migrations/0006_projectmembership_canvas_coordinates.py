from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_project_application_question'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectmembership',
            name='canvas_x',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='projectmembership',
            name='canvas_y',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
