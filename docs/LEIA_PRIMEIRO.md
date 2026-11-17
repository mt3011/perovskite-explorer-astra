# Perovskite Explorer Astra — guia rápido

**Para que serve:** descobrir quais orgânicos merecem investigação em
semicondutores híbridos, reunindo publicações, evidências e estruturas. Funciona
sem IA; usa Python e APIs de dados científicos.

## 1. Instale e execute

Com Python 3.11+, dentro da pasta do repositório:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# No Windows PowerShell, use: .venv\Scripts\Activate.ps1
python -m pip install -e ".[pdf,chem]"
perovskite-explorer run examples/organicos.txt --out runs/meu-estudo
```

Para sua própria lista, substitua `examples/organicos.txt` pelo seu TXT UTF-8,
com **um nome em inglês por linha**. Abra `runs/meu-estudo/report.html` no navegador.
Ali há filtros, artigos, trechos de evidência, dados cristalográficos e links CIF.
As tabelas `summary.csv` e `queries.csv` abrem em planilhas.

## 2. Entenda a pesquisa

**Nome → identidade → busca → evidência → estrutura → contagem → revisão.**

O PubChem ajuda a conferir CID, fórmula e SMILES. COD e HybriD³ fornecem registros
de estruturas e propriedades. Crossref, OpenAlex e Europe PMC fornecem literatura.
As consultas combinam nomes e variantes com perovskitas, antiperovskitas, haletos
metálicos, híbridos, semicondutores e polímeros de coordenação. O programa também
busca no COD os DOIs dos candidatos encontrados na literatura.

Uma regra procura o nome junto a expressões de incorporação estrutural. Outras
identificam passivação, aditivos, transporte de cargas, negações e hipóteses.
O texto aberto do Europe PMC pode complementar os resumos; artigos fechados podem
ser importados por você como PDF/TXT obtidos legitimamente.

Não se restringe à fórmula ABX₃: inclui candidatos 0D–3D e estruturas relacionadas.
A dimensionalidade é informação reportada; não é calculada a partir da rede.
Ter uma estrutura híbrida não comprova propriedades semicondutoras.

## 3. Leia as contagens sem confundir conceitos

| Resultado | Como interpretar |
|---|---|
| Candidato estrutural | Indício automático que precisa de leitura do artigo/CIF. |
| DOI estrutural revisado | Trabalho confirmado por você como uso estrutural. |
| CIF distinto | Arquivo estrutural por hash; pode repetir uma fase de outro arquivo. |
| Reprodução revisada | Outro trabalho ligado manualmente à mesma fase, com evidência experimental. |
| Citações | Influência bibliográfica, não reprodução. |
| Falha/limite | Pesquisa incompleta. Não significa que não há trabalhos. |

DOIs iguais em várias fontes contam uma vez. Poucos trabalhos podem motivar
estudo, mas “nada encontrado” **não significa “molécula inédita”**. Os trechos,
fontes e consultas ficam disponíveis para conferir as conclusões.

## 4. Confirme os casos interessantes

Abra o CIF no Mercury/VESTA e confira molécula/íon, função na rede, estequiometria,
fase e síntese. A miniatura do relatório é somente uma projeção sem ligações.

Copie `review_template.csv` para `minhas_revisoes.csv`. Para confirmar, preencha
`decision=structural_confirmed`, `reviewer`, `note` com página/CIF/evidência e
`sample_id` da fase. Para registrar reprodução, `replication_of` deve conter a
chave `doi:...` de outro trabalho confirmado da mesma fase.

```bash
perovskite-explorer review runs/meu-estudo minhas_revisoes.csv
```

“4-Aminophenyl sulfone” fica **ambíguo**: confirme nome/CAS/CID antes de priorizá-lo.
Adicione sinônimos e formas protonadas em `config.toml`; o exemplo comentado está
em `examples/config.toml`. Uma identidade resolvida automaticamente ainda merece
conferência. Formas protonadas são variantes de busca, não identidades presumidas.

## 5. Retome e proteja os resultados

```bash
perovskite-explorer resume runs/meu-estudo
perovskite-explorer export runs/meu-estudo
perovskite-explorer backup runs/meu-estudo --out /outro/disco/backup-estudo
```

Cada página é salva em SQLite; Ctrl+C ou queda de energia não apagam páginas já
confirmadas. O cache evita downloads repetidos. Faça backup em outro disco: a
cópia automática local não protege contra perda física do dispositivo.
Para atualizar a literatura ou aumentar limites, use uma **nova pasta de execução**.

## 6. Fontes que precisam de acesso

Configure `OPENALEX_API_KEY` para paginar no OpenAlex. Cambridge usa o SDK oficial
`ccdc`, licença e base instalados; depois selecione `csd` em `--sources`. Esse
conector está preparado, mas não foi testado com licença nesta entrega. Não há
promessa de acesso automático a todos os bancos comerciais.

**Confiança:** use a ferramenta como triagem rastreável. Regras determinísticas
também erram; nomes ausentes, metadados incompletos e artigos fechados deixam
lacunas. Os testes verificam funcionamento, não precisão científica medida em
corpus rotulado. [Manual completo](GUIA.md) · [Metodologia e fontes](METODOLOGIA.md).
