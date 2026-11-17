from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tomllib
from collections import Counter
from pathlib import Path

from filelock import FileLock, Timeout

from . import __version__
from .local import import_files, import_reviews
from .pipeline import DEFAULTS, initialize, run
from .report import export_report
from .store import Store


def parser():
    root = argparse.ArgumentParser(description="Pesquisa auditável de orgânicos em semicondutores híbridos, sem IA.")
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)
    start = sub.add_parser("run", help="Iniciar pesquisa a partir de TXT")
    start.add_argument("input", type=Path)
    start.add_argument("--out", required=True, type=Path)
    start.add_argument("--config", type=Path)
    start.add_argument("--sources", help="Fontes separadas por vírgula; csd exige licença")
    for name in ("max-results", "page-size", "max-aliases", "max-hybrid3-records", "max-fulltexts"):
        start.add_argument("--" + name, type=int)
    start.add_argument("--no-cifs", action="store_true")
    start.add_argument("--no-fulltext", action="store_true")
    start.add_argument("--offline", action="store_true")
    resume = sub.add_parser("resume", help="Retomar consultas pendentes/falhas preservando o cache")
    resume.add_argument("directory", type=Path)
    resume.add_argument("--offline", action="store_true")
    resume.add_argument("--timeout", type=int, help="Timeout HTTP em segundos; alteração registrada no histórico")
    for cmd, description in [("status", "Ver estado, pendências e integridade"),
                             ("export", "Recriar HTML/CSV/JSON sem consultar a rede"),
                             ("backup", "Criar cópia consistente de toda a execução")]:
        command = sub.add_parser(cmd, help=description)
        command.add_argument("directory", type=Path)
        if cmd == "backup":
            command.add_argument("--out", required=True, type=Path)
    restore = sub.add_parser("restore", help="Restaurar o backup SQLite para uma pasta nova")
    restore.add_argument("directory", type=Path)
    restore.add_argument("--out", required=True, type=Path)
    imported = sub.add_parser("import", help="Importar CIF e/ou artigo TXT/PDF obtidos legitimamente")
    imported.add_argument("directory", type=Path)
    imported.add_argument("--cif", type=Path)
    imported.add_argument("--text", type=Path)
    imported.add_argument("--doi", default="")
    imported.add_argument("--title", default="")
    imported.add_argument("--chemical-name", default="")
    imported.add_argument("--year", type=int)
    review = sub.add_parser("review", help="Aplicar decisões de revisão em CSV")
    review.add_argument("directory", type=Path)
    review.add_argument("csv", type=Path)
    doctor = sub.add_parser("doctor", help="Verificar instalação e, opcionalmente, acesso às fontes")
    doctor.add_argument("--network", action="store_true")
    doctor.add_argument("--out", type=Path, default=Path("runs/doctor"))
    return root


def ensure_run(directory):
    if not (directory / "state.sqlite").is_file():
        raise ValueError("Execução inexistente; informe a pasta que contém state.sqlite.")


def copy_run(store, target):
    if target.exists():
        raise ValueError("Destino já existe. Escolha uma pasta nova para preservar os dados.")
    if target.resolve().is_relative_to(store.directory.resolve()):
        raise ValueError("Backup deve ficar fora da pasta de origem.")
    store.backup()
    shutil.copytree(store.directory, target,
                    ignore=shutil.ignore_patterns("state.sqlite", "state.sqlite-wal", "state.sqlite-shm", ".run.lock"))
    shutil.copy2(store.directory / "state.backup.sqlite", target / "state.sqlite")


def doctor(network, directory):
    import importlib.util
    import platform
    print(f"Python {platform.python_version()} · Perovskite Explorer {__version__}")
    for package in ("requests", "gemmi", "filelock", "pypdf", "rdkit", "ccdc"):
        print(f"{package}: {'instalado' if importlib.util.find_spec(package) else 'ausente'}")
    if not network:
        return 0
    from .http import HttpClient, SourceError
    from .sources import fetch_page
    with FileLock(str(directory.resolve()) + ".lock", timeout=0):
        store = Store(directory)
        http = HttpClient(store, retries=1)
        probes = {"PubChem": ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/phenazine/cids/JSON", None),
                  "COD": ("https://www.crystallography.net/cod/result", {"id": "1100746", "format": "json"}),
                  "HybriD3": ("https://materials.hybrid3.duke.edu/materials/datasets/", {"page_size": 1})}
        failures = 0
        try:
            for name, (url, params) in probes.items():
                try:
                    http.json(url, params)
                    print(f"{name}: JSON acessível")
                except SourceError as exc:
                    failures += 1
                    print(f"{name}: {exc}")
            for name in ("crossref", "openalex", "europepmc"):
                try:
                    page = fetch_page(name, '"phenazine" AND perovskite', None, 0, http, DEFAULTS | {"max_results": 1, "page_size": 1})
                    print(f"{name}: contrato validado ({len(page.records)} registro)")
                except (SourceError, KeyError, ValueError) as exc:
                    failures += 1
                    print(f"{name}: {type(exc).__name__}")
            store.event("doctor", f"falhas={failures}")
            store.backup()
        finally:
            store.close()
        return 2 if failures else 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return doctor(args.network, args.out)
        if args.command == "run":
            content = tomllib.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
            config = dict(content.get("search", {}))
            for key in ("max_results", "page_size", "max_aliases", "max_hybrid3_records", "max_fulltexts"):
                if getattr(args, key) is not None:
                    config[key] = getattr(args, key)
            if args.sources:
                config["sources"] = [s.strip() for s in args.sources.split(",")]
            if args.no_cifs:
                config["download_cifs"] = False
            if args.no_fulltext:
                config["fulltext"] = False
            initialize(args.out, args.input, config, content.get("compounds"))
            code = run(args.out, args.offline)
            print(f"Relatório: {(args.out / 'report.html').resolve()}")
            return code
        if args.command == "restore":
            if args.out.exists():
                raise ValueError("Restaure em uma pasta nova.")
            if args.out.resolve().is_relative_to(args.directory.resolve()):
                raise ValueError("Destino de restauração deve ficar fora da origem.")
            with FileLock(str(args.directory / ".run.lock"), timeout=0):
                backup = args.directory / "state.backup.sqlite"
                if not backup.is_file():
                    raise ValueError("state.backup.sqlite ausente.")
                with sqlite3.connect(f"file:{backup.resolve()}?mode=ro", uri=True) as db:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Backup não passou na verificação de integridade.")
                shutil.copytree(args.directory, args.out, ignore=shutil.ignore_patterns("state.sqlite*", ".run.lock"))
                shutil.copy2(backup, args.out / "state.sqlite")
                print(f"Restaurado. Execute: perovskite-explorer resume {args.out}")
                return 0
        ensure_run(args.directory)
        if args.command == "resume":
            code = run(args.directory, args.offline, timeout=args.timeout)
            print(f"Relatório: {(args.directory / 'report.html').resolve()}")
            return code
        with FileLock(str(args.directory / ".run.lock"), timeout=0):
            store = Store(args.directory)
            try:
                if args.command == "status":
                    print(json.dumps({"integrity": store.integrity(), "jobs": dict(Counter(j["status"] for j in store.jobs())),
                                      "truncated": sum(j["truncated"] for j in store.jobs()),
                                      "failures": [{"source": j["source"], "query": j["query"], "error": j["error"]}
                                                   for j in store.jobs() if j["status"] == "failed"]}, indent=2, ensure_ascii=False))
                    return 0
                if args.command == "backup":
                    copy_run(store, args.out)
                    print(f"Backup completo: {args.out.resolve()}")
                    return 0
                if args.command == "import":
                    result = import_files(store, args.cif, args.text, args.doi, args.title, args.chemical_name, args.year)
                    print(f"Importado: {result}")
                if args.command == "review":
                    print(f"Revisões aplicadas: {import_reviews(store, args.csv)}")
                export_report(store)
                store.backup()
                print(f"Relatório: {(args.directory / 'report.html').resolve()}")
            finally:
                store.close()
        return 0
    except Timeout:
        print("Outra execução usa esta pasta. Aguarde ou escolha outra pasta.", file=sys.stderr)
        return 2
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
