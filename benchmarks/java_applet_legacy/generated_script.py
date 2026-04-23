import rpakit
from rpakit import UI, run_workflow, wait, log


@run_workflow("java_applet_legacy")
def run(
    numero_oab: str,
    senha: str,
    numero_processo: str,
    tipo_peticao: str,
) -> dict:
    ui = UI.attach("e-SAJ Peticionamento")
    
    ui.wait_for({
        "primary": {"method": "ocr_anchor", "text": "Login do Advogado"},
        "fallback": {"method": "coordinates", "x": 400, "y": 150},
        "label": "Java applet login screen",
        "control_type": "Unknown"
    })
    
    ui.click({
        "primary": {"method": "ocr_anchor", "text": "Numero OAB"},
        "fallback": {"method": "coordinates", "x": 380, "y": 230},
        "label": "OAB field (no UIA)",
        "control_type": "Unknown"
    })
    
    ui.fill({
        "primary": {"method": "ocr_anchor", "text": "Numero OAB"},
        "fallback": {"method": "coordinates", "x": 380, "y": 230},
        "label": "OAB field (no UIA)",
        "control_type": "Unknown"
    }, numero_oab)
    
    ui.click({
        "primary": {"method": "ocr_anchor", "text": "Senha"},
        "fallback": {"method": "coordinates", "x": 380, "y": 290},
        "label": "Password field (no UIA)",
        "control_type": "Unknown"
    })
    
    ui.fill({
        "primary": {"method": "ocr_anchor", "text": "Senha"},
        "fallback": {"method": "coordinates", "x": 380, "y": 290},
        "label": "Password field (no UIA)",
        "control_type": "Unknown"
    }, senha)
    
    ui.click({
        "primary": {"method": "ocr_anchor", "text": "Entrar"},
        "fallback": {"method": "coordinates", "x": 400, "y": 350},
        "label": "Login button (no UIA)",
        "control_type": "Unknown"
    })
    
    ui.wait_for({
        "primary": {"method": "ocr_anchor", "text": "Painel de Peticionamento"},
        "fallback": {"method": "coordinates", "x": 400, "y": 100},
        "label": "Main panel loaded",
        "control_type": "Unknown"
    })
    
    ui.click({
        "primary": {"method": "ocr_anchor", "text": "Novo Peticionamento"},
        "fallback": {"method": "coordinates", "x": 150, "y": 180},
        "label": "Novo Peticionamento button (no UIA)",
        "control_type": "Unknown"
    })
    
    ui.click({
        "primary": {"method": "ocr_anchor", "text": "Numero do Processo"},
        "fallback": {"method": "coordinates", "x": 400, "y": 250},
        "label": "Processo number field (no UIA)",
        "control_type": "Unknown"
    })
    
    ui.fill({
        "primary": {"method": "ocr_anchor", "text": "Numero do Processo"},
        "fallback": {"method": "coordinates", "x": 400, "y": 250},
        "label": "Processo number field (no UIA)",
        "control_type": "Unknown"
    }, numero_processo)
    
    ui.click({
        "primary": {"method": "ocr_anchor", "text": tipo_peticao},
        "fallback": {"method": "coordinates", "x": 400, "y": 340},
        "label": "Tipo de peticao selection (no UIA)",
        "control_type": "Unknown"
    })
    
    ui.click({
        "primary": {"method": "ocr_anchor", "text": "Protocolar"},
        "fallback": {"method": "coordinates", "x": 400, "y": 500},
        "label": "Protocolar button (no UIA)",
        "control_type": "Unknown"
    })
    
    return {}