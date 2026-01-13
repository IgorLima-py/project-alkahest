from django.shortcuts import render
from django.db.models import Q
from django.core.paginator import Paginator
from .models import UserLibraryEntry
from django.shortcuts import render, get_object_or_404 # <--- Importe get_object_or_404
from .models import UserLibraryEntry, UserAchievement 
from django.db.models import Sum, Count, Q


def library_view(request):
    # 1. Base Query
    entries = UserLibraryEntry.objects.select_related(
        'platform_game__master_game', 
        'platform_game__platform'
    ).filter(user=request.user)

    # --- FILTROS ---
    
    # Busca por Texto
    query = request.GET.get('q')
    if query:
        entries = entries.filter(
            Q(platform_game__master_game__title__icontains=query) | 
            Q(platform_game__external_title__icontains=query)
        )

    # Filtro de Status
    status_filter = request.GET.get('status')
    if status_filter in ['playing', 'backlog', 'completed', 'dropped']:
        entries = entries.filter(status=status_filter)

    # Filtro de Plataforma (NOVO)
    platform_filter = request.GET.get('platform')
    if platform_filter:
        entries = entries.filter(platform_game__platform__slug=platform_filter)

    # --- ORDENAÇÃO (NOVO) ---
    sort_by = request.GET.get('sort', '-last_played') # Padrão: Recentes
    
    ordering_map = {
        'name_asc': 'platform_game__master_game__title',
        'name_desc': '-platform_game__master_game__title',
        'playtime_desc': '-playtime_minutes',
        'playtime_asc': 'playtime_minutes',
        'recent': '-last_played',
        # Nota: Ordenar por % de conquista exige cálculo pesado, deixamos pra Fase 4
    }
    
    db_order = ordering_map.get(sort_by, '-last_played')
    entries = entries.order_by(db_order)

    # --- PAGINAÇÃO ---
    paginator = Paginator(entries, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Contexto para o Template saber quais filtros estão ativos
    context = {
        'page_obj': page_obj,
        'total_games': paginator.count,
        'current_sort': sort_by,
        'current_platform': platform_filter,
        'current_status': status_filter
    }
    return render(request, 'library.html', context)

def game_detail_view(request, game_id):
    entry = get_object_or_404(
        UserLibraryEntry.objects.select_related('platform_game__master_game', 'platform_game__platform'),
        pk=game_id,
        user=request.user
    )
    
    total_achievements = entry.platform_game.achievements.count()
    
    # Busca QUAIS conquistas o user tem (trazendo só o ID da conquista pra ser leve)
    unlocked_ids = UserAchievement.objects.filter(
        user=request.user,
        achievement__platform_game=entry.platform_game
    ).values_list('achievement_id', flat=True)
    
    unlocked_count = len(unlocked_ids) # Conta o tamanho da lista

    if total_achievements > 0:
        percentage = (unlocked_count / total_achievements) * 100
    else:
        percentage = 0

    context = {
        'entry': entry,
        'master': entry.platform_game.master_game,
        'platform': entry.platform_game.platform,
        'total_achievements': total_achievements,
        'unlocked_achievements': unlocked_count,
        'percentage': round(percentage, 1),
        'unlocked_ids': set(unlocked_ids) # Transforma em SET para busca rápida no HTML
    }
    return render(request, 'game_detail.html', context)

def profile_view(request):
    user = request.user
    
    # 1. KPIs de Biblioteca
    library = UserLibraryEntry.objects.filter(user=user)
    total_games = library.count()
    completed_games = library.filter(status='completed').count()
    playing_games = library.filter(status='playing').count()
    backlog_games = library.filter(status='backlog').count()
    
    # Soma das horas jogadas (tratando caso seja None)
    total_playtime_minutes = library.aggregate(Sum('playtime_minutes'))['playtime_minutes__sum'] or 0
    total_hours = round(total_playtime_minutes / 60, 1)

    # 2. KPIs de Conquistas (A Gamificação)
    # Total de XP ganho pelo usuário
    total_xp = UserAchievement.objects.filter(user=user).aggregate(Sum('achievement__xp_value'))['achievement__xp_value__sum'] or 0
    
    # Contagem de conquistas
    total_achievements_unlocked = UserAchievement.objects.filter(user=user).count()
    
    # 3. Cálculo do Nível (Fórmula RPG Simples)
    # Nível 1 = 0 XP. Nível 2 = 1000 XP. Nível 10 = 9000 XP...
    # Fórmula: Nível = 1 + (XP / 1000)
    current_level = 1 + int(total_xp / 1000)
    
    # XP para o próximo nível
    xp_next_level = (current_level) * 1000
    xp_progress = total_xp - ((current_level - 1) * 1000)
    level_progress_percent = (xp_progress / 1000) * 100

    # 4. Distribuição por Plataforma (Para gráfico ou lista)
    platform_stats = library.values('platform_game__platform__name').annotate(
        count=Count('id')
    ).order_by('-count')

    context = {
        'user': user,
        'total_games': total_games,
        'completed_games': completed_games,
        'playing_games': playing_games,
        'backlog_games': backlog_games,
        'total_hours': total_hours,
        'total_xp': total_xp,
        'current_level': current_level,
        'achievements_count': total_achievements_unlocked,
        'level_progress_percent': level_progress_percent,
        'xp_current': xp_progress,
        'platform_stats': platform_stats,
    }
    return render(request, 'profile.html', context)