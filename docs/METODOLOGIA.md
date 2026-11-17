# Metodologia, fontes e limitações

Versão das regras: `2026-11-16.1`. O escopo é deliberadamente amplo: híbridos
orgânico-inorgânicos de interesse semicondutor, incluindo perovskitas, derivados,
antiperovskitas e candidatos 0D–3D. Formação de fase e desempenho eletrônico não
são previstos pelo programa.

## Fontes implementadas

| Fonte | Uso e interface | Limitação material |
|---|---|---|
| [PubChem PUG REST](https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest) | Resolver nome→CID e obter propriedades/sinônimos | CID resolvido não valida a identidade da amostra. CIDs múltiplos ficam ambíguos. |
| [COD REST](https://wiki.crystallography.net/RESTful_API/) | `text` para nomes; `doi` para referências; JSON e CIF | Busca metadados, não enumera todas as moléculas por grafo. A API documentada não oferece offset; limite é aplicado localmente e declarado. |
| [HybriD³ / MatD³](https://hybrid3-database.readthedocs.io/en/latest/website.html) | Snapshot paginado de `/materials/datasets/`, sistemas, referências e propriedades aninhados | A API nem sempre inclui URL de arquivo CIF. Dados de cela sozinhos não são estrutura completa. Pode conter resultados calculados. |
| [Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | Títulos, resumos quando depositados, DOI, referências/links e contagens de citações | Busca por relevância, não Boolean exata; os totais brutos incluem resultados irrelevantes. Não fornece sistematicamente o texto completo. |
| [OpenAlex](https://help.openalex.org/api/searching/) | Busca lexical Boolean; título, resumo invertido, DOI, citações, OA e alerta de retratação | A busca pode encontrar o nome no texto integral, mas só fornecer metadados sem aquele trecho. Não se confirma uso nesse caso. |
| [Europe PMC](https://europepmc.org/RestfulWebService) | Busca Boolean, metadados core e XML aberto quando autorizado | Cobertura de ciência de materiais é incompleta. XML do corpo não assegura que a afirmação seja original dos autores. |
| [CSD Python API](https://downloads.ccdc.cam.ac.uk/documentation/API/descriptive_docs/text_numeric_searching.html) | Conector opcional `TextNumericSearch`, entrada/cristal e CIF | SDK, licença e dados locais são necessários. Não foi validado com licença nesta entrega. Busca nominal pode perder nomes abreviados e protonados. |
| Arquivos locais | CIF, TXT, PDF com texto, DOI e título informados pelo usuário | Proveniência e permissão de acesso são do usuário; extração de PDF pode alterar ordem de colunas e tabelas. |

Documentação de [autenticação OpenAlex](https://help.openalex.org/api/authentication/)
foi consultada durante o desenvolvimento: há acesso inicial sem chave, e paginação
por cursor exige chave. O programa não usa endpoints semânticos, embeddings,
classificadores remotos ou geração de texto.

## Estratégia de recuperação

Um nome por linha recebe ID SHA-256 do nome normalizado. Entradas repetidas por
capitalização são removidas; isômeros/nomes diferentes não são fundidos. A
normalização trata Unicode, espaços e variantes tipográficas de hífen/apóstrofo,
sem remover substituintes, posições ou sinais de carga.

Há um pequeno dicionário transparente para a lista de exemplo. Sinônimos e formas
de protonação são campos separados. Nenhuma busca presume que uma espécie
protonada seja idêntica à molécula neutra. `config.toml` permite expandir ambas as
listas após conferência. Os sinônimos genéricos do PubChem ficam disponíveis para
consulta, mas não são automaticamente aceitos.

Para OpenAlex e Europe PMC, cada alias é combinado por AND com um grupo OR de
`perovskite`, `antiperovskite`, `metal halide`, `organic-inorganic`, `semiconductor`
e `coordination polymer`. Termos extras são configuráveis. Não é preciso que um
artigo use “perovskite” para ser recuperado.

Crossref recebe três consultas por alias: perovskite; hybrid metal halide;
semiconductor coordination polymer. Não se presume que aspas tenham a mesma
semântica nas três fontes. A verificação literal posterior exige nome delimitado
por fronteiras de palavra e impede, por exemplo, tratar `dipyrido-phenazine` como
`phenazine`. Essa decisão aumenta precisão, mas perde nomes aglutinados/derivados
que talvez interessem: acrescente aliases explícitos.

Todas as páginas até o limite configurado são consultadas. A tabela `jobs` guarda
consulta, cursor, quantidade recebida, total bruto quando fornecido, estado,
tentativas, erro e data. Um total grande do Crossref não é uma frequência química.
O HybriD³ é percorrido como snapshot global, reutilizado para todos os compostos.
Páginas desse provedor são limitadas a 25 registros para evitar respostas muito
lentas de datasets espectrais. Na retomada de páginas maiores, o offset é
preservado matematicamente. Falha persistente não é ignorada.
Limites do snapshot e do número de aliases são declarados na cobertura.

Texto integral aberto é buscado para PMCIDs elegíveis, até `max_fulltexts` por
execução. O limite e a quantidade planejada constam do JSON. A seleção prioriza
candidatos/menções no escopo e congela os PMCIDs para a execução. O classificador usa
parágrafos do corpo XML; referências/back/agradecimentos são excluídos. Nos TXT/PDF,
o corte é uma heurística na primeira seção isolada References/Bibliography/
Referências: formatação incomum pode impedir o corte ou retirar texto posterior.

DOIs de candidatos estruturais são consultados novamente no COD, inclusive quando
nomes químicos não constam dos índices. Isso pode recuperar múltiplas amostras de
um mesmo artigo; **associação por DOI não prova que todas contenham o orgânico**.
Cada registro continua submetido às mesmas regras de correspondência.

## Critérios de evidência

Regras estão em `analysis.py` e versionadas. As classes são ordinais de triagem,
sem probabilidade estatística ou “confiança de 95%”.

- **Candidato estrutural:** nome no contexto de cátion/ligante orgânico, incorporação
  em rede ou descrição estrutural de híbrido, ou nome nos metadados químicos de um
  depósito com carbono e elemento metálico/metaloide selecionado.
- **Misto:** evidências estruturais e de aditivo/transporte coexistem no trabalho
  ou entre fontes. É preciso separar fases e funções.
- **Uso não estrutural provável:** contexto de passivação, aditivo, interface,
  dopagem ou transporte de cargas, sem indício estrutural nas regras.
- **Menção:** nome presente, mas contexto insuficiente. Uma frase negada ou
  hipotética não eleva a evidência estrutural.
- **Revisão, cálculo/preprint e alerta editorial:** classes próprias, sem promoção
  automática a confirmação experimental.
- **Confirmado:** exclusivamente decisão humana com revisor, nota e ID de fase.

Se fontes classificarem o mesmo DOI de formas diferentes, o relatório preserva os
trechos e sinaliza o conflito. Resumos diferentes não são concatenados como se
fossem texto contínuo de um único documento.

A confirmação requer julgamento cristalográfico. Nomes em CIF podem se referir a
solvatos, ligantes de complexos isolados, co-cristais ou fases secundárias; ter C e
metal não estabelece uma perovskita, nem condutividade. O programa não reconstrói
grafo molecular periódico, não verifica a topologia octaédrica e não executa DFT.

## Estruturas e propriedades

Gemmi analisa todos os blocos CIF, incluindo fórmula, moiedade, nome, DOI, grupo
espacial, cela/volume, coordenadas fracionárias, elementos, temperatura e R quando
informados. Exige cela cristalina e coordenadas numéricas para marcar estrutura
disponível. Ocupações parciais geram aviso. Um parser bem-sucedido não significa
que o refinamento ou a estrutura física estejam corretos.

Arquivos são preservados e identificados por SHA-256. Miniaturas projetam sítios
da unidade assimétrica (máximo 500) sem inventar ligações. Estruturas equivalentes
com serialização diferente têm hashes diferentes. Comparação por simetria,
polimorfismo e deduplicação estrutural ficam a cargo da revisão especializada.

HybriD³ pode fornecer dimensionalidade, valores/erros de propriedades, unidades,
condições de medida, método, síntese e marcação experimental/computacional. Esses
dados permanecem ligados ao dataset e ao seu DOI, em vez de serem atribuídos
genericamente ao orgânico. A seção expandida do relatório exibe os metadados.
No endpoint de datasets, a dimensionalidade aninhada usa códigos de opções do
servidor; o programa converte 3→2,5D e 4→3D, preservando o código original, conforme
o [mapeamento do MatD³](https://github.com/HybriD3-database/MatD3/blob/master/materials/serializers.py).

No texto, trechos sobre band gap, fotoluminescência, excítons, condutividade,
mobilidade, estabilidade etc. só são destacados se mencionam um alias na mesma
frase. Não há conversão automática de todos os números em propriedades da amostra:
um artigo pode conter controles, comparações e cálculos de várias fases.

RDKit é opcional: contagem de doadores/aceptores de ligação de hidrogênio, ligações
rotacionáveis, anéis aromáticos e TPSA a partir do SMILES resolvido. Esses
descritores ajudam a inspecionar o orgânico, mas não são modelos de cristalização,
protonação, encaixe na rede ou desempenho semicondutor. Não se aplica fator de
tolerância de Goldschmidt indistintamente a estruturas 0D/1D/2D.

## Contagem e priorização

DOIs são normalizados e unidos entre fontes. Cada fonte mantém seu próprio número
de citações, que nunca é somado. Registros sem DOI não são fundidos por título,
pois isso pode unir trabalhos diferentes; um hash de título é disponibilizado
como pista para curadoria. Preprint e artigo final com DOIs diferentes continuam
distintos. Suplementos indexados como `component` não entram isoladamente na
contagem de DOIs candidatos a publicações primárias.

As recomendações seguem regras simples, sem pontuação de “potencial científico”:
resolver identidade; revisar candidatos; verificar um conjunto de 1–3 publicações
estruturais revisadas; investigar diferenças de fase; ou ampliar cobertura.
O limiar de três trabalhos é organizacional e não uma propriedade científica.

Para medir uma **amostra específica**, o usuário atribui `sample_id`, distinguindo
composição, polimorfo e condições relevantes. Só a revisão pode afirmar que outro
artigo reproduziu a mesma fase: `replication_of` deve referenciar outro registro
confirmado do mesmo composto/fase. O programa rejeita ciclos e autorreferência.
A ferramenta não estabelece independência entre laboratórios, nem distingue
automaticamente nova síntese de nova medida na mesma amostra. Zero reproduções
revisadas significa ausência de revisão cadastrada, não irreprodutibilidade.

## Auditabilidade e recuperação

- `manifest.json`: entrada, aliases, configuração, versões, momento de criação e
  presença (não valor) das configurações de credenciais.
- `state.sqlite`: tabelas `jobs`, `http_cache`, `events`, `reviews`, `local_records`
  e `meta`. As respostas brutas ficam em `http_cache.body` com URL/parâmetros
  públicos, data e checksum. Nunca registre a chave em uma URL de configuração.
- `queries.csv`: consultas e limites; `results.json`: resultados com evidências;
  `summary.csv`: resumo; `report.html`: visualização local; `structures/`: CIF/SVG.
- Transações por página, WAL, sincronização completa, bloqueio de escritor,
  retries finitos, timeout, espaçamento por host e respeito a `Retry-After`.
  Esperas solicitadas superiores a 60 s tornam a tarefa pendente para retomada.
- SIGTERM/Ctrl+C geram relatório parcial. Após SIGKILL/queda de energia, tarefas
  em andamento retomam do cursor confirmado. Cache corrompido é rejeitado.
- O cache não expira dentro da execução: uma atualização é uma execução nova.
  Uma chave OpenAlex adicionada depois pode completar uma pendência de paginação.
- HTML escapa texto das fontes; CSV neutraliza fórmulas; nenhuma resposta de fonte
  é executada como código. Não há carregamento de scripts/CDNs no relatório.

O backup SQLite é consistente mesmo com WAL; copiar somente `state.sqlite` durante
uma busca não é o procedimento correto. Use `backup` ou copie a pasta após parar.
Backups locais não substituem uma cópia em outro dispositivo.

## Validação e limites conhecidos

Os testes offline cobrem duplicação de DOI, negacões/hipóteses, aliases ambíguos,
passivantes/derivados, CIFs sem coordenadas ou com vários blocos, XML sem referências,
paginação, falhas HTTP, segredos no cache, revisão transacional, contagem de
reprodução e recuperação após interrupção. Há testes de contratos com respostas
sintéticas; o comando `doctor --network` exercita os endpoints reais.

A execução de demonstração usa os seis compostos do usuário. Seus parâmetros e
limitações estão no [registro de validação](VALIDACAO.md). Os dados obtidos nela
não constituem uma lista já validada de moléculas novas.

Persistem falsos positivos e falsos negativos: aliases ausentes, abreviações,
traduções, sais/tautômeros, OCR, metadados incompletos, artigos fechados, estudos
indexados apenas em outras fontes, limites de consulta e relações semânticas
complexas. As regras predominam em inglês. Mesmo texto com nome e “organic cation”
pode citar trabalho prévio ou outro material na mesma frase. Não se declara
sensibilidade/especificidade sem um conjunto rotulado por especialistas.

Próximo passo científico recomendado: selecionar um conjunto de artigos positivos
e negativos, rotular composto/fase/função com dois revisores, medir precisão e
recall por fonte e regra, e só então calibrar aliases e prioridades. Isso é
diferente de simplesmente aumentar o número de resultados de uma busca.
