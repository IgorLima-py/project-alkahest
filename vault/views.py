# BLOCO 0: IMPORTAÇÕES
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import F, Q, Sum, Count, Case, When, Value, FloatField, CharField
from django.core.paginator import Paginator
from django.utils import timezone
from decouple import config
import requests
import json
import uuid
from django.http import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
from itertools import chain

# Formulários
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
    UserProfile,
    UserFollow,
    User
)

# Utils
from .utils_igdb import get_igdb_token 

# === HELPER: ACTIVITY FEED (Definido antes do uso) ===
def get_community_pulse(user):
    """
    Busca atividades recentes (Jogos iniciados, Reviews, Platinas)
    dos usuários que eu sigo + atividades globais relevantes.
    """
    # Quem eu sigo
    following_ids = list(UserFollow.objects.filter(follower=user).values_list('target_id', flat=True))
    following_ids.append(user.id) # Inclui eu mesmo

    # 1. Reviews recentes dessa galera
    recent_reviews = Review.objects.filter(
        user_id__in=following_ids
    ).select_related('user', 'library_entry__platform_game__master_game').annotate(
        activity_type=Value('review', output_field=CharField())
    ).order_by('-created_at')[:5]

    # 2. Jogos iniciados recentemente
    recent_starts = UserLibraryEntry.objects.filter(
        user_id__in=following_ids,
        status='playing'
    ).select_related('user', 'platform_game__master_game').annotate(
        activity_type=Value('started', output_field=CharField())
    ).order_by('-last_synced')[:5]

    # Merge simples
    activity_feed = sorted(
        chain(recent_reviews, recent_starts),
        key=lambda x: x.created_at if hasattr(x, 'created_at') else x.last_synced,
        reverse=True
    )[:7] 
    
    return activity_feed


# BLOCO 1: DASHBOARD
@login_required
def dashboard_view(request):
    user = request.user
    
    # Bento Grid: Jogos Jogando
    playing_games = UserLibraryEntry.objects.filter(
        user=user, 
        status='playing'
    ).select_related('platform_game__master_game', 'platform_game__platform').order_by('-last_played')[:6]
    
    # Community Pulse Real
    community_pulse = get_community_pulse(request.user)

    # Reviews Globais Recentes
    recent_reviews = Review.objects.select_related(
        'user', 
        'library_entry__platform_game__master_game'
    ).order_by('-created_at')[:5]
    
    # Stats Rápidos
    total_completed = UserLibraryEntry.objects.filter(user=user, status='completed').count()
    total_minutes = UserLibraryEntry.objects.filter(user=user).aggregate(Sum('playtime_minutes'))['playtime_minutes__sum'] or 0
    playing_count = UserLibraryEntry.objects.filter(user=user, status='playing').count()
    backlog_count = UserLibraryEntry.objects.filter(user=user, status='backlog').count()
    
    # Mock Trending (substitua por lógica real futuramente)
    trending_ids = Review.objects.values_list('library_entry__platform_game__master_game_id', flat=True)[:10]
    trending_games = MasterGame.objects.filter(id__in=trending_ids).distinct()[:4]

    context = {
        'playing_games': playing_games,
        'recent_reviews': recent_reviews,
        'community_pulse': community_pulse,
        'playing_count': playing_count,
        'backlog_count': backlog_count,
        'total_completed': total_completed,
        'total_hours': round(total_minutes / 60, 1),
        'trending_games': trending_games,
    }
    return render(request, 'dashboard.html', context)


# BLOCO 2: BIBLIOTECA
@login_required
def library_view(request):
    items_per_page = request.GET.get('per_page', 24)
    items_per_page = 9999 if items_per_page == 'all' else int(items_per_page)

    base_query = UserLibraryEntry.objects.filter(user=request.user).select_related(
        'platform_game__master_game', 'platform_game__platform'
    )
    
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

    status_filter = request.GET.get('status')
    if status_filter: entries = entries.filter(status=status_filter)
    
    platform_filter = request.GET.get('platform')
    if platform_filter: entries = entries.filter(platform_game__platform__slug=platform_filter)

    sort_by = request.GET.get('sort', 'recent')
    ordering_map = {
        'name_asc': 'platform_game__master_game__title',
        'playtime_desc': '-playtime_minutes',
        'rating_desc': F('rating').desc(nulls_last=True),
        'recent': F('last_played').desc(nulls_last=True),
    }
    order_expression = ordering_map.get(sort_by, F('last_played').desc(nulls_last=True))
    entries = entries.order_by(order_expression)

    paginator = Paginator(entries, items_per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

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


# BLOCO 3: DETALHES DO JOGO
@login_required
def game_detail_view(request, game_id):
    entry = get_object_or_404(
        UserLibraryEntry.objects.select_related('platform_game__master_game', 'platform_game__platform'),
        pk=game_id,
        user=request.user
    )
    master = entry.platform_game.master_game

    if request.method == 'POST':
        if 'toggle_favorite' in request.POST:
            entry.is_favorite = not entry.is_favorite
            entry.save()
            return redirect('game_detail', game_id=game_id)

        if 'create_review' in request.POST:
            rating_val = request.POST.get('rating')
            rec_val = request.POST.get('is_recommended')
            is_rec = True if rec_val == 'true' else (False if rec_val == 'false' else None)
            
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
                achievement_percent_snapshot=current_pct
            )
            
            if rating_val: 
                entry.rating = float(rating_val)
            if is_rec is not None:
                entry.is_recommended = is_rec
            entry.save()
            return redirect('game_detail', game_id=game_id)

        elif 'create_tip' in request.POST:
            GameTip.objects.create(
                user=request.user,
                master_game=master,
                text=request.POST.get('tip_text')
            )
            return redirect('game_detail', game_id=game_id)

        elif 'vote_tip' in request.POST:
            tip_id = request.POST.get('tip_id')
            vote_val = int(request.POST.get('vote_value'))
            tip = get_object_or_404(GameTip, pk=tip_id)
            
            existing_vote = TipVote.objects.filter(user=request.user, tip=tip).first()
            if not existing_vote:
                TipVote.objects.create(user=request.user, tip=tip, value=vote_val)
                if vote_val == 1: tip.upvotes = F('upvotes') + 1
                else: tip.downvotes = F('downvotes') + 1
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

    total_achievements = entry.platform_game.achievements.count()
    unlocked_ids = UserAchievement.objects.filter(
        user=request.user, 
        achievement__platform_game=entry.platform_game
    ).values_list('achievement_id', flat=True)
    percentage = (len(unlocked_ids) / total_achievements * 100) if total_achievements > 0 else 0

    user_reviews = Review.objects.filter(user=request.user, library_entry=entry).order_by('-created_at')
    
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


# BLOCO 4: PERFIL
@login_required
def profile_view(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    library = UserLibraryEntry.objects.filter(user=user)
    
    total_games = library.count()
    
    # Cálculos em memória
    total_playtime_minutes = library.aggregate(Sum('playtime_minutes'))['playtime_minutes__sum'] or 0
    total_hours = round(total_playtime_minutes / 60, 1)
    
    total_xp = UserAchievement.objects.filter(user=user).aggregate(Sum('achievement__xp_value'))['achievement__xp_value__sum'] or 0
    total_achievements_unlocked = UserAchievement.objects.filter(user=user).count()

    current_level = 1 + int(total_xp / 1000)
    xp_progress = total_xp - ((current_level - 1) * 1000)
    level_progress_percent = (xp_progress / 1000) * 100

    # Atualiza stats do gráfico (apenas em memória ou via save controlado)
    started_games = library.exclude(status='backlog').count()
    completed_games = library.filter(status='completed').count()
    
    profile.stat_volume = min(int((total_xp / 50000) * 100), 100)
    profile.stat_skill = min(int((completed_games / started_games) * 100), 100) if started_games > 0 else 0
    unique_platforms = library.values('platform_game__platform').distinct().count()
    profile.stat_variety = min(int((unique_platforms / 5) * 100), 100)
    
    social_count = Review.objects.filter(user=user).count() + GameTip.objects.filter(user=user).count()
    profile.stat_social = min(int((social_count / 20) * 100), 100)
    profile.stat_speed = min(int((completed_games / total_games) * 100), 100) if total_games > 0 else 0
    profile.save() # Ok, mantivemos o save aqui por simplicidade, mas o ideal é mover depois.
    
    platform_stats = library.values('platform_game__platform__name').annotate(count=Count('id')).order_by('-count')

    context = {
        'user': user,
        'profile': profile,
        'total_games': total_games,
        'completed_games': completed_games,
        'total_hours': total_hours,
        'achievements_count': total_achievements_unlocked,
        'total_xp': total_xp,
        'current_level': current_level,
        'level_progress_percent': level_progress_percent,
        'xp_current': xp_progress,
        'platform_stats': platform_stats,
    }
    return render(request, 'profile.html', context)


# BLOCO 5: ADICIONAR JOGO
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
                    headers = {'Client-ID': CLIENT_ID, 'Authorization': f'Bearer {access_token}'}
                    q = f'search "{search_query}"; fields name, cover.url, first_release_date; limit 20;'
                    response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=q)
                    results = response.json()
                    if isinstance(results, list):
                        for res in results:
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


# BLOCO 6: LISTAS
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
    game_list = get_object_or_404(GameList, pk=list_id)
    # Check de segurança simples
    if not game_list.is_public and game_list.user != request.user:
         return redirect('dashboard')
         
    items = game_list.items.select_related('master_game').all().order_by('order')
    return render(request, 'lists/list_detail.html', {'list': game_list, 'items': items})

@login_required
def add_to_list_view(request, game_id):
    if request.method == 'POST':
        list_id = request.POST.get('list_id')
        comment = request.POST.get('comment', '')
        target_list = get_object_or_404(GameList, pk=list_id, user=request.user)
        entry = get_object_or_404(UserLibraryEntry, pk=game_id)
        master = entry.platform_game.master_game
        last_order = target_list.items.count() + 1
        GameListItem.objects.create(game_list=target_list, master_game=master, order=last_order, comment=comment)
        return redirect('game_detail', game_id=game_id)
    return redirect('library')


# BLOCO 7: EXPORT
@login_required
def export_data_view(request):
    user = request.user
    data = {'username': user.username, 'exported_at': str(timezone.now()), 'library': []}
    for entry in UserLibraryEntry.objects.filter(user=user):
        data['library'].append({
            'game': entry.platform_game.master_game.title,
            'status': entry.status,
            'rating': entry.rating
        })
    response = HttpResponse(json.dumps(data, indent=4, cls=DjangoJSONEncoder), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="alkahest_data_{user.username}.json"'
    return response


# BLOCO 8: CRUD
@login_required
def edit_review_view(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            entry = review.library_entry
            if entry.rating != review.rating:
                entry.rating = review.rating
                entry.save()
            return redirect('game_detail', game_id=entry.id)
    else: form = ReviewForm(instance=review)
    return render(request, 'reviews/edit_review.html', {'form': form, 'review': review})

@login_required
def delete_review_view(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    game_id = review.library_entry.id
    if request.method == 'POST':
        review.delete()
        return redirect('game_detail', game_id=game_id)
    return render(request, 'reviews/delete_review_confirm.html', {'review': review})

@login_required
def edit_library_entry_view(request, entry_id):
    entry = get_object_or_404(UserLibraryEntry, id=entry_id, user=request.user)
    if request.method == 'POST':
        form = UserLibraryEntryForm(request.POST, instance=entry)
        if form.is_valid():
            # Lógica de troca de plataforma mantida
            new_platform = form.cleaned_data['platform']
            if new_platform != entry.platform_game.platform:
                master = entry.platform_game.master_game
                pg, _ = PlatformGame.objects.get_or_create(
                    master_game=master, platform=new_platform,
                    defaults={'external_id': f"manual_{uuid.uuid4()}", 'external_title': master.title}
                )
                entry.platform_game = pg
            
            entry.status = form.cleaned_data['status']
            entry.rating = form.cleaned_data['rating']
            entry.is_favorite = form.cleaned_data['is_favorite']
            entry.save()
            return redirect('game_detail', game_id=entry.id)
    else: form = UserLibraryEntryForm(instance=entry)
    return render(request, 'library/edit_entry.html', {'form': form, 'entry': entry})

@login_required
def edit_tip_view(request, tip_id):
    tip = get_object_or_404(GameTip, id=tip_id, user=request.user)
    if request.method == 'POST':
        form = GameTipForm(request.POST, instance=tip)
        if form.is_valid():
            form.save()
            entry = UserLibraryEntry.objects.filter(user=request.user, platform_game__master_game=tip.master_game).first()
            return redirect('game_detail', game_id=entry.id) if entry else redirect('dashboard')
    else: form = GameTipForm(instance=tip)
    return render(request, 'tips/edit_tip.html', {'form': form, 'tip': tip})

@login_required
def delete_tip_view(request, tip_id):
    tip = get_object_or_404(GameTip, id=tip_id, user=request.user)
    if request.method == 'POST':
        tip.delete()
        return redirect('dashboard')
    return render(request, 'tips/delete_tip_confirm.html', {'tip': tip})


# BLOCO 9: SOCIAL VIEWS (Fase 2)
@login_required
def discovery_view(request):
    return render(request, 'discovery.html')

@login_required
def toggle_follow_view(request, username):
    target = get_object_or_404(User, username=username)
    if target != request.user:
        follow, created = UserFollow.objects.get_or_create(follower=request.user, target=target)
        if not created: follow.delete()
    return redirect(request.META.get('HTTP_REFERER', 'social_hub'))

@login_required
def social_hub_view(request):
    following = UserFollow.objects.filter(follower=request.user).select_related('target__profile')
    followers = UserFollow.objects.filter(target=request.user).select_related('follower__profile')
    suggestions = User.objects.exclude(id__in=[f.target.id for f in following] + [request.user.id])[:5]
    return render(request, 'social/hub.html', {'following': following, 'followers': followers, 'suggestions': suggestions})

@login_required
def rivals_view(request):
    following_ids = list(UserFollow.objects.filter(follower=request.user).values_list('target_id', flat=True))
    following_ids.append(request.user.id)
    
    leaderboard_data = []
    # Busca perfis com otimização
    profiles = UserProfile.objects.filter(user_id__in=following_ids).select_related('user')
    
    for profile in profiles:
        total_xp = UserAchievement.objects.filter(user=profile.user).aggregate(Sum('achievement__xp_value'))['achievement__xp_value__sum'] or 0
        
        # Correção do Erro B: Calcular nível aqui no Python
        level = 1 + int(total_xp / 1000) 

        leaderboard_data.append({
            'user': profile.user,
            'xp': total_xp,
            'level': level, # Passando o nível pronto
            'games_completed': UserLibraryEntry.objects.filter(user=profile.user, status='completed').count(),
            'avatar': profile.avatar_url
        })
    
    leaderboard_data.sort(key=lambda x: x['xp'], reverse=True)
    return render(request, 'social/rivals.html', {'leaderboard': leaderboard_data})

    
    leaderboard_data.sort(key=lambda x: x['xp'], reverse=True)
    return render(request, 'social/rivals.html', {'leaderboard': leaderboard_data})
