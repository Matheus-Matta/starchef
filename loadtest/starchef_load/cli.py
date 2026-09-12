"""Linha de comando do teste de carga."""
import argparse
import sys
import time

from . import report
from .config import PROFILES, LoadConfig
from .context import Context
from .suites import backend, desktop, mobile, web

SUITES = {"backend": backend, "web": web, "desktop": desktop, "mobile": mobile}
ORDEM = ["backend", "web", "desktop", "mobile"]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="loadtest",
        description="Teste de carga pesada do StarChef (backend, web, desktop e mobile).",
        epilog="Rode SEMPRE contra um ambiente descartavel: a suite cria milhares de registros de proposito.",
    )
    parser.add_argument("suite", choices=[*ORDEM, "all"], help="qual frente atacar")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="medio", help="intensidade (padrao: medio)")
    parser.add_argument("--base-url", dest="base_url", help="API (padrao http://127.0.0.1:8001)")
    parser.add_argument("--frontend-url", dest="frontend_url", help="SPA (padrao http://127.0.0.1:5173)")
    parser.add_argument("--username", help="usuario da conta de teste")
    parser.add_argument("--password", help="senha da conta de teste")
    parser.add_argument("--workers", type=int, help="conexoes simultaneas")
    parser.add_argument("--rate", type=int, help="taxa alvo por modelo, em requisicoes/s")
    parser.add_argument("--duration", type=int, help="segundos por fase")
    parser.add_argument("--count", type=int, help="numero fixo de requisicoes por fase (ignora --duration)")
    parser.add_argument("--timeout", type=float, help="timeout HTTP em segundos")
    parser.add_argument("--chaos-ratio", dest="chaos_ratio", type=float, help="fracao de payloads errados (0 a 1)")
    parser.add_argument("--sloppy-ratio", dest="sloppy_ratio", type=float,
                        help="fracao de payloads validos porem toscos (CPF errado, e-mail sem arroba)")
    parser.add_argument("--offline-ratio", dest="offline_ratio", type=float, help="chance de o terminal cair por venda")
    parser.add_argument("--terminals", type=int, help="quantidade de PDVs simulados")
    parser.add_argument("--waiters", type=int, help="quantidade de aparelhos de garcom")
    parser.add_argument("--sales", type=int, help="vendas por terminal")
    parser.add_argument("--seed", type=int, help="semente do gerador (repete a mesma execucao)")
    parser.add_argument("--models", nargs="*", help="filtra os modelos da suite backend (por trecho do nome)")
    parser.add_argument("--report-dir", dest="report_dir", help="onde gravar o relatorio")
    parser.add_argument("--label", help="sufixo do arquivo de relatorio")
    parser.add_argument("--cleanup", action="store_true", default=None, help="apaga os registros criados no fim")
    parser.add_argument("--skip-bootstrap", dest="skip_bootstrap", action="store_true", default=None,
                        help="nao cria o cenario minimo (produto/comanda/forma de pagamento)")
    parser.add_argument("--verbose", action="store_true", default=None, help="detalha cada fase")
    return parser


def _aviso_de_ambiente(config, log):
    log("=" * 78)
    log("TESTE DE CARGA STARCHEF — este comando FOI FEITO para degradar o alvo.")
    log(f"  API .......: {config.base_url}")
    log(f"  Frontend ..: {config.frontend_url}")
    log(f"  Perfil ....: {config.profile} ({config.workers} conexoes, alvo {config.rate}/s, {config.duration}s/fase)")
    log("  Use um banco descartavel e THROTTLE_RATE_* alto (veja docs/TESTE_CARGA.md).")
    log("=" * 78)


def main(argv=None):
    args = build_parser().parse_args(argv)
    config = LoadConfig.from_args(args)
    log = print
    _aviso_de_ambiente(config, log)

    escolhidas = ORDEM if args.suite == "all" else [args.suite]
    precisa_refs = any(nome in ("backend", "desktop", "mobile", "web") for nome in escolhidas)
    ctx = Context(config, log=log)
    inicio = time.time()
    try:
        ctx.prepare(need_schema=True, need_refs=precisa_refs)
    except Exception as erro:  # noqa: BLE001 — falha de preparo tem de explicar, nao stacktrace
        log(f"\nFALHA NO PREPARO: {erro}")
        log("Confira se o backend esta no ar, se as credenciais valem e se ha um restaurante na conta.")
        return 2

    executadas = []
    for nome in escolhidas:
        log("")
        log(f">>> suite {nome.upper()}")
        try:
            SUITES[nome].run(ctx)
            executadas.append(nome)
        except KeyboardInterrupt:
            log("\ninterrompido — gerando o relatorio parcial")
            executadas.append(f"{nome} (interrompida)")
            break
        except Exception as erro:  # noqa: BLE001
            ctx.note(nome, f"a suite abortou com {type(erro).__name__}: {erro}")
            executadas.append(f"{nome} (abortada)")
            log(f"!!! a suite {nome} abortou: {type(erro).__name__}: {erro}")

    dados = report.build(ctx.recorder, config, executadas, time.time() - inicio)
    caminho_md, caminho_json = report.write(dados, config.report_dir, config.label)
    log("")
    log(report.to_markdown(dados))
    log(f"Relatorio: {caminho_md}")
    log(f"JSON .....: {caminho_json}")
    totais = dados["totais"]
    falhou = totais["defeitos"] > 0 or any(not c["ok"] for c in dados["verificacoes"])
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
