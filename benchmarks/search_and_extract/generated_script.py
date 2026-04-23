import rpakit
from rpakit import UI, run_workflow, log


@run_workflow("search_and_extract")
def search_and_extract(termo_busca: str, comarca: str) -> dict:
    """Navigate to TJSP jurisprudence search, type query, execute search, and extract case results."""
    
    ui = UI.attach("TJSP - Consulta de Jurisprudencia - Google Chrome")
    
    # Step 2: Click Jurisprudencia link
    jurisprudencia_selector = {
        "primary": {"method": "uia_automation_id", "value": "lnkJurisprudencia"},
        "secondary": {"method": "css_selector", "value": "a#nav-jurisprudencia"},
        "tertiary": {"method": "ocr_anchor", "text": "Jurisprudencia"},
        "fallback": {"method": "coordinates", "x": 350, "y": 65},
        "label": "Jurisprudencia",
        "control_type": "Hyperlink"
    }
    ui.click(jurisprudencia_selector)
    
    # Step 3: Wait for search field
    pesquisa_livre_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtPesquisaLivre"},
        "secondary": {"method": "css_selector", "value": "input#pesquisa-livre"},
        "label": "Campo de pesquisa",
        "control_type": "Edit"
    }
    ui.wait_for(pesquisa_livre_selector)
    
    # Step 4: Fill search term
    pesquisa_livre_fill_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtPesquisaLivre"},
        "secondary": {"method": "css_selector", "value": "input#pesquisa-livre"},
        "tertiary": {"method": "ocr_anchor", "text": "Pesquisa livre"},
        "fallback": {"method": "coordinates", "x": 500, "y": 200},
        "label": "Pesquisa livre",
        "control_type": "Edit"
    }
    ui.fill(pesquisa_livre_fill_selector, termo_busca)
    
    # Step 5: Fill comarca
    comarca_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtComarca"},
        "secondary": {"method": "css_selector", "value": "input#comarca"},
        "tertiary": {"method": "ocr_anchor", "text": "Comarca"},
        "fallback": {"method": "coordinates", "x": 500, "y": 270},
        "label": "Comarca",
        "control_type": "Edit"
    }
    ui.fill(comarca_selector, comarca)
    
    # Step 6: Click search button
    pesquisar_selector = {
        "primary": {"method": "uia_automation_id", "value": "btnPesquisar"},
        "secondary": {"method": "css_selector", "value": "button#btn-pesquisar"},
        "tertiary": {"method": "ocr_anchor", "text": "Pesquisar"},
        "fallback": {"method": "coordinates", "x": 500, "y": 340},
        "label": "Pesquisar",
        "control_type": "Button"
    }
    ui.click(pesquisar_selector)
    
    # Step 7: Wait for results grid
    grid_resultados_selector = {
        "primary": {"method": "uia_automation_id", "value": "gridResultados"},
        "secondary": {"method": "css_selector", "value": "div#resultados-lista"},
        "label": "Resultados grid",
        "control_type": "DataGrid"
    }
    ui.wait_for(grid_resultados_selector)
    
    # Step 8: Click first result
    primeiro_resultado_selector = {
        "primary": {"method": "uia_automation_id", "value": "resultado_0"},
        "secondary": {"method": "css_selector", "value": "div.resultado-item:first-child a"},
        "tertiary": {"method": "ocr_anchor", "text": "Apelacao"},
        "fallback": {"method": "coordinates", "x": 500, "y": 420},
        "label": "Primeiro resultado",
        "control_type": "Hyperlink"
    }
    ui.click(primeiro_resultado_selector)
    
    # Step 9: Extract case number
    numero_processo_selector = {
        "primary": {"method": "uia_automation_id", "value": "lblNumeroProcesso"},
        "secondary": {"method": "css_selector", "value": "span.numero-processo"},
        "tertiary": {"method": "ocr_anchor", "text": "Processo:"},
        "fallback": {"method": "coordinates", "x": 400, "y": 180},
        "label": "Numero do Processo",
        "control_type": "Text"
    }
    numero_processo = ui.read(numero_processo_selector)
    
    # Step 10: Extract ementa
    ementa_selector = {
        "primary": {"method": "uia_automation_id", "value": "lblEmenta"},
        "secondary": {"method": "css_selector", "value": "div.ementa-text"},
        "tertiary": {"method": "ocr_anchor", "text": "Ementa"},
        "fallback": {"method": "coordinates", "x": 400, "y": 320},
        "label": "Ementa",
        "control_type": "Text"
    }
    ementa = ui.read(ementa_selector)
    
    return {
        "numero_processo": numero_processo,
        "ementa": ementa
    }


if __name__ == "__main__":
    result = search_and_extract(
        termo_busca="dano moral acidente de transito",
        comarca="Sao Paulo"
    )
    print(f"Numero do Processo: {result['numero_processo']}")
    print(f"Ementa: {result['ementa'][:200]}...")