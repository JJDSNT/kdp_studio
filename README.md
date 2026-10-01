# README.md

# KDP Studio

Pipeline editorial multiagente baseado em LangGraph para acompanhar a produção de livros desde a pesquisa e a escrita até a criação da capa, editoração impressa, EPUB, tradução, publicação e divulgação.

## Estado do projeto

Projeto em fase de concepção. Este README descreve o escopo pretendido e a arquitetura proposta. As capacidades e integrações apresentadas ainda serão implementadas.

## Visão

Criar um ambiente de produção editorial em que agentes especializados cooperem sobre uma fonte comum de conteúdo, com acompanhamento humano, entregas verificáveis e histórico de decisões.

O autor poderá iniciar uma obra, importar um manuscrito existente ou executar apenas uma etapa, como revisão, tradução, produção de capa ou preparação de EPUB.

O Amazon Kindle Direct Publishing será o canal inicial de publicação, com possibilidade de incorporar outros canais posteriormente.

## Objetivos

- Organizar pesquisa, planejamento, escrita e revisão por obra e por capítulo.
- Produzir edições impressas e digitais a partir de uma versão editorial aprovada.
- Criar capas e uma identidade visual consistente para cada obra.
- Produzir e revisar traduções com glossários compartilhados.
- Preparar arquivos, metadados e materiais para publicação.
- Planejar campanhas e produzir materiais de marketing e divulgação.
- Permitir pausas, retomadas, correções e aprovação humana.
- Registrar fontes, versões e dependências entre entregas.

## Agentes

| Agente | Responsabilidades | Entregas principais |
|---|---|---|
| Coordenação editorial | Consolidar briefing, público, escopo, estrutura, cronograma e critérios de aprovação; distribuir tarefas e acompanhar pendências. | Plano editorial, tarefas e relatório de andamento. |
| Pesquisa | Localizar e avaliar fontes, organizar referências e verificar afirmações; sinalizar lacunas e divergências. | Dossiês, bibliografia e registros de verificação. |
| Escrita | Desenvolver sumário, capítulos, exemplos, exercícios e demais textos conforme o briefing e as fontes. | Estrutura da obra e manuscrito versionado. |
| Revisão | Avaliar linguagem, clareza, coerência, continuidade, terminologia e consistência factual. | Pareceres, propostas de alteração e texto revisado. |
| Tradução | Adaptar a obra aos idiomas de destino, preservando sentido, voz e terminologia. | Manuscritos traduzidos e glossários por idioma. |
| Capa e identidade visual | Propor conceitos, produzir ou selecionar arte, compor título e autoria e adaptar a identidade aos formatos e idiomas. | Capas digitais, frente, lombada, contracapa, arquivos editáveis e peças visuais. |
| Editoração impressa | Compor o miolo, definir tipografia, margens, imagens, sumário, cabeçalhos e paginação. | PDF de impressão, prova de leitura e relatório de validação. |
| Editoração EPUB | Estruturar conteúdo digital, navegação, estilos, imagens, metadados e acessibilidade. | EPUB, prévias e relatório de validação. |
| Publicação | Preparar o pacote por canal, conferir arquivos e metadados e executar integrações disponíveis após aprovação. | Pacote de publicação, registro de envio e acompanhamento do resultado. |
| Marketing e divulgação | Desenvolver posicionamento, descrições comerciais, calendário de lançamento e conteúdos para os canais escolhidos. | Plano de divulgação, textos, peças e relatórios de campanha. |

Um agente representa uma responsabilidade editorial e poderá executar várias tarefas ou utilizar ferramentas diferentes.

Conversão, composição e validação também poderão ser realizadas por ferramentas determinísticas, sem depender de geração por modelos.

## Fluxo editorial

1. O autor cria ou importa a obra e define o briefing.
2. A coordenação propõe o plano editorial e os critérios de qualidade.
3. Pesquisa, escrita e revisão trabalham em ciclos, por capítulo e pela obra completa.
4. O autor aprova uma versão editorial de referência.
5. As traduções são produzidas e revisadas a partir dessa versão.
6. A capa, o miolo impresso e o EPUB são preparados para cada edição e idioma.
7. Os arquivos passam por validação técnica e avaliação visual.
8. O autor aprova o pacote final de cada edição.
9. A publicação e a divulgação são executadas conforme os canais e as autorizações definidos.

A identidade visual e o planejamento de marketing poderão começar durante a escrita.

A capa impressa será finalizada após a definição da paginação, do papel e das especificações de impressão.

Reprovações deverão retornar à etapa responsável com observações objetivas. Alterações no manuscrito aprovado deverão identificar quais traduções, capas, arquivos e materiais promocionais precisam ser atualizados.

## Orquestração com LangGraph

A arquitetura proposta utiliza LangGraph para representar tarefas, dependências, ramificações, ciclos de revisão e pontos de intervenção humana.

O fluxo será organizado em subgrafos por responsabilidade editorial. O estado compartilhado registrará a obra, as tarefas e as referências aos artefatos. Arquivos extensos e imagens permanecerão no armazenamento do projeto.

### Capacidades pretendidas

- Execução de etapas independentes em paralelo quando as dependências permitirem.
- Persistência do estado e retomada de trabalhos interrompidos.
- Encaminhamento condicional após revisão ou validação.
- Aprovação humana de estrutura, manuscrito, tradução, capa e pacote final.
- Limites de tentativas, orçamento e duração para evitar ciclos indefinidos.
- Registro de erros e repetição controlada de tarefas.
- Prevenção de envios e publicações duplicados ao retomar uma execução.

## Fonte editorial comum

Cada obra terá um conjunto próprio de arquivos e registros:

- Briefing, público, objetivos e diretrizes de estilo.
- Sumário, manuscrito e versões aprovadas.
- Fontes, citações, bibliografia e verificações factuais.
- Glossário, nomes próprios e decisões de terminologia.
- Imagens, legendas, créditos e registros de origem e direitos de uso.
- Traduções e vínculo com a versão de origem.
- Identidade visual, capas e arquivos editáveis.
- Especificações de impressão, EPUB e canais de publicação.
- Pareceres, aprovações, pendências e histórico de alterações.
- Materiais de divulgação e registros de publicação.

As edições serão derivadas dessa fonte comum. Cada pacote final deverá indicar quais versões do manuscrito, da tradução e dos recursos foram utilizadas.

## Produção de capa

O agente de capa receberá título, autoria, sinopse, público, gênero e referências visuais.

Poderá propor alternativas para aprovação e utilizar ferramentas de geração de imagens, edição e composição gráfica.

A arte e a aplicação de texto serão etapas distintas, permitindo controle preciso de tipografia e legibilidade.

### Entregas previstas

- Conceitos visuais para avaliação do autor.
- Capa digital.
- Capa impressa com frente, lombada e contracapa.
- Adaptações para cada idioma e edição.
- Arquivos editáveis.
- Mockups e materiais promocionais.

### Validação

- Legibilidade do título e da autoria, inclusive em miniatura.
- Resolução e dimensões.
- Sangria e áreas seguras.
- Adequação da lombada à paginação e ao papel.
- Correspondência entre capa, idioma e edição.
- Conformidade com as especificações do canal escolhido.

## Tradução

Cada tradução partirá de uma versão editorial identificada e terá seu próprio ciclo de revisão.

O processo deverá preservar:

- Sentido e voz autoral.
- Terminologia técnica.
- Nomes próprios e referências.
- Estrutura de capítulos e exercícios.
- Relação entre texto, imagens e legendas.

Adaptações culturais e alterações de exemplos deverão ser registradas para avaliação editorial.

## Validação e controle humano

| Área | Verificações previstas |
|---|---|
| Conteúdo | Coerência, referências, afirmações sem suporte, consistência entre capítulos e atendimento ao briefing. |
| Tradução | Fidelidade de sentido, terminologia, fluência e adequação cultural. |
| Impressão | Dimensões, margens, sangria, fontes, imagens, paginação e inspeção visual do PDF. |
| EPUB | Estrutura, navegação, metadados, acessibilidade e visualização em leitores de teste. |
| Capa | Legibilidade, composição, medidas e correspondência com a edição. |
| Publicação | Correspondência entre arquivos, idioma, edição, autoria, descrição e canal de destino. |

O sistema apresentará arquivos e pareceres para avaliação do autor.

Publicações, envios e campanhas externas dependerão de autorização explícita, concedida por ação ou por um escopo previamente definido.

As aprovações permanecerão vinculadas à versão avaliada.

## Publicação

O agente de publicação deverá preparar um pacote específico para cada edição e canal.

### Conteúdo do pacote

- Arquivo do miolo ou EPUB.
- Capa correspondente.
- Título, subtítulo e autoria.
- Idioma e identificação da edição.
- Descrição comercial.
- Palavras-chave e categorias propostas.
- Informações editoriais aplicáveis.
- Relatórios de validação.
- Registro de aprovação.

As integrações serão implementadas conforme as interfaces disponíveis em cada plataforma.

Quando não houver uma integração adequada, o sistema entregará um pacote pronto para envio manual e registrará a pendência.

## Marketing e divulgação

O agente de marketing trabalhará com o briefing, o conteúdo aprovado e a identidade visual da obra.

### Entregas previstas

- Posicionamento e proposta de valor.
- Descrição comercial e textos de apresentação.
- Calendário de pré-lançamento, lançamento e continuidade.
- Posts, anúncios e roteiros promocionais.
- Mockups, banners e outras peças.
- Materiais adaptados aos idiomas da obra.
- Relatórios de resultados quando houver integração com os canais.

## Integrações previstas

A implementação permitirá adaptadores para:

- Modelos locais e serviços externos.
- Pesquisa e recuperação de fontes.
- Geração e edição de imagens.
- Composição e conversão de documentos.
- Produção e validação de EPUB.
- Composição e inspeção de PDFs.
- Armazenamento e versionamento.
- Publicação e divulgação.

A escolha de ferramentas, provedores e modelos será configurável por tarefa.

Credenciais permanecerão fora dos manuscritos e do repositório. As permissões de acesso serão atribuídas conforme a função de cada integração.

## Estrutura proposta do repositório

| Caminho | Conteúdo |
|---|---|
| `src/kdp_studio/agents/` | Agentes especializados. |
| `src/kdp_studio/graphs/` | Grafos e subgrafos do LangGraph. |
| `src/kdp_studio/state/` | Modelos de estado, tarefas e artefatos. |
| `src/kdp_studio/tools/` | Ferramentas editoriais e validadores. |
| `src/kdp_studio/adapters/` | Integrações com modelos, serviços e canais. |
| `prompts/` | Instruções versionadas dos agentes. |
| `templates/` | Modelos de briefing, estilo, capas e edições. |
| `examples/` | Obras demonstrativas e configurações de exemplo. |
| `docs/` | Arquitetura, operação e decisões de projeto. |
| `tests/` | Verificações dos fluxos e integrações. |

Os projetos editoriais do usuário terão armazenamento próprio, separado dos exemplos e do código da aplicação.

## Etapas de desenvolvimento

- [ ] Definir o modelo de obra, estado compartilhado e armazenamento de artefatos.
- [ ] Implementar coordenação, pesquisa, escrita e revisão.
- [ ] Implementar persistência, retomada e aprovações humanas.
- [ ] Implementar tradução e revisão por idioma.
- [ ] Implementar capa e identidade visual.
- [ ] Implementar editoração impressa e EPUB.
- [ ] Implementar validação técnica e visual.
- [ ] Implementar preparação dos pacotes de publicação.
- [ ] Implementar planejamento e produção de materiais de marketing.
- [ ] Adicionar integrações de publicação e divulgação.
- [ ] Validar o ciclo completo com uma obra piloto.

## Desenvolvimento

A implementação ainda não está disponível. Instruções de instalação e execução serão adicionadas quando houver uma versão utilizável.

Os arquivos Python deverão seguir a formatação e as verificações do flake8.

## Licença

A licença do código será definida antes da distribuição.

Manuscritos, traduções e recursos de cada obra terão seus próprios registros de autoria e condições de uso, separados da licença da aplicação.
