import rpakit


def run(numero_processo: str) -> dict:
    """Search for a legal case and extract results."""
    app = rpakit.connect(title="Consulta Processual")

    # -- Selectors --
    processo_sel = rpakit.Selector(automation_id="txtNumeroProcesso")
    pesquisar_sel = rpakit.Selector(automation_id="btnPesquisar")
    grid_sel = rpakit.Selector(automation_id="gridResultados")
    status_sel = rpakit.Selector(automation_id="lblStatus")

    # -- Enter search query --
    rpakit.wait_for(processo_sel, timeout_ms=5000)
    rpakit.fill(processo_sel, numero_processo)

    # -- Execute search --
    rpakit.wait_for(pesquisar_sel, timeout_ms=5000)
    rpakit.click(pesquisar_sel)

    # -- Wait for results to load --
    rpakit.wait_for(grid_sel, timeout_ms=10000)

    # -- Extract results --
    resultado_busca = rpakit.extract_text(grid_sel)
    assert resultado_busca, "Expected search results but grid was empty"

    rpakit.wait_for(status_sel, timeout_ms=5000)
    status_processo = rpakit.extract_text(status_sel)
    assert status_processo, "Expected status text but field was empty"

    return {
        "resultado_busca": resultado_busca,
        "status_processo": status_processo,
    }


if __name__ == "__main__":
    result = run(numero_processo="0001234-56.2024.8.26.0100")
    print("Resultado:", result["resultado_busca"][:200])
    print("Status:", result["status_processo"])
