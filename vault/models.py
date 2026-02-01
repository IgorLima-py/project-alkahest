import uuid
from django.db import models
from django.contrib.auth.models import User
import markdown
import nh3
from django.utils.translation import gettext_lazy as _


# ==========================================
# BLOCO 1: PERFIL DO USUÁRIO
# ==========================================
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True, max_length=500)
    avatar_url = models.URLField(blank=True, null=True)
    
    # Stats gamificados (0-100)
    stat_volume = models.IntegerField(default=0)
    stat_skill = models.IntegerField(default=0)
    stat_variety = models.IntegerField(default=0)
    stat_social = models.IntegerField(default=0)
    stat_speed = models.IntegerField(default=0)

    def __str__(self):
        return f"Perfil de {self.user.username}"

# ==========================================
# BLOCO 2: PLATAFORMAS (Movido para cima para evitar NameError)
# ==========================================
class Platform(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=50)
    
    def __str__(self):
        return self.name

# ==========================================
# BLOCO 3: JOGO MESTRE (METADADOS RICOS)
# ==========================================

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

class GameStatus(models.IntegerChoices):
    RELEASED = 0, 'Released'
    ALPHA = 2, 'Alpha'
    BETA = 3, 'Beta'
    EARLY_ACCESS = 4, 'Early Access'
    OFFLINE = 5, 'Offline'
    CANCELLED = 6, 'Cancelled'
    RUMORED = 7, 'Rumored'
    DELISTED = 8, 'Delisted'

class MasterGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    igdb_id = models.BigIntegerField(unique=True, db_index=True)
    
    # --- Identidade & Hierarquia ---
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    category = models.IntegerField(choices=GameCategory.choices, default=GameCategory.MAIN_GAME)
    status = models.IntegerField(choices=GameStatus.choices, default=GameStatus.RELEASED)
    
    # --- Multimídia ---
    cover_url = models.URLField(blank=True, null=True) # Capa vertical (Poster)
    background_url = models.URLField(blank=True, null=True) # Hero Image (Artwork/Screenshot)
    
    artworks = models.JSONField(default=list, blank=True) 
    screenshots = models.JSONField(default=list, blank=True)
    videos = models.JSONField(default=list, blank=True) # IDs do YouTube
    
    # --- Texto & Lore ---
    summary = models.TextField(blank=True, null=True) # Resumo curto
    storyline = models.TextField(blank=True, null=True) # Enredo completo
    
    # --- Metadados Técnicos ---
    release_date = models.DateField(blank=True, null=True)
    developers = models.JSONField(default=list, blank=True)
    publishers = models.JSONField(default=list, blank=True)
    game_engines = models.JSONField(default=list, blank=True)
    
    # --- Classificação & Estilo ---
    genres = models.JSONField(default=list, blank=True)
    themes = models.JSONField(default=list, blank=True) # Sci-fi, Horror...
    game_modes = models.JSONField(default=list, blank=True) # Single, Multi, Co-op
    player_perspectives = models.JSONField(default=list, blank=True) # FPS, TPS...
    
    # --- Relações ---
    collection = models.CharField(max_length=255, blank=True, null=True) # Nome da Série
    franchises = models.JSONField(default=list, blank=True) 
    similar_games = models.JSONField(default=list, blank=True) # Lista de IDs
    dlcs = models.JSONField(default=list, blank=True) # Lista de IDs
    
    # --- Localização ---
    supported_languages = models.JSONField(default=dict, blank=True)
    
    # --- IDs Externos (O Santo Graal do Sync) ---
    external_ids = models.JSONField(default=dict, blank=True) # Steam, PSN, etc.
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

# ==========================================
# BLOCO 4: JOGO VINCULADO À PLATAFORMA
# ==========================================
class PlatformGame(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    master_game = models.ForeignKey(MasterGame, on_delete=models.CASCADE, related_name='platforms')
    platform = models.ForeignKey(Platform, on_delete=models.CASCADE)
    
    # Dados específicos da loja (Ex: AppID Steam 292030)
    external_id = models.CharField(max_length=255)
    external_title = models.CharField(max_length=255)
    
    class Meta:
        unique_together = ('platform', 'external_id')

# ==========================================
# BLOCO 5: BIBLIOTECA DO USUÁRIO
# ==========================================
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
    last_played = models.DateTimeField(blank=True, null=True, db_index=True)
    last_synced = models.DateTimeField(auto_now=True)
    rating = models.IntegerField(null=True, blank=True, db_index=True, help_text="Armazenado como 0-100")
    
    is_favorite = models.BooleanField(default=False)
    is_recommended = models.BooleanField(null=True, blank=True)
    
    # Campos Financeiros
    price_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='BRL', blank=True)
    
    # Campos Legado (serão depreciados pelo sistema de Review)
    review_text = models.TextField(blank=True, null=True) 
    review_date = models.DateTimeField(null=True, blank=True)

    @property
    def playtime_hours(self):
        if self.playtime_minutes: return round(self.playtime_minutes / 60, 1)
        return 0

# ==========================================
# BLOCO 6: CONQUISTAS
# ==========================================
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

# ==========================================
# BLOCO 7: REVIEWS
# ==========================================
class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    library_entry = models.ForeignKey(UserLibraryEntry, on_delete=models.CASCADE, related_name='reviews')
    
    title = models.CharField(max_length=100, blank=True)
    text = models.TextField(help_text="Escreva usando Markdown")
    text_html = models.TextField(editable=False, blank=True)
    
    rating = models.IntegerField(null=True, blank=True, help_text="Armazenado como 0-100")
    is_recommended = models.BooleanField(null=True, blank=True)
    
    playtime_at_review = models.IntegerField(null=True)
    contains_spoilers = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    is_replay = models.BooleanField(default=False)
    language = models.CharField(max_length=10, default='pt-br')
    
    # Snapshot: Estatísticas no momento da review
    achievement_percent_snapshot = models.FloatField(default=0.0)
    date_started = models.DateField(null=True, blank=True)
    date_finished = models.DateField(null=True, blank=True)
    tags = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes_count = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        # Sanitização de segurança (XSS protection)
        html = markdown.markdown(self.text)
        allowed_tags = {'b', 'i', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li', 'a', 'blockquote', 'code', 'h1', 'h2', 'hr'}
        allowed_attrs = {'a': {'href', 'title'}, 'img': {'src', 'alt'}}
        self.text_html = nh3.clean(html, tags=allowed_tags, attributes=allowed_attrs)
        super().save(*args, **kwargs)
        
        # Sincronia Automática: Atualiza a Library Entry
        if self.library_entry:
            self.library_entry.rating = self.rating
            # Lógica opcional: Se der nota, remove do backlog?
            # if self.rating is not None and self.library_entry.status == 'backlog':
            #     self.library_entry.status = 'playing' 
            self.library_entry.save(update_fields=['rating'])

    def __str__(self):
        return f"Review de {self.user} - {self.library_entry.platform_game.master_game.title}"

# ==========================================
# BLOCO 8: DICAS & LISTAS
# ==========================================
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
    is_public = models.BooleanField(default=True)
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

# ==========================================
# BLOCO 9: SOCIAL (FOLLOW SYSTEM)
# ==========================================
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
    

    # ==========================================
# BLOCO 10: MARKETPLACE & PREÇOS (Project Alkahest)
# ==========================================

class Store(models.Model):
    id = models.AutoField(primary_key=True)
    slug = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    
    # Mapeamento para o 'category' do IGDB para facilitar a busca
    igdb_category_id = models.IntegerField(null=True, blank=True, unique=True)

    def __str__(self):
        return self.name

class GameStoreLink(models.Model):
    """
    Conecta um MasterGame a uma Loja Específica.
    Ex: Elden Ring (MasterGame) -> Steam (Store) -> AppID 1245620
    Esta é a tabela que o robô de preços vai usar como fila.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    master_game = models.ForeignKey(MasterGame, on_delete=models.CASCADE, related_name='store_links')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='game_links')
    
    external_id = models.CharField(max_length=255, db_index=True, help_text="AppID da Steam, ConceptID da PSN, etc")
    
    # Controle de Fila do Robô
    last_checked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('store', 'external_id')
        ordering = ['last_checked_at']

    def __str__(self):
        return f"{self.master_game.title} on {self.store.name}"

class PriceHistory(models.Model):
    """
    Histórico imutável de preços.
    O robô só insere aqui se o preço MUDOU.
    """
    CURRENCY_CHOICES = (('BRL', 'Real'), ('USD', 'Dólar'), ('EUR', 'Euro'))
    
    id = models.BigAutoField(primary_key=True)
    link = models.ForeignKey(GameStoreLink, on_delete=models.CASCADE, related_name='price_history')
    
    price_regular = models.DecimalField(max_digits=10, decimal_places=2, help_text="Preço cheio sem desconto")
    price_final = models.DecimalField(max_digits=10, decimal_places=2, help_text="Preço final para o consumidor (com desconto)")
    
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='BRL', db_index=True)
    
    is_free = models.BooleanField(default=False)
    is_on_sale = models.BooleanField(default=False)
    is_subscription = models.BooleanField(default=False, help_text="Ex: GamePass, PS Plus Extra")
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['link', 'timestamp']),
        ]
        verbose_name_plural = "Price Histories"
        ordering = ['-timestamp']


# ==========================================
# BLOCO 11: SISTEMA DE NOTIFICAÇÕES (Fase 4)
# ==========================================

class NotificationType(models.TextChoices):
    SYSTEM = 'system', _('Sistema')
    SOCIAL_FOLLOW = 'follow', _('Novo Seguidor')
    SOCIAL_LIKE = 'like', _('Curtida')
    PRICE_ALERT = 'price', _('Alerta de Preço')
    GAME_RELEASE = 'release', _('Lançamento')

class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', db_index=True)
    
    # Tipo para permitir filtragem e ícones diferentes no front
    notification_type = models.CharField(
        max_length=20, 
        choices=NotificationType.choices, 
        default=NotificationType.SYSTEM
    )
    
    title = models.CharField(max_length=255) # Ex: "Elden Ring está em promoção!"
    message = models.TextField(blank=True)   # Ex: "Desconto de 50% na Steam."
    link_url = models.CharField(max_length=500, blank=True) # Ação ao clicar (HTMX target)
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            # Índice composto crítico para performance do badge (count unread)
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.recipient.username} - {self.get_notification_type_display()}"
