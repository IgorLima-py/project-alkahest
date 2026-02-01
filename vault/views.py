# BLOCO 0: IMPORTAÇÕES
import io
import csv
import zipfile
import time
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import F, Q, Sum, Count, Case, When, Value, FloatField, CharField
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.utils.translation import activate
from django.conf import settings
from itertools import chain
from core.celery import app
import json
import uuid

from .tasks import run_backloggd_import_task
from .models import ProfileImportJob


# Forms
from .forms import ReviewForm, UserLibraryEntryForm, GameTipForm

# Models
from .models import (
    UserLibraryEntry, UserAchievement, Review, GameTip, TipVote, 
    GameList, GameListItem, MasterGame, Platform, PlatformGame,
    UserProfile, UserFollow, User, Notification
)

from .tasks import sync_steam_library_task, delete_user_account_task, export_user_data_task

# Services (A Nova Camada Inteligente)
from .services import fetch_and_update_game
from .utils_igdb import get_igdb_token

# === HELPER: ACTIVITY FEED ===
def get_community_pulse(user):
    following_ids = list(UserFollow.objects.filter(follower=user).values_list('target_id', flat=True))
    following_ids.append(user.id)
    
    recent_reviews = Review.objects.filter(
        user_id__in=following_ids
    ).select_related('user', 'library_entry__platform_game__master_game').annotate(
        activity_type=Value('review', output_field=CharField())
    ).order_by('-created_at')[:5]

    recent_starts = UserLibraryEntry.objects.filter(
        user_id__in=following_ids, status='playing'
    ).select_related('user', 'platform_game__master_game').annotate(
        activity_type=Value('started', output_field=CharField())
    ).order_by('-last_synced')[:5]

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
    playing_games = UserLibraryEntry.objects.filter(
        user=user, status='playing'
    ).select_related('platform_game__master_game', 'platform_game__platform').order_by('-last_played')[:6]
    
    community_pulse = get_community_pulse(user)
    recent_reviews = Review.objects.select_related('user', 'library_entry__platform_game__master_game').order_by('-created_at')[:5]
    
    stats = UserLibraryEntry.objects.filter(user=user).aggregate(
        total_completed=Count('id', filter=Q(status='completed')),
        total_minutes=Sum('playtime_minutes'),
        playing_count=Count('id', filter=Q(status='playing')),
        backlog_count=Count('id', filter=Q(status='backlog'))
    )
    
    # Trending (placeholder)
    trending_ids = Review.objects.values_list('library_entry__platform_game__master_game_id', flat=True)[:10]
    trending_games = MasterGame.objects.filter(id__in=trending_ids).distinct()[:4]

    context = {
        'playing_games': playing_games,
        'recent_reviews': recent_reviews,
        'community_pulse': community_pulse,
        'playing_count': stats['playing_count'],
        'backlog_count': stats['backlog_count'],
        'total_completed': stats['total_completed'],
        'total_hours': round((stats['total_minutes'] or 0) / 60, 1),
        'trending_games': trending_games,
    }
    return render(request, 'dashboard.html', context)

# BLOCO 2: BIBLIOTECA
@login_required
def library_view(request):
    items_per_page = request.GET.get('per_page', 24)
    items_per_page = 9999 if items_per_page == 'all' else int(items_per_page)

    entries = UserLibraryEntry.objects.filter(user=request.user).select_related(
        'platform_game__master_game', 'platform_game__platform'
    ).annotate(
        total_achievements=Count('platform_game__achievements', distinct=True),
        unlocked_achievements=Count(
            'platform_game__achievements__userachievement',
            filter=Q(platform_game__achievements__userachievement__user=F('user')),
            distinct=True
        )
    ).annotate(
        achievement_percentage=Case(
            When(total_achievements__gt=0, then=(F('unlocked_achievements') * 100.0 / F('total_achievements'))),
            default=Value(0.0), output_field=FloatField()
        )
    )

    status_filter = request.GET.get('status')
    if status_filter: entries = entries.filter(status=status_filter)
    
    platform_filter = request.GET.get('platform')
    if platform_filter: entries = entries.filter(platform_game__platform__slug=platform_filter)

    sort_by = request.GET.get('sort', 'recent')
    
    if sort_by == 'name_asc': 
        order = 'platform_game__master_game__title'
    elif sort_by == 'playtime_desc': 
        order = '-playtime_minutes'
    elif sort_by == 'rating_desc': 
        # Força ordenação decrescente de inteiro, jogando nulos pro final
        order = F('rating').desc(nulls_last=True)
    else: 
        # recent
        order = F('last_played').desc(nulls_last=True)
    
    entries = entries.order_by(order)
    paginator = Paginator(entries, items_per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    platforms = Platform.objects.filter(platformgame__userlibraryentry__user=request.user).distinct().order_by('name')

    context = {
        'page_obj': page_obj, 'total_games': paginator.count, 'platforms': platforms,
        'current_status': status_filter, 'current_platform': platform_filter, 'current_sort': sort_by
    }
    return render(request, 'library.html', context)

# BLOCO 3: DETALHES DO JOGO (Agora com lógica de metadados ricos)
@login_required
@ratelimit(key='user', rate='50/d', block=True) # Limite de 10 reviews por dia
def game_detail_view(request, game_id):
    entry = get_object_or_404(
        UserLibraryEntry.objects.select_related('platform_game__master_game', 'platform_game__platform'),
        pk=game_id, user=request.user
    )
    master = entry.platform_game.master_game

    # POST ACTIONS
    if request.method == 'POST':
        if 'toggle_favorite' in request.POST:
            entry.is_favorite = not entry.is_favorite
            entry.save()
            return redirect('game_detail', game_id=game_id)

        if 'create_review' in request.POST:
            form = ReviewForm(request.POST)
            
            if form.is_valid():
                review = form.save(commit=False) # O form já tratou o rating 0-100
                review.user = request.user
                review.library_entry = entry
                
                # Snapshot do tempo
                review.playtime_at_review = entry.playtime_minutes
                
                review.save() # AQUI o model.save() vai atualizar o entry.rating automaticamente!
                
                # Atualiza APENAS status se veio no POST (pois status não tá no form de review)
                status_val = request.POST.get('status')
                if status_val and status_val != entry.status:
                    entry.status = status_val
                    entry.save(update_fields=['status']) # Não precisa salvar rating de novo
                
                return redirect('game_detail', game_id=game_id)

        if 'create_tip' in request.POST:
            GameTip.objects.create(user=request.user, master_game=master, text=request.POST.get('tip_text'))
            return redirect('game_detail', game_id=game_id)

    # VIEW DATA
    total_ach = entry.platform_game.achievements.count()
    unlocked_ids = UserAchievement.objects.filter(
        user=request.user, achievement__platform_game=entry.platform_game
    ).values_list('achievement_id', flat=True)
    pct = (len(unlocked_ids) / total_ach * 100) if total_ach > 0 else 0

    user_reviews = Review.objects.filter(user=request.user, library_entry=entry).order_by('-created_at')
    community_reviews = Review.objects.filter(library_entry__platform_game__master_game=master).exclude(user=request.user).select_related('user__profile').order_by('-likes_count', '-created_at')[:10]
    tips = sorted(list(GameTip.objects.filter(master_game=master)), key=lambda t: t.score(), reverse=True)
    user_lists = GameList.objects.filter(user=request.user).order_by('-updated_at')

    existing_review = Review.objects.filter(user=request.user, library_entry=entry).first()
    
    if existing_review:
        review_form = ReviewForm(instance=existing_review)
    else:
        # Se não tem review, mas tem rating na library, preenche o rating
        initial_data = {'rating': entry.rating} if entry.rating is not None else {}
        review_form = ReviewForm(initial=initial_data)

    context = {
        'entry': entry, 
        'master': master, 
        'platform': entry.platform_game.platform,
        'community_reviews': community_reviews,
        'total_achievements': total_ach, 
        'unlocked_achievements': len(unlocked_ids),
        'percentage': pct, 
        'unlocked_ids': set(unlocked_ids),
        'user_reviews': user_reviews, 
        'tips': tips, 
        'user_lists': user_lists,
        'review_form': review_form, # <--- ADICIONE ESTA LINHA
    }
    return render(request, 'game_detail.html', context)

# BLOCO 4: PERFIL
@login_required
def profile_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    # Recalculando Stats Rápido (Ideal mover para signal ou job async)
    total_xp = UserAchievement.objects.filter(user=user).aggregate(Sum('achievement__xp_value'))['achievement__xp_value__sum'] or 0
    profile.stat_volume = min(int((total_xp / 50000) * 100), 100)
    profile.save()

    context = {
        'user': user, 'profile': profile,
        'total_xp': total_xp,
        'total_games': UserLibraryEntry.objects.filter(user=user).count()
    }
    return render(request, 'profile.html', context)

@login_required
@require_POST
def request_data_export_view(request):
    """Dispara o dump de dados assíncrono."""
    export_user_data_task.delay(request.user.id)
    # Feedback visual (Toast ou Message)
    return HttpResponse("Solicitação recebida. Você será notificado quando o arquivo estiver pronto.")

@login_required
@require_POST
def delete_account_view(request):
    """Soft Delete da conta."""
    # Verificação extra de segurança (ex: senha) seria ideal aqui
    delete_user_account_task.delay(request.user.id)
    # Logout imediato
    from django.contrib.auth import logout
    logout(request)
    return redirect('login')

# BLOCO 5: ADICIONAR JOGO (Lógica Nova Inteligente)
@login_required
def add_game_view(request):
    platforms = Platform.objects.all().order_by('name')
    results = []
    search_query = ""

    if request.method == 'POST':
        # BUSCA
        if 'search_query' in request.POST:
            search_query = request.POST.get('search_query')
            
            # Detecção de ID vs Nome
            # Se for só números, assume ID do IGDB
            igdb_id = int(search_query) if search_query.isdigit() else None
            
            # Chama o Service Inteligente (ele busca no IGDB e salva/atualiza o MasterGame Local)
            master = fetch_and_update_game(igdb_id=igdb_id, search_name=search_query if not igdb_id else None)
            
            if master:
                # Retorna como lista para o template iterar
                results = [master]
            else:
                # Se o service não achar (ex: nome muito genérico ou erro), tenta busca raw só pra mostrar lista
                # Mas o ideal é que o service lide com isso.
                # Por hora, se o service retornar None, é pq não achou nada exato.
                pass

        # ADICIONAR À BIBLIOTECA
        elif 'add_master_id' in request.POST:
            master_id = request.POST.get('add_master_id') # ID local do nosso banco (UUID)
            platform_slug = request.POST.get('platform_slug')
            status = request.POST.get('status')
            
            master = get_object_or_404(MasterGame, id=master_id)
            platform = get_object_or_404(Platform, slug=platform_slug)
            
            # Cria vinculo PlatformGame se não existir
            pg, _ = PlatformGame.objects.get_or_create(
                master_game=master, platform=platform,
                defaults={'external_id': f"manual_{uuid.uuid4()}", 'external_title': master.title}
            )
            
            entry, created = UserLibraryEntry.objects.get_or_create(
                user=request.user, platform_game=pg, defaults={'status': status}
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
            # 1. Lógica de Troca de Plataforma (Mantida intacta)
            new_platform = form.cleaned_data['platform']
            if new_platform != entry.platform_game.platform:
                master = entry.platform_game.master_game
                pg, _ = PlatformGame.objects.get_or_create(
                    master_game=master, platform=new_platform,
                    defaults={'external_id': f"manual_{uuid.uuid4()}", 'external_title': master.title}
                )
                entry.platform_game = pg
            
            # 2. Salva campos padrão (Status, Favorito) E o Rating (via lógica interna do Form)
            entry = form.save() 
            
            return redirect('game_detail', game_id=entry.id)
    else:
        form = UserLibraryEntryForm(instance=entry)
    
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
    
    leaderboard_data = UserProfile.objects.filter(
        user_id__in=following_ids
    ).select_related('user').annotate(
        total_xp=Sum('user__userachievement__achievement__xp_value', default=0),
        games_completed=Count('user__library', filter=Q(user__library__status='completed'))
    ).order_by('-total_xp')

    # Ajuste no template: iterar direto sobre 'leaderboard_data'
    # Nível pode ser calculado no template ou via property no Model (melhor)
    return render(request, 'social/rivals.html', {'leaderboard': leaderboard_data})


@login_required
@require_POST
def trigger_steam_sync_view(request):
    user_id = request.user.id
    
    # Manda o Celery buscar a task pelo nome (string)
    # Isso evita o erro de "function object"
    app.send_task('vault.tasks.sync_steam_library_task', args=[user_id])
    
    return HttpResponse(f"""
        <button class="btn btn-sm btn-outline-warning text-warning d-flex align-items-center gap-2 opacity-75" disabled>
            <div class="spinner-border spinner-border-sm" role="status"></div>
            <span>Sincronizando...</span>
        </button>
    """)


@login_required
@ratelimit(key='user', rate='50/h', block=True) # Aumentei para 10/h para você testar sem travar
def request_export_view(request):
    user = request.user
    
    # 1. Preparar CSV da Biblioteca
    lib_buffer = io.StringIO()
    writer_lib = csv.writer(lib_buffer)
    writer_lib.writerow(['Title', 'Platform', 'Status', 'Rating', 'Playtime (Min)', 'Last Played'])
    
    library = UserLibraryEntry.objects.filter(user=user).select_related('platform_game__master_game', 'platform_game__platform')
    for entry in library:
        writer_lib.writerow([
            entry.platform_game.master_game.title,
            entry.platform_game.platform.name,
            entry.status,
            entry.rating or '',
            entry.playtime_minutes,
            str(entry.last_played or '')
        ])
        
    # 2. Preparar CSV de Reviews
    rev_buffer = io.StringIO()
    writer_rev = csv.writer(rev_buffer)
    writer_rev.writerow(['Game', 'Date', 'Rating', 'Review Text', 'Recommended'])
    
    reviews = Review.objects.filter(user=user).select_related('library_entry__platform_game__master_game')
    for rev in reviews:
        writer_rev.writerow([
            rev.library_entry.platform_game.master_game.title,
            rev.created_at.strftime('%Y-%m-%d'),
            rev.rating or '',
            rev.text,
            'Yes' if rev.is_recommended else 'No'
        ])

    # 3. Zipar tudo em Bytes
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(f'alkahest_library.csv', lib_buffer.getvalue())
        zip_file.writestr(f'alkahest_reviews.csv', rev_buffer.getvalue())
    
    # 4. Retornar como Download
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="alkahest_export_{user.username}_{int(time.time())}.zip"'
    return response

@login_required
def delete_account_view(request):
    if request.method == 'POST':
        # Idealmente pedir confirmação de senha aqui
        delete_user_account_task.delay(request.user.id)
        logout(request)
        return redirect('login')
    return render(request, 'settings/delete_confirm.html')

# ==========================================
# BLOCO 10: API & UTILS (Addendum Fase 4)
# ==========================================

@login_required
def set_language_view(request):
    """
    Endpoint para trocar idioma via POST/HTMX.
    Salva na sessão e no perfil (se existir).
    """
    lang_code = request.POST.get('language')
    next_url = request.POST.get('next', '/')
    
    if lang_code and lang_code in dict(settings.LANGUAGES).keys():
        activate(lang_code)
        request.session[settings.LANGUAGE_COOKIE_NAME] = lang_code
        
        # Persistência no Perfil (se você adicionou o campo sugerido anteriormente)
        if hasattr(request.user, 'profile'):
            request.user.profile.language_preference = lang_code
            request.user.profile.save(update_fields=['language_preference'])
            
    response = redirect(next_url)
    response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang_code)
    return response

@login_required
def notifications_check_view(request):
    """
    Endpoint leve para Polling (HTMX).
    Retorna apenas JSON com count para atualizar o badge.
    """
    # Performance: count() é mais rápido que carregar objetos
    # O indice composto [recipient, is_read] criado no model garante O(1) aqui.
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    
    # Se o request for HTMX, podemos retornar um partial HTML do badge
    if request.headers.get('HX-Request'):
        if unread_count == 0:
            return HttpResponse("") 
        
        # HTML FORÇANDO O VISUAL VERMELHO
        html = f"""
        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger border border-light">
            {unread_count}
            <span class="visually-hidden">unread messages</span>
        </span>
        """
        return HttpResponse(html)


@login_required
@require_POST
def notifications_mark_read_view(request):
    """Marca tudo como lido ao abrir o dropdown"""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    
    # Para o HTMX saber que deu certo
    return HttpResponse("OK")



@login_required
def design_lab_view(request):
    # Mock Data simulando jogos reais da sua library
    samples = [
        {
            'id': 1,
            'title': 'Bad Rats', # Exemplo Common
            'rating': 25, # 2.5
            'tier': 'common',
            'color': '#ff1744',
            'cover': 'https://placehold.co/300x450/333/FFF?text=Bad+Rats'
        },
        {
            'id': 2,
            'title': 'Cyber Glitch', # Exemplo Uncommon
            'rating': 55, # 5.5
            'tier': 'uncommon',
            'color': '#ffd600',
            'cover': 'https://placehold.co/300x450/444/FFF?text=Cyber'
        },
        {
            'id': 3,
            'title': 'Eco Warrior', # Exemplo Rare
            'rating': 78, # 7.8
            'tier': 'rare',
            'color': '#00e676',
            'cover': 'https://placehold.co/300x450/555/FFF?text=Eco'
        },
        {
            'id': 4,
            'title': 'Starfield 2', # Exemplo Legendary
            'rating': 99, # 9.9
            'tier': 'legendary',
            'color': '#940ef9', # Roxo padrão, mas será customizável no front
            'cover': 'https://placehold.co/300x450/666/FFF?text=Starfield'
        },
    ]
    return render(request, 'design_lab.html', {'samples': samples})


@login_required
@require_POST
def start_backloggd_import(request):
    username = request.POST.get('backloggd_username')
    if not username:
        return HttpResponse("Username required", status=400)
    
    # Cria Job
    job = ProfileImportJob.objects.create(
        user=request.user,
        target_username=username,
        status='pending'
    )
    
    # Dispara Async
    run_backloggd_import_task.delay(job.id)
    
    # Retorna HTML inicial do progresso (HTMX swap)
    return render(request, 'includes/import_progress.html', {'job': job})

@login_required
def check_import_status(request, job_id):
    job = get_object_or_404(ProfileImportJob, id=job_id, user=request.user)
    
    if job.status == 'completed':
        # Retorna mensagem de sucesso e trigger para refresh da página
        response = HttpResponse('<div class="alert alert-success">Importação concluída! Recarregando...</div>')
        response['HX-Trigger'] = 'libraryChanged' # Evento para frontend recarregar
        return response
        
    return render(request, 'includes/import_progress.html', {'job': job})