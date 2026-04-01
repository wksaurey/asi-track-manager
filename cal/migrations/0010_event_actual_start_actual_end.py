from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('cal', '0009_seed_default_tracks'),
    ]
    operations = [
        migrations.AddField(
            model_name='event',
            name='actual_start',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='actual_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
