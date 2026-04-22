import rpakit


def run(usuario: str, senha: str):
    """Log into the legal portal and wait for the dashboard."""
    app = rpakit.connect(title="Portal Juridico - Login")

    # -- Selectors --
    user_sel = rpakit.Selector(automation_id="txtUsuario")
    pass_sel = rpakit.Selector(automation_id="txtSenha")
    login_sel = rpakit.Selector(automation_id="btnEntrar")
    dashboard_sel = rpakit.Selector(automation_id="pnlDashboard")

    # -- Fill credentials --
    rpakit.wait_for(user_sel, timeout_ms=5000)
    rpakit.fill(user_sel, usuario)

    rpakit.wait_for(pass_sel, timeout_ms=5000)
    rpakit.fill(pass_sel, senha)

    # -- Submit login --
    rpakit.wait_for(login_sel, timeout_ms=5000)
    rpakit.click(login_sel)

    # -- Wait for dashboard to confirm successful login --
    rpakit.wait_for(dashboard_sel, timeout_ms=15000)


if __name__ == "__main__":
    run(usuario="guilherme.santiago", senha="S3cret!Pass")
