---
description: Retoma o trabalho — pull, lê o estado do projeto e diz onde paramos
---

Estamos abrindo uma sessão de trabalho. Faça isto **antes** de me responder qualquer coisa,
e sem me perguntar nada:

1. `git pull`. Se der conflito, ou se houver mudança local não commitada, **pare e me avise**
   antes de qualquer outra coisa.
2. Leia o `CLAUDE.md` da raiz do projeto. Se ele tiver uma seção **`## Ao abrir a sessão`**,
   execute os passos dela na ordem — é ali que mora o que é específico deste projeto.
3. Se o `CLAUDE.md` não tiver essa seção, faça o mínimo: leia o documento de estado que ele
   indicar (ou o `README.md`), e rode `git log --oneline -5` e `git status --short`.

Depois me responda em **no máximo 10 linhas**, nesta ordem:

- **Onde paramos**: a última coisa feita e em que ponto do projeto ela deixou as coisas.
- **Próximo passo concreto**: o que o documento de estado aponta como próximo.
- **Pendências**: coisa não commitada, teste falhando, medição faltando, prazo vencendo.
- **Atenção**: o que eu preciso plugar, instalar ou conferir **nesta máquina** antes de
  começar. Se algo estiver faltando, diga qual e onde está documentado.

Por fim, **proponha um nome para esta sessão** e tente renomeá-la. O nome sai do trabalho, não
do comando: curto, específico, no formato `<assunto> — <o que se quer fechar>`, como
`F2 — aceite na rua` ou `corredor não aparece`. Nunca "oi", nunca um número solto, nunca o nome
do projeto sozinho (a barra lateral já agrupa por projeto).

Se você não conseguir renomear a si mesmo, apenas mostre o nome sugerido em uma linha, para eu
colar clicando no título da sessão. Não insista nem tente contornar.

Termine perguntando o que vamos fazer hoje. **Não comece a trabalhar antes de eu responder.**
