"""
Gerenciador de autenticação da aplicação.

Responsável por:
    - Carregar as credenciais dos usuários a partir de `auth/users.yaml`;
    - Renderizar o formulário de login;
    - Manter a sessão do usuário persistida em cookie do navegador, para que
      um F5 (refresh) na página não exija login novamente;
    - Fornecer o mecanismo de logout.

Baseado na biblioteca `streamlit-authenticator`, que implementa o
armazenamento de sessão via cookie assinado (persistência de sessão real,
sobrevive a reloads da página dentro do prazo de expiração configurado em
`users.yaml -> cookie.expiry_days`).

Segurança da chave do cookie:
    A chave que assina o cookie de sessão (`cookie.key`) é o segredo mais
    sensível da aplicação - com ela, seria possível forjar uma sessão logada.
    Por isso, em produção (ex.: Streamlit Community Cloud), essa chave deve
    vir dos "Secrets" da plataforma (nunca do arquivo versionado no Git). O
    valor definido em `users.yaml` só é usado como fallback para rodar a
    aplicação localmente, em ambiente de desenvolvimento.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

USERS_YAML_PATH = Path(__file__).parent / "users.yaml"


class AuthManager:
    """Encapsula o ciclo de vida de autenticação da aplicação."""

    def __init__(self, credentials_path: Path = USERS_YAML_PATH) -> None:
        self._credentials_path = credentials_path
        self._config = self._load_config()
        self.authenticator = stauth.Authenticate(
            self._config["credentials"],
            self._config["cookie"]["name"],
            self._config["cookie"]["key"],
            self._config["cookie"]["expiry_days"],
            self._config.get("preauthorized", {}).get("emails", []),
        )

    def _load_config(self) -> dict:
        if not self._credentials_path.exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais não encontrado em: {self._credentials_path}"
            )
        with open(self._credentials_path, "r", encoding="utf-8") as arquivo:
            config = yaml.load(arquivo, Loader=SafeLoader)

        chave_local = config.get("cookie", {}).get("key", "")
        config["cookie"]["key"] = self._resolver_cookie_key(chave_local)
        return config

    @staticmethod
    def _resolver_cookie_key(chave_local: str) -> str:
        """
        Retorna a chave de assinatura do cookie priorizando `st.secrets`
        (esperado em produção). Se nenhum secret estiver configurado - caso
        comum em desenvolvimento local sem `.streamlit/secrets.toml` - usa o
        valor do `users.yaml` como fallback, para não travar o `streamlit run`.
        """
        try:
            if "auth" in st.secrets and "cookie_key" in st.secrets["auth"]:
                chave_secreta = st.secrets["auth"]["cookie_key"]
                if chave_secreta:
                    return chave_secreta
        except Exception:
            # st.secrets pode levantar exceção quando não existe nenhum
            # secrets.toml configurado - comportamento normal em dev local.
            pass
        return chave_local

    def render_login_form(self) -> tuple[Optional[str], Optional[bool], Optional[str]]:
        """
        Renderiza o formulário de login e retorna (nome, status, username).

        status:
            True  -> autenticado com sucesso
            False -> usuário/senha incorretos
            None  -> nenhuma tentativa de login ainda
        """
        name, authentication_status, username = self.authenticator.login(
            location="main",
            fields={
                "Form name": "Acesso ao Painel de Qualidade",
                "Username": "Usuário",
                "Password": "Senha",
                "Login": "Entrar",
            },
        )
        return name, authentication_status, username

    def logout(self) -> None:
        """Encerra a sessão do usuário e limpa o cookie de persistência."""
        self.authenticator.logout(button_name="Sair", location="sidebar")

    @staticmethod
    def is_authenticated() -> bool:
        return st.session_state.get("authentication_status") is True

    @staticmethod
    def current_user_name() -> Optional[str]:
        return st.session_state.get("name")

    @staticmethod
    def current_username() -> Optional[str]:
        return st.session_state.get("username")
