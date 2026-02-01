# Dentro do arquivo de migração gerado:
from django.db import migrations, models

def convert_ratings(apps, schema_editor):
    Review = apps.get_model('vault', 'Review')
    UserLibraryEntry = apps.get_model('vault', 'UserLibraryEntry')

    # SE suas notas antigas eram 0-10 (ex: 8.5, 9.0):
    # Multiplicamos por 10 para virar 85, 90.
    for obj in Review.objects.filter(rating__isnull=False):
        obj.rating = int(obj.rating * 20)
        obj.save()
        
    for obj in UserLibraryEntry.objects.filter(rating__isnull=False):
        obj.rating = int(obj.rating * 20)
        obj.save()

class Migration(migrations.Migration):

    dependencies = [
        ('vault', '0003_notification'), # Não mexa aqui
    ]

    operations = [
        # 1. Primeiro converte os dados (ainda como float mas com valores altos)
        migrations.RunPython(convert_ratings),

        # 2. Depois altera a coluna para Integer
        migrations.AlterField(
            model_name='review',
            name='rating',
            field=models.IntegerField(blank=True, help_text='Armazenado como 0-100', null=True),
        ),
        migrations.AlterField(
            model_name='userlibraryentry',
            name='rating',
            field=models.IntegerField(blank=True, help_text='Armazenado como 0-100', null=True),
        ),
    ]
