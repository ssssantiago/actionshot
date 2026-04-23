import rpakit
from rpakit import UI, run_workflow, log


@run_workflow("excel_to_form")
def run(excel_path: str, row_number: str) -> dict:
    """Read data from Excel and fill web form with client information."""
    
    # -- Connect to Excel --
    ui_excel = UI.attach("cadastro_clientes.xlsx - Microsoft Excel")
    log("Connected to Excel workbook")
    
    # -- Click on cell A2 --
    cell_a2_selector = {
        "primary": {"method": "uia_automation_id", "value": "A2"},
        "secondary": {"method": "uia_name", "value": "Celula A2"},
        "tertiary": {"method": "ocr_anchor", "text": "Nome Completo"},
        "fallback": {"method": "coordinates", "x": 85, "y": 145},
        "label": "Cell A2 - Nome",
        "control_type": "DataItem"
    }
    ui_excel.click(cell_a2_selector)
    
    # -- Extract nome from cell A2 --
    nome_selector = {
        "primary": {"method": "uia_automation_id", "value": "NameBox"},
        "tertiary": {"method": "ocr_anchor", "text": "A2"},
        "fallback": {"method": "coordinates", "x": 85, "y": 145},
        "label": "Cell value - Nome",
        "control_type": "Edit"
    }
    nome_cliente = ui_excel.read(nome_selector)
    log(f"Extracted nome: {nome_cliente}")
    
    # -- Extract CPF from cell B2 --
    cpf_selector = {
        "primary": {"method": "uia_automation_id", "value": "B2"},
        "tertiary": {"method": "ocr_anchor", "text": "CPF"},
        "fallback": {"method": "coordinates", "x": 200, "y": 145},
        "label": "Cell B2 - CPF",
        "control_type": "DataItem"
    }
    cpf_cliente = ui_excel.read(cpf_selector)
    log(f"Extracted CPF: {cpf_cliente}")
    
    # -- Extract telefone from cell C2 --
    telefone_selector = {
        "primary": {"method": "uia_automation_id", "value": "C2"},
        "tertiary": {"method": "ocr_anchor", "text": "Telefone"},
        "fallback": {"method": "coordinates", "x": 320, "y": 145},
        "label": "Cell C2 - Telefone",
        "control_type": "DataItem"
    }
    telefone_cliente = ui_excel.read(telefone_selector)
    log(f"Extracted telefone: {telefone_cliente}")
    
    # -- Connect to web form --
    ui_web = UI.attach("Cadastro de Clientes - Google Chrome")
    log("Connected to web form")
    
    # -- Fill nome completo field --
    nome_field_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtNomeCompleto"},
        "secondary": {"method": "css_selector", "value": "input#nome-completo"},
        "tertiary": {"method": "ocr_anchor", "text": "Nome Completo"},
        "fallback": {"method": "coordinates", "x": 450, "y": 220},
        "label": "Nome Completo",
        "control_type": "Edit"
    }
    ui_web.fill(nome_field_selector, nome_cliente)
    
    # -- Fill CPF field --
    cpf_field_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtCPF"},
        "secondary": {"method": "css_selector", "value": "input#cpf"},
        "tertiary": {"method": "ocr_anchor", "text": "CPF"},
        "fallback": {"method": "coordinates", "x": 450, "y": 290},
        "label": "CPF",
        "control_type": "Edit"
    }
    ui_web.fill(cpf_field_selector, cpf_cliente)
    
    # -- Fill telefone field --
    telefone_field_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtTelefone"},
        "secondary": {"method": "css_selector", "value": "input#telefone"},
        "tertiary": {"method": "ocr_anchor", "text": "Telefone"},
        "fallback": {"method": "coordinates", "x": 450, "y": 360},
        "label": "Telefone",
        "control_type": "Edit"
    }
    ui_web.fill(telefone_field_selector, telefone_cliente)
    
    # -- Click cadastrar button --
    cadastrar_selector = {
        "primary": {"method": "uia_automation_id", "value": "btnCadastrar"},
        "secondary": {"method": "css_selector", "value": "button#submit-cadastro"},
        "tertiary": {"method": "ocr_anchor", "text": "Cadastrar"},
        "fallback": {"method": "coordinates", "x": 450, "y": 440},
        "label": "Cadastrar",
        "control_type": "Button"
    }
    ui_web.click(cadastrar_selector)
    log("Form submitted successfully")
    
    return {}


if __name__ == "__main__":
    result = run(
        excel_path="C:\\Clientes\\cadastro_clientes.xlsx",
        row_number="2"
    )