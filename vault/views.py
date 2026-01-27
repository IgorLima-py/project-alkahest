# BLOCO 0: IMPORTAÇÕES
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import F, Q, Sum, Count, Case, When, Value, FloatField
from django.core.paginator import Paginator
from django.utils import timezone
from decouple import config
import requests
import json
import uuid
from django.http import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder

# Formulários (Certifique-se de que forms.py está criado)
from .forms import ReviewForm, UserLibraryEntryForm, GameTipForm

# Models
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

# Utils
from .utils_igdb import get_igdb_token 

# BLOCO 1: DASHBOARD (RESUMO RÁPIDO)
@login_required
def dashboard_view(request):
    user = request.user
    
    # Bento Grid: Jogos sendo jogados (com otimização select_related)
    playing_games = UserLibraryEntry.objects.filter(
        user=user, 
        status='playing'
    ).select_related('platform_game__master_game', 'platform_game__platform').order_by('-last_played')[:6]
    
    # Bento Grid: Reviews Recentes (com otimização select_related)
    recent_reviews = Review.objects.select_related(
        'user', 
        'library_entry__platform_game__master_game'
    ).order_by('-created_at')[:5]
    
    # Stats Rápidos (Agregação no Banco)
    total_completed = UserLibraryEntry.objects.filter(user=user, status='completed').count()
    
    # Soma total de minutos jogados
    total_minutes = UserLibraryEntry.objects.filter(user=user).aggregate(Sum('playtime_minutes'))['playtime_minutes__sum'] or 0
    
    # Counts simples
    playing_count = UserLibraryEntry.objects.filter(user=user, status='playing').count()
    backlog_count = UserLibraryEntry.objects.filter(user=user, status='backlog').count()
    
    context = {
        'playing_games': playing_games,
        'recent_reviews': recent_reviews,
        'playing_count': playing_count,
        'backlog_count': backlog_count,
        'total_completed': total_completed,
        'total_hours': round(total_minutes / 60, 1),
    }
    return render(request, 'dashboard.html', context)

# BLOCO 2: BIBLIOTECA (FILTROS + PERF + UX)
@login_required
def library_view(request):
    # Paginação
    items_per_page = request.GET.get('per_page', 24)
    items_per_page = 9999 if items_per_page == 'all' else int(items_per_page)

    # Query Base Otimizada (select_related evita N+1 queries)
    base_query = UserLibraryEntry.objects.filter(user=request.user).select_related(
        'platform_game__master_game', 'platform_game__platform'
    )
    
    # Annotate para Contagem de Conquistas (Lógica Complexa)
    # Conta apenas as conquistas que O USUÁRIO desbloqueou
    base_query = base_query.annotate(
        total_achievements=Count('platform_game__achievements', distinct=True),
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
        'rating_desc': F('rating').desc(nulls_last=True), # Nulos ficam por último
        'recent': F('last_played').desc(nulls_last=True),
    }
    # Default para 'recent' se vier lixo na URL
    order_expression = ordering_map.get(sort_by, F('last_played').desc(nulls_last=True))
    entries = entries.order_by(order_expression)

    # Paginação Aplicada
    paginator = Paginator(entries, items_per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Plataformas disponíveis (apenas as que o user tem jogos)
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


# BLOCO 3: DETALHES DO JOGO (HUB CENTRAL)
@login_required
def game_detail_view(request, game_id):
    # Busca Entry com joins necessários
    entry = get_object_or_404(
        UserLibraryEntry.objects.select_related('platform_game__master_game', 'platform_game__platform'),
        pk=game_id,
        user=request.user
    )
    master = entry.platform_game.master_game

    if request.method == 'POST':
        
        # A. ALTERNAR FAVORITO (Botão Rápido)
        if 'toggle_favorite' in request.POST:
            entry.is_favorite = not entry.is_favorite
            entry.save()
            return redirect('game_detail', game_id=game_id)

        # B. CRIAR REVIEW
        if 'create_review' in request.POST:
            rating_val = request.POST.get('rating')
            rec_val = request.POST.get('is_recommended') # 'true', 'false' ou None
            
            # Converte 'true' string para Boolean
            is_rec = True if rec_val == 'true' else (False if rec_val == 'false' else None)
            
            # Snapshot de conquistas para "congelar" o progresso na hora da review
            total_ach = entry.platform_game.achievements.count()
            unlocked = UserAchievement.objects.filter(user=request.user, achievement__platform_game=entry.platform_game).count()
            current_pct = (unlocked / total_ach * 100) if total_ach > 0 else 0

            Review.objects.create(
                user=request.user,
                library_entry=entry,
                text=request.POST.get('review_text'),
                rating=float(rating_val) if rating_val else None,
                is_recommended=is_rec,
                contains_spoilers=request.POST.get('contains_spoilers') == 'on',
                is_replay=request.POST.get('is_replay') == 'on',
                playtime_at_review=entry.playtime_minutes,
                date_started=request.POST.get('date_started') or None,
                date_finished=request.POST.get('date_finished') or None,
                tags=request.POST.get('tags', ''),
                achievement_percent_snapshot=current_pct
            )
            
            # Sincroniza nota e recomendação com a entrada da biblioteca
            if rating_val: 
                entry.rating = float(rating_val)
            if is_rec is not None:
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
            
            # Lógica de Voto (Upvote/Downvote com toggle)
            existing_vote = TipVote.objects.filter(user=request.user, tip=tip).first()
            
            if not existing_vote:
                TipVote.objects.create(user=request.user, tip=tip, value=vote_val)
                if vote_val == 1: tip.upvotes = F('upvotes') + 1
                else: tip.downvotes = F('downvotes') + 1
            elif existing_vote.value != vote_val:
                # Inverte o voto anterior
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

    # --- PREPARAÇÃO DE DADOS PARA O TEMPLATE ---
    
    # Conquistas
    total_achievements = entry.platform_game.achievements.count()
    unlocked_ids = UserAchievement.objects.filter(
        user=request.user, 
        achievement__platform_game=entry.platform_game
    ).values_list('achievement_id', flat=True)
    percentage = (len(unlocked_ids) / total_achievements * 100) if total_achievements > 0 else 0

    # Reviews e Dicas
    user_reviews = Review.objects.filter(user=request.user, library_entry=entry).order_by('-created_at')
    
    # Ordena dicas por score (Python sort para não sobrecarregar DB com annotations complexas agora)
    all_tips = list(GameTip.objects.filter(master_game=master))
    sorted_tips = sorted(all_tips, key=lambda t: t.score(), reverse=True)

    user_lists = GameList.objects.filter(user=request.user).order_by('-updated_at')

    context = {
        'entry': entry,
        'master': master,
        'platform': entry.platform_game.platform,
        'total_achievements': total_achievements,
        'unlocked_achievements': len(unlocked_ids),
        'percentage': round(percentage, 1),
        'unlocked_ids': set(unlocked_ids),
        'user_reviews': user_reviews,
        'tips': sorted_tips,
        'user_lists': user_lists,
    }
    return render(request, 'game_detail.html', context)



# BLOCO 4: PERFIL (RADAR CHART & STATS)
@login_required
def profile_view(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    library = UserLibraryEntry.objects.filter(user=user)
    
    # Stats Gerais
    total_games = library.count()
    completed_games = library.filter(status='completed').count()
    playing_games = library.filter(status='playing').count()
    backlog_games = library.filter(status='backlog').count()
    
    total_playtime_minutes = library.aggregate(Sum('playtime_minutes'))['playtime_minutes__sum'] or 0
    total_hours = round(total_playtime_minutes / 60, 1)
    
    total_xp = UserAchievement.objects.filter(user=user).aggregate(Sum('achievement__xp_value'))['achievement__xp_value__sum'] or 0
    total_achievements_unlocked = UserAchievement.objects.filter(user=user).count()

    # --- CÁLCULO DA ESTRELA ALKAHEST (Simplificado) ---
    started_games = library.exclude(status='backlog').count()
    
    # 1. Volume (XP Total)
    profile.stat_volume = min(int((total_xp / 50000) * 100), 100)
    
    # 2. Skill (Completion Rate)
    if started_games > 0:
        profile.stat_skill = min(int((completed_games / started_games) * 100), 100)
    else: 
        profile.stat_skill = 0

    # 3. Variety (Plataformas Únicas)
    unique_platforms = library.values('platform_game__platform').distinct().count()
    profile.stat_variety = min(int((unique_platforms / 5) * 100), 100)
    
    # 4. Social (Interações)
    social_count = Review.objects.filter(user=user).count() + GameTip.objects.filter(user=user).count()
    profile.stat_social = min(int((social_count / 20) * 100), 100)
    
    # 5. Speed (Dedicação - Zerados vs Total)
    if total_games > 0:
        profile.stat_speed = min(int((completed_games / total_games) * 100), 100)
    else: 
        profile.stat_speed = 0

    profile.save()

    # Nível do Jogador
    current_level = 1 + int(total_xp / 1000)
    xp_progress = total_xp - ((current_level - 1) * 1000)
    level_progress_percent = (xp_progress / 1000) * 100
    
    platform_stats = library.values('platform_game__platform__name').annotate(count=Count('id')).order_by('-count')

    context = {
        'user': user,
        'profile': profile,
        'total_games': total_games,
        'completed_games': completed_games,
        'playing_games': playing_games,
        'backlog_games': backlog_games,
        'total_hours': total_hours,
        'achievements_count': total_achievements_unlocked,
        'total_xp': total_xp,
        'current_level': current_level,
        'level_progress_percent': level_progress_percent,
        'xp_current': xp_progress,
        'platform_stats': platform_stats,
    }
    return render(request, 'profile.html', context)



# BLOCO 5: ADICIONAR JOGO (IGDB)
@login_required
def add_game_view(request):
    platforms = Platform.objects.all().order_by('name')
    results = []
    search_query = ""

    if request.method == 'POST':
        if 'search_query' in request.POST:
            search_query = request.POST.get('search_query')
            CLIENT_ID = config('TWITCH_CLIENT_ID')
            
            access_token = get_igdb_token()
            
            if access_token:
                try:
                    headers = {
                        'Client-ID': CLIENT_ID, 
                        'Authorization': f'Bearer {access_token}'
                    }
                    # Busca nome, capa e data
                    q = f'search "{search_query}"; fields name, cover.url, first_release_date; limit 20;'
                    response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=q)
                    results = response.json()
                    
                    if isinstance(results, list):
                        for res in results:
                            # Melhora qualidade da imagem da capa
                            if 'cover' in res:
                                res['cover']['url'] = 'https:' + res['cover']['url'].replace('t_thumb', 't_cover_big')
                except Exception as e:
                    print(f"ERRO API IGDB: {e}")

        elif 'add_game_id' in request.POST:
            igdb_id = int(request.POST.get('add_game_id'))
            title = request.POST.get('game_title')
            cover_url = request.POST.get('cover_url')
            platform_slug = request.POST.get('platform_slug')
            status = request.POST.get('status')
            
            # Cria ou atualiza MasterGame
            master, _ = MasterGame.objects.update_or_create(
                igdb_id=igdb_id, defaults={'title': title, 'cover_url': cover_url}
            )
            
            # Cria PlatformGame
            platform = get_object_or_404(Platform, slug=platform_slug)
            p_game, _ = PlatformGame.objects.get_or_create(
                platform=platform, external_id=str(igdb_id),
                defaults={'master_game': master, 'external_title': title}
            )
            
            # Adiciona à biblioteca do usuário
            entry, created = UserLibraryEntry.objects.get_or_create(
                user=request.user, platform_game=p_game, defaults={'status': status}
            )
            if not created:
                entry.status = status
                entry.save()

            return redirect('game_detail', game_id=entry.id)

    return render(request, 'add_game.html', {'platforms': platforms, 'results': results, 'search_query': search_query})



# BLOCO 6: SISTEMA DE LISTAS
@login_required
def my_lists_view(request):
    lists = GameList.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'lists/my_lists.html', {'lists': lists})

@login_required
def create_list_view(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        desc = request.POST.get('description')
        if title:
            new_list = GameList.objects.create(user=request.user, title=title, description=desc)
            return redirect('list_detail', list_id=new_list.id)
    return render(request, 'lists/create_list.html')

@login_required
def list_detail_view(request, list_id):
    # Permite ver listas de outros usuários (futuro social), mas por enquanto só vê as próprias
    # Se quiser bloquear, adicionar user=request.user no get_object_or_404
    game_list = get_object_or_404(GameList, pk=list_id)
    items = game_list.items.select_related('master_game').all().order_by('order')
    return render(request, 'lists/list_detail.html', {'list': game_list, 'items': items})

@login_required
def add_to_list_view(request, game_id):
    if request.method == 'POST':
        list_id = request.POST.get('list_id')
        comment = request.POST.get('comment', '')
        
        # Só pode adicionar em listas que pertencem ao usuário logado
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



# BLOCO 7: EXPORTAÇÃO DE DADOS (LGPD/BACKUP)
@login_required
def export_data_view(request):
    user = request.user
    data = {
        'username': user.username,
        'exported_at': str(timezone.now()),
        'library': [],
        'reviews': [],
        'tips': []
    }
    
    for entry in UserLibraryEntry.objects.filter(user=user):
        data['library'].append({
            'game': entry.platform_game.master_game.title,
            'platform': entry.platform_game.platform.name,
            'status': entry.status,
            'rating': entry.rating,
            'is_favorite': entry.is_favorite,
            'playtime_minutes': entry.playtime_minutes,
            'last_played': str(entry.last_played) if entry.last_played else None
        })

    for rev in Review.objects.filter(user=user):
        data['reviews'].append({
            'game': rev.library_entry.platform_game.master_game.title,
            'text': rev.text,
            'rating': rev.rating,
            'is_recommended': rev.is_recommended,
            'created_at': str(rev.created_at)
        })
        
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



# BLOCO 8: CRUDS DE EDIÇÃO (NOVO REFACTOR COM FORMS)
# A. Editar e Deletar Reviews
@login_required
def edit_review_view(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            # Sincronizar nota da review com o jogo na biblioteca se mudou
            entry = review.library_entry
            if entry.rating != review.rating:
                entry.rating = review.rating
                entry.save()
            return redirect('game_detail', game_id=entry.id)
    else:
        form = ReviewForm(instance=review)

    return render(request, 'reviews/edit_review.html', {'form': form, 'review': review})

@login_required
def delete_review_view(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    game_id = review.library_entry.id
    if request.method == 'POST':
        review.delete()
        return redirect('game_detail', game_id=game_id)
    return render(request, 'reviews/delete_review_confirm.html', {'review': review})


# B. Editar Entrada da Biblioteca (Mudança de Plataforma)
@login_required
def edit_library_entry_view(request, entry_id):
    entry = get_object_or_404(UserLibraryEntry, id=entry_id, user=request.user)
    
    if request.method == 'POST':
        form = UserLibraryEntryForm(request.POST, instance=entry)
        if form.is_valid():
            new_platform = form.cleaned_data['platform']
            
            # Lógica Crítica: Se mudou a plataforma, precisamos apontar para outro PlatformGame
            if new_platform != entry.platform_game.platform:
                master = entry.platform_game.master_game
                
                # Tenta achar o PlatformGame existente ou cria um "Manual"
                # Ex: Mudou de PC para PS5. Se não existir PS5 no banco para esse jogo, cria.
                pg, _ = PlatformGame.objects.get_or_create(
                    master_game=master,
                    platform=new_platform,
                    defaults={
                        # ID externo dummy pois é uma troca manual
                        'external_id': f"manual_switch_{uuid.uuid4()}",
                        'external_title': master.title
                    }
                )
                entry.platform_game = pg
            
            entry.status = form.cleaned_data['status']
            entry.rating = form.cleaned_data['rating']
            entry.is_favorite = form.cleaned_data['is_favorite']
            entry.save()
            return redirect('game_detail', game_id=entry.id)
    else:
        form = UserLibraryEntryForm(instance=entry)
        
    return render(request, 'library/edit_entry.html', {'form': form, 'entry': entry})


# C. Editar e Deletar Dicas
@login_required
def edit_tip_view(request, tip_id):
    tip = get_object_or_404(GameTip, id=tip_id, user=request.user)
    if request.method == 'POST':
        form = GameTipForm(request.POST, instance=tip)
        if form.is_valid():
            form.save()
            # Redireciona para o primeiro jogo encontrado na biblioteca do usuário que combine
            entry = UserLibraryEntry.objects.filter(
                user=request.user, 
                platform_game__master_game=tip.master_game
            ).first()
            if entry:
                return redirect('game_detail', game_id=entry.id)
            return redirect('library') # Fallback
    else:
        form = GameTipForm(instance=tip)
    return render(request, 'tips/edit_tip.html', {'form': form, 'tip': tip})

@login_required
def delete_tip_view(request, tip_id):
    tip = get_object_or_404(GameTip, id=tip_id, user=request.user)
    if request.method == 'POST':
        master = tip.master_game
        tip.delete()
        entry = UserLibraryEntry.objects.filter(
            user=request.user, platform_game__master_game=master
        ).first()
        if entry:
            return redirect('game_detail', game_id=entry.id)
        return redirect('library')
    return render(request, 'tips/delete_tip_confirm.html', {'tip': tip})

# BLOCO X: DISCOVERY VIEW (PÁGINA EM BRANCO PARA FUTURO SOCIAL/RECOMENDAÇÕES)
@login_required
def discovery_view(request):
    return render(request, 'discovery.html')