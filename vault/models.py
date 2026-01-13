import uuid  # <--- Importante
from django.db import models
from django.contrib.auth.models import User

# 1. A Fonte da Verdade (Vem do IGDB)
class MasterGame(models.Model):
    # UUID como chave primária
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    igdb_id = models.BigIntegerField(unique=True, help_text="ID único do jogo no IGDB")
    title = models.CharField(max_length=255)
    cover_url = models.URLField(blank=True, null=True)
    release_date = models.DateField(blank=True, null=True)
    genres = models.JSONField(default=list)
    
    def __str__(self):
        return self.title

# 2. As Plataformas
class Platform(models.Model):
    # Plataformas são poucas, ID numérico aqui não tem problema, mas vamos padronizar
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    slug = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=50)
    
    def __str__(self):
        return self.name

# 3. O Jogo na Plataforma
class PlatformGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    master_game = models.ForeignKey(MasterGame, on_delete=models.CASCADE, related_name='platforms')
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=255)
    external_title = models.CharField(max_length=255)
    
    class Meta:
        unique_together = ('platform', 'external_id')

# 4. A Biblioteca do Usuário
class UserLibraryEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='library')
    platform_game = models.ForeignKey(PlatformGame, on_delete=models.CASCADE)
    
    STATUS_CHOICES = [
        ('backlog', 'Backlog'),
        ('playing', 'Jogando'),
        ('completed', 'Zerado'),
        ('dropped', 'Largado'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='backlog')
    playtime_minutes = models.IntegerField(default=0)
    last_played = models.DateTimeField(blank=True, null=True)
    last_synced = models.DateTimeField(auto_now=True)
    
    rating = models.IntegerField(null=True, blank=True)
    review_text = models.TextField(blank=True)
    
    @property
    def playtime_hours(self):
        if self.playtime_minutes:
            return round(self.playtime_minutes / 60, 1)
        return 0

# 5. Conquistas
class Achievement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    platform_game = models.ForeignKey(PlatformGame, on_delete=models.CASCADE, related_name='achievements')
    external_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    description = models.TextField()
    icon_url = models.URLField(blank=True, null=True)
    is_hidden = models.BooleanField(default=False)
    xp_value = models.IntegerField(default=0)

class UserAchievement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    unlocked_at = models.DateTimeField()
    
    class Meta:
        unique_together = ('user', 'achievement')