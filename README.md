# Perovskite Explorer Astra

Pesquisa **sem IA** de orgânicos em perovskitas e outros semicondutores híbridos,
incluindo candidatos 0D, 1D, 2D, 3D e estruturas inversas/derivadas.
Recebe uma lista TXT, pesquisa fontes científicas, reúne estruturas e gera um
relatório auditável para priorizar a leitura e os experimentos.

**Comece pelo [guia rápido de uso e metodologia](docs/LEIA_PRIMEIRO.md).**
Também disponível em [PDF de duas páginas](docs/GUIA_RAPIDO.pdf).
Consulte também o [manual](docs/GUIA.md), a [metodologia detalhada](docs/METODOLOGIA.md)
e o [registro de validação](docs/VALIDACAO.md).

## O que entrega

- Busca nominal e por variantes químicas no **COD**, **HybriD³**, **Crossref**,
  **OpenAlex** e **Europe PMC**, com identidade auxiliada pelo **PubChem**.
- Conector opcional para o **CSD Python API** licenciado da Cambridge.
- CIFs disponíveis, grupo espacial, fórmula, cela, temperatura/R quando informados,
  verificação de coordenadas e miniatura da unidade assimétrica.
- Evidências de função estrutural, aditivo/passivante ou transporte, com trechos e
  links. Propriedades e condições dos datasets HybriD³ são preservadas.
- Contagens separadas de trabalhos por DOI, estruturas, amostras e reproduções
  revisadas. Citações não são tratadas como reproduções.
- HTML local com filtros; CSV/JSON; importação de CIF/TXT/PDF; planilha de revisão.
- SQLite transacional por página, cache com checksum, backup, retomada,
  registros de consultas/erros e bloqueio contra execução simultânea na mesma pasta.

## Instalação e primeiro uso

Python **3.11+**. Linux/macOS:

```bash
git clone https://github.com/mt3011/perovskite-explorer-astra.git
cd perovskite-explorer-astra
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[pdf,chem]"
perovskite-explorer run examples/organicos.txt --out runs/primeira-busca
```

No Windows PowerShell, ative com `.venv\Scripts\Activate.ps1`.
Abra **`runs/primeira-busca/report.html`** no navegador.
Para instalação mínima, sem importação PDF/descritores RDKit: `pip install -e .`.

```bash
# Ver estado, retomar uma interrupção e exportar sem rede
perovskite-explorer status runs/primeira-busca
perovskite-explorer resume runs/primeira-busca
perovskite-explorer export runs/primeira-busca

# Conferir instalação/acesso e testar o código
perovskite-explorer doctor --network
python -m pip install -e ".[dev]"
python -m pytest
```

Novas buscas precisam de internet, mas não de IA. A API do OpenAlex permite
consulta inicial sem chave e exige `OPENALEX_API_KEY` para paginação. Email
opcional em `PEROVSKITE_EMAIL`. Acesso/chaves são contratados diretamente com as
fontes; o programa não compra créditos. Consulte o manual para Cambridge.

## Como ler as conclusões

**Candidato estrutural não é confirmação.** O programa usa regras determinísticas,
sem modelos de linguagem. Nomes em metadados, protonação e contexto podem ser
ambíguos. Confirmação exige revisar artigo/CIF e registrar a decisão.
Poucos resultados indicam pouca evidência no conjunto recuperado, não ineditismo.

“4-Aminophenyl sulfone” é sinalizado como ambíguo, sem assumir dapsona. As formas
neutras/protonadas pesquisadas aparecem separadas no relatório. A dimensionalidade
é declarada pela fonte/texto; o programa não calcula topologia ou band gap.

O [exemplo real](docs/VALIDACAO.md) é uma validação de funcionamento, com limites
explícitos, e não uma revisão científica já concluída dos seis compostos.

## Organização

```text
src/perovskite_explorer/
  cli.py          comandos de uso, backup e restauração
  identity.py     entrada TXT, aliases, resolução PubChem
  sources.py      conectores e paginação das fontes
  http.py         cache, retries, rate limiting e proteção de credenciais
  store.py        transações, tarefas, histórico e backup SQLite
  pipeline.py     execução e retomada por etapas
  structures.py  validação CIF e projeções de coordenadas
  analysis.py     regras explícitas, DOI e descritores opcionais
  local.py        importação de documentos e revisão humana
  report.py       relatório HTML e exportações CSV/JSON
docs/             guias, metodologia, validação
examples/         lista fornecida e configuração comentada
tests/            testes offline de qualidade e recuperação
PROGRESS.md       estado do desenvolvimento para retomada
```

Dados de execução ficam em `runs/`, excluídos do Git. Faça backup externo da pasta
completa para se proteger de perda física de disco. Bases licenciadas, chaves e
artigos locais não devem ser enviados ao repositório.
