# ==============================================================================
# ARQUIVO: vault/views.py (COMPLETO v4.0)
# ==============================================================================

# BLOCO 1: IMPORTAÇÕES
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import F, Q, Sum, Count, Avg, Case, When, Value, FloatField
from django.core.paginator import Paginator
from django.utils import timezone
from decouple import config
import requests
import json
from django.http import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
from .forms import ReviewForm, UserLibraryEntryForm, GameTipForm


from .models import (
    UserLibraryEntry, 
    UserAchievement, 
    Review, 
    GameTip, 
    TipVote, 
    GameList, 
    GameListItem, 
    MasterGame,
    Platform,
    PlatformGame,
    UserProfile
)
from .utils_igdb import get_igdb_token 


# ==============================================================================
# BLOCO 2: BIBLIOTECA (COM FILTROS DINÂMICOS E SORT POR NOTA)
# ==============================================================================
@login_required
def library_view(request):
    items_per_page = request.GET.get('per_page', 24)
    if items_per_page == 'all':
        items_per_page = 9999
    else:
        items_per_page = int(items_per_page)

    base_query = UserLibraryEntry.objects.filter(user=request.user).select_related(
        'platform_game__master_game', 'platform_game__platform'
    )
    
    # A MÁGICA DA CORREÇÃO ESTÁ AQUI
    base_query = base_query.annotate(
        total_achievements=Count('platform_game__achievements', distinct=True),
        
        # O CAMINHO CORRETO:
        # Contamos as conquistas (achievements) do jogo na plataforma (platform_game),
        # mas apenas aquelas onde a conquista desbloqueada (userachievement) pertence ao usuário
        # da linha atual da biblioteca (F('user')).
        unlocked_achievements=Count(
            'platform_game__achievements__userachievement',
            filter=Q(platform_game__achievements__userachievement__user=F('user')),
            distinct=True
        )
    ).annotate(
        achievement_percentage=Case(
            When(total_achievements__gt=0, then=(F('unlocked_achievements') * 100.0 / F('total_achievements'))),
            default=Value(0.0),
            output_field=FloatField()
        )
    )

    entries = base_query

    # Filtros
    status_filter = request.GET.get('status')
    if status_filter: entries = entries.filter(status=status_filter)
    
    platform_filter = request.GET.get('platform')
    if platform_filter: entries = entries.filter(platform_game__platform__slug=platform_filter)

    # Ordenação
    sort_by = request.GET.get('sort', 'recent')
    ordering_map = {
        'name_asc': 'platform_game__master_game__title',
        'playtime_desc': '-playtime_minutes',
        'rating_desc': F('rating').desc(nulls_last=True), # Usar F() para tratar nulos
        'recent': F('last_played').desc(nulls_last=True),
    }
    order_expression = ordering_map.get(sort_by, F('last_played').desc(nulls_last=True))
    entries = entries.order_by(order_expression)

    # Paginação
    paginator = Paginator(entries, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Plataformas disponíveis para o usuário
    user_platforms_pks = base_query.values_list('platform_game__platform__pk', flat=True).distinct()
    available_platforms = Platform.objects.filter(pk__in=user_platforms_pks).order_by('name')

    context = {
        'page_obj': page_obj,
        'total_games': paginator.count,
        'platforms': available_platforms,
        'current_params': request.GET.urlencode(),
        'current_status': status_filter,
        'current_platform': platform_filter,
        'current_sort': sort_by,
        'current_per_page': str(items_per_page),
    }
    return render(request, 'library.html', context)


# ==============================================================================
# BLOCO 3: DETALHES DO JOGO (HUB CENTRAL)
# ==============================================================================
def game_detail_view(request, game_id):
    entry = get_object_or_404(
        UserLibraryEntry.objects.select_related('platform_game__master_game', 'platform_game__platform'),
        pk=game_id,
        user=request.user
    )
    master = entry.platform_game.master_game

    if request.method == 'POST':
        
        # A. ALTERNAR FAVORITO (Botão Rápido Coração)
        if 'toggle_favorite' in request.POST:
            entry.is_favorite = not entry.is_favorite
            entry.save()
            return redirect('game_detail', game_id=game_id)

        # B. CRIAR REVIEW (ATUALIZADO COM NOTA DECIMAL E LIKE)
        if 'create_review' in request.POST:
            rating_val = request.POST.get('rating') # Ex: "4.5"
            tags_raw = request.POST.get('tags', '')
            
            # Tratamento da Recomendação (Radio Button retorna string 'true'/'false')
            rec_val = request.POST.get('is_recommended') # Retorna 'true', 'false' ou None
            is_rec = None
            if rec_val == 'true': is_rec = True
            if rec_val == 'false': is_rec = False
            
            # Snapshot de conquistas
            total_ach = entry.platform_game.achievements.count()
            unlocked = UserAchievement.objects.filter(user=request.user, achievement__platform_game=entry.platform_game).count()
            current_pct = (unlocked / total_ach * 100) if total_ach > 0 else 0

            Review.objects.create(
                user=request.user,
                library_entry=entry,
                text=request.POST.get('review_text'),
                rating=float(rating_val) if rating_val else None,
                is_recommended=is_rec, # Salva se recomendou ou não
                contains_spoilers=request.POST.get('contains_spoilers') == 'on',
                is_replay=request.POST.get('is_replay') == 'on',
                playtime_at_review=entry.playtime_minutes,
                date_started=request.POST.get('date_started') or None,
                date_finished=request.POST.get('date_finished') or None,
                tags=tags_raw,
                achievement_percent_snapshot=current_pct
            )
            is_recommended=is_rec, # Salva True, False ou None
            # Atualiza Entry com dados recentes
            entry.rating = float(rating_val) if rating_val else None
            entry.is_recommended = is_rec
            entry.save()
            return redirect('game_detail', game_id=game_id)

        # C. CRIAR DICA
        elif 'create_tip' in request.POST:
            GameTip.objects.create(
                user=request.user,
                master_game=master,
                text=request.POST.get('tip_text'),
                related_achievement_name=request.POST.get('achievement_name') or None
            )
            return redirect('game_detail', game_id=game_id)

        # D. VOTAR EM DICA
        elif 'vote_tip' in request.POST:
            tip_id = request.POST.get('tip_id')
            vote_val = int(request.POST.get('vote_value'))
            tip = get_object_or_404(GameTip, pk=tip_id)
            existing_vote = TipVote.objects.filter(user=request.user, tip=tip).first()
            
            if not existing_vote:
                TipVote.objects.create(user=request.user, tip=tip, value=vote_val)
                if vote_val == 1: tip.upvotes = F('upvotes') + 1
                else: tip.downvotes = F('downvotes') + 1
                tip.save()
            elif existing_vote.value != vote_val:
                if vote_val == 1:
                    tip.upvotes = F('upvotes') + 1
                    tip.downvotes = F('downvotes') - 1
                else:
                    tip.upvotes = F('upvotes') - 1
                    tip.downvotes = F('downvotes') + 1
                existing_vote.value = vote_val
                existing_vote.save()
                tip.save()
            return redirect('game_detail', game_id=game_id)

    # --- DADOS PARA O TEMPLATE ---
    total_achievements = entry.platform_game.achievements.count()
    unlocked_ids = UserAchievement.objects.filter(
        user=request.user, 
        achievement__platform_game=entry.platform_game
    ).values_list('achievement_id', flat=True)
    unlocked_count = len(unlocked_ids)
    percentage = (unlocked_count / total_achievements * 100) if total_achievements > 0 else 0

    user_reviews = Review.objects.filter(user=request.user, library_entry=entry).order_by('-created_at')
    
    all_tips = GameTip.objects.filter(master_game=master)
    sorted_tips = sorted(all_tips, key=lambda t: t.score(), reverse=True)

    user_lists = GameList.objects.filter(user=request.user).order_by('-updated_at')

    context = {
        'entry': entry,
        'master': master,
        'platform': entry.platform_game.platform,
        'total_achievements': total_achievements,
        'unlocked_achievements': unlocked_count,
        'percentage': round(percentage, 1),
        'unlocked_ids': set(unlocked_ids),
        'user_reviews': user_reviews,
        'tips': sorted_tips,
        'user_lists': user_lists,
    }
    return render(request, 'game_detail.html', context)


# ==============================================================================
# BLOCO 4: PERFIL (CORRIGIDO E COMPLETO)
# ==============================================================================
def profile_view(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    library = UserLibraryEntry.objects.filter(user=user)
    
    # --- CÁLCULOS BÁSICOS (RECOLOCADOS) ---
    total_games = library.count()
    completed_games = library.filter(status='completed').count()
    playing_games = library.filter(status='playing').count() # Para a barra de status
    backlog_games = library.filter(status='backlog').count() # Para a barra de status
    
    # "Iniciados" = Tudo menos Backlog puro
    started_games = library.exclude(status='backlog').count()
    
    # CORREÇÃO: Estas linhas estavam faltando no context
    total_playtime_minutes = library.aggregate(Sum('playtime_minutes'))['playtime_minutes__sum'] or 0
    total_hours = round(total_playtime_minutes / 60, 1)
    total_achievements_unlocked = UserAchievement.objects.filter(user=user).count()

    total_xp = UserAchievement.objects.filter(user=user).aggregate(Sum('achievement__xp_value'))['achievement__xp_value__sum'] or 0

    # --- CÁLCULO DA ESTRELA ALKAHEST ---
    xp_score = (total_xp / 50000) * 100
    profile.stat_volume = min(int(xp_score), 100)
    
    if started_games > 0:
        skill_score = (completed_games / started_games) * 100
        profile.stat_skill = min(int(skill_score), 100)
    else: profile.stat_skill = 0

    unique_platforms = library.values('platform_game__platform').distinct().count()
    profile.stat_variety = min(int((unique_platforms / 5) * 100), 100)
    
    social_count = Review.objects.filter(user=user).count() + GameTip.objects.filter(user=user).count()
    profile.stat_social = min(int((social_count / 20) * 100), 100)
    
    if total_games > 0:
        dedication_score = (completed_games / total_games) * 100
        profile.stat_speed = min(int(dedication_score), 100)
    else: profile.stat_speed = 0

    profile.save()

    # Níveis
    current_level = 1 + int(total_xp / 1000)
    xp_progress = total_xp - ((current_level - 1) * 1000)
    level_progress_percent = (xp_progress / 1000) * 100
    
    platform_stats = library.values('platform_game__platform__name').annotate(count=Count('id')).order_by('-count')

    context = {
        'user': user,
        'profile': profile,
        'total_games': total_games,
        'completed_games': completed_games,
        'playing_games': playing_games, # CORREÇÃO: Faltava no context
        'backlog_games': backlog_games, # CORREÇÃO: Faltava no context
        'total_hours': total_hours, # CORREÇÃO: Faltava no context
        'achievements_count': total_achievements_unlocked, # CORREÇÃO: Faltava no context
        'total_xp': total_xp,
        'current_level': current_level,
        'level_progress_percent': level_progress_percent,
        'xp_current': xp_progress,
        'platform_stats': platform_stats,
    }
    return render(request, 'profile.html', context)

# ==============================================================================
# BLOCO 5: ADICIONAR JOGO MANUAL (IGDB)
# ==============================================================================
def add_game_view(request):
    platforms = Platform.objects.all()
    results = []
    search_query = ""

    if request.method == 'POST':
        if 'search_query' in request.POST:
            search_query = request.POST.get('search_query')
            CLIENT_ID = config('TWITCH_CLIENT_ID')
            
            # Usa o utilitário de cache que criamos
            access_token = get_igdb_token()
            
            if access_token:
                try:
                    headers = {
                        'Client-ID': CLIENT_ID, 
                        'Authorization': f'Bearer {access_token}'
                    }
                    q = f'search "{search_query}"; fields name, cover.url, first_release_date; limit 20;'
                    response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=q)
                    results = response.json()
                    
                    if isinstance(results, list):
                        for res in results:
                            if 'cover' in res:
                                res['cover']['url'] = 'https:' + res['cover']['url'].replace('t_thumb', 't_cover_big')
                    else:
                        print("Erro API IGDB:", results)
                        results = []
                except Exception as e:
                    print(f"ERRO GERAL SEARCH: {e}")

        elif 'add_game_id' in request.POST:
            igdb_id = int(request.POST.get('add_game_id'))
            title = request.POST.get('game_title')
            cover_url = request.POST.get('cover_url')
            platform_slug = request.POST.get('platform_slug')
            status = request.POST.get('status')
            
            master, _ = MasterGame.objects.update_or_create(
                igdb_id=igdb_id, defaults={'title': title, 'cover_url': cover_url}
            )
            platform = get_object_or_404(Platform, slug=platform_slug)
            p_game, _ = PlatformGame.objects.get_or_create(
                platform=platform, external_id=str(igdb_id),
                defaults={'master_game': master, 'external_title': title}
            )
            entry, created = UserLibraryEntry.objects.get_or_create(
                user=request.user, platform_game=p_game, defaults={'status': status}
            )
            if not created:
                entry.status = status
                entry.save()

            return redirect('game_detail', game_id=entry.id)

    return render(request, 'add_game.html', {'platforms': platforms, 'results': results, 'search_query': search_query})


# ==============================================================================
# BLOCO 6: SISTEMA DE LISTAS
# ==============================================================================
def my_lists_view(request):
    lists = GameList.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'lists/my_lists.html', {'lists': lists})

def create_list_view(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        desc = request.POST.get('description')
        if title:
            new_list = GameList.objects.create(user=request.user, title=title, description=desc)
            return redirect('list_detail', list_id=new_list.id)
    return render(request, 'lists/create_list.html')

def list_detail_view(request, list_id):
    game_list = get_object_or_404(GameList, pk=list_id)
    items = game_list.items.select_related('master_game').all()
    context = {'list': game_list, 'items': items}
    return render(request, 'lists/list_detail.html', context)

def add_to_list_view(request, game_id):
    if request.method == 'POST':
        list_id = request.POST.get('list_id')
        comment = request.POST.get('comment', '')
        
        target_list = get_object_or_404(GameList, pk=list_id, user=request.user)
        entry = get_object_or_404(UserLibraryEntry, pk=game_id)
        master = entry.platform_game.master_game
        
        last_order = target_list.items.count() + 1
        
        GameListItem.objects.create(
            game_list=target_list,
            master_game=master,
            order=last_order,
            comment=comment
        )
        return redirect('game_detail', game_id=game_id)
    
    return redirect('library')


# ==============================================================================
# BLOCO 7: EXPORTAÇÃO DE DADOS (NOVA FEATURE)
# ==============================================================================
def export_data_view(request):
    """
    Exporta todos os dados do usuário para um arquivo JSON.
    Inclui Biblioteca, Reviews e Dicas.
    """
    user = request.user
    data = {
        'username': user.username,
        'exported_at': str(timezone.now()),
        'library': [],
        'reviews': [],
        'tips': []
    }
    
    # Exporta Biblioteca
    for entry in UserLibraryEntry.objects.filter(user=user):
        data['library'].append({
            'game': entry.platform_game.master_game.title,
            'platform': entry.platform_game.platform.name,
            'status': entry.status,
            'rating': entry.rating,
            'is_favorite': entry.is_favorite,
            'is_recommended': entry.is_recommended,
            'playtime_minutes': entry.playtime_minutes,
            'last_played': str(entry.last_played) if entry.last_played else None
        })

    # Exporta Reviews
    for rev in Review.objects.filter(user=user):
        data['reviews'].append({
            'game': rev.library_entry.platform_game.master_game.title,
            'text': rev.text,
            'rating': rev.rating,
            'is_recommended': rev.is_recommended,
            'created_at': str(rev.created_at)
        })
        
    # Exporta Dicas
    for tip in GameTip.objects.filter(user=user):
        data['tips'].append({
            'game': tip.master_game.title,
            'text': tip.text,
            'upvotes': tip.upvotes
        })
        
    response = HttpResponse(
        json.dumps(data, indent=4, cls=DjangoJSONEncoder),
        content_type='application/json'
    )
    response['Content-Disposition'] = f'attachment; filename="alkahest_data_{user.username}.json"'
    return response

# ==============================================================================
# BLOCO 10: EDITAR E DELETAR REVIEW (NOVO)
# ==============================================================================
from django.shortcuts import render, get_object_or_404, redirect
from .forms import ReviewForm # Vamos criar este form a seguir

def edit_review_view(request, review_id):
    # Garante que a review existe e pertence ao usuário logado (SEGURANÇA)
    review = get_object_or_404(Review, id=review_id, user=request.user)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            # Redireciona de volta para a página do jogo
            return redirect('game_detail', game_id=review.library_entry.id)
    else:
        form = ReviewForm(instance=review)

    return render(request, 'reviews/edit_review.html', {
        'form': form,
        'review': review
    })

def delete_review_view(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    
    if request.method == 'POST':
        game_id = review.library_entry.id
        review.delete()
        return redirect('game_detail', game_id=game_id)
        
    return render(request, 'reviews/delete_review_confirm.html', {'review': review})

# =g) VIEW PARA EDITAR A ENTRADA DA BIBLIOTECA (EX: MUDAR PLATAFORMA)
def edit_library_entry_view(request, entry_id):
    entry = get_object_or_404(UserLibraryEntry, id=entry_id, user=request.user)
    
    if request.method == 'POST':
        form = UserLibraryEntryForm(request.POST, instance=entry)
        if form.is_valid():
            selected_platform = form.cleaned_data['platform']
            
            # Precisamos encontrar ou criar um PlatformGame correspondente
            p_game, created = PlatformGame.objects.get_or_create(
                master_game=entry.platform_game.master_game,
                platform=selected_platform,
                # Usamos um ID externo genérico para jogos manuais
                defaults={'external_id': f"manual_{entry.platform_game.master_game.igdb_id}", 'external_title': entry.platform_game.master_game.title}
            )
            
            entry.platform_game = p_game
            entry.status = form.cleaned_data['status']
            entry.save()
            return redirect('game_detail', game_id=entry.id)
    else:
        form = UserLibraryEntryForm(instance=entry)
        
    return render(request, 'library/edit_entry.html', {'form': form, 'entry': entry})

# =a) VIEWS PARA EDITAR E DELETAR DICAS
def edit_tip_view(request, tip_id):
    tip = get_object_or_404(GameTip, id=tip_id, user=request.user)
    if request.method == 'POST':
        form = GameTipForm(request.POST, instance=tip)
        if form.is_valid():
            form.save()
            # Pega o primeiro jogo do usuário associado a este master_game para redirecionar
            entry = UserLibraryEntry.objects.filter(user=request.user, platform_game__master_game=tip.master_game).first()
            return redirect('game_detail', game_id=entry.id)
    else:
        form = GameTipForm(instance=tip)
    return render(request, 'tips/edit_tip.html', {'form': form, 'tip': tip})

def delete_tip_view(request, tip_id):
    tip = get_object_or_404(GameTip, id=tip_id, user=request.user)
    if request.method == 'POST':
        entry = UserLibraryEntry.objects.filter(user=request.user, platform_game__master_game=tip.master_game).first()
        tip.delete()
        return redirect('game_detail', game_id=entry.id)
    return render(request, 'tips/delete_tip_confirm.html', {'tip': tip})
