from django.db import migrations
from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension

class Migration(migrations.Migration):

    dependencies = [
        ('vault', '0001_initial'), # Agora ele depende do 0001 novo que criamos
    ]

    operations = [
        TrigramExtension(),
        UnaccentExtension(),
    ]
