from django.db.models import Sum, Count, Avg
from .models import UserAchievement, Review, GameTip, UserLibraryEntry

class RadarChartService:
    def __init__(self, user):
        self.user = user

    def calculate_stats(self):
        """
        Calcula os 5 pilares do Death Stranding Chart.
        Retorna um dicionário com valores de 0 a 100 (normalizados).
        """
        stats = {
            'volume': 0,    # XP Total
            'skill': 0,     # Raridade (Por enquanto, % de platinas)
            'variety': 0,   # Gêneros únicos jogados
            'social': 0,    # Likes e Upvotes recebidos
            'speed': 0      # (Implementar futuramente com HLTB)
        }

        # 1. VOLUME (Baseado em XP - Vamos supor que 100.000 XP é o teto para 100%)
        total_xp = UserAchievement.objects.filter(user=self.user).aggregate(Sum('achievement__xp_value'))['achievement__xp_value__sum'] or 0
        stats['volume'] = min((total_xp / 100000) * 100, 100)

        # 2. SKILL (Média de % de completude dos jogos que iniciou)
        # Pega jogos onde user tem pelo menos 1 conquista
        games_started = UserLibraryEntry.objects.filter(user=self.user, play_status__in=['playing', 'completed', 'dropped'])
        # (Lógica simplificada para exemplo - ideal é calcular raridade média das conquistas)
        completed_count = games_started.filter(status='completed').count()
        total_started = games_started.count()
        if total_started > 0:
            stats['skill'] = (completed_count / total_started) * 100

        # 3. VARIETY (Contagem de Gêneros distintos em MasterGames jogados)
        # Requer que você tenha genres populado no MasterGame
        # stats['variety'] = ... (Lógica de contagem de JSON ou M2M)

        # 4. SOCIAL (Soma de likes em reviews + upvotes em dicas)
        review_likes = Review.objects.filter(user=self.user).aggregate(Sum('likes_count'))['likes_count__sum'] or 0
        tip_upvotes = GameTip.objects.filter(user=self.user).aggregate(Sum('upvotes'))['upvotes__sum'] or 0
        total_social = review_likes + tip_upvotes
        # Teto de 500 interações para 100%
        stats['social'] = min((total_social / 500) * 100, 100)

        return stats