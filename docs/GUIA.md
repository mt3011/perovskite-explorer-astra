# Guia de uso e confiança nos resultados

O **Perovskite Explorer Astra** recebe um TXT de orgânicos e reúne artigos,
registros cristalográficos, estruturas CIF e evidências de possível uso estrutural.
Funciona em Python, sem LLM, embeddings ou API de IA. A pesquisa online usa apenas
APIs de dados científicos; a consulta aos resultados salvos funciona sem internet.

## 1. Instalar

Requer Python **3.11 ou superior**, Git e internet para novas buscas.

```bash
git clone https://github.com/mt3011/perovskite-explorer-astra.git
cd perovskite-explorer-astra
python -m venv .venv
```

Ative o ambiente:

```bash
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell (use este em vez do comando acima)
.venv\Scripts\Activate.ps1
```

```bash
python -m pip install -e ".[pdf,chem]"
perovskite-explorer doctor
```

`pdf` permite importar PDFs com texto; `chem` adiciona descritores RDKit.
Para uma instalação menor, use `pip install -e .`.
O projeto pode ser instalado no mesmo Python do SDK Cambridge; confirme primeiro
que esse Python é compatível com o SDK e com o requisito ≥3.11 do projeto.

## 2. Pesquisar a lista

Salve um arquivo UTF-8 com **um nome por linha**, preferencialmente em inglês.
Linhas vazias e iniciadas com `#` são ignoradas. A lista fornecida está em
[`examples/organicos.txt`](../examples/organicos.txt).

```bash
perovskite-explorer run examples/organicos.txt --out runs/estudo-01
```

Abra `runs/estudo-01/report.html` no navegador. Não precisa de servidor ou conta.
O filtro permite procurar composto, DOI e classificação; clique em cada trabalho
para ver as evidências e os arquivos estruturais.

Para uma primeira exploração com menos resultados por consulta:

```bash
perovskite-explorer run examples/organicos.txt --out runs/piloto --max-results 30
```

O limite é **por consulta**, não por composto. Resultados além dele ficam marcados
como truncados. Para ampliar os limites ou mudar nomes/configuração, inicie outra
pasta; a pasta anterior é um registro reproduzível da busca anterior.

O OpenAlex pode responder sem chave, mas **a paginação exige chave**, conforme sua
documentação atual. Obtenha uma chave pessoal no próprio serviço. Ela não é de IA.
No Linux/macOS, configure sem colocá-la em arquivos versionados:

```bash
export OPENALEX_API_KEY="sua-chave"
export PEROVSKITE_EMAIL="seu-email"
```

No PowerShell: `$env:OPENALEX_API_KEY="sua-chave"` e
`$env:PEROVSKITE_EMAIL="seu-email"`. O email é opcional e identifica o cliente
educadamente às APIs. Chave e email não são impressos nos relatórios.
O programa não faz contratação nem compra créditos. Limites e políticas pertencem
a cada provedor; indisponibilidade é registrada como pendência.

## 3. Interpretar corretamente

| Campo | Significado |
|---|---|
| DOIs estruturais revisados | Trabalhos distintos cuja incorporação estrutural foi confirmada por você na revisão. Começa em zero. |
| DOIs candidatos | Trabalhos distintos com indícios automáticos; **não são confirmações**. |
| CIFs distintos | Arquivos diferentes pelo SHA-256; não necessariamente fases cristalográficas diferentes. |
| Entradas estruturais | Identificadores de depósito/sistema; um artigo pode ter vários. |
| Reprodução revisada | Uma nova publicação ligada manualmente a outra, na mesma fase, com evidência de repetição experimental. |
| Citações | Visibilidade bibliográfica informada pela fonte. Não equivale a síntese ou reprodução. |
| Pendências / limites | Consultas falhas/inacabadas e consultas truncadas. Zero resultado com falha não é uma busca negativa. |

As categorias automáticas distinguem candidato estrutural, evidência mista,
passivação/aditivo/transporte, revisão bibliográfica, cálculo/preprint, simples
menção e fora de escopo. Cada decisão acompanha nomes encontrados e trechos.
Se o texto não está disponível, o programa declara essa limitação.

**Pouco reportado** significa poucos DOIs recuperados/revisados. O limiar de 1–3
trabalhos serve apenas para organizar a revisão, não para prever sucesso de síntese.
Nenhum resultado permite, sozinho, escrever “este composto nunca foi utilizado”.

## 4. Como a busca funciona

1. **Identidade:** consulta o PubChem e registra CID, fórmula, InChIKey, SMILES e
   propriedades disponíveis. Múltiplos CIDs não são resolvidos escolhendo o
   primeiro. Sinônimos retornados são sugestões; não entram indiscriminadamente
   nas consultas. A pequena lista de nomes revisáveis do programa distingue
   sinônimos de variantes de protonação.
2. **Estruturas:** busca os nomes/variantes no COD e lê os datasets do HybriD³.
   A correspondência no HybriD³ usa nome, grupo, descrição química e IUPAC, além
   dos metadados bibliográficos. Fórmula sozinha não identifica um orgânico.
3. **Literatura:** combina cada nome com perovskitas, antiperovskitas, haletos
   metálicos, híbridos orgânico-inorgânicos, semicondutores e polímeros de
   coordenação. Pesquisa Crossref, OpenAlex e Europe PMC com paginação e limites
   explícitos. O Crossref ranqueia resultados aproximados; seu total bruto não é
   uma contagem exata de artigos do composto.
4. **Texto:** examina títulos/resumos e, quando disponível, o corpo do texto aberto
   no Europe PMC. Bibliografia é excluída do corpo XML. PDFs/TXT locais também
   podem ser importados. Não contorna paywalls.
5. **Classificação:** regras de texto exigem o nome no contexto relevante, tratam
   negações, hipóteses, uso como aditivo e conflitos. Um nome nos metadados de um
   cristal com carbono e metal é candidato, pois ainda pode ser solvato, ligante
   ou parte de uma fase diferente. Só a revisão humana marca “confirmado”.
6. **Complementação:** procura no COD os DOIs dos candidatos para localizar
   estruturas mesmo quando o nome não consta do índice. Baixa CIFs com URL
   disponível e verifica blocos, cela, coordenadas, elementos e ocupações com Gemmi.
7. **Contagem:** une fontes pelo DOI normalizado. Registros sem DOI permanecem
   provisórios. Mantém separadas publicações, depósitos, amostras e reproduções.
8. **Entrega:** gera HTML, CSV e JSON, com consultas, datas, fontes, limitações e
   referências. Respostas originais ficam no SQLite, com SHA-256, para auditoria.

O escopo inclui 0D–3D, estruturas derivadas/inversas e outros híbridos de possível
interesse semicondutor. **A dimensionalidade não é calculada da conectividade**:
é informação declarada pelo HybriD³ ou mencionada no contexto textual, a revisar.
Band gaps, emissão e outras propriedades aparecem com seu contexto; não se atribui
automaticamente um número a uma fase. Descritores do orgânico não predizem band gap.

## 5. Conferir a estrutura e a frequência

Abra os CIFs no **Mercury** ou **VESTA**. A miniatura do relatório é somente uma
projeção da unidade assimétrica, sem ligações nem expansão de simetria.

Para confirmar um candidato, confira:

- se a molécula/íon é realmente o composto ou uma variante que interessa;
- se integra a estrutura da fase, ou se está apenas na superfície/solvente;
- fórmula, estequiometria, grupo espacial, protonação e conectividade;
- se o estudo é experimental e apresenta síntese/caracterização;
- se o artigo descreve uma nova amostra ou apenas cita outra publicação.

Copie `review_template.csv` para **outro nome**, por exemplo `minhas_revisoes.csv`.
O template é regenerado; sua planilha editada deve ter nome diferente.
Preencha apenas as linhas que examinou:

| Coluna | Como preencher |
|---|---|
| `decision` | `structural_confirmed`, `nonstructural_confirmed`, `excluded` ou `uncertain` |
| `reviewer` | Seu nome/identificação |
| `note` | Evidência e referência: página, tabela, CIF, átomo/componentes e razão da decisão |
| `sample_id` | Obrigatório para confirmação: identificador de uma fase, como `phenazinium-PbI4-fase-A` |
| `replication_of` | Só quando comprovada repetição: chave de outro trabalho confirmado da mesma fase, como `doi:10.xxxx/abc` |

```bash
perovskite-explorer review runs/estudo-01 minhas_revisoes.csv
```

Use `sample_id` diferente para polimorfos/composições distintos. A qualidade da
contagem de reprodução depende desta curadoria. O histórico das alterações fica
registrado no banco. As decisões são aplicadas atomicamente: uma linha inválida
impede a importação de toda a planilha.

## 6. Corrigir nomes e adicionar fontes locais

**“4-Aminophenyl sulfone” é ambíguo.** O programa não presume que seja dapsona.
Confirme o nome completo, CAS/CID ou estrutura. Para corrigir e ampliar variantes,
copie [`examples/config.toml`](../examples/config.toml), preencha a seção do composto
e inicie uma nova pesquisa:

```bash
perovskite-explorer run minha_lista.txt --config minha_config.toml --out runs/estudo-02
```

`family_aliases` permite buscar formas protonadas/desprotonadas, mas elas continuam
marcadas como variantes. A lista interna é curta e não enumera todas as espécies,
tautômeros, abreviações ou traduções: acrescente o vocabulário da sua área.

Para importar um artigo e seu CIF, inclusive exportações de bases licenciadas:

```bash
perovskite-explorer import runs/estudo-01 --cif amostra.cif --text artigo.pdf --doi "10.xxxx/doi-real" --title "Título do artigo"
```

Substitua o DOI ilustrativo por um DOI válido. `--text artigo.txt` aceita texto
UTF-8. PDFs digitalizados precisam de OCR externo; não há OCR ou modelo de IA
embutido. Você pode informar `--chemical-name` e `--year`. Uma importação local
não confirma automaticamente o uso estrutural.

## 7. Cambridge e outras bases

Quando tiver o **CSD Python API oficial**, instalado e licenciado:

```bash
perovskite-explorer doctor
perovskite-explorer run minha_lista.txt --out runs/com-cambridge --sources cod,hybrid3,csd,crossref,openalex,europepmc
```

O conector usa `ccdc.search.TextNumericSearch.add_compound_name`, lê as entradas e
exporta CIFs localmente. Requer dados/licença CSD disponíveis na máquina. **Não é
uma integração fictícia com uma API web**: se seu futuro contrato fornecer outro
serviço, seu endpoint/autenticação precisará de um adaptador específico.

O conector foi escrito conforme a documentação oficial; não pôde ser exercitado
contra uma instalação licenciada nesta entrega. Até lá, Access Structures permite
localizar depósitos por DOI e baixar manualmente; depois importe o CIF.
O projeto não pesquisa ICSD, SpringerMaterials, Scopus ou Web of Science sem seus
respectivos acessos. Não existe promessa de cobertura de todos os bancos.

## 8. Interrupção, backup e atualização

```bash
perovskite-explorer status runs/estudo-01
perovskite-explorer resume runs/estudo-01
perovskite-explorer export runs/estudo-01
perovskite-explorer backup runs/estudo-01 --out /caminho/em/outro/disco/backup-01
```

No Windows, use um destino apropriado, por exemplo `D:\Backups\estudo-01`.
Se uma fonte estiver lenta, use `resume runs/estudo-01 --timeout 90`; o novo timeout
fica registrado no histórico, sem alterar a estratégia científica da busca.
`resume` repete somente pendências/falhas; páginas concluídas permanecem no SQLite.
`export` recria relatórios sem rede. `resume --offline` usa apenas respostas já
salvas; chamadas ausentes permanecem pendentes.
O código de saída é 0 para conclusão das tarefas, 2 para erro/busca parcial e 130
para interrupção. Consultas truncadas pelo limite escolhido aparecem no relatório,
mesmo quando o processo encerra com 0.

Cada página é confirmada em transação SQLite com WAL e `synchronous=FULL`.
Arquivos usam escrita temporária e substituição atômica; há bloqueio contra dois
processos na mesma pasta. Ctrl+C/SIGTERM preservam o estado e geram relatório parcial;
queda abrupta pode deixar a última página em andamento, que será repetida.

Existe `state.backup.sqlite`, atualizado periodicamente e ao finalizar. Se o banco
principal falhar, restaure uma cópia em pasta nova:

```bash
perovskite-explorer restore runs/estudo-01 --out runs/restaurado
perovskite-explorer resume runs/restaurado
```

Uma cópia no mesmo disco **não protege contra perda do disco**: faça backup externo
da pasta completa. O Git guarda o programa e o registro de desenvolvimento
`PROGRESS.md`; resultados científicos e bases licenciadas ficam fora do Git.

O cache é um **snapshot da execução**, sem expiração automática. Para atualizar a
literatura, mude configurações ou amplie limites, use uma nova pasta. Adicionar a
chave OpenAlex antes de `resume` permite completar páginas pendentes, mas não
reabre consultas já encerradas no limite escolhido.

## Até onde confiar

Confie no programa como **triagem auditável**, não como revisão sistemática
validada ou prova de novidade. Os testes verificam funcionamento, recuperação e
casos críticos de regras; não medem sensibilidade/especificidade em um corpus
rotulado por cristalógrafos. Consulte a [metodologia detalhada](METODOLOGIA.md)
para lacunas, contratos das APIs e critérios de validação.
