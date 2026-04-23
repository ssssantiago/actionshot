import rpakit


@rpakit.run_workflow("loop_over_spreadsheet")
def run(planilha_path: str, total_linhas: str) -> dict:
    """Iterate over rows in an Excel spreadsheet, filling a web form for each client row."""
    
    # Convert total_linhas to integer
    iterations = int(total_linhas)
    
    # Open the Excel spreadsheet
    ui_excel = rpakit.UI.attach("clientes_pendentes.xlsx - Microsoft Excel")
    
    # Click on header row A1
    ui_excel.click({
        "primary": {"method": "uia_automation_id", "value": "A1"},
        "tertiary": {"method": "ocr_anchor", "text": "Nome"},
        "fallback": {"method": "coordinates", "x": 85, "y": 125},
        "label": "Header row cell A1",
        "control_type": "DataItem"
    })
    
    registros_processados = 0
    
    # Loop over each row
    for row_idx in range(iterations):
        # Extract Nome from column A
        nome_selector = {
            "primary": {"method": "uia_automation_id", "value": f"A{row_idx+2}"},
            "tertiary": {"method": "ocr_anchor", "text": "Nome"},
            "fallback": {"method": "coordinates", "x": 85, "y": 125 + (row_idx * 20)},
            "label": "Nome do cliente (row)",
            "control_type": "DataItem"
        }
        nome_atual = ui_excel.read(nome_selector)
        
        # Extract CPF from column B
        cpf_selector = {
            "primary": {"method": "uia_automation_id", "value": f"B{row_idx+2}"},
            "tertiary": {"method": "ocr_anchor", "text": "CPF"},
            "fallback": {"method": "coordinates", "x": 200, "y": 125 + (row_idx * 20)},
            "label": "CPF do cliente (row)",
            "control_type": "DataItem"
        }
        cpf_atual = ui_excel.read(cpf_selector)
        
        # Extract OAB from column C
        oab_selector = {
            "primary": {"method": "uia_automation_id", "value": f"C{row_idx+2}"},
            "tertiary": {"method": "ocr_anchor", "text": "Numero OAB"},
            "fallback": {"method": "coordinates", "x": 320, "y": 125 + (row_idx * 20)},
            "label": "OAB do advogado (row)",
            "control_type": "DataItem"
        }
        oab_atual = ui_excel.read(oab_selector)
        
        # Switch to the web form in Chrome
        ui_chrome = rpakit.UI.attach("Cadastro Processual - Google Chrome")
        
        # Fill Nome field
        ui_chrome.fill({
            "primary": {"method": "uia_automation_id", "value": "txtNomeCliente"},
            "secondary": {"method": "css_selector", "value": "input#nome-cliente"},
            "tertiary": {"method": "ocr_anchor", "text": "Nome do Cliente"},
            "fallback": {"method": "coordinates", "x": 450, "y": 220},
            "label": "Nome do Cliente",
            "control_type": "Edit"
        }, nome_atual)
        
        # Fill CPF field
        ui_chrome.fill({
            "primary": {"method": "uia_automation_id", "value": "txtCPFCliente"},
            "secondary": {"method": "css_selector", "value": "input#cpf-cliente"},
            "tertiary": {"method": "ocr_anchor", "text": "CPF"},
            "fallback": {"method": "coordinates", "x": 450, "y": 290},
            "label": "CPF",
            "control_type": "Edit"
        }, cpf_atual)
        
        # Fill OAB field
        ui_chrome.fill({
            "primary": {"method": "uia_automation_id", "value": "txtOAB"},
            "secondary": {"method": "css_selector", "value": "input#oab-advogado"},
            "tertiary": {"method": "ocr_anchor", "text": "OAB"},
            "fallback": {"method": "coordinates", "x": 450, "y": 360},
            "label": "Numero OAB",
            "control_type": "Edit"
        }, oab_atual)
        
        # Click Salvar button
        ui_chrome.click({
            "primary": {"method": "uia_automation_id", "value": "btnSalvar"},
            "secondary": {"method": "css_selector", "value": "button#btn-salvar"},
            "tertiary": {"method": "ocr_anchor", "text": "Salvar"},
            "fallback": {"method": "coordinates", "x": 450, "y": 440},
            "label": "Salvar",
            "control_type": "Button"
        })
        
        # Wait for success confirmation
        ui_chrome.wait_for({
            "primary": {"method": "uia_automation_id", "value": "lblSucesso"},
            "secondary": {"method": "css_selector", "value": "div.alert-success"},
            "tertiary": {"method": "ocr_anchor", "text": "Registro salvo"},
            "label": "Confirmacao de sucesso",
            "control_type": "Text"
        })
        
        registros_processados += 1
        
        # Click Novo Cadastro to prepare for next row
        ui_chrome.click({
            "primary": {"method": "uia_automation_id", "value": "btnNovoCadastro"},
            "secondary": {"method": "css_selector", "value": "button#btn-novo"},
            "tertiary": {"method": "ocr_anchor", "text": "Novo Cadastro"},
            "fallback": {"method": "coordinates", "x": 300, "y": 440},
            "label": "Novo Cadastro",
            "control_type": "Button"
        })
    
    # Return to Excel and save
    ui_excel = rpakit.UI.attach("clientes_pendentes.xlsx - Microsoft Excel")
    ui_excel.click("dummy")
    
    return {"registros_processados": str(registros_processados)}