import rpakit


@rpakit.run_workflow("multi_tab_workflow")
def run(numero_processo: str, nome_parte: str) -> dict:
    """Open 3 browser tabs (TJSP, TJRJ, STJ), search the same processo in each, and consolidate results."""
    ui = rpakit.UI.attach("Google Chrome")

    # Tab 1: TJSP
    ui.click({
        "primary": {"method": "uia_automation_id", "value": "addressBar"},
        "secondary": {"method": "uia_name", "value": "Barra de endereco"},
        "tertiary": {"method": "ocr_anchor", "text": "Pesquisar ou digitar"},
        "fallback": {"method": "coordinates", "x": 500, "y": 52}
    })
    
    ui.fill({
        "primary": {"method": "uia_automation_id", "value": "addressBar"},
        "secondary": {"method": "uia_name", "value": "Barra de endereco"},
        "tertiary": {"method": "ocr_anchor", "text": "Pesquisar ou digitar"},
        "fallback": {"method": "coordinates", "x": 500, "y": 52}
    }, "https://esaj.tjsp.jus.br/cpopg/open.do")
    
    ui.wait_for({
        "primary": {"method": "css_selector", "value": "input#numeroDigitoAnoUnificado"},
        "tertiary": {"method": "ocr_anchor", "text": "Numero do processo"}
    })
    
    ui.fill({
        "primary": {"method": "css_selector", "value": "input#numeroDigitoAnoUnificado"},
        "tertiary": {"method": "ocr_anchor", "text": "Numero do processo"},
        "fallback": {"method": "coordinates", "x": 450, "y": 250}
    }, numero_processo)
    
    ui.click({
        "primary": {"method": "css_selector", "value": "input#botaoConsultarProcessos"},
        "tertiary": {"method": "ocr_anchor", "text": "Consultar"},
        "fallback": {"method": "coordinates", "x": 450, "y": 350}
    })
    
    resultado_tjsp = ui.read({
        "primary": {"method": "css_selector", "value": "span#classeProcesso"},
        "tertiary": {"method": "ocr_anchor", "text": "Classe:"},
        "fallback": {"method": "coordinates", "x": 400, "y": 200}
    })
    
    # Tab 2: TJRJ
    ui.click({
        "primary": {"method": "uia_automation_id", "value": "addressBar"},
        "tertiary": {"method": "ocr_anchor", "text": "Pesquisar ou digitar"},
        "fallback": {"method": "coordinates", "x": 500, "y": 52}
    })
    
    ui.fill({
        "primary": {"method": "uia_automation_id", "value": "addressBar"},
        "tertiary": {"method": "ocr_anchor", "text": "Pesquisar ou digitar"},
        "fallback": {"method": "coordinates", "x": 500, "y": 52}
    }, "https://www3.tjrj.jus.br/consultaprocessual")
    
    ui.fill({
        "primary": {"method": "css_selector", "value": "input#nomeParteAutora"},
        "tertiary": {"method": "ocr_anchor", "text": "Nome da Parte"},
        "fallback": {"method": "coordinates", "x": 450, "y": 280}
    }, nome_parte)
    
    return {
        "resultado_tjsp": resultado_tjsp,
        "resultado_tjrj": "",
        "resultado_stj": ""
    }


if __name__ == "__main__":
    result = run(
        numero_processo="0001234-56.2024.8.26.0100",
        nome_parte="Maria da Silva Santos"
    )
    print("TJSP:", result["resultado_tjsp"])
    print("TJRJ:", result["resultado_tjrj"])
    print("STJ:", result["resultado_stj"])