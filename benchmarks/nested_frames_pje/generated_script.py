import rpakit
from rpakit import UI, run_workflow, log


@run_workflow("nested_frames_pje")
def nested_frames_pje(
    cpf_advogado: str,
    senha_pje: str,
    classe_processual: str,
    assunto_principal: str,
    comarca: str,
    vara: str,
    nome_autor: str,
    cpf_autor: str,
) -> dict:
    """Login to PJe, navigate through nested iframes, and fill the processo initial form."""
    
    ui = UI.attach("PJe - Processo Judicial Eletronico - Google Chrome")
    
    log("Step 2: Filling CPF do Advogado")
    cpf_selector = {
        "primary": {"method": "css_selector", "value": "input#username"},
        "secondary": {"method": "uia_automation_id", "value": "txtCPF"},
        "tertiary": {"method": "ocr_anchor", "text": "CPF"},
        "fallback": {"method": "coordinates", "x": 640, "y": 300},
        "label": "CPF do Advogado",
        "control_type": "Edit",
        "frame": "frameLogin"
    }
    ui.fill(cpf_selector, cpf_advogado)
    
    log("Step 3: Filling Senha PJe")
    senha_selector = {
        "primary": {"method": "css_selector", "value": "input#password"},
        "secondary": {"method": "uia_automation_id", "value": "txtSenha"},
        "tertiary": {"method": "ocr_anchor", "text": "Senha"},
        "fallback": {"method": "coordinates", "x": 640, "y": 370},
        "label": "Senha PJe",
        "control_type": "Edit",
        "frame": "frameLogin"
    }
    ui.fill(senha_selector, senha_pje)
    
    log("Step 4: Clicking Entrar button")
    entrar_selector = {
        "primary": {"method": "css_selector", "value": "button#btnEntrar"},
        "secondary": {"method": "uia_automation_id", "value": "btnEntrar"},
        "tertiary": {"method": "ocr_anchor", "text": "Entrar"},
        "fallback": {"method": "coordinates", "x": 640, "y": 430},
        "label": "Entrar no PJe",
        "control_type": "Button",
        "frame": "frameLogin"
    }
    ui.click(entrar_selector)
    
    log("Step 5: Waiting for Painel principal")
    painel_selector = {
        "primary": {"method": "css_selector", "value": "div#painel-usuario"},
        "tertiary": {"method": "ocr_anchor", "text": "Painel do Advogado"},
        "label": "Painel principal",
        "control_type": "Pane"
    }
    ui.wait_for(painel_selector)
    
    log("Step 6: Clicking Novo Processo")
    novo_processo_selector = {
        "primary": {"method": "css_selector", "value": "a#menuNovoProcesso"},
        "secondary": {"method": "uia_automation_id", "value": "lnkNovoProcesso"},
        "tertiary": {"method": "ocr_anchor", "text": "Novo Processo"},
        "fallback": {"method": "coordinates", "x": 180, "y": 120},
        "label": "Novo Processo",
        "control_type": "Hyperlink",
        "frame": "frameMenu"
    }
    ui.click(novo_processo_selector)
    
    log("Step 7: Waiting for ngFrame")
    ngframe_selector = {
        "primary": {"method": "css_selector", "value": "iframe#ngFrame"},
        "label": "Frame principal do formulario",
        "control_type": "Pane"
    }
    ui.wait_for(ngframe_selector)
    
    log("Step 8: Selecting Classe Processual")
    classe_selector = {
        "primary": {"method": "css_selector", "value": "select#classeProcessual"},
        "secondary": {"method": "uia_automation_id", "value": "cboClasseProcessual"},
        "tertiary": {"method": "ocr_anchor", "text": "Classe Processual"},
        "fallback": {"method": "coordinates", "x": 500, "y": 220},
        "label": "Classe Processual",
        "control_type": "ComboBox",
        "frame": "ngFrame > frameFormulario"
    }
    ui.select(classe_selector, classe_processual)
    
    log("Step 9: Filling Assunto Principal")
    assunto_selector = {
        "primary": {"method": "css_selector", "value": "input#assuntoPrincipal"},
        "secondary": {"method": "uia_automation_id", "value": "txtAssuntoPrincipal"},
        "tertiary": {"method": "ocr_anchor", "text": "Assunto Principal"},
        "fallback": {"method": "coordinates", "x": 500, "y": 290},
        "label": "Assunto Principal",
        "control_type": "Edit",
        "frame": "ngFrame > frameFormulario"
    }
    ui.fill(assunto_selector, assunto_principal)
    
    log("Step 10: Selecting Comarca")
    comarca_selector = {
        "primary": {"method": "css_selector", "value": "select#comarca"},
        "secondary": {"method": "uia_automation_id", "value": "cboComarca"},
        "tertiary": {"method": "ocr_anchor", "text": "Comarca"},
        "fallback": {"method": "coordinates", "x": 500, "y": 360},
        "label": "Comarca",
        "control_type": "ComboBox",
        "frame": "ngFrame > frameFormulario"
    }
    ui.select(comarca_selector, comarca)
    
    log("Step 11: Selecting Vara")
    vara_selector = {
        "primary": {"method": "css_selector", "value": "select#vara"},
        "secondary": {"method": "uia_automation_id", "value": "cboVara"},
        "tertiary": {"method": "ocr_anchor", "text": "Vara"},
        "fallback": {"method": "coordinates", "x": 500, "y": 430},
        "label": "Vara",
        "control_type": "ComboBox",
        "frame": "ngFrame > frameFormulario"
    }
    ui.select(vara_selector, vara)
    
    log("Step 12: Filling Nome do Autor")
    nome_autor_selector = {
        "primary": {"method": "css_selector", "value": "input#nomeAutor"},
        "secondary": {"method": "uia_automation_id", "value": "txtNomeAutor"},
        "tertiary": {"method": "ocr_anchor", "text": "Nome do Autor"},
        "fallback": {"method": "coordinates", "x": 500, "y": 510},
        "label": "Nome do Autor",
        "control_type": "Edit",
        "frame": "ngFrame > frameFormulario > framePartes"
    }
    ui.fill(nome_autor_selector, nome_autor)
    
    log("Step 13: Filling CPF do Autor")
    cpf_autor_selector = {
        "primary": {"method": "css_selector", "value": "input#cpfAutor"},
        "secondary": {"method": "uia_automation_id", "value": "txtCPFAutor"},
        "tertiary": {"method": "ocr_anchor", "text": "CPF do Autor"},
        "fallback": {"method": "coordinates", "x": 500, "y": 570},
        "label": "CPF do Autor",
        "control_type": "Edit",
        "frame": "ngFrame > frameFormulario > framePartes"
    }
    ui.fill(cpf_autor_selector, cpf_autor)
    
    log("Step 14: Clicking Protocolar button")
    protocolar_selector = {
        "primary": {"method": "css_selector", "value": "button#btnProtocolar"},
        "secondary": {"method": "uia_automation_id", "value": "btnProtocolar"},
        "tertiary": {"method": "ocr_anchor", "text": "Protocolar"},
        "fallback": {"method": "coordinates", "x": 500, "y": 640},
        "label": "Protocolar",
        "control_type": "Button",
        "frame": "ngFrame > frameFormulario"
    }
    ui.click(protocolar_selector)
    
    return {}