"""
Data migration: seed default track assets.

Creates Asset objects of type='track' for each of the seven default tracks
if they do not already exist.
"""

from django.db import migrations

DEFAULT_TRACKS = [
    'Figure Eight',
    'Main Track',
    'Vineyard',
    'Mining Loop',
    'Dirt Track',
    'West Field(N)',
    'South Field',
]


def seed_tracks(apps, schema_editor):
    Asset = apps.get_model('cal', 'Asset')
    for name in DEFAULT_TRACKS:
        Asset.objects.get_or_create(
            name=name,
            defaults={'asset_type': 'track'},
        )


def unseed_tracks(apps, schema_editor):
    """Reverse: remove only the tracks that were created by this migration."""
    Asset = apps.get_model('cal', 'Asset')
    Asset.objects.filter(name__in=DEFAULT_TRACKS, asset_type='track').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cal', '0008_remove_asset_is_active'),
    ]

    operations = [
        migrations.RunPython(seed_tracks, reverse_code=unseed_tracks),
    ]
