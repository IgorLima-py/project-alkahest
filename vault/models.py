import uuid
from django.db import models
from django.contrib.auth.models import User
import markdown
import nh3

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
class GameCategory(models.IntegerChoices):
    MAIN_GAME = 0, 'Main Game'
    DLC_ADDON = 1, 'DLC/Addon'
    EXPANSION = 2, 'Expansion'
    BUNDLE = 3, 'Bundle'
    STANDALONE_EXPANSION = 4, 'Standalone Expansion'
    MOD = 5, 'Mod'
    EPISODE = 6, 'Episode'
    SEASON = 7, 'Season'
    REMAKE = 8, 'Remake'
    REMASTER = 9, 'Remaster'
    EXPANDED_GAME = 10, 'Expanded Game'
    PORT = 11, 'Port'
    FORK = 12, 'Fork'
    PACK = 13, 'Pack'
    UPDATE = 14, 'Update'
class MasterGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    igdb_id = models.BigIntegerField(unique=True, db_index=True)
    
    # Hierarquia e Categoria
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children', db_index=True)
    category = models.IntegerField(choices=GameCategory.choices, default=GameCategory.MAIN_GAME)
    
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, blank=True, null=True) # Útil para URLs amigáveis
    
    # Metadados Ricos (JSON é mais performático que criar 5 tabelas novas agora)
    summary = models.TextField(blank=True, null=True)
    cover_url = models.URLField(blank=True, null=True)
    release_date = models.DateField(blank=True, null=True)
    
    genres = models.JSONField(default=list, blank=True)        # Ex: ["RPG", "Adventure"]
    developers = models.JSONField(default=list, blank=True)    # Ex: ["CD Projekt Red"]
    publishers = models.JSONField(default=list, blank=True)    # Ex: ["Bandai Namco"]
    game_engines = models.JSONField(default=list, blank=True)  # Ex: ["REDengine 3"]
    
    # O "Santo Graal" do Sync: IDs de outras lojas
    # Ex: {"steam": "292030", "psn": "CUSA00001", "retroachievements": "123"}
    external_ids = models.JSONField(default=dict, blank=True) 

    updated_at = models.DateTimeField(auto_now=True) # Saber quando atualizamos por último

    def __str__(self):
        return self.title

class PlatformGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    master_game = models.ForeignKey(MasterGame, on_delete=models.CASCADE, related_name='platforms')
    platform = models.ForeignKey('Platform', on_delete=models.CASCADE)
    
    # Identificadores específicos da plataforma
    external_id = models.CharField(max_length=255) # Ex: AppID da Steam
    external_title = models.CharField(max_length=255) # Título como aparece na loja
    
    class Meta:
        unique_together = ('platform', 'external_id')

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
        ('dropped', 'Largado'),]
    

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='backlog', db_index=True)
    playtime_minutes = models.IntegerField(default=0)
    last_played = models.DateTimeField(blank=True, null=True, db_index=True)
    last_synced = models.DateTimeField(auto_now=True)
    rating = models.FloatField(null=True, blank=True, db_index=True) 
    
    is_favorite = models.BooleanField(default=False)
    is_recommended = models.BooleanField(null=True, blank=True)
    
    # NOVOS CAMPOS (Fase 1 - Preço/Moeda)
    price_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='BRL', blank=True)
    
    review_text = models.TextField(blank=True, null=True) # Legado
    review_date = models.DateTimeField(null=True, blank=True) # Legado

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
        allowed_tags = {'b', 'i', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li', 'a', 'blockquote', 'code', 'h1', 'h2', 'hr'}
        allowed_attrs = {'a': {'href', 'title'}, 'img': {'src', 'alt'}}
        self.text_html = nh3.clean(html, tags=allowed_tags, attributes=allowed_attrs)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Review de {self.user} - {self.library_entry.platform_game.master_game.title}"

# BLOCO 7: DICAS & LISTAS
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
    is_public = models.BooleanField(default=True) # Novo (Segurança)
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

# BLOCO 8: SOCIAL (Fase 2 - ESTE É O BLOCO QUE FALTAVA)
class UserFollow(models.Model):
    follower = models.ForeignKey(User, related_name='following', on_delete=models.CASCADE)
    target = models.ForeignKey(User, related_name='followers', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('follower', 'target')
        indexes = [
            models.Index(fields=['follower']),
            models.Index(fields=['target']),
        ]

    def __str__(self):
        return f"{self.follower.username} follows {self.target.username}"
