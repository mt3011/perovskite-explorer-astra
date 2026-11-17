# Registro de validação

Validação realizada em Linux, Python 3.12.14. Nenhum resultado abaixo constitui
confirmação de novidade ou recomendação experimental validada.

## Procedimento

- Instalação em ambiente Python isolado.
- Testes offline de classificação, persistência, fontes e revisão.
- Execução real da lista de seis compostos em `examples/organicos.txt`.
- Inspeção do HTML e verificação dos arquivos de saída.
- Teste de backup/restauração e retomada.

## Verificações concluídas

- **48 testes offline aprovados**, cobrindo qualidade das regras, DOI, fontes,
  arquivos estruturais, revisão e persistência. Inclui interrupção controlada e
  encerramento forçado real de subprocesso durante uma transação não confirmada.
- `ruff check src tests`: aprovado.
- Geração de wheel e distribuição fonte: aprovada.
- HTML exercitado com Chromium/Playwright em 1440×1000 e 390×844: filtro por
  composto funcional, seis seções presentes, sem erros JavaScript ou transbordo
  horizontal da página (tabelas têm rolagem própria).
- Guia PDF de duas páginas: texto extraído e conferido.
- Testes de backup/restauração, exclusão mútua e importação idempotente.
- `doctor --network`: PubChem, COD, Crossref, OpenAlex e Europe PMC responderam
  com o contrato esperado. HybriD³ respondeu inicialmente e depois apresentou
  timeouts; foi possível avançar retomando páginas menores.

Comando do piloto (limites intencionais):

```bash
perovskite-explorer run examples/organicos.txt --out runs/example-live --max-results 30 --page-size 50 --max-fulltexts 15
```

Cambridge não foi ativado, por ausência de SDK/licença. Não há chave OpenAlex
configurada: buscas limitadas à primeira página podem ser truncadas. O piloto
não é uma revisão exaustiva da literatura.

## Resultado operacional do piloto

Foram concluídas 220 de 221 tarefas registradas, com **47 CIFs baixados** e 15
textos integrais abertos. Houve 88 consultas truncadas pelos limites intencionais.
O snapshot HybriD³ preservou **425 de 2.298 datasets** informados pelo serviço,
com próximo cursor na página 18 de tamanho 25, onde ocorreu novo timeout. O
relatório registra essa lacuna em todos os compostos.

| Entrada | DOIs candidatos estruturais* | CIFs distintos recuperados** |
|---|---:|---:|
| 4-Aminophenyl sulfone | 0 | 0 |
| Phenazine | 6 | 9 |
| Niacinamide | 5 | 7 |
| Theobromine | 3 | 14 |
| 3-Aminobenzoic acid | 7 | 10 |
| Nicotinic acid | 10 | 7 |

\* Regras amplas de híbridos/coordenação; incluem possíveis falsos positivos e
materiais sem semicondutividade demonstrada. **Não** são uma lista de perovskitas
confirmadas. Nenhuma confirmação/reprodução humana foi cadastrada no piloto.

\** Arquivos vinculados a registros com o nome/variante; podem representar
complexos, outras fases e estudos fora do interesse final. Não equivalem ao
número de amostras semicondutoras. Um DOI pode conter vários depósitos.

A identidade da primeira entrada ficou ambígua; as outras cinco tiveram resposta
única no PubChem, ainda marcada como não revisada. O piloto foi iniciado durante
o desenvolvimento: preserva as consultas originais (incluindo uma repetição de
capitalização em Phenazine) e a seleção inicial dos 15 PMCIDs. Novas execuções
eliminam essa repetição e priorizam os textos por indícios/menções no escopo.

Para continuar o piloto, se a pasta de resultados estiver disponível:

```bash
perovskite-explorer resume runs/example-live --timeout 90
```

Para pesquisa aprofundada, comece outra execução com limites maiores e aliases
conferidos, configure a chave OpenAlex e acrescente o CSD quando licenciado. Os
resultados completos do piloto ficam na pasta de execução local e no pacote de
entrega, não no Git: respostas brutas, textos e CIFs não são versionados.

## O que não foi validado

- CSD real: SDK/licença não disponíveis; apenas caminho de indisponibilidade
  testado. Não se declara consulta a Cambridge concluída.
- Precisão/recall em corpus científico rotulado: não medidos.
- Windows/macOS localmente: não executados nesta máquina. A configuração de CI
  cobre Windows e Linux com Python 3.11–3.13 quando GitHub Actions estiver ativo.
- Ineditismo, reprodutibilidade experimental ou desempenho semicondutor dos
  compostos: dependem de revisão e experimentação.
