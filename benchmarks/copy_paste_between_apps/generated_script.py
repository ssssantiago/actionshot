import rpakit
from rpakit import UI, run_workflow, log


@run_workflow("copy_paste_between_apps")
def run(source_text: str) -> dict:
    """Copy text from Notepad and paste into Word document."""
    
    log("Attaching to Notepad")
    notepad_ui = UI.attach("Documento.txt - Bloco de Notas")
    
    log("Selecting all text in Notepad")
    notepad_ui.keyboard_shortcut("ctrl+a")
    
    log("Copying selected text")
    notepad_ui.keyboard_shortcut("ctrl+c")
    
    log("Attaching to Word")
    word_ui = UI.attach("Peticao Inicial.docx - Microsoft Word")
    
    log("Pasting text into Word")
    word_ui.keyboard_shortcut("ctrl+v")
    
    return {}


if __name__ == "__main__":
    result = run(source_text="Contrato de Prestacao de Servicos")