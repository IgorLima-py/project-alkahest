# BLOCO 1: IMPORTAÇÕES
import uuid
from django.db import models
from django.contrib.auth.models import User
import markdown
import bleach

# BLOCO 2: PERFIL
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True, max_length=500)
    avatar_url = models.URLField(blank=True, null=True)
    stat_volume = models.IntegerField(default=0)
    stat_skill = models.IntegerField(default=0)
    stat_variety = models.IntegerField(default=0)
    stat_social = models.IntegerField(default=0)
    stat_speed = models.IntegerField(default=0)

    def __str__(self):
        return f"Perfil de {self.user.username}"

# BLOCO 3: MASTER GAME
class MasterGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    igdb_id = models.BigIntegerField(unique=True, db_index=True) # Indexado para busca rápida
    title = models.CharField(max_length=255, db_index=True)      # Indexado para autocomplete
    cover_url = models.URLField(blank=True, null=True)
    release_date = models.DateField(blank=True, null=True)
    genres = models.JSONField(default=list)
    
    def __str__(self):
        return self.title

class Platform(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=50)
    
    def __str__(self):
        return self.name

class PlatformGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    master_game = models.ForeignKey(MasterGame, on_delete=models.CASCADE, related_name='platforms')
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=255)
    external_title = models.CharField(max_length=255)
    
    class Meta:
        unique_together = ('platform', 'external_id')

# BLOCO 4: LIBRARY
class UserLibraryEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='library', db_index=True)
    platform_game = models.ForeignKey(PlatformGame, on_delete=models.CASCADE)
    
    STATUS_CHOICES = [
        ('backlog', 'Backlog'),
        ('playing', 'Jogando'),
        ('completed', 'Zerado'),
        ('dropped', 'Largado'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='backlog', db_index=True)
    playtime_minutes = models.IntegerField(default=0)
    # Índices críticos para ordenação da biblioteca
    last_played = models.DateTimeField(blank=True, null=True, db_index=True)
    last_synced = models.DateTimeField(auto_now=True)
    rating = models.FloatField(null=True, blank=True, db_index=True) 
    
    is_favorite = models.BooleanField(default=False)
    is_recommended = models.BooleanField(null=True, blank=True)
    
    # Legado
    review_text = models.TextField(blank=True, null=True)
    review_date = models.DateTimeField(null=True, blank=True)

    @property
    def playtime_hours(self):
        if self.playtime_minutes: return round(self.playtime_minutes / 60, 1)
        return 0

# BLOCO 5: ACHIEVEMENTS
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
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    unlocked_at = models.DateTimeField()
    
    class Meta:
        unique_together = ('user', 'achievement')

# BLOCO 6: REVIEWS
class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    library_entry = models.ForeignKey(UserLibraryEntry, on_delete=models.CASCADE, related_name='reviews')
    
    title = models.CharField(max_length=100, blank=True)
    text = models.TextField(help_text="Escreva usando Markdown")
    text_html = models.TextField(editable=False, blank=True)
    
    rating = models.FloatField(null=True, blank=True)
    is_recommended = models.BooleanField(null=True, blank=True)
    
    playtime_at_review = models.IntegerField(null=True)
    contains_spoilers = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    is_replay = models.BooleanField(default=False)
    language = models.CharField(max_length=10, default='pt-br')
    
    achievement_percent_snapshot = models.FloatField(default=0.0)
    date_started = models.DateField(null=True, blank=True)
    date_finished = models.DateField(null=True, blank=True)
    tags = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes_count = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        html = markdown.markdown(self.text)
        # NOTA DE SEGURANÇA: bleach é deprecated, considere nh3 no futuro.
        allowed_tags = ['b', 'i', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li', 'a', 'blockquote', 'code', 'h1', 'h2', 'hr']
        allowed_attrs = {'a': ['href', 'title']}
        self.text_html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Review de {self.user} - {self.library_entry.platform_game.master_game.title}"

# BLOCO 7: DICAS & LISTAS (Mantidos iguais, apenas contexto)
class GameTip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tips')
    master_game = models.ForeignKey(MasterGame, on_delete=models.CASCADE, related_name='tips')
    related_achievement_name = models.CharField(max_length=255, blank=True, null=True)
    text = models.CharField(max_length=280)
    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def score(self):
        return self.upvotes - self.downvotes

class TipVote(models.Model):
    VOTE_CHOICES = ((1, 'Upvote'), (-1, 'Downvote'))
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tip = models.ForeignKey(GameTip, on_delete=models.CASCADE, related_name='votes')
    value = models.IntegerField(choices=VOTE_CHOICES)
    class Meta:
        unique_together = ('user', 'tip')

class GameList(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_lists')
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    likes_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.title

class GameListItem(models.Model):
    game_list = models.ForeignKey(GameList, on_delete=models.CASCADE, related_name='items')
    master_game = models.ForeignKey(MasterGame, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    comment = models.TextField(blank=True)
    class Meta:
        ordering = ['order']