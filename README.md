# Project Alkahest

> **Arquivado em 28 de agosto de 2026.** Projeto encerrado, não será retomado.
> O código fica público como registro técnico e post-mortem.

> 🇬🇧 **In English:** Alkahest was a Django platform that synced a player's game
> library and achievements across Steam and RetroAchievements, reconciled them
> against IGDB's canonical catalog, and built a unified profile with reviews,
> lists and a social graph. Developed Jan–Feb 2026, archived unfinished. This
> README is a post-mortem: what was built, what wasn't, and why it stopped.

---

## O que era

Um "perfil gamer unificado": você conectava suas contas, o sistema puxava
biblioteca e conquistas de cada plataforma, resolvia a identidade de cada jogo
contra o catálogo canônico do IGDB, e montava um perfil único com diário de
jogos, reviews, listas e grafo social.

O problema real que ele atacava não era a interface — era **reconciliação de
identidade**. "Final Fantasy VII Remake" na Steam, na PSN e no IGDB são três
registros diferentes, com nomes, IDs e edições diferentes. Boa parte do código
existe para resolver isso.

## Status: incompleto

| | |
|---|---|
| Período de desenvolvimento | 12/jan/2026 → 09/fev/2026 (~4 semanas) |
| Commits | 114 |
| Python | 4.438 linhas |
| Models | 23 |
| Templates | 31 |
| Testes de segurança | 542 linhas |
| Roadmap (Linear) | 154 issues — **15 concluídas** |
| Estado do deploy | beta fechado; nunca subiu de forma estável |
| Usuários externos | 0 |

## Stack

Django · PostgreSQL · Celery · Redis · IGDB API · django-allauth (Steam OpenID +
RetroAchievements) · django-environ · nh3 · django-ratelimit · django-dbbackup ·
PostHog · i18n PT-BR / EN / ES

## O que chegou a funcionar

- **Sync de biblioteca e conquistas** — Steam e RetroAchievements, via tasks
  Celery com cache de API externa por camada (`vault/tasks.py`).
- **Matching de jogos contra o IGDB** — normalização de nome em dois níveis
  (`_sanitize_light` / `_sanitize_heavy`) + fuzzy matching, com fila de
  enriquecimento assíncrono (`vault/services.py`).
- **Modelo de dados em três camadas** — `MasterGame` (obra canônica) →
  `PlatformGame` (a obra numa plataforma) → `UserLibraryEntry` (a cópia do
  usuário). Foi a decisão de arquitetura mais acertada do projeto.
- **Reviews, listas, tips e grafo social** (follow, notificações in-app).
- **Importador de Backloggd** — scraper + job assíncrono para migração de
  usuários vindos do concorrente.
- **LGPD completo** — export e delete de conta como tasks Celery.
- **Hardening** — sanitização XSS com `nh3`, checagens de ownership contra IDOR,
  rate limiting em views e em tasks, e uma suíte de testes de segurança
  (`tests/security/`) incluindo um `test_red_team.py`.
- **i18n** PT-BR / EN / ES e um painel administrativo ("God Mode") com
  ferramenta de merge de jogos duplicados.

## O que nunca saiu do papel

- Feed de atividades, discovery social, onboarding.
- **Robô de preços** — os models (`Store`, `GameStoreLink`, `PriceHistory`)
  estão desenhados e migrados, com `PriceHistory` como histórico imutável e
  `GameStoreLink` como fila de checagem. Nenhum crawler foi escrito.
- PSN, Xbox, Epic, GOG, Nintendo.
- Gamificação (XP, badges, streaks), monetização, apps mobile.

---

## Post-mortem

### 1. Escopo antes de validação

154 issues distribuídas em 5 fases foram planejadas antes de um único usuário
externo tocar no produto. As fases 6, 7 e 8 — 76 issues — descreviam features
para uma escala que nunca existiu. Nesse mesmo período, zero horas foram gastas
conversando com quem usaria a coisa.

O sintoma foi visível no próprio board: 15 issues concluídas contra 139 abertas.
O roadmap virou um objeto de consumo em si, não um instrumento de priorização.

### 2. O diferencial imaginado era feature; o diferencial real era distribuição

A tese do projeto era que o conjunto de features certo venceria. Em fevereiro de
2026, [Your Gamer Profile](https://yourgamerprofile.com) — projeto brasileiro
independente, construído sobre o **mesmo** IGDB — lançou publicamente com uma
sobreposição quase total do roadmap do Alkahest: sync multi-plataforma,
conquistas, reviews, listas, badges, comunidades, feed, app Android e
monetização ativa.

Não foi cópia. Foi a mesma lacuna óbvia, lida por duas pessoas — a que Backloggd,
Grouvee e Exophase deixam aberta há anos. A ideia nunca foi o fosso. Quem chegou
ao público com audiência construída venceu, e a diferença entre os dois projetos
não foi técnica.

O mesmo vale para o pivô que chegou a ser considerado (rastreador de preços e
detector de assinaturas): IsThereAnyDeal e GG.deals já ocupavam esse espaço havia
mais de uma década, de graça, com API pública. A pesquisa que teria revelado isso
custaria uma tarde — e não foi feita antes de 15 issues serem escritas.

### 3. Segurança e compliance cedo: instinto certo, momento errado

LGPD, XSS, IDOR, rate limiting e uma suíte de red team foram implementados na
Fase 4, antes do primeiro usuário externo. É trabalho de qualidade e é a parte do
repositório que melhor se defende hoje. Mas consumiu semanas de um projeto que
ainda não tinha provado que alguém queria usá-lo. Endurecer o que ainda não foi
validado é otimização prematura com outro nome.

### 4. Generalização para uma escala que não veio

A separação `MasterGame` / `PlatformGame` está correta e é o que eu repetiria.
Já `PriceHistory` com histórico imutável e fila de checagem indexada foi
projetado para um volume que o produto nunca chegou perto de ter — e nunca teve
uma linha de crawler para alimentá-lo. Modelar bem é barato; modelar cedo
demais, não.

### 5. O que eu levo

Não considero as 4 semanas perdidas. Django, Celery, OAuth, integração com APIs
externas, reconciliação de entidades, i18n, LGPD e testes de segurança são
conhecimento que ficou. O erro não foi construir — foi construir por quatro
semanas sem em nenhum momento verificar se o mundo lá fora precisava daquilo, e
descobrir a resposta por acidente.

---

## Rodar localmente

Não recomendado — o projeto foi arquivado sem um deploy estável. Se ainda assim:

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Crie um `.env` na raiz:

```
DJANGO_SECRET_KEY=<gere um>
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgres://user:pass@localhost:5432/alkahest
REDIS_URL=redis://127.0.0.1:6379/1
STEAM_API_KEY=<steamcommunity.com/dev/apikey>
TWITCH_CLIENT_ID=<dev.twitch.tv — usado pelo IGDB>
TWITCH_CLIENT_SECRET=<idem>
BETA_ACTIVE=False
ENABLE_ANALYTICS=False
```

Precisa de PostgreSQL e Redis rodando. Depois:

```bash
python manage.py migrate
celery -A core worker -l info    # em outro terminal
python manage.py runserver
```

## Licença

Sem licença definida. O código está público para leitura e referência.

---

*Arquivado por Igor Lima em agosto de 2026.*
