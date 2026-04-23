import rpakit


@rpakit.run_workflow("conditional_approval")
def run(numero_processo: str, valor_honorarios: str, advogado_responsavel: str) -> dict:
    ui = rpakit.UI.attach("Sistema de Honorarios - Google Chrome")
    
    ui.click({
        "primary": {"method": "uia_automation_id", "value": "btnNovoHonorario"},
        "secondary": {"method": "css_selector", "value": "button#novo-honorario"},
        "tertiary": {"method": "ocr_anchor", "text": "Novo Honorario"},
        "fallback": {"method": "coordinates", "x": 150, "y": 55},
        "label": "Novo Honorario",
        "control_type": "Button"
    })
    
    ui.fill(
        {
            "primary": {"method": "uia_automation_id", "value": "txtNumeroProcesso"},
            "secondary": {"method": "css_selector", "value": "input#numero-processo"},
            "tertiary": {"method": "ocr_anchor", "text": "Numero do Processo"},
            "fallback": {"method": "coordinates", "x": 450, "y": 180},
            "label": "Numero do Processo",
            "control_type": "Edit"
        },
        numero_processo
    )
    
    ui.fill(
        {
            "primary": {"method": "uia_automation_id", "value": "txtValorHonorarios"},
            "secondary": {"method": "css_selector", "value": "input#valor-honorarios"},
            "tertiary": {"method": "ocr_anchor", "text": "Valor (R$)"},
            "fallback": {"method": "coordinates", "x": 450, "y": 250},
            "label": "Valor Honorarios",
            "control_type": "Edit"
        },
        valor_honorarios
    )
    
    ui.fill(
        {
            "primary": {"method": "uia_automation_id", "value": "txtAdvogado"},
            "secondary": {"method": "css_selector", "value": "input#advogado-responsavel"},
            "tertiary": {"method": "ocr_anchor", "text": "Advogado Responsavel"},
            "fallback": {"method": "coordinates", "x": 450, "y": 320},
            "label": "Advogado Responsavel",
            "control_type": "Edit"
        },
        advogado_responsavel
    )
    
    valor_float = float(valor_honorarios.replace(",", "."))
    
    if valor_float > 5000:
        ui.click({
            "primary": {"method": "uia_automation_id", "value": "btnEncaminharSocioGerente"},
            "secondary": {"method": "css_selector", "value": "button#encaminhar-socio-gerente"},
            "tertiary": {"method": "ocr_anchor", "text": "Encaminhar ao Socio-Gerente"},
            "fallback": {"method": "coordinates", "x": 350, "y": 420},
            "label": "Encaminhar ao Socio-Gerente",
            "control_type": "Button"
        })
        
        ui.fill(
            {
                "primary": {"method": "uia_automation_id", "value": "txtJustificativa"},
                "secondary": {"method": "css_selector", "value": "textarea#justificativa"},
                "tertiary": {"method": "ocr_anchor", "text": "Justificativa"},
                "fallback": {"method": "coordinates", "x": 450, "y": 500},
                "label": "Justificativa",
                "control_type": "Edit"
            },
            "Valor acima do limite de aprovacao automatica. Solicita-se aprovacao do socio-gerente."
        )
    else:
        ui.click({
            "primary": {"method": "uia_automation_id", "value": "btnEncaminharSocioJunior"},
            "secondary": {"method": "css_selector", "value": "button#encaminhar-socio-junior"},
            "tertiary": {"method": "ocr_anchor", "text": "Encaminhar ao Socio-Junior"},
            "fallback": {"method": "coordinates", "x": 550, "y": 420},
            "label": "Encaminhar ao Socio-Junior",
            "control_type": "Button"
        })
    
    ui.click({
        "primary": {"method": "uia_automation_id", "value": "btnConfirmar"},
        "secondary": {"method": "css_selector", "value": "button#confirmar-envio"},
        "tertiary": {"method": "ocr_anchor", "text": "Confirmar Envio"},
        "fallback": {"method": "coordinates", "x": 450, "y": 560},
        "label": "Confirmar Envio",
        "control_type": "Button"
    })
    
    ui.wait_for({
        "primary": {"method": "uia_automation_id", "value": "lblStatusAprovacao"},
        "secondary": {"method": "css_selector", "value": "span#status-aprovacao"},
        "tertiary": {"method": "ocr_anchor", "text": "Status:"},
        "label": "Status da aprovacao",
        "control_type": "Text"
    })
    
    status_aprovacao = ui.read({
        "primary": {"method": "uia_automation_id", "value": "lblStatusAprovacao"},
        "secondary": {"method": "css_selector", "value": "span#status-aprovacao"},
        "tertiary": {"method": "ocr_anchor", "text": "Status:"},
        "fallback": {"method": "coordinates", "x": 550, "y": 200},
        "label": "Status aprovacao",
        "control_type": "Text"
    })
    
    return {"status_aprovacao": status_aprovacao}


if __name__ == "__main__":
    result = run(
        numero_processo="0001234-56.2024.8.26.0100",
        valor_honorarios="7500.00",
        advogado_responsavel="Dr. Carlos Mendes - OAB/SP 123.456"
    )
    print("Status:", result["status_aprovacao"])