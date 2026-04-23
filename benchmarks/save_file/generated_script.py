import rpakit


@rpakit.run_workflow("save_file")
def run(filename: str) -> dict:
    """Save the current document with a specific filename using Ctrl+S dialog."""
    ui = rpakit.UI.attach("")
    
    ui.keyboard_shortcut("ctrl+s")
    
    filename_selector = {
        "primary": {
            "method": "uia_automation_id",
            "value": "FileNameControlHost"
        },
        "secondary": {
            "method": "uia_name",
            "value": "Nome do arquivo:"
        },
        "tertiary": {
            "method": "ocr_anchor",
            "text": "Nome do arquivo"
        },
        "fallback": {
            "method": "coordinates",
            "x": 520,
            "y": 480
        }
    }
    
    ui.wait_for(filename_selector)
    ui.fill(filename_selector, filename)
    
    save_button_selector = {
        "primary": {
            "method": "uia_automation_id",
            "value": "1"
        },
        "secondary": {
            "method": "uia_name",
            "value": "Salvar"
        },
        "tertiary": {
            "method": "ocr_anchor",
            "text": "Salvar"
        },
        "fallback": {
            "method": "coordinates",
            "x": 680,
            "y": 520
        }
    }
    
    ui.wait_for(save_button_selector)
    ui.click(save_button_selector)
    
    return {}


if __name__ == "__main__":
    run(filename="Peticao_Inicial_2024.docx")