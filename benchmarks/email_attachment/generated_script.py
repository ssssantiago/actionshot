import rpakit


@rpakit.run_workflow("email_attachment")
def email_attachment(destinatario: str, assunto: str, anexo_path: str) -> dict:
    """Open Outlook, compose a new email with recipient, subject, attach a PDF file, and send."""
    ui = rpakit.UI.attach("Microsoft Outlook")
    
    # Click "New Email" button
    novo_email_sel = {
        "primary": {"method": "uia_automation_id", "value": "btnNovoEmail"},
        "secondary": {"method": "uia_name", "value": "Novo Email"},
        "tertiary": {"method": "ocr_anchor", "text": "Novo Email"},
        "fallback": {"method": "coordinates", "x": 75, "y": 48},
        "label": "Novo Email",
        "control_type": "Button"
    }
    ui.click(novo_email_sel)
    
    # Wait for "To" field to appear
    para_sel = {
        "primary": {"method": "uia_automation_id", "value": "txtPara"},
        "label": "Para field",
        "control_type": "Edit"
    }
    ui.wait_for(para_sel)
    
    # Fill "To" field with recipient
    para_fill_sel = {
        "primary": {"method": "uia_automation_id", "value": "txtPara"},
        "secondary": {"method": "uia_name", "value": "Para"},
        "tertiary": {"method": "ocr_anchor", "text": "Para..."},
        "fallback": {"method": "coordinates", "x": 450, "y": 120},
        "label": "Para",
        "control_type": "Edit"
    }
    ui.fill(para_fill_sel, destinatario)
    
    # Fill "Subject" field
    assunto_sel = {
        "primary": {"method": "uia_automation_id", "value": "txtAssunto"},
        "secondary": {"method": "uia_name", "value": "Assunto"},
        "tertiary": {"method": "ocr_anchor", "text": "Assunto"},
        "fallback": {"method": "coordinates", "x": 450, "y": 160},
        "label": "Assunto",
        "control_type": "Edit"
    }
    ui.fill(assunto_sel, assunto)
    
    # Click "Attach File" button
    anexar_sel = {
        "primary": {"method": "uia_automation_id", "value": "btnAnexarArquivo"},
        "secondary": {"method": "uia_name", "value": "Anexar Arquivo"},
        "tertiary": {"method": "ocr_anchor", "text": "Anexar Arquivo"},
        "fallback": {"method": "coordinates", "x": 120, "y": 85},
        "label": "Anexar Arquivo",
        "control_type": "Button"
    }
    ui.click(anexar_sel)
    
    # Fill file path in file picker dialog
    file_name_sel = {
        "primary": {"method": "uia_automation_id", "value": "FileNameControlHost"},
        "secondary": {"method": "uia_name", "value": "Nome do arquivo:"},
        "tertiary": {"method": "ocr_anchor", "text": "Nome do arquivo"},
        "fallback": {"method": "coordinates", "x": 520, "y": 480},
        "label": "Nome do arquivo",
        "control_type": "Edit"
    }
    ui.fill(file_name_sel, anexo_path)
    
    # Click "Send" button
    enviar_sel = {
        "primary": {"method": "uia_automation_id", "value": "btnEnviar"},
        "secondary": {"method": "uia_name", "value": "Enviar"},
        "tertiary": {"method": "ocr_anchor", "text": "Enviar"},
        "fallback": {"method": "coordinates", "x": 75, "y": 48},
        "label": "Enviar",
        "control_type": "Button"
    }
    ui.click(enviar_sel)
    
    return {}