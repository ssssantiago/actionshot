import rpakit


def run(numero_processo: str) -> dict:
    """Check deadline status and take the appropriate action."""
    app = rpakit.connect(title="Gestao de Prazos")

    # -- Selectors --
    busca_sel = rpakit.Selector(automation_id="txtBuscaProcesso")
    buscar_sel = rpakit.Selector(automation_id="btnBuscar")
    prazo_sel = rpakit.Selector(automation_id="lblPrazo")
    urgencia_sel = rpakit.Selector(automation_id="btnSolicitarUrgencia")
    confirmar_sel = rpakit.Selector(automation_id="btnConfirmar")
    concluido_sel = rpakit.Selector(automation_id="btnMarcarConcluido")

    # -- Search for the case --
    rpakit.wait_for(busca_sel, timeout_ms=5000)
    rpakit.fill(busca_sel, numero_processo)

    rpakit.wait_for(buscar_sel, timeout_ms=5000)
    rpakit.click(buscar_sel)

    # -- Extract deadline status --
    rpakit.wait_for(prazo_sel, timeout_ms=8000)
    prazo_status = rpakit.extract_text(prazo_sel)
    assert prazo_status, "Expected deadline status but field was empty"

    # -- Conditional branch --
    if "Vencido" in prazo_status:
        # Deadline expired: request urgency
        rpakit.wait_for(urgencia_sel, timeout_ms=5000)
        rpakit.click(urgencia_sel)

        rpakit.wait_for(confirmar_sel, timeout_ms=5000)
        rpakit.click(confirmar_sel)

        acao_tomada = "urgencia_solicitada"
    else:
        # Deadline OK: mark as completed
        rpakit.wait_for(concluido_sel, timeout_ms=5000)
        rpakit.click(concluido_sel)

        acao_tomada = "marcado_concluido"

    return {"acao_tomada": acao_tomada}


if __name__ == "__main__":
    result = run(numero_processo="0001234-56.2024.8.26.0100")
    print("Acao:", result["acao_tomada"])
