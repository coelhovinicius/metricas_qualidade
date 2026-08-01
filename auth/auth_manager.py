"""
Gerenciador de autenticação da aplicação.

Responsável por:
    - Carregar as credenciais dos usuários (ver "De onde vêm as credenciais"
      abaixo);
    - Renderizar o formulário de login;
    - Manter a sessão do usuário persistida em cookie do navegador, para que
      um F5 (refresh) na página não exija login novamente;
    - Fornecer o mecanismo de logout.

Baseado na biblioteca `streamlit-authenticator`, que implementa o
armazenamento de sessão via cookie assinado (persistência de sessão real,
sobrevive a reloads da página dentro do prazo de expiração configurado em
`cookie.expiry_days`).

De onde vêm as credenciais (usuários, hash de senha, config do cookie):
    Prioridade 1 - Secrets do Streamlit (`st.secrets["auth"]`), com a seção
    inteira (`credentials`, `cookie`, `preauthorized`) dentro de `[auth]` -
    é o caminho usado em produção (Streamlit Community Cloud). Assim, o
    banco de usuários (incluindo hash de senha de cada um) nunca precisa
    estar no repositório Git - só nos Secrets, que o Streamlit trata como
    dado sensível e não versiona.

    Prioridade 2 (fallback) - arquivo local `auth/users.yaml`, usado só
    quando os Secrets não têm essa seção completa - pensado para rodar a
    aplicação na sua própria máquina sem precisar configurar Secrets antes.
    Esse arquivo NÃO deve ser commitado no Git (ver `.gitignore`) - motivo:
    ele guarda hash de senha de cada usuário, e um repositório público (ou
    qualquer pessoa com acesso ao repo, mesmo privado) não deveria ter
    acesso a isso.

    Ver `scripts/migrar_credenciais_para_secrets.py` para converter um
    `auth/users.yaml` já existente no bloco TOML equivalente, pronto para
    colar nos Secrets (local e/ou do Streamlit Community Cloud).

Segurança da chave do cookie:
    A chave que assina o cookie de sessão (`cookie.key`) é o segredo mais
    sensível da aplicação - com ela, seria possível forjar uma sessão logada.
    Quando as credenciais inteiras já vêm dos Secrets (prioridade 1 acima),
    essa chave também vem de lá, dentro da mesma estrutura. Como reforço -
    inclusive para quem ainda está só no fallback do arquivo local -, existe
    também um override específico: se `st.secrets["auth"]["cookie_key"]`
    (chave solta, fora de `credentials`) estiver definido, ele sempre vence
    o que estiver em `cookie.key`, venha de onde vier. Nunca é obrigatório
    ter as duas coisas - é só uma forma a mais de garantir que essa chave
    específica nunca dependa só do arquivo local.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

import streamlit as st
import streamlit.components.v1 as components
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

USERS_YAML_PATH = Path(__file__).parent / "users.yaml"


def _secrets_para_dict(valor: Any) -> Any:
    """
    Converte recursivamente um valor vindo de `st.secrets` num equivalente só
    com tipos nativos do Python (dict/list/str/...).

    `st.secrets` não devolve um `dict` "de verdade" - devolve um tipo próprio
    do Streamlit (parecido com dict, navegável com `["chave"]`/`.items()`,
    mas não é uma instância de `dict`). A `streamlit-authenticator` faz
    operações internas (cópia, iteração, serialização) que esperam um `dict`
    de verdade em todos os níveis - passar o objeto do Streamlit sem
    converter pode falhar de forma sutil dependendo da versão da lib. Por
    isso todo valor vindo de `st.secrets` passa por aqui antes de ser usado.
    """
    if hasattr(valor, "items"):  # dict comum OU o tipo especial de st.secrets
        return {chave: _secrets_para_dict(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_secrets_para_dict(item) for item in valor]
    return valor


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
        config = self._carregar_de_secrets()
        if config is None:
            config = self._carregar_de_arquivo_local()

        chave_local = config.get("cookie", {}).get("key", "")
        config["cookie"]["key"] = self._resolver_cookie_key(chave_local)
        return config

    @staticmethod
    def _carregar_de_secrets() -> Optional[dict]:
        """
        Tenta montar a config inteira (credentials/cookie/preauthorized) a
        partir de `st.secrets["auth"]` - fonte usada em produção, ver
        docstring do módulo. Devolve `None` (sem levantar erro) quando essa
        seção não existe ou não tem `credentials` dentro dela, para o
        chamador cair no fallback do arquivo local em vez de travar.
        """
        try:
            secao_auth = st.secrets.get("auth")
        except Exception:
            # st.secrets pode levantar exceção quando não existe nenhum
            # secrets.toml configurado - comportamento normal em dev local
            # sem esse arquivo, mesmo tratamento já usado em `_resolver_cookie_key`.
            return None
        if not secao_auth or "credentials" not in secao_auth:
            return None
        return _secrets_para_dict(secao_auth)

    def _carregar_de_arquivo_local(self) -> dict:
        """
        Fallback de desenvolvimento: lê `auth/users.yaml` do disco. Só é
        usado quando os Secrets não têm a seção `[auth].credentials`
        completa - em produção, com os Secrets migrados, este método nunca
        chega a ser chamado.
        """
        if not self._credentials_path.exists():
            raise FileNotFoundError(
                "Nenhuma credencial encontrada: configure [auth].credentials nos Secrets "
                f"do Streamlit, ou crie o arquivo local de desenvolvimento em: "
                f"{self._credentials_path}"
            )
        with open(self._credentials_path, "r", encoding="utf-8") as arquivo:
            return yaml.load(arquivo, Loader=SafeLoader)

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
        self._forcar_logout_ao_fechar_navegador()

        name, authentication_status, username = self.authenticator.login(
            location="main",
            fields={
                "Form name": "Acesso ao Painel de Qualidade",
                "Username": "Usuário",
                "Password": "Senha",
                "Login": "Entrar",
            },
            # Limpa os campos do formulário (Usuário E Senha) depois de cada
            # tentativa de "Entrar", tenha dado certo ou não - senão a senha
            # digitada continua visível/preenchida na caixa de texto depois
            # do envio, o que não é uma boa prática de segurança (alguém
            # pode ver por cima do ombro, ou o navegador pode oferecer pra
            # salvar/autocompletar o valor que ficou no campo).
            clear_on_submit=True,
        )

        if authentication_status is True:
            # A reautenticação silenciosa via cookie (sem o usuário ter
            # clicado em "Entrar" agora - é o caso de um F5 ou de reabrir a
            # aba) depende de um componente assíncrono (o gerenciador de
            # cookies da lib) confirmar o valor do cookie de volta pro
            # Python. Isso normalmente exige uma rodada extra de rerun, que
            # some sozinha quando o LOGIN é feito pelo formulário (o próprio
            # componente que GRAVA o cookie de sessão dispara essa rodada
            # extra) - mas não existe rodada extra equivalente quando é só
            # LEITURA do cookie. Resultado: a tela ficava "presa" mostrando o
            # formulário de login já sem os campos de Usuário/Senha (porque o
            # código internamente já sabia que estava autenticado e pulou o
            # desenho deles), até o usuário clicar em qualquer coisa - foi
            # exatamente o que você viu no vídeo: o botão "Solicitar acesso"
            # aparecia sozinho, e clicar nele (ou em qualquer botão) "acordava"
            # a tela e mostrava o app já logado.
            #
            # Forçar um rerun aqui, assim que percebemos que a autenticação
            # deu certo (seja pelo cookie, seja pelo formulário agora),
            # resolve isso: a página recarrega uma vez sozinha e cai direto
            # no app autenticado corretamente, sem precisar de nenhum clique
            # do usuário.
            #
            # A pequena pausa antes é necessária por outro motivo: quando é
            # um login pelo FORMULÁRIO (não pelo cookie), a lib GRAVA um
            # cookie novo nesse exato momento - e essa gravação também passa
            # por um componente assíncrono (mesmo mecanismo da leitura, só
            # que escrevendo). Sem essa pausa, o rerun forçado aqui corria na
            # frente dessa gravação e cancelava ela pela metade - o login
            # funcionava, mas o cookie nunca chegava a ser salvo de verdade,
            # e o próximo F5 pedia login de novo (o contrário do que
            # queremos). 400ms é uma folga confortável mesmo em conexões mais
            # lentas que o localhost onde testei; testei com e sem essa
            # pausa e sem ela o cookie realmente não era salvo.
            time.sleep(0.4)
            st.rerun()

        return name, authentication_status, username

    def _forcar_logout_ao_fechar_navegador(self) -> None:
        """
        Faz a sessão "esquecer" o cookie de login sempre que a aba/janela do
        navegador é fechada de verdade - na prática, o mesmo efeito de clicar
        em "Sair" automaticamente nesse caso.

        Por que isso é necessário:
            O cookie de sessão do streamlit-authenticator (`cookie.expiry_days`
            em `users.yaml`) é um cookie comum, salvo em disco pelo navegador -
            por isso ele sobrevive a fechar e reabrir a janela, não só a um F5
            (aliás, é assim que o F5 continua funcionando sem pedir login de
            novo, de propósito). O problema é que, num navegador normal (não
            anônimo), fechar a aba pelo X e abrir de novo reaproveita esse
            mesmo cookie - e a lib de autenticação autentica a sessão em
            silêncio, sem passar pela tela de login, mesmo já tendo "fechado o
            app". Isso é o que você viu no vídeo: só clicando em "Sair" na
            barra lateral é que os campos de Usuário/Senha voltavam a
            aparecer.

            O navegador, por padrão, não avisa o código Python quando a aba é
            fechada de verdade (diferente de um F5) - não existe esse evento
            chegando ao servidor. A forma prática de diferenciar os dois casos
            é usando um "marcador" guardado em `sessionStorage`: essa é uma
            funcionalidade nativa do navegador que sobrevive a F5/
            recarregamentos da MESMA aba/janela, mas nasce vazia de novo
            sempre que uma aba/janela NOVA é aberta - mesmo que seja dentro do
            mesmo processo/perfil do navegador (por exemplo, se o navegador
            ficou rodando escondido em segundo plano depois de você fechar a
            última janela - comportamento padrão em várias instalações de
            Edge/Chrome). É exatamente a distinção que precisamos: cookie
            normal não serve pra isso porque é compartilhado por todo o
            processo do navegador, não por aba/janela.

            (Cheguei a usar um cookie de sessão como marcador numa versão
            anterior, mas voltei para `sessionStorage` depois de analisar o
            vídeo em que você mostrou o problema acontecendo mesmo assim: em
            algumas configurações do Edge/Chrome - por exemplo, "Continuar
            executando extensões e aplicativos em segundo plano quando o
            navegador é fechado", que vem ligada por padrão em muitas
            instalações - fechar a última janela pelo X ou Ctrl+W NÃO encerra
            de verdade o processo do navegador, ele continua rodando escondido.
            Nesse caso, uma janela NOVA aberta depois reaproveita o MESMO
            processo, e cookies são compartilhados por todo o processo/perfil -
            inclusive cookies de sessão, que só desaparecem quando o processo
            termina de verdade. Resultado: o cookie marcador continuava lá
            mesmo depois de "fechar e abrir de novo", então a sessão nunca era
            encerrada - foi exatamente o que apareceu no seu vídeo.

            `sessionStorage`, por outro lado, é isolado por ABA/JANELA (o termo
            técnico é "contexto de navegação de nível superior"), não pelo
            processo do navegador como um todo - uma janela nova sempre começa
            com `sessionStorage` vazio, mesmo que seja o mesmo processo/perfil
            ainda rodando por baixo. É exatamente a distinção que precisamos
            aqui, e é por isso que voltei a usar `sessionStorage` em vez de
            outro cookie.)

        Como funciona:
            Este método injeta um pequeno JavaScript, executado ANTES do
            formulário de login. Se não existe o marcador em `sessionStorage`
            (ou seja, esta aba/janela acabou de ser aberta do zero - mesmo que
            o processo do navegador continuasse rodando escondido por baixo),
            ele cria o marcador e, só então, apaga o cookie de sessão de LOGIN
            e recarrega a página uma vez - o usuário cai na tela de login
            normalmente, como se tivesse clicado em "Sair". Se o marcador já
            existe (o usuário só deu F5 na mesma aba, ou navegou dentro do
            próprio app), não faz nada, e a sessão persistida continua valendo
            normalmente.

        Limitação conhecida:
            Isso depende de `sessionStorage`, comportamento padrão de
            navegador - não existe uma API oficial de "a janela foi fechada"
            que o servidor consiga escutar. É a abordagem mais confiável que
            existe hoje para esse cenário (testada e confirmada em Chromium,
            inclusive no caso de o navegador continuar rodando em segundo
            plano depois de fechar a última janela), mas, em teoria, algum
            navegador com uma função de "restaurar sessão" agressiva o
            suficiente pra também restaurar `sessionStorage` de uma aba
            fechada (não é o comportamento padrão do Chrome/Edge, mas
            navegadores variam) poderia escapar dessa proteção - isso seria
            uma configuração/comportamento do navegador, não do app. Se
            `sessionStorage` estiver bloqueado (raro - alguma extensão ou
            política bem restritiva), o código abaixo detecta isso e não faz
            nada, pra não arriscar travar a aplicação em loop de reload.
        """
        nome_cookie = self._config["cookie"]["name"]
        components.html(
            f"""
            <script>
            (function() {{
                const NOME_COOKIE = {nome_cookie!r};
                const NOME_MARCADOR = "refu_sessao_ativa_marcador";

                function lerCookie(nome) {{
                    return document.cookie.split("; ").some(function(c) {{
                        return c.indexOf(nome + "=") === 0;
                    }});
                }}

                let marcadorJaExistia;
                try {{
                    marcadorJaExistia = sessionStorage.getItem(NOME_MARCADOR) === "1";
                }} catch (e) {{
                    // sessionStorage bloqueado (extensão/política) - assume que
                    // o marcador "existe" pra não arriscar um loop de reload
                    // infinito; nesse cenário raro, simplesmente não conseguimos
                    // detectar fechamento real de navegador.
                    marcadorJaExistia = true;
                }}

                if (!marcadorJaExistia) {{
                    try {{
                        sessionStorage.setItem(NOME_MARCADOR, "1");
                    }} catch (e) {{
                        // mesmo raciocínio do catch acima - ignora.
                    }}

                    if (lerCookie(NOME_COOKIE)) {{
                        document.cookie = NOME_COOKIE + "=; Max-Age=0; path=/;";
                        // `st.components.v1.html` roda este script dentro de um
                        // iframe - "window" aqui é a janela do IFRAME, não a da
                        // página do app. Recarregar com "window.location.reload()"
                        // só recarregaria esse iframe invisível, sem efeito
                        // nenhum na tela real. "window.top" é a janela do
                        // navegador de verdade (o topo de toda a árvore de
                        // frames), que é o que precisa recarregar.
                        window.top.location.reload();
                    }}
                }}
            }})();
            </script>
            """,
            height=0,
        )

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
