# Registro de implementação e retomada

Este arquivo acompanha o desenvolvimento. O estado das buscas científicas será
guardado separadamente, em SQLite, dentro de cada pasta de execução.

## Escopo autorizado

Programa Python, sem LLM ou API de IA, para pesquisar orgânicos em estruturas
híbridas de interesse semicondutor (incluindo 0D–3D e perovskitas inversas).
Entregar código no repositório mt3011/perovskite-explorer-astra e guia em português.

## Decisões

- Fontes: COD, HybriD³, Crossref, OpenAlex, Europe PMC e PubChem; CSD via SDK licenciado.
- Contar trabalhos por DOI; nunca somar contagens brutas das fontes.
- Menção, uso estrutural provável e confirmação revisada são conceitos diferentes.
- Falha de fonte, limite de resultados e identidade ambígua nunca significam ineditismo.
- Salvar respostas, consultas, versões, hashes, tentativas e decisões de revisão.
- Estruturas CIF ficam disponíveis; ausência de CIF é lacuna explícita.
- Repetição de síntese exige revisão humana; citações não medem reprodução.

## Etapas

- [x] Localizar repositório e consultar documentação oficial das fontes.
- [x] Implementar núcleo, persistência, fontes e análise determinística.
- [x] Implementar CLI, relatórios e importação/revisão local.
- [x] Testar falhas, retomada, qualidade das classificações e contratos das fontes.
- [x] Executar exemplo real e documentar disponibilidade e limitações.
- [ ] Salvar commits e enviar ao GitHub.

## Retomada do desenvolvimento

1. Ler este arquivo, `git status` e o guia.
2. Executar `.venv/bin/python -m pytest` quando os testes estiverem disponíveis.
3. Preservar `runs/`, respostas e bancos de dados existentes.
4. Não colocar chaves, bases licenciadas ou texto integral de editoras no Git.

## Estado da entrega

- Código inicial já enviado ao GitHub; concluir commit final de documentação/testes.
- 48 testes passaram; lint e build também. Relatório testado em Chromium desktop/mobile.
- `docs/GUIA_RAPIDO.pdf` tem duas páginas; fonte em `docs/LEIA_PRIMEIRO.md`.
- Piloto real: `runs/example-live`, 47 CIFs, 220/221 tarefas concluídas.
- A pendência é um timeout externo no HybriD³ após 425 datasets. Não apagar nem
  marcar como concluída. Pode retomar com `resume runs/example-live --timeout 90`.
- Revisão científica não executada; contagens de candidatos não são confirmações.
- Conector CSD preparado conforme SDK oficial, sem validação licenciada.
