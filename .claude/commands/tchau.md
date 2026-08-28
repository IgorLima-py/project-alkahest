---
description: Encerra a sessão — escreve o handoff, commita e faz push
---

Vou parar por aqui e possivelmente continuar em **outra máquina, num chat novo que não terá
nada deste histórico**. Prepare a saída:

1. Leia o `CLAUDE.md` da raiz. Se ele tiver uma seção **`## Ao encerrar a sessão`**, execute
   os passos dela na ordem — é ali que mora o que é específico deste projeto.
2. Se não tiver essa seção, faça o mínimo:
   - escreva o handoff no documento de estado do projeto: o que foi feito e em quais arquivos,
     o que ficou pela metade e onde exatamente parou, **o que foi tentado e falhou e por quê**,
     o próximo passo concreto (específico o bastante para alguém sem contexto executar), e o
     que estiver preso a esta máquina ou a hardware;
   - registre decisões e medições onde o projeto as guarda;
   - confira `git status --porcelain` e **pare e me avise** se qualquer segredo aparecer;
   - `git add -A`, commit com mensagem descritiva (nunca "wip"), e `git push`.

Se eu escrevi alguma observação depois do comando, incorpore ao handoff: $ARGUMENTS

No fim, me responda em **no máximo 6 linhas**: o que foi commitado, o hash curto, e a primeira
frase que a próxima sessão vai ler como próximo passo. Se o push falhar, diga isso primeiro.
