# Sistema editorial agentivo — especificação para implementação

**Para:** o agente que vai construir este sistema.
**Objetivo:** produzir livros de não ficção em português brasileiro e inglês, do conceito ao pacote pronto para a Amazon KDP, com agentes especializados e portões de aprovação humana.
**Três modos de entrada:** livro do zero (§3.1), a partir de material já escrito (§3.2), ou só produção de um manuscrito pronto, sem mudar uma palavra (§3.3).
**Origem:** escrito a partir da produção real de *A Era dos Agentes* (Jaime Dias) — 142 páginas, PT-BR, PDF para impressão e EPUB. Os catálogos de falhas nas seções 9 e 10 são observações de campo, não hipóteses.

---

## 1. Decisão de framework

**Use LangGraph.** Não é uma preferência estética; decorre da forma do trabalho.

Produzir um livro é um **processo longo, retomável e cheio de portões**, não uma deliberação aberta entre especialistas. As características dominantes são:

- Dura semanas. Precisa sobreviver a queda de máquina, reinício e pausa de dias.
- Tem **aprovações humanas obrigatórias** no meio, que param tudo até alguém responder.
- Tem etapas **determinísticas** e caras de repetir: compilar LaTeX, validar EPUB, medir PDF.
- Tem laços de revisão (escrever → revisar → reescrever) com condição de saída.
- Tem paralelismo delimitado: revisar capítulos independentes, traduzir capítulos.

LangGraph entrega exatamente isso: grafo explícito, estado persistente com checkpoint, `interrupt` para intervenção humana, arestas condicionais e retomada a partir de qualquer ponto.

**Quando o ADK seria melhor:** se o produto fosse ideação aberta — várias vozes discutindo um problema sem sequência conhecida. Não é o caso. Se um dia quiser uma etapa assim (por exemplo, um conselho editorial debatendo a proposta de um livro novo), implemente **aquele nó** com um time ADK e o chame de dentro do grafo LangGraph. Não inverta: um pipeline de publicação dentro de um time de agentes vira algo que ninguém consegue auditar.

**Modelo:** o sistema deve ser agnóstico. Redação e revisão pedem o modelo mais capaz disponível; extração, validação e classificação rodam bem em modelos pequenos, inclusive locais. Não pendure o desenho num fornecedor.

---

## 2. O princípio que decide tudo

> **A intenção do autor é um artefato de primeira classe, versionado, e vence qualquer outro documento.**

Este sistema existe por causa de uma falha específica e cara: no projeto de origem, os documentos editoriais descreviam corretamente **o que cobrir** e não diziam **para que o livro serve**. O resultado foi tecnicamente fiel e editorialmente errado, e custou duas reescritas completas.

Consequências de implementação, obrigatórias:

1. Existe um arquivo `intentions.md` com a intenção do autor **nas palavras dele**, incluindo o que o livro **não** é.
2. Todo artefato produzido passa por um agente que o confronta com esse arquivo antes de seguir.
3. Quando um documento de apoio conflitar com a intenção, **a intenção ganha** e o documento é corrigido, não contornado.
4. Se o sistema não consegue derivar a intenção do que o autor escreveu, ele **pergunta** antes de escrever qualquer capítulo.

---

## 3. Arquitetura do grafo

### 3.1 Modo A — livro do zero

```
                    ┌─────────────────┐
                    │  ENTREVISTA     │  extrai a intenção do autor
                    └────────┬────────┘  e escreve intentions.md
                             ▼
                    ╔═════════════════╗
                    ║ PORTÃO HUMANO 1 ║  autor confirma a intenção
                    ╚════════┬════════╝
                             ▼
                    ┌─────────────────┐
                    │   ARQUITETO     │  partes, capítulos, progressão
                    └────────┬────────┘  de capacidade, casos condutores
                             ▼
                    ╔═════════════════╗
                    ║ PORTÃO HUMANO 2 ║  autor aprova a arquitetura
                    ╚════════┬════════╝
                             ▼
                    ┌─────────────────┐
                    │ CAPÍTULO-PILOTO │  um capítulo completo
                    └────────┬────────┘
                             ▼
                    ╔═════════════════╗
                    ║ PORTÃO HUMANO 3 ║  autor aprova VOZ e densidade
                    ╚════════┬════════╝  ← o portão mais importante
                             ▼
        ┌────────────────────┴────────────────────┐
        │        LAÇO POR CAPÍTULO (paralelo)     │
        │  PESQUISA → REDAÇÃO → REVISÕES → gate   │
        └────────────────────┬────────────────────┘
                             ▼
                    ┌─────────────────┐
                    │  CONTINUIDADE   │  o livro inteiro de uma vez
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │  VERIFICAÇÃO    │  fatos, fontes, alegações
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │  DIAGRAMAÇÃO    │  LaTeX + EPUB
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │ INSPEÇÃO VISUAL │  rasteriza e OLHA
                    └────────┬────────┘
                             ▼
                    ┌─────────────────┐
                    │  VALIDAÇÃO KDP  │  medidas, não opiniões
                    └────────┬────────┘
                             ▼
                    ╔═════════════════╗
                    ║ PORTÃO HUMANO 4 ║  congelamento do texto
                    ╚════════┬════════╝
                             ▼
              ┌──────────────┴──────────────┐
              ▼                             ▼
     ┌─────────────────┐          ┌─────────────────┐
     │   LOCALIZAÇÃO   │          │  EMPACOTAMENTO  │
     │   (EN, etc.)    │          │      KDP        │
     └────────┬────────┘          └────────┬────────┘
              └──────────────┬─────────────┘
                             ▼
                    ╔═════════════════╗
                    ║ PORTÃO HUMANO 5 ║  publicação
                    ╚═════════════════╝
```

### 3.2 Modo B — partindo de material já escrito

O grafo acima nasce do zero. Na prática, a entrada mais comum é outra: **o autor já tem material** — um manuscrito antigo, artigos soltos, anotações, um rascunho feito por outra ferramenta. O sistema precisa aceitar isso, e o ramo é diferente o bastante para merecer desenho próprio.

```
      ┌─────────────────┐        ┌─────────────────┐
      │  ENTREVISTA     │        │   INGESTÃO      │  normaliza tudo
      │  (acontece      │        │   (md, docx,    │  para Markdown e
      │   do mesmo      │        │    pdf, txt)    │  cataloga
      │   jeito)        │        └────────┬────────┘
      └────────┬────────┘                 │
               └────────────┬─────────────┘
                            ▼
                   ┌─────────────────┐
                   │  DIAGNÓSTICO    │  o material serve à intenção?
                   │   EDITORIAL     │  onde diverge, e a que custo?
                   └────────┬────────┘
                            ▼
                   ╔═════════════════╗
                   ║ PORTÃO HUMANO 1b║  autor decide o destino
                   ╚════════┬════════╝  do material existente
                            ▼
                   ┌─────────────────┐
                   │   MAPEADOR      │  cada trecho -> aproveitar,
                   └────────┬────────┘  revisar, reescrever, descartar
                            ▼
                     (segue no ARQUITETO, com o
                      material já classificado)
```

**A regra que não pode ser invertida:**

> A intenção é extraída **do autor**, nunca inferida do material existente.

O material que ele traz pode já ter se afastado da intenção — foi exatamente o que aconteceu no projeto de origem, onde um rascunho tecnicamente correto servia a um livro diferente do que o autor queria. Se o sistema ler o rascunho e deduzir dali a intenção, ele **canoniza o erro** e nunca mais sai dele.

Por isso a entrevista acontece igual, antes ou em paralelo, e o material é julgado contra a intenção — não o contrário.

### 3.3 Modo C — só produção

O autor entrega um manuscrito **pronto** e quer apenas a produção: diagramação, validação e pacote KDP. **Nenhuma palavra muda.**

O grafo é o Modo B com o Mapeador marcando tudo como `INTOCÁVEL`, e com o auditor de fidelidade (§5.19) em 100%. Os agentes de redação e revisão ficam desligados; os de verificação de fatos podem ficar ligados, mas só **relatam** — nunca corrigem.

É o modo certo para quem já escreveu o livro e só quer publicá-lo bem.

**Regra dura:** nenhuma aresta contorna um portão humano. Se um portão não responde, o grafo fica parado — não decide sozinho, não segue com um valor padrão, não expira.

---

## 4. Estado compartilhado

Persistente em checkpoint. O que o grafo carrega entre nós:

```python
class EstadoLivro(TypedDict):
    # imutável depois do portão 1
    intencao: str                 # conteúdo de intentions.md
    idioma_fonte: str             # "pt-BR"
    idiomas_alvo: list[str]       # ["en"]

    # arquitetura
    arquitetura: dict             # partes, capítulos, progressão
    casos_condutores: dict        # parte -> caso que a atravessa
    guia_de_voz: str              # aprovado no portão 3

    # produção
    capitulos: dict[str, Capitulo]   # id -> texto, estado, histórico
    fontes: list[Fonte]              # url, claim, verificada_em, status
    pendencias: list[Pendencia]      # o que falta verificar na prática

    # produção gráfica
    metricas_build: dict          # overfull, underfull, páginas, brancas
    validacao_kdp: dict           # cada item medido, não estimado

    # governança
    aprovacoes: dict[str, Aprovacao]   # portão -> quem, quando, o quê
    trilha: list[Evento]               # quem fez o quê, com que base
```

**Exigências:**

- Cada capítulo guarda **histórico de versões com o motivo da mudança**. "Reescrito" não basta; "reescrito porque a voz destoava do guia, ver portão 3" basta.
- Toda fonte guarda **data de verificação e resultado**. Fonte não aberta é fonte inexistente.
- A trilha registra **com base em qual informação** cada decisão automática foi tomada. Sem isso não há como explicar o livro depois.

---

## 5. Os agentes

Para cada um: responsabilidade, critério de aceite, e o antipadrão que ele existe para evitar.

### 5.1 Entrevistador
Conversa com o autor e produz `intentions.md`. Pergunta explicitamente: para quem é, de onde o leitor sai e aonde chega, o que o livro **não** é, e o que o leitor leva embora.
**Aceite:** o autor lê e reconhece as próprias intenções no texto.
**Antipadrão:** deduzir a intenção a partir do tema. Tema não é intenção.

### 5.2 Arquiteto
Desenha partes e capítulos como **progressão de capacidade**, não como cobertura de assuntos. Define um caso condutor por parte.
**Aceite:** para cada capítulo existe uma frase dizendo o que o leitor passa a conseguir fazer.
**Antipadrão:** sumário que é lista de tópicos da área.

### 5.3 Pesquisador
Busca fontes, sempre abrindo o que cita.
**Aceite:** toda fonte com URL acessada e data registrada. **"Não encontrei" é resposta válida e deve ser possível de emitir.**
**Antipadrão:** URL com forma plausível nunca aberta. Este erro aconteceu no projeto de origem e só foi pego por inspeção de padrão de slug.

### 5.4 Verificador de fatos
**Agente separado do pesquisador, de propósito.** Reabre cada fonte e confere se ela sustenta a afirmação que o texto faz.
**Aceite:** relatório por afirmação — sustentada, parcialmente sustentada, não sustentada, fonte inacessível.
**Antipadrão:** confiar na síntese de quem pesquisou. Quem pesquisa tem viés de confirmação do próprio achado.

### 5.5 Redator
Escreve capítulos seguindo o guia de voz aprovado.
**Aceite:** o capítulo entrega a capacidade prometida pelo arquiteto.
**Antipadrões:** repetir a tese do livro em vez de demonstrá-la em situação nova; encolher o capítulo achando que isso o torna narrativo; deixar o exemplo de uma parte vazar para outra.

### 5.6 Revisor de voz
Compara o texto com o guia de voz e com o catálogo de vícios (seção 9).
**Aceite:** varredura automática limpa nos padrões catalogados **mais** parecer humano de leitura.
**Antipadrão:** aprovar por gramática. Tudo pode estar gramaticalmente correto e soar de outro país.

### 5.7 Revisor de continuidade
Lê o livro **inteiro de uma vez**, não capítulo a capítulo.
**Aceite:** mapa de repetições entre capítulos distantes; confirmação de que cada caso condutor atravessa sua parte; remissões cruzadas coerentes.
**Antipadrão:** revisar em janelas. Repetição entre o capítulo 4 e o 17 só aparece para quem leu os dois.

### 5.8 Revisor técnico
Confere correção no domínio do livro e distingue capacidade verificada de promessa de fornecedor.
**Aceite:** nenhuma afirmação técnica sem base; incertezas declaradas como incertezas.

### 5.9 Experimentador
Se o livro manda o leitor fazer algo, **este agente faz** e relata o que aconteceu de verdade: quantas tentativas, o que quebrou, quanto demorou, em que máquina.
**Aceite:** nenhum exercício publicado sem execução registrada.
**Antipadrão:** publicar instruções não testadas. É simultaneamente problema de qualidade e de responsabilidade quando o livro manda instalar software.

### 5.10 Diagramador
Gera LaTeX (impresso) e EPUB (digital) a partir da mesma fonte Markdown, compila e lê os logs.
**Aceite:** zero *overfull* e zero *underfull*; nenhum erro de compilação.
**Antipadrão:** tratar os dois formatos como o mesmo objeto. Ver seção 10.

### 5.11 Inspetor visual
**Rasteriza páginas e olha.** Abertura de parte, abertura de capítulo, sumário, cada tipo de box, primeira e última página de cada parte.
**Aceite:** confirmação visual por tipo de página, não por ausência de erro no log.
**Antipadrão:** confiar no log. No projeto de origem, um rótulo de capítulo **sumiu da página sem gerar erro nenhum**, por interação entre duas opções da classe. Só inspeção visual pega isso.

### 5.12 Validador KDP
Mede o artefato, não estima. Cada item da seção 11.
**Aceite:** relatório com valor medido, limite exigido e veredito por item.
**Antipadrão:** aceitar "deve estar certo".

### 5.13 Localizador
Adapta editorialmente para o idioma alvo. Não traduz literalmente exemplos, trocadilhos, referências culturais nem instruções que dependam de teclado, sistema ou disponibilidade regional.
**Aceite:** identificadores de exercício estáveis entre idiomas; glossário bilíngue consistente; o texto passa pelo revisor de voz **daquele** idioma.
**Antipadrão:** traduzir e mandar. Um livro traduzido literalmente lê como livro traduzido literalmente.

### 5.14 Empacotador KDP
Monta o pacote: miolo com e sem sangria, capa envolvente calculada a partir do número final de páginas, metadados, categorias, palavras-chave, descrição.
**Aceite:** todos os arquivos passam pelo validador; capa gerada **depois** do congelamento.
**Antipadrão:** montar a capa antes do texto congelar. Cada página muda a lombada.

### 5.16 Ingestor
Aceita o que o autor tiver: Markdown, Word, PDF, texto solto, arquivos espalhados, repositório. Normaliza para Markdown, preserva o original intacto e cataloga o que existe — quantos textos, que tamanho, que assunto, que estado.
**Aceite:** inventário completo, com o original preservado e rastreável até a fonte.
**Antipadrão:** começar a editar durante a ingestão. Ingestão não opina.

### 5.17 Diagnosticador editorial
Lê o material inteiro e o confronta com a intenção. Produz **parecer, não reescrita**: o que o material realmente é, onde serve à intenção, onde diverge, o que custa manter e o que custa jogar fora.
**Aceite:** o autor lê o parecer e reconhece problemas que ele sentia mas não sabia nomear.
**Antipadrões:** começar a corrigir antes de diagnosticar; suavizar o diagnóstico. Se o material não serve, a frase útil é "não serve, e eis por quê" — dita cedo, custa uma conversa; dita tarde, custa o livro.

### 5.18 Mapeador
Classifica cada trecho do material existente contra a arquitetura aprovada, com um destino explícito e justificado:

| Destino | Quando |
| --- | --- |
| **Aproveitar** | serve à intenção e está na voz certa |
| **Revisar** | conteúdo bom, forma fora do guia |
| **Reescrever** | o assunto fica, o texto não |
| **Mover** | está certo, mas em outra parte do livro |
| **Descartar** | não serve à intenção, por mais bem escrito que esteja |
| **Preservar** | **bom demais para arriscar numa reescrita** |

A última coluna existe por uma razão concreta: no projeto de origem, um quadro conceitual que era a espinha do livro foi apagado numa reescrita porque **nenhum documento registrava que ele importava**. Toda reescrita precisa carregar uma lista de "o que preservar", aprovada pelo autor.

**Aceite:** todo trecho tem destino e motivo; a lista de preservação está aprovada.
**Antipadrão:** reescrever tudo por precaução. Descarta material bom e desperdiça o trabalho que o autor já fez.

### 5.19 Auditor de fidelidade
Garante que o texto de saída corresponde ao de entrada onde isso foi combinado, e que toda diferença fora disso é **declarada, atribuída e justificada**.

É um agente determinístico: compara hashes e diferenças, não julga qualidade. Um LLM não é confiável para responder "mudou alguma coisa?" — essa pergunta é de máquina.

**O que ele verifica**

1. **Passagem intacta.** Todo bloco marcado `INTOCÁVEL` sai do manuscrito com hash idêntico ao da ingestão. Qualquer divergência **para o grafo**.
2. **Diferença atribuída.** Todo bloco alterado tem diferença registrada, com o agente que alterou, o motivo e a versão da instrução sob a qual agiu. Alteração sem autor identificado é violação.
3. **Deriva silenciosa.** Depois que qualquer agente toca num capítulo, a diferença é comparada com **o escopo declarado da tarefa dele**. O revisor de voz foi chamado para corrigir registro: se ele também trocou um número, um nome ou uma data, isso é violação, mesmo que a troca esteja certa.
4. **Literais congelados.** Certos trechos nunca são editáveis, em nenhum modo: citações diretas, títulos de fontes, URLs, código, pedidos a agentes, nomes próprios, números e datas. São marcados na ingestão e conferidos na saída.
5. **Inventário de fatos.** Extrai de entrada e saída todos os números, datas, nomes próprios e URLs. Qualquer item que apareça, suma ou mude sem motivo registrado é sinalizado. **É a verificação que mais pega deriva de LLM na prática** — o modelo "conserta" uma data e ninguém percebe.

**Aceite:** relatório de fidelidade emitido antes do portão de congelamento, com contagem por categoria e zero violações não justificadas.
**Antipadrões:** pedir a um modelo que confirme a fidelidade; aceitar "melhorei de passagem" como justificativa; permitir que um agente altere fora do próprio escopo por achar que está ajudando.

### 5.15 Guardião da intenção
Atravessa o grafo inteiro. Em cada portão automático, confronta o artefato com `intentions.md`.
**Aceite:** parecer explícito — "compatível" ou "diverge em X".
**Antipadrão:** ser um nó só no começo. A intenção se perde no meio, não no início.

---

## 6. Portões humanos

| # | Momento | O que o autor decide |
| --- | --- | --- |
| 1 | Após a entrevista | A intenção está correta? |
| 1b | Após o diagnóstico | Qual o destino do material existente? (só no Modo B) |
| 2 | Após a arquitetura | A estrutura serve à intenção? |
| 3 | Após o capítulo-piloto | **A voz está certa?** |
| 4 | Após a validação | Congelar o texto |
| 5 | Antes do envio | Publicar |

**O portão 3 é o mais caro de errar.** Aprovar voz errada custa o livro inteiro reescrito. Ele deve mostrar ao autor um capítulo **completo e diagramado**, não uma amostra de parágrafos — voz se julga em extensão e com a página montada.

Cada portão registra quem aprovou, quando e sobre qual versão. Aprovação não é herdada por versões posteriores.

---

## 7. Portões automáticos

Bloqueiam o avanço. Nenhum é opinião.

| Portão | Critério |
| --- | --- |
| Fontes | 100% das URLs abertas e datadas; zero afirmações sem base |
| Exercícios | 100% executados com relato registrado |
| Voz | varredura de vícios limpa |
| Continuidade | nenhuma repetição não intencional; casos condutores íntegros |
| Composição | zero *overfull*, zero *underfull* |
| Páginas em branco | todas em verso, com motivo estrutural, **nenhuma com fólio** |
| Estrutura | aberturas de parte em recto; sequência de capítulos sem furo |
| KDP | todos os itens da seção 11 aprovados |
| EPUB | XML válido; sumário navegável **e** visível; NCX presente |
| Fidelidade | 100% dos blocos `INTOCÁVEL` com hash idêntico; zero alterações sem autor e motivo; zero deriva de número, data, nome ou URL |

### 7.1 Em que camada "ipsis litteris" se verifica

Isto precisa ficar explícito, porque a exigência é razoável em uma camada e impossível em outra.

| Camada | O que dá para garantir |
| --- | --- |
| **Manuscrito (Markdown)** | **Igualdade exata de bytes.** É aqui que a fidelidade se verifica e se exige. |
| **PDF e EPUB** | **Equivalência textual após normalização**, não igualdade de bytes. |

A composição tipográfica **necessariamente** transforma o texto: aspas retas viram aspas curvas, hífens viram travessões, ligaduras se formam, a hifenização parte palavras no fim da linha. Um PDF cujo texto extraído fosse byte a byte igual ao Markdown seria um PDF mal composto.

Então o auditor trabalha assim:
- No manuscrito, compara **hash exato**.
- No PDF e no EPUB, extrai o texto, aplica uma normalização **declarada e versionada** (desfaz hifenização de fim de linha, converte aspas e travessões de volta, colapsa espaço) e compara o resultado.

A lista de normalizações é um artefato do sistema, não uma decisão de ocasião. Se ela precisar crescer para um livro passar, isso é sinal de problema — e o portão deve exigir aprovação para cada normalização nova.

---

## 8. Ferramentas que o sistema precisa

- **Sistema de arquivos e execução** — compilar, medir, inspecionar.
- **Busca web com leitura real de página** — não só o snippet.
- **LuaLaTeX + memoir + microtype + fontes de livro** — a composição profissional depende disso.
- **Rasterizador de PDF** (Ghostscript) — para inspeção visual e medição de bounding box.
- **Leitura de imagem pelo modelo** — o inspetor visual precisa ver de verdade.
- **Validador de EPUB** — XML e estrutura.
- **Geração de QR code** — para exercícios que vivem num repositório.
- **Git** — histórico de versões dos capítulos.

Os geradores do projeto de origem (`scripts/gerar_tex.py`, `scripts/gerar_epub.py`, `producao/estilo.tex`) servem de ponto de partida e já contêm as correções das armadilhas da seção 10.

---

## 9. Catálogo de vícios de escrita

Cada um foi observado no projeto de origem. A varredura deve ser automática onde couber.

**De conteúdo**
- Cobrir definições no lugar de formar competência: o leitor sai sabendo nomear o que continua sem saber usar.
- Repetir a tese do livro como refrão em vez de demonstrá-la em situação nova.
- Encolher um capítulo em vez de reescrevê-lo: remove o conteúdo e deixa as transições.
- Deixar o exemplo de uma parte vazar para outra, achatando o conceito da parte anterior.
- Tratar o leitor como aprendiz do ofício quando ele deveria ser observador do trabalho.

**De origem mista** (aparecem ao juntar material de fontes diferentes)
- **Costura visível:** partes reescritas convivendo com partes antigas, com voz, densidade e recursos gráficos diferentes. No projeto de origem o livro trocava de registro no meio — metade com boxes e subtítulos, metade em prosa corrida. O leitor sente, mesmo sem saber nomear.
- **Regime gráfico inconsistente:** um trecho usa boxes, outro não.
- **Exemplo órfão:** um caso condutor citado numa parte que foi descartada.
- **Remissão quebrada:** referência a capítulo que mudou de lugar ou deixou de existir.

**De forma**
- Par antitético no fim de todo parágrafo. Boa frase isolada; trinta seguidas viram maneirismo.
- Abrir parágrafos com "Imagine…" / "Pense em…".
- Trocar de pessoa no meio: chamar o leitor de "o leitor" num texto que o trata por "você".
- Hedge dentro do exercício: "se você tiver acesso", "quando disponível". Verificar antes e escrever com firmeza; pendência vai em comentário editorial.
- Conduzir história por sucessão de marcos datados, cada um com sua moral.

**De registro — português brasileiro**
Todas as formas abaixo são gramaticalmente corretas. A régua não é a gramática; é se um brasileiro escreveria aquilo.

| Evitar | Usar |
| --- | --- |
| ênclise (`vê-lo`, `fazê-las`, `escrevendo-o`) | reescrever com objeto explícito |
| `encheu-se`, `seguiram-se`, `escolhe-se` | próclise (`se encheu`) ou sujeito explícito |
| `lhe` / `lhes` como objeto | `para ele`, `dele`, ou reescrever |
| `se` impessoal (`o que se faz`, `para se saber`) | `o que fazer`, `para descobrir` |
| `convém` | `vale` |
| `afortunado`, `outrora`, `cumpre`, `porquanto` | vocabulário corrente |
| `havia feito` em excesso | `tinha feito` |

**De fonte**
- URL com forma plausível nunca aberta.
- Domínio não oficial atribuído ao fabricante.
- Página citada que não sustenta a afirmação feita.

---

## 10. Armadilhas de produção gráfica

Observadas e resolvidas. Quem implementar vai reencontrá-las.

### LaTeX / memoir
- **`\setsecnumdepth{part}` faz o rótulo do capítulo sumir da página sem erro**, porque o memoir passa a tratar o capítulo como não numerado e nem chama o comando que imprime o rótulo. Imprimir por contador próprio dentro de `\printchaptertitle`.
- **O sumário e a apresentação usam a mesma máquina de abertura de capítulo** e consomem o contador, deslocando a numeração inteira. Precisam de exceção explícita.
- **Monoespaçada justificada abre buracos** — sem hifenização, a justificação só tem espaços para esticar. Bandeira à direita, sempre.
- **Caixas com fundo precisam poder quebrar entre páginas**, senão estouram o quadro. Mas o painel de QR deve ficar **inteiro**: QR partido não funciona.
- **Chapado de borda a borda exige sangria**: página = aparo + 0,125″ no topo, no pé e no corte externo, **nada na lombada**.
- **Entreletra por espaços não funciona** em compositor que colapsa espaço em branco. Usar recurso real de *character spacing*.

### EPUB
- **Nunca forçar cor de fundo no `body`.** Quebra o modo escuro e desenha um retângulo dentro da página do leitor.
- **Nenhuma distinção pode depender só de cor.** Filete lateral e etiqueta têm de sobreviver ao leitor descartar o fundo.
- **Chapado escuro não serve em tinta eletrônica**: refresh lento, e muitos leitores ignoram `background-color`, o que deixa texto claro invisível. Fazer a hierarquia com espaço, entreletra e fio.
- **`nav.xhtml` fora da leitura linear não produz sumário visível.** Colocar na spine **e** gerar `toc.ncx` para leitores antigos.
- **Markdown junta linhas seguidas num parágrafo só**, então o rótulo de um box gruda no corpo. Pré-processar antes de renderizar.
- **Regra de `p` vence herança de `text-align` do bloco pai** — rótulo centrado sai à esquerda. Declarar explicitamente.
- **Título e subtítulo no mesmo `dc:title`** trunca feio no cabeçalho do leitor. Campos separados com `title-type`.

### Princípio geral
**Os dois formatos não precisam ser idênticos; precisam ser igualmente bons no meio em que vivem.** Copiar a decisão do impresso para o digital produziu, neste projeto, exatamente os piores defeitos.

---

## 11. Especificações KDP a validar

Medidas verificadas no projeto de origem, 6 × 9 pol, miolo P&B.

| Item | Critério |
| --- | --- |
| Aparo | tamanho padrão KDP (6 × 9 é um deles) |
| Páginas | 24 a 828 (P&B). **100+ para haver texto na lombada** |
| Medianiz | 0,375″ até 150 pág; 0,5″ de 151 a 300; 0,625″ de 301 a 500 |
| Margens externas | 0,25″ mínimo |
| Sangria | só se houver conteúdo na borda: página = 6,125 × 9,25″ |
| Fontes | todas embutidas, como subconjunto |
| Transparência | evitar; achatar |
| Lombada | páginas × 0,0025″ (creme) ou × 0,002252″ (branco) |
| Capa impressa | sangria + contracapa + lombada + capa + sangria, **300 dpi** |
| Capa Kindle | 1600 × 2560 px recomendado |
| Miolo de impressão | **sem a capa embutida** |

**Ordem obrigatória:** congelar texto → contar páginas → calcular lombada → gerar capa. Nunca o inverso.

---

## 12. Implementação por fases

1. **Esqueleto do grafo** com os cinco portões humanos e o estado persistente. Sem agentes ainda — nós que só registram. Prove que para, retoma e audita.
2. **Diagramação e validação.** Markdown de brinquedo → PDF e EPUB → validador KDP. É a parte determinística e a que dá confiança no resto.
3. **Inspetor visual.** Rasterizar e olhar. Sem isso o item 2 mente.
4. **Ingestão, diagnóstico e mapeamento** (Modo B), se houver material existente. Vale implementar cedo: é o que permite testar o resto com texto de verdade em vez de texto de brinquedo.
5. **Redação e revisões**, com o catálogo de vícios como verificação automática.
6. **Pesquisa e verificação de fatos**, com o verificador separado do pesquisador.
7. **Experimentador**, se o livro tiver exercícios.
8. **Localização.**
9. **Empacotamento KDP.**

Não inverta 2 e 4. Escrever um livro inteiro antes de saber se ele compila e valida é como este projeto começou, e custou caro.

---

## 13. Critérios de aceite do sistema

O sistema está pronto quando:

- Produz um livro curto do zero, passando por todos os portões, e **para** de verdade em cada um.
- **Aceita um material já escrito**, diagnostica o que ele é, propõe destino trecho a trecho e não descarta nada sem o autor aprovar.
- **Diverge do material existente quando a intenção manda**, em vez de canonizar o que já estava lá.
- Sobrevive a ser interrompido no meio e retomado no dia seguinte, sem perder estado.
- Recusa avançar com uma fonte não verificada, e diz qual.
- Detecta, por conta própria, pelo menos um vício da seção 9 num texto plantado.
- **Detecta uma alteração plantada num bloco marcado `INTOCÁVEL` e para o grafo.**
- **Detecta uma data trocada silenciosamente por um agente de revisão**, mesmo que a data nova esteja correta.
- Roda o Modo C de ponta a ponta com **zero divergência** no manuscrito.
- Emite relatório de validação KDP com valor medido por item.
- Produz a edição em inglês sem que os exercícios mudem de identificador.
- Consegue **explicar** qualquer decisão automática: com base em quê, em que momento, sob qual versão da intenção.

O último é o mais importante. Um sistema editorial que não consegue se explicar produz livros que ninguém consegue defender.
