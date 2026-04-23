from actionshot.rpakit import UI, run_workflow


@run_workflow("simple_login")
def run(username: str, password: str) -> dict:
    """Log into the firm's internal portal with username and password, then wait for the dashboard."""
    ui = UI.attach("Portal Juridico - Google Chrome")

    username_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtUsuario"},
        "secondary": {"method": "css_selector", "value": "input#username"},
        "tertiary": {"method": "ocr_anchor", "text": "Usuario"},
        "fallback": {"method": "coordinates", "x": 640, "y": 320},
        "label": "Usuario",
        "control_type": "Edit"
    }

    password_selector = {
        "primary": {"method": "uia_automation_id", "value": "txtSenha"},
        "secondary": {"method": "css_selector", "value": "input#password"},
        "tertiary": {"method": "ocr_anchor", "text": "Senha"},
        "fallback": {"method": "coordinates", "x": 640, "y": 390},
        "label": "Senha",
        "control_type": "Edit"
    }

    login_button_selector = {
        "primary": {"method": "uia_automation_id", "value": "btnEntrar"},
        "secondary": {"method": "css_selector", "value": "button#login-btn"},
        "tertiary": {"method": "ocr_anchor", "text": "Entrar"},
        "fallback": {"method": "coordinates", "x": 640, "y": 460},
        "label": "Entrar",
        "control_type": "Button"
    }

    dashboard_selector = {
        "primary": {"method": "uia_automation_id", "value": "lblDashboard"},
        "secondary": {"method": "css_selector", "value": "#dashboard-title"},
        "tertiary": {"method": "ocr_anchor", "text": "Painel de Controle"},
        "label": "Dashboard title",
        "control_type": "Text"
    }

    ui.fill(username_selector, username)
    ui.fill(password_selector, password)
    ui.click(login_button_selector)
    ui.wait_for(dashboard_selector)

    return {}