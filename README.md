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

As **139 ideias que morreram no roadmap** estão listadas na íntegra em
[Banco de ideias](#banco-de-ideias--as-139-que-nunca-saíram-do-papel), no fim
deste README — tier lists, Alkahest Chart, Sistema de Honra, Oracle League,
Museu do Hardware, Calculadora de Shame e o resto.

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

## Banco de ideias — as 139 que nunca saíram do papel

O roadmap tinha 154 issues. 15 foram entregues; **139 morreram como ideia**. Elas
estão aqui na íntegra, porque é a parte do projeto que tem mais valor do que o
código: é o registro do que eu achava que um tracker de jogos deveria ser.

Cada item traz o ID original do Linear. Nada foi filtrado por qualidade — tem
ideia boa, ideia cara demais, ideia que já existia em outro lugar e ideia que era
só um bilhete pra mim mesmo.

### Reviews & diário

- **ALK-16 · Reviews 2.0** — Texto rico (sanitizado com nh3), tags de spoiler colapsáveis, datas de início/fim, checkbox de "Replay" (segunda jogatina), nota 0–10 num slider colorido estilo Metacritic isolado e centralizado no topo do formulário, botão de recomenda/não recomenda, tags livres, adicionar a uma lista durante a escrita, marcar se recebeu o jogo de graça, idioma da review (PT/EN/ES/outro), e tempo até zerar e até platinar (ambos opcionais). UI progressiva: **Review Simples** (nota + texto + spoiler) por padrão, com um accordion "Adicionar Detalhes" abrindo o resto. Botão explícito de salvar rascunho, mesmo com auto-save.
- **ALK-17 · Social em reviews** — Like/dislike, botão de report (placeholder), e a pergunta em aberto: permitir comentários?
- **ALK-18 · Drafts & edição** — Auto-save a cada 30s via AJAX. Editar review publicada com carimbo "Editado em X". Ownership check antes de editar/deletar.
- **ALK-19 · Filtros de diário com persistência** — Ordenar por data jogada, ano, nota, plataforma — e salvar a preferência ("Lembrar minha escolha").
- **ALK-20 · Tips rápidas (estilo Dark Souls)** — Dicas de 140 caracteres, sem formatação rica, separadas das reviews longas. Rate limit de 20/dia. *(A única ideia que eu já tinha cancelado sozinho.)*
- **ALK-21 · Indicador de review na grid** — Ícone na capa dos jogos que já têm review, ao lado da nota que o usuário deu.
- **ALK-45 · Opções avançadas de edição de review** — Anotado com um "ver se vale a pena fazer isso ou não".
- **ALK-143 · Mídia da cópia** — Na review, marcar se o jogo foi físico, digital, etc.
- **ALK-148 · Custom Scores** — Nota padrão 0–10 inteira; usuário free pode optar por estrelas estilo Letterboxd. Usuário Pro monta uma **nota composta**: escolhe de 2 a 5 critérios cujos pesos somam 100% e avalia cada um. Nas visualizações simples continua aparecendo o 0–10 normalizado (para as médias do site fecharem), mas com ícone hexagonal com brilho neon em vez do quadrado flat.

### Coleção, listas & tier lists

- **ALK-22 · Listas com ownership** — Criar listas (nome, descrição sanitizada, pública/privada), adicionar jogos, ordenar à mão. Página "Explore Lists" com busca e filtros de mais populares/recentes.
- **ALK-23 · Grid vs Lista** — Alternar entre capas e tabela (plataforma/nota/status), salvando a preferência.
- **ALK-24 · Modos de visualização do diário** — Calendário heatmap estilo GitHub (dia = jogo finalizado), lista condensada, e distribuição das notas do usuário igual ao Letterboxd.
- **ALK-25 · Software vs jogo** — Tag `is_software` baseada na categoria do IGDB, para esconder emuladores/DLCs/demos da biblioteca e separar "horas em jogos" de "horas em software".
- **ALK-26 · Efeito "Platina"** — Borda dourada com glow sutil nos jogos 100%, e efeito equivalente para os marcados como finalizados. Com opção de desligar, pra quem acha brega.
- **ALK-38 · Ordenação avançada** — Por nota pessoal, nota da crítica (IGDB), tempo de jogo, data de lançamento.
- **ALK-140 · Comentar nas listas.**
- **ALK-141 · Pódio nas listas ordenadas** — 1º, 2º e 3º lugar com o número em dourado, prateado e bronze.
- **ALK-142 · Progresso por lista** — Mostrar a % de quanto você já jogou e/ou zerou de uma determinada lista.
- **ALK-147 · Tier lists** — Nas listas, opção de montar tier list com subdivisões.

### Perfil & identidade

- **ALK-27 · Perfil v1** — Bio sanitizada, Top 5 jogos (com opção de deixar rankeado ou não), atividade recente, "setup" do usuário (console principal, gênero favorito), upload de avatar validado.
- **ALK-28 · Top 5 customizável** — Slot vazio abre modal com busca AJAX no IGDB.
- **ALK-95 · Alkahest Chart (5 pontas)** — Radar chart no perfil com cinco dimensões normalizadas 0–100: **Volume** (total de jogos), **Skill** (raridade média dos troféus), **Social** (seguidores + reviews curtidas), **Speed** (jogos zerados por mês) e **Variety** (diversidade de gêneros).
- **ALK-101 · Museu do Hardware (inspirado em Astro Bot)** — Ícones isométricos dos consoles que o usuário jogou, em estilo *embroidered patch*. Console que ele ainda tem fica colorido; o que jogou mas não tem mais fica cinza. Emulador: não sabia o que fazer.

### Gamificação, XP & badges

- **ALK-158 · Sistema de XP** — Tabela proposta com a lógica de cada valor: escrever review +50 (gera conteúdo/SEO), importar biblioteca +100 uma única vez (lock-in), seguir alguém +10 (aumenta o grafo), receber like numa review +5 (incentiva review boa, não spam), platinar um jogo de verdade +200 (valida a tese de "tracker real"). Em vez de "Nível 10", **títulos derivados do Alkahest Chart**: muitos jogos e pouca platina = *Hoarder*; poucos jogos e muita platina = *Completionist/Hunter*; muitas reviews curtidas = *Critic/Oracle*; joga de tudo = *Jack of All Trades*.
- **ALK-96 · Nível & XP** — Níveis 1–100 em curva exponencial, com badge no perfil.
- **ALK-97 · Raridade real recalculada** — Recalcular raridade dos troféus pela % de unlock **na base do Alkahest**, não na da Steam/PSN. Só ativar acima de 10 mil usuários ativos.
- **ALK-98 · Heatmap de conquistas** — 365 dias estilo GitHub, cor = intensidade de troféus desbloqueados.
- **ALK-99 · Badges & insígnias** — Conquistas do próprio site ("Jogou 10 RPGs", "Zerou um jogo em 1 semana", "Primeira Platina"), com galeria em `/badges/`.
- **ALK-100 · Sistema de Honra (estilo RDR2)** — Reputação social: +honra por reviews úteis, denúncias procedentes e contribuir com metadados; −honra por denúncia falsa, spoiler não marcado e spam. Badge "Honorable" (verde) ou "Dishonorable" (vermelho), consultada pelos moderadores antes de banir.
- **ALK-123 · Streak counter de conquistas.**
- **ALK-139 · Eventos com XP e badge exclusiva** — Ex.: competição de quem pega primeiro o top 1 nos 50 jogos mais obscuros, ou runs no speedrun.com. Prêmio e badge personalizada para a conquista mais rara.
- **ALK-155 · Streaks viciantes** — Daily login bonus e "review streak": três semanas seguidas escrevendo review dá a badge "Crítico Dedicado". Push notification (via PWA) lembrando do streak.

### Social & comunidade

- **ALK-29 · Grafo social + bloqueio** — Seguir/deixar de seguir, mais bloqueio real (impede ver perfil, reviews, listas e aparecer na busca) e mute (esconde sem notificar).
- **ALK-30 · Discovery social** — Busca de usuários, página "Top Reviewers", CTA de seguir ao lado do autor da review.
- **ALK-31 · Feed de atividades** — Reviews e notas de quem você segue nos últimos 7 dias, com `select_related`/`prefetch_related` para matar N+1, paginação de 20 e cache de 5 min.
- **ALK-32 · Sino de notificações v2** — Badge de não lidas, dropdown com as últimas 5, link para ver todas.
- **ALK-33 · Moderação básica** — Botão de reportar em reviews/listas/perfis, fila de denúncias no admin, shadowban manual.
- **ALK-102 · Sistema de Rival** — Escolher um amigo como rival e ter uma página de comparação direta: jogos em comum (quem platinou e quem não), ranking de troféus raros, gráfico de atividade mensal. Opt-in dos dois lados.
- **ALK-103 · Matchmaking social** — "Descubra Amigos" por similaridade de cosseno entre vetores de gêneros jogados, plataformas e nota média.
- **ALK-104 · Comunidades & grupos** — Páginas para clãs e criadores (ex.: "Speedrunners Brasil") com feed próprio, listas compartilhadas e eventos ("Maratona de Platinas").
- **ALK-105 · Desafios & contratos** — Desafiar um amigo ("Platine Bloodborne antes de mim"), com deadline e notificação quando aceito/completo.
- **ALK-106 · Recomendações P2P** — "Recomendar para amigo" na página do jogo, que cai na wishlist dele se aceitar. Rate limit de 5/dia.
- **ALK-108 · Perfil privado + follow request.**
- **ALK-120 · Presença em tempo real** — "Quem está jogando AGORA" via WebSocket. Anotado como infraestrutura cara (heartbeat a cada 30s) — e a dúvida se dava pra puxar do Discord em vez disso.

### Economia, preços & assinaturas

- **ALK-51 · Wishlist unificada** — Lista central de desejados, escolhendo por jogo quais lojas monitorar (Steam/PSN/Nuuvem/Amazon).
- **ALK-55 · Rastreador de preços** — O robô que preencheria as tabelas `PriceHistory`/`GameStoreLink` que já estavam modeladas e migradas. Nunca foi escrito.
- **ALK-56 · Alertas de promoção** — Queda de preço >20% gera notificação e e-mail (se opt-in), com no máximo 1 e-mail por dia agrupando os alertas.
- **ALK-57 · Filosofia de utilidade** — Widget "Best Deals" no dashboard: os 5 jogos da wishlist com maior desconto, link direto pra loja. A tese era "economizar agora".
- **ALK-58 · Detector de assinaturas** — Badge "Disponível no Game Pass / PS Plus" na página do jogo, atualizado por task semanal, **separado por país**.
- **ALK-59 · Avisos de grandes sales** — Banner no dashboard durante Steam Summer Sale, Black Friday, sale da PSN.
- **ALK-60 · Lista oficial de jogos de assinatura.**
- **ALK-62 · Consultor de compra** — "Comprar agora" (desconto >50% + menor preço histórico) vs "Esperar" (acima da média + lançamento recente). Explicitamente **não é LLM, é condicional** — o nome tinha "IA" só de marketing.
- **ALK-88 · Notificação de "deveria comprar agora".**
- **ALK-119 · IA de cupons e jogos usados** — Marcada como baixa prioridade.
- **ALK-121 · Calendário de sales futuras** — ML simples pra prever quando a Steam Summer Sale começa, pelo histórico. Auto-anotado como "low ROI, adiar".

### Backlog, shame & gestão de tempo

- **ALK-61 · Calculadora de Shame** — Valor total gasto vs horas jogadas, custo por hora. E a camada social: "seu custo/hora é R$5, a média dos seus amigos é R$3", "você gastou 30% mais que usuários com perfil parecido" (clustering por gêneros favoritos).
- **ALK-63 · Planejador de tempo** — "Tenho X horas por semana" → "você levará Y meses pra zerar o backlog", somando o HLTB main story da fila.
- **ALK-64 / ALK-65 · Modo Foco** *(duplicada no board)* — Escolher até 3 jogos prioritários e esconder o resto do backlog, com badge 🎯 nos escolhidos.
- **ALK-66 · Decida por Mim** — Roleta de jogo aleatório filtrada por tempo disponível ("tenho 2h hoje" → jogos com HLTB curto ou sessões curtas), gênero e plataforma. Com animação de caça-níquel.
- **ALK-144 · Time tracker manual** — Pra plataforma que não sincroniza sozinha.

### Página do jogo & metadados

- **ALK-73 · Hub do jogo completo** — Quantos têm, quantos zeraram, quais amigos e top users têm na biblioteca, edições disponíveis.
- **ALK-74 · HowLongToBeat completo** — Main/Extra/Completionist, cache de 30 dias, com fallback no `time_to_beat` do IGDB.
- **ALK-149 · HLTB** *(bilhete solto, mesma ideia)*
- **ALK-75 · Agregadores de nota** — Metacritic e OpenCritic, com badge "Universal Acclaim" acima de 90.
- **ALK-76 · Metadados estendidos** — Engine (Unity/Unreal), DLCs, demos/betas, dev e publisher.
- **ALK-77 · Datas de lançamento múltiplas** — Por região e plataforma.
- **ALK-78 · Prêmios & GOTY** — Badge dourado pra quem venceu, e badge/lista também pra quem só foi indicado.
- **ALK-79 · Origem RetroAchievements** — Mostrar o sistema original (NES/SNES/PS1) nos jogos retro.
- **ALK-80 · Troféus na página do jogo** — Quantos platinaram, raridade média, gráfico de distribuição bronze/prata/ouro/platina.
- **ALK-81 · Badge "Software"** — E esconder software do "Top Games".
- **ALK-86 · Merge de edições & filtro de colossos** — Unificar "The Witcher 3" e "The Witcher 3 GOTY" num só registro; e um toggle "ocultar jogos com mais de 100h".
- **ALK-87 · Upcoming games** — Jogos não lançados, botão de hype, notificação quando sai (e também pra quem tem na wishlist).
- **ALK-92 · Spoiler progressivo** — Esconder guias e troféus até o usuário marcar "estou jogando" ou "zerado", com toggle manual.
- **ALK-118 · Listas de exclusivos** — Filtro "apenas exclusivos PS5" / "apenas Nintendo", via campo de exclusividade derivado do IGDB.

### Descoberta & recomendação

- **ALK-82 · Motor de recomendação** — Collaborative filtering simples ("quem jogou X gostou de Y") com feedback do usuário.
- **ALK-83 · Busca avançada** — Por década, exclusividade, empresa, gênero, nota mínima.
- **ALK-84 · Listas dinâmicas** — "Coming Soon" (30 dias), "Sleeper Hits" (nota >8 com menos de 1000 reviews), "Mais Antecipados" (mais adicionados em wishlists), atualizadas diariamente.
- **ALK-85 · Estatísticas públicas** — Gêneros mais jogados, plataformas mais populares, jogos mais 100%-ados.

### Onboarding, UX, mobile & viral

- **ALK-34 · Onboarding em 3 passos** — (1) conectar conta via OAuth **ou** cadastro manual, com CSV depois; (2) escolher 3 jogos favoritos por busca no IGDB pra popular o Top 5; (3) opcional — primeira review **ou** ver recomendações, com "Pular por enquanto" bem visível. **Não forçar review.** Mais um passo pra escolher que tipo de coisa você curte.
- **ALK-39 · UI mais sóbria + design modular** — HTMX no lugar de AJAX manual, e uma ideia maior: **a interface se reorganiza segundo o tipo de jogador**. Cinco pilares — 🏆 Conquistas (*Hunter*), ✍️ Review (*Critic*), 📚 Coleção (*Collector*), 🤝 Social (*Socialite*), ⏳ Exploração (*Explorer*). O pilar no topo muda o que os cards destacam. Havia três variantes anotadas para o quinto pilar: **Tempo** (destaque gigante pro "Main Story: 15h" — recomendada por ser dado objetivo, diferente de nota que é subjetiva e conquista que é binária), **Backlog** (foco no que *será* jogado, pra quem usa tracker mais pra planejar compra que pra registrar passado) e **Discovery** (o feed vira vitrine de recomendação — "transforma o app de ferramenta passiva/Excel em ferramenta ativa/Netflix").
- **ALK-35 · Banner "What's New"** — Feature flags mostrando novidade ao logar, dismissível.
- **ALK-36 · Sidebar híbrida** — Colapsável no desktop, com estado persistido.
- **ALK-37 · Interface mobile app-like** — Bottom navigation bar (Home, Search, [ADD], Library, Profile) com botão central flutuante.
- **ALK-48 · Tela de configuração.**
- **ALK-49 · Menu do perfil** — Com a dúvida em aberto: estilo Facebook, Instagram, ou outro?
- **ALK-112 · Gerador de imagem social** — "Meu Ano em Games" pra Instagram/Twitter: favoritos, horas totais, conquista mais rara.
- **ALK-116 · PWA** — Manifest, service worker com cache offline da biblioteca e do perfil, push mobile.
- **ALK-145 · Botão de adicionar jogo direto ao lado da busca.**
- **ALK-150 · Testes de UI e A/B** — PostHog desde o dia zero, com flag pro novo onboarding. Objetivo declarado: medir conversão de OAuth vs e-mail.
- **ALK-151 · Wrapped compartilhável** — Imagem estática pra free, GIF/WebP animado pra Pro, com QR code ou link curto na imagem pra aquisição viral.
- **ALK-46 · App iOS** · **ALK-47 · App Android**

### Monetização — o tier Pro

- **ALK-109 · Tier "Alkahest Patron"** — R$9,90/mês ou R$99/ano. Sync mais frequente, capas animadas, badge Pro dourado, acesso antecipado a betas. Stripe ou Mercado Pago. E uma nota que quase ninguém lembra de escrever no roadmap: **se cobrar R$9,90 no Brasil, cedo ou tarde precisa emitir nota fiscal** (API do eNotas ou similar) — com a pergunta em aberto sobre o que muda nos EUA e na Europa.
- **ALK-125 · Sync de 1h** (free: 6h) · **ALK-126 · 6 slots de rival** (free: 3)
- **ALK-122 · Temas personalizados** — Talvez inspirados em jogos ou consoles.
- **ALK-130 · Capa e avatar animados** · **ALK-136 · Customização de pôsteres/capas** · **ALK-146 · Capas alternativas** *(essa marcada como grátis)*
- **ALK-132 · Fixar conquistas ou jogos no perfil** · **ALK-131 · Esconder jogos** *(com a ressalva: "se pá que é normal", ou seja, talvez devesse ser grátis)*
- **ALK-133 · Badge de apoiador** — Marcando se foi dos primeiros ou apoiador de determinado ano.
- **ALK-134 · Filtros avançados e listas inteligentes** — "RPGs dos anos 90 que eu ainda não joguei", "jogos no backlog com HLTB menor que 10h", "jogos que eu dei 5 estrelas mas não platinei".
- **ALK-135 · Histórico de atividades privado** · **ALK-124 · Export Excel avançado** com gráficos embutidos · **ALK-128 · Early access a features beta** · **ALK-127 · Cargo e canal no Discord**
- **ALK-138 · Badges por prêmios e colocações** — Importar as runs é grátis; as badges personalizadas por colocação seriam Pro.
- **ALK-113 · Mudança de username** — Uma por ano, guardando o histórico de nomes antigos pra evitar impersonation.
- **ALK-114 · Feature suggestion board.**

### Plataformas & migração

- **ALK-50 · Importação de CSV** — Backloggd, Steam (caso o OAuth falhasse) e PSNProfiles, com tela de "Review Import" mostrando conflitos e duplicatas antes de confirmar.
- **ALK-54 · Parar de hotlinkar capa do IGDB** — Baixar e guardar em object storage (S3, R2 ou Supabase), com o banco apontando pro bucket próprio.
- **ALK-68 · PSN** — Sem API pública confiável: import por CSV obrigatório mais scraping leve do PSNProfiles (1 request a cada 10s), com disclaimer de que é experimental.
- **ALK-110 · Xbox e Epic** — Xbox via OpenXBL (API paga), Epic via scraping ou API não oficial.
- **ALK-111 · Merge inteligente multi-plataforma** — Quem tem Hades na Steam e na PSN vê **uma** entrada com as duas tags, não duas.
- **ALK-137 · Speedrun.com.**

### Infra, escala, segurança & compliance

- **ALK-67 · Cache Redis** — Nas views pesadas (stats da home, página do jogo, top reviewers), com TTL de 15 min e invalidação por signal quando entra review nova.
- **ALK-70 · Celery Beat** — Sync de preços a cada 6h, disponibilidade em assinatura a cada 7 dias, limpeza de notificações antigas aos 30 dias.
- **ALK-93 · WebSockets** — django-channels no lugar do polling AJAX do feed.
- **ALK-94 · Infra de alta escala** — Nginx como load balancer, Daphne para WebSocket e Gunicorn para HTTP, Redis Cluster, read replicas no Postgres para rankings e stats.
- **ALK-91 · Moderação avançada** — Fila automatizada com ML simples pra spam/ofensivo, e moderação community-driven: quem tem Honra alta (ALK-100) pode revisar denúncias.
- **ALK-72 · SEO com Schema.org** — JSON-LD dos tipos `VideoGame` e `Review`. Anotado como "o único jeito de aparecer no Google com as estrelinhas — vital para aquisição orgânica".
- **ALK-71 · Roadmap público com votação** — Modelo `FeatureRequest` com upvotes, e uma task diária usando LLM pra ler sugestões novas e agrupar duplicatas automaticamente.
- **ALK-69 · Compliance CCPA (EUA)** — "Do Not Sell My Data" no rodapé, opt-out de analytics de terceiros.
- **ALK-90 · Privacidade como diferencial** — Página explicando propriedade dos dados: "não vendemos seus dados, usamos analytics self-hosted (PostHog) só pra melhorar o produto". A ideia era virar argumento de marketing contra Letterboxd e Backloggd, que usam trackers de terceiros.
- **ALK-152 · Footer & compliance** — Marcado como criticidade alta: sem cookie banner e "Do Not Sell", viola LGPD/CCPA.
- **ALK-154 · 2FA** — Com a auto-crítica junto: "games tracker não é banking, 2FA adiciona atrito" — adiar e tratar como feature de conta Pro.
- **ALK-153 · Beta fechado & hospedagem** — Railway com ambiente de staging, convites geridos por token no admin em vez de só e-mail, "pra gerar escassez e hype, estilo Bluesky/Clubhouse".
- **ALK-159 · Convites beta** — Códigos individualizados e links de uso único; e a mecânica viral: quem compartilha e traz 3 amigos pra waitlist ganha acesso liberado.
- **ALK-43 · Envio de e-mail via Celery** · **ALK-52 · Sistema de notificações por e-mail** (SendGrid/Mailgun, com opt-in/opt-out)
- **ALK-44 · E-mails de ciclo de vida** — Boas-vindas no primeiro login, e reengajamento com 1 semana, 1 mês, 3 e 6 meses sem logar.
- **ALK-156 · Sessão de refatoração** — Usando `vulture` e `coverage` pra achar código morto **cientificamente, em vez de "achar"**.

### Bugs abertos no dia em que parou

- **ALK-40 · Botão "Log Game" não funcionando**
- **ALK-41 · Busca de jogos não funcionando**
- **ALK-42 · Botão de trocar idioma quebrado**
- **ALK-157 · Plano de testes manuais** — Roteiro escrito à mão pra validar o merge tool do God Mode, o cookie banner com PostHog carregando só após consentimento, e um teste manual de IDOR tentando acessar `/god/merge/` como usuário comum.

### A aposta esquisita

- **ALK-117 · Oracle League (Fantasy Critic)** — Liga de fantasy game: usuários fazem draft dos jogos que acham que vão ganhar prêmios no próximo Game Awards. Acertar o GOTY vale 100 pontos, melhor jogo de ação vale 20, e por aí. Modelo `FantasyLeague` com temporada, participantes, picks e placar, calculado automaticamente quando as premiações saem.

  *De todas as 139, é a única que não é uma feature de tracker — é um produto separado. Provavelmente por isso é a de que eu mais gostava.*

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
