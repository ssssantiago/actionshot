import rpakit


def run(
    nome_completo: str,
    cpf: str,
    email: str,
    telefone: str,
    endereco: str,
):
    """Fill the client registration form and submit."""
    app = rpakit.connect(title="Sistema Cadastro - Novo Cliente")

    # -- Selectors --
    nome_sel = rpakit.Selector(automation_id="txtNomeCompleto")
    cpf_sel = rpakit.Selector(automation_id="txtCPF")
    email_sel = rpakit.Selector(automation_id="txtEmail")
    tel_sel = rpakit.Selector(automation_id="txtTelefone")
    end_sel = rpakit.Selector(automation_id="txtEndereco")
    salvar_sel = rpakit.Selector(automation_id="btnSalvar")

    # -- Fill fields --
    rpakit.wait_for(nome_sel, timeout_ms=5000)
    rpakit.fill(nome_sel, nome_completo)

    rpakit.wait_for(cpf_sel, timeout_ms=5000)
    rpakit.fill(cpf_sel, cpf)

    rpakit.wait_for(email_sel, timeout_ms=5000)
    rpakit.fill(email_sel, email)

    rpakit.wait_for(tel_sel, timeout_ms=5000)
    rpakit.fill(tel_sel, telefone)

    rpakit.wait_for(end_sel, timeout_ms=5000)
    rpakit.fill(end_sel, endereco)

    # -- Submit --
    rpakit.wait_for(salvar_sel, timeout_ms=5000)
    rpakit.click(salvar_sel)


if __name__ == "__main__":
    run(
        nome_completo="Maria Silva Santos",
        cpf="123.456.789-00",
        email="maria@exemplo.com.br",
        telefone="+55 11 98765-4321",
        endereco="Rua das Flores, 123",
    )
