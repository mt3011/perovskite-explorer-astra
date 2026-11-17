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
- [ ] Implementar núcleo, persistência, fontes e análise determinística.
- [ ] Implementar CLI, relatórios e importação/revisão local.
- [ ] Testar falhas, retomada, qualidade das classificações e contratos das fontes.
- [ ] Executar exemplo real e documentar disponibilidade e limitações.
- [ ] Salvar commits e enviar ao GitHub.

## Retomada do desenvolvimento

1. Ler este arquivo, `git status` e o guia.
2. Executar `.venv/bin/python -m pytest` quando os testes estiverem disponíveis.
3. Preservar `runs/`, respostas e bancos de dados existentes.
4. Não colocar chaves, bases licenciadas ou texto integral de editoras no Git.
