# Generated manually for subtrack support

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cal', '0008_remove_asset_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='parent',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='subtracks',
                to='cal.asset',
                help_text='Parent track (only for subtracks)',
            ),
        ),
    ]
