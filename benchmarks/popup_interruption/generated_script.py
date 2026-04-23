import rpakit


@rpakit.run_workflow("popup_interruption")
def run(nome_cliente: str, email_cliente: str) -> dict:
    ui = rpakit.UI.attach("Cadastro de Partes - Google Chrome")

    nome_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtNome"},
        "secondary": {"method": "css_selector", "value": "input#nome-parte"},
        "tertiary": {"method": "ocr_anchor", "text": "Nome da Parte"},
        "fallback": {"method": "coordinates", "x": 450, "y": 220},
        "label": "Nome da Parte",
        "control_type": "Edit"
    }
    ui.fill(nome_selector, nome_cliente)

    windows_update_selector = {
        "primary": {"method": "uia_name", "value": "Lembrar mais tarde"},
        "secondary": {"method": "uia_name", "value": "Agora nao"},
        "tertiary": {"method": "ocr_anchor", "text": "Lembrar mais tarde"},
        "fallback": {"method": "coordinates", "x": 780, "y": 620},
        "label": "Dismiss Windows Update popup",
        "control_type": "Button"
    }
    try:
        ui.wait_for(windows_update_selector, timeout=3)
        ui.click(windows_update_selector)
        rpakit.log("Dismissed Windows Update popup")
    except:
        rpakit.log("No Windows Update popup detected")

    cookie_selector = {
        "primary": {"method": "css_selector", "value": "div.cookie-banner button.accept"},
        "secondary": {"method": "uia_automation_id", "value": "btnAceitarCookies"},
        "tertiary": {"method": "ocr_anchor", "text": "Aceitar Cookies"},
        "fallback": {"method": "coordinates", "x": 640, "y": 700},
        "label": "Aceitar Cookies (LGPD)",
        "control_type": "Button"
    }
    try:
        ui.wait_for(cookie_selector, timeout=3)
        ui.click(cookie_selector)
        rpakit.log("Dismissed cookie consent banner")
    except:
        rpakit.log("No cookie banner detected")

    email_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtEmail"},
        "secondary": {"method": "css_selector", "value": "input#email-parte"},
        "tertiary": {"method": "ocr_anchor", "text": "Email"},
        "fallback": {"method": "coordinates", "x": 450, "y": 290},
        "label": "Email",
        "control_type": "Edit"
    }
    ui.fill(email_selector, email_cliente)

    salvar_selector = {
        "primary": {"method": "uia_automation_id", "value": "btnSalvar"},
        "secondary": {"method": "css_selector", "value": "button#salvar-parte"},
        "tertiary": {"method": "ocr_anchor", "text": "Salvar"},
        "fallback": {"method": "coordinates", "x": 450, "y": 380},
        "label": "Salvar",
        "control_type": "Button"
    }
    ui.click(salvar_selector)

    alert_selector = {
        "primary": {"method": "uia_name", "value": "OK"},
        "tertiary": {"method": "ocr_anchor", "text": "OK"},
        "fallback": {"method": "coordinates", "x": 640, "y": 400},
        "label": "Dismiss JS alert",
        "control_type": "Button"
    }
    try:
        ui.wait_for(alert_selector, timeout=5)
        ui.click(alert_selector)
        rpakit.log("Dismissed JavaScript alert")
    except:
        rpakit.log("No JavaScript alert detected")

    success_selector = {
        "primary": {"method": "uia_automation_id", "value": "lblCadastroSucesso"},
        "secondary": {"method": "css_selector", "value": "div.alert-success"},
        "tertiary": {"method": "ocr_anchor", "text": "Cadastro realizado com sucesso"},
        "label": "Success confirmation",
        "control_type": "Text"
    }
    ui.wait_for(success_selector, timeout=10)

    return {}