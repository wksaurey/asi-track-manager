from django.db import migrations

NEW_PALETTE = [
    '#dc2626', '#ea580c', '#d97706', '#ca8a04',
    '#65a30d', '#16a34a', '#059669', '#0d9488',
    '#0891b2', '#0284c7', '#2563eb', '#4f46e5',
    '#7c3aed', '#9333ea', '#c026d3', '#db2777',
]


def reassign_colors(apps, schema_editor):
    Asset = apps.get_model('cal', 'Asset')
    tracks = list(Asset.objects.filter(asset_type='track').order_by('pk'))
    for i, track in enumerate(tracks):
        track.color = NEW_PALETTE[i % len(NEW_PALETTE)]
        track.save(update_fields=['color'])


class Migration(migrations.Migration):

    dependencies = [
        ('cal', '0013_asset_color'),
    ]

    operations = [
        migrations.RunPython(reassign_colors, migrations.RunPython.noop),
    ]
