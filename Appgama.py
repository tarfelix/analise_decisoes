# -*- coding: utf-8 -*-
# Assistente Jurídico DataJuri v3.6
# App unificado com consulta, análise, cálculo avançado de custas/depósitos e gestão de prazos.
# Correção: Ajustado o cálculo de custas (nunca pela metade) e a lógica de redução do depósito recursal.

import streamlit as st
import pandas as pd
import requests
import base64
import json
import os
import logging
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
import holidays
import re

# ==============================================================================
# CONFIGURAÇÃO GERAL E CONSTANTES
# ==============================================================================

st.set_page_config(
    page_title="Assistente Jurídico DataJuri",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Constantes de Configuração e Valores Legais ---
TOKEN_FILE = 'token.json'
LOG_FILE = 'assistente.log'
UPDATE_FOLDER = 'atualizacoes_robo' # Pasta para salvar os arquivos JSON
TOKEN_EXPIRATION_MINUTES = 50

# ATENÇÃO: Atualize estes valores conforme as portarias do CSJT.
# Valores vigentes a partir de 01/08/2024 (Ato SEJUD.GP Nº 477/2024)
TETOS_DEPOSITO_RECURSAL = {
    "Recurso Ordinário (RO)": 12969.43,
    "Recurso de Revista (RR)": 25938.87,
    "Recurso de Embargos (E-RR/E-ED)": 25938.87,
    "Agravo de Instrumento em Recurso Ordinário (AIRO)": 6484.72, # Metade do teto do RO
    "Agravo de Instrumento em Recurso de Revista (AIRR)": 12969.44, # Metade do teto do RR
    "Outro": 25938.87 # Usa o teto máximo como padrão
}

CLIENTE_OPTIONS = ["Reclamante", "Reclamado", "Outro (Terceiro, MPT, etc.)"]
DECISAO_OPTIONS = [
    "Sentença (Vara do Trabalho)", "Acórdão (TRT)", "Acórdão (TST - Turma)",
    "Acórdão (TST - SDI)", "Decisão Monocrática (Relator TRT/TST)",
    "Despacho Denegatório de Recurso", "Decisão de Embargos de Declaração",
    "Decisão Interlocutória", "Outro"
]
RESULTADO_OPTIONS = ["Favorável", "Desfavorável", "Parcialmente Favorável"]
ED_OPTIONS = ["Cabe ED", "Não cabe ED"]
RECURSO_OPTIONS = [
    "Não Interpor Recurso", "Recurso Ordinário (RO)", "Recurso de Revista (RR)",
    "Agravo de Instrumento em Recurso Ordinário (AIRO)",
    "Agravo de Instrumento em Recurso de Revista (AIRR)", "Agravo de Petição (AP)",
    "Agravo Regimental / Agravo Interno", "Recurso de Embargos (E-RR/E-ED)",
    "Recurso Extraordinário (RE)", "Outro"
]
ISENCAO_OPTIONS = ["Não se aplica", "Justiça Gratuita", "Entidade Filantrópica", "Massa Falida", "Entidade Beneficente", "Outro motivo"]

MAPA_DECISAO_RECURSO = {
    "Sentença (Vara do Trabalho)": 1, "Acórdão (TRT)": 2, "Acórdão (TST - Turma)": 7,
    "Acórdão (TST - SDI)": 8, "Decisão Monocrática (Relator TRT/TST)": 6,
    "Despacho Denegatório de Recurso": 4, "Decisão de Embargos de Declaração": 1,
    "Decisão Interlocutória": 0, "Outro": 0
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=LOG_FILE, filemode='a')

# ==============================================================================
# FUNÇÕES AUXILIARES E DE API
# ==============================================================================

@st.cache_resource
def get_new_token():
    st.info("➡️ Solicitando um novo token de acesso à API...")
    logging.info("Requesting new access token.")
    try:
        client_id = st.secrets["DATAJURI_CLIENT_ID"]
        client_secret = st.secrets["DATAJURI_SECRET_ID"]
        user_email = st.secrets["DATAJURI_USERNAME"]
        user_password = st.secrets["DATAJURI_PASSWORD"]
        api_base_url = st.secrets["DATAJURI_BASE_URL"]
    except KeyError as e:
        st.error(f"⚠️ ATENÇÃO: A credencial '{e.args[0]}' não foi encontrada. Configure os 'Secrets' no Streamlit Cloud.")
        return None

    try:
        auth_string = f"{client_id}:{client_secret}"
        auth_base64 = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        token_url = f"{api_base_url}/oauth/token"
        headers = {'Authorization': f'Basic {auth_base64}', 'Content-Type': 'application/x-www-form-urlencoded'}
        payload = {'grant_type': 'password', 'username': user_email, 'password': user_password}
        response = requests.post(token_url, headers=headers, data=payload)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')
        if not access_token:
            st.error("❌ Erro: 'access_token' não encontrado na resposta da API.")
            return None
        token_info = {'access_token': access_token, 'timestamp': datetime.now().isoformat()}
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_info, f)
        st.success("✅ Novo token obtido e salvo com sucesso!")
        return access_token
    except Exception as e:
        st.error(f"❌ Erro na autenticação: {e}")
        logging.error(f"Authentication error: {e}")
        return None

@st.cache_resource
def get_valid_token():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                token_info = json.load(f)
            token_timestamp = datetime.fromisoformat(token_info['timestamp'])
            if datetime.now() < token_timestamp + timedelta(minutes=TOKEN_EXPIRATION_MINUTES):
                st.sidebar.success("Token de acesso válido. ✅")
                return token_info['access_token']
            else:
                st.sidebar.warning("Token existente expirou. ⚠️")
        except Exception:
            st.sidebar.error("Arquivo de token inválido. ⚠️")
    return get_new_token()

def get_entity_data(api_base_url, api_headers, module_name, fields, criteria_list):
    with st.spinner(f"Buscando dados do módulo '{module_name}'..."):
        try:
            params = [('campos', ",".join(fields)), ('pageSize', 1000)]
            params.extend([('criterio', item) for item in criteria_list])
            entity_url = f"{api_base_url}/v1/entidades/{module_name}"
            logging.info(f"REQUEST: GET {entity_url} with PARAMS: {params}")
            response = requests.get(entity_url, headers=api_headers, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            st.error(f"❌ Erro na busca ({module_name}): {e}")
            logging.error(f"API Search Error ({module_name}): {e}")
            return None

@st.cache_data
def get_holidays(_year):
    return holidays.country_holidays('BR', years=_year)

def add_business_days(from_date, num_days):
    if not isinstance(from_date, date): return None
    br_holidays = get_holidays(from_date.year)
    if num_days != 0:
        end_year = (from_date + timedelta(days=num_days * 2)).year
        if end_year != from_date.year:
             br_holidays.update(get_holidays(end_year))
    current_date, days_added = from_date, 0
    increment = 1 if num_days >= 0 else -1
    while days_added < abs(num_days):
        current_date += timedelta(days=increment)
        if current_date.weekday() < 5 and current_date not in br_holidays:
            days_added += 1
    return current_date

def format_report_from_df(df: pd.DataFrame, tipo_decisao: str):
    """Formata a seção de pedidos do relatório a partir de um DataFrame, incluindo resultados."""
    if df.empty: return "Nenhum pedido encontrado."
    report_lines = []
    df_sorted = df.sort_values(by='nomeObjeto').reset_index(drop=True) if 'nomeObjeto' in df.columns else df.reset_index(drop=True)

    for index, row in df_sorted.iterrows():
        report_lines.append(f"{index + 1}) {row.get('nomeObjeto', 'N/A')}")
        if situacao := row.get('situacao', '').strip():
            report_lines.append(f" - Situação: {situacao}")

        res1 = row.get('resultado_1_instanci', 'N/A')
        res2 = row.get('resultado_2_instanci', 'N/A')
        resSup = row.get('resultado_instancia_', 'N/A')

        tipo_decisao_lower = tipo_decisao.lower() if tipo_decisao else ""
        show_res2 = "acórdão" in tipo_decisao_lower or "monocrática" in tipo_decisao_lower or "denegatório" in tipo_decisao_lower
        show_resSup = "tst" in tipo_decisao_lower or "denegatório" in tipo_decisao_lower

        def is_relevant(res_value):
            return res_value and isinstance(res_value, str) and res_value.lower().strip() not in ["aguardando julgamento", "n/a", "", "não houve recurso"]

        if is_relevant(res1): report_lines.append(f" - Resultado 1ª Instância: {res1}")
        if show_res2 and is_relevant(res2): report_lines.append(f" - Resultado 2ª Instância: {res2}")
        if show_resSup and is_relevant(resSup): report_lines.append(f" - Resultado Instância Superior: {resSup}")
        report_lines.append("")
    return "\n".join(report_lines)

def format_prazos(prazos_list):
    if not prazos_list: return "Nenhum prazo informado."
    lines = []
    for i, p in enumerate(prazos_list, start=1):
        lines.append(f"{i}) {p.get('descricao','N/A')}")
        data_d_str = p['data_d'].strftime('%d/%m/%Y') if isinstance(p.get('data_d'), date) else 'Inválido'
        lines.append(f"   - Data D-: {data_d_str}")
        data_fatal_str = p['data_fatal'].strftime('%d/%m/%Y') if isinstance(p.get('data_fatal'), date) else 'Inválido'
        lines.append(f"   - Data Fatal: {data_fatal_str}")
        if obs := p.get('obs','').strip():
            lines.append(f"   - Observações: {obs}")
        lines.append("")
    return "\n".join(lines)

def generate_final_text(sections):
    final_lines = []
    visible_idx = 1
    for title, content in sections:
        if content and str(content).strip():
            final_lines.append(f"{visible_idx}. {title}:")
            final_lines.append(str(content).strip())
            final_lines.append("")
            visible_idx += 1
    return "\n".join(final_lines)

# ==============================================================================
# INICIALIZAÇÃO DO APP E ESTADO DA SESSÃO
# ==============================================================================

if "page" not in st.session_state: st.session_state.page = "consulta"
if "access_token" not in st.session_state: st.session_state.access_token = None
if "processo_data" not in st.session_state: st.session_state.processo_data = None
if "pedidos_df" not in st.session_state: st.session_state.pedidos_df = None
if "edited_pedidos_df" not in st.session_state: st.session_state.edited_pedidos_df = None
if "prazos" not in st.session_state: st.session_state.prazos = []
if "report_generated" not in st.session_state: st.session_state.report_generated = False

st.session_state.access_token = get_valid_token()
api_base_url = st.secrets.get("DATAJURI_BASE_URL", "") if 'DATAJURI_BASE_URL' in st.secrets else ""

if st.session_state.access_token:
    api_headers = {'Authorization': f'Bearer {st.session_state.access_token}'}
else:
    st.error("Não foi possível obter um token de acesso. A aplicação não pode continuar.")
    st.stop()

# ==============================================================================
# PÁGINA 1: CONSULTA DE PROCESSO
# ==============================================================================
def render_consulta_page():
    st.title("🔎 Assistente Jurídico - Consulta")
    st.markdown("Busque pelo número da pasta do processo para carregar os dados e iniciar a análise.")
    st.session_state.report_generated = False

    numero_processo = st.text_input("Número da Pasta do Processo:", key="numero_processo_input")

    if st.button("Buscar Processo", type="primary"):
        if not numero_processo:
            st.warning("Por favor, insira o número da pasta do processo.")
            return
        
        processo_fields = ["pasta", "cliente.nome", "adverso.nome", "posicaoCliente", "assunto", "status", "faseAtual.vara", "faseAtual.forum"]
        processo_raw_data = get_entity_data(api_base_url, api_headers, "Processo", processo_fields, [f"pasta | igual a | {numero_processo}"])
        if processo_raw_data and processo_raw_data.get('rows'):
            st.session_state.processo_data = processo_raw_data['rows'][0]
            st.success(f"Processo **{st.session_state.processo_data['pasta']}** encontrado!")
        else:
            st.error("Nenhum processo encontrado com este número.")
            st.session_state.processo_data = None
            return
        
        pedidos_fields = ["id", "nomeObjeto", "situacao", "resultado_1_instanci", "resultado_2_instanci", "resultado_instancia_"]
        pedidos_raw_data = get_entity_data(api_base_url, api_headers, "PedidoProcesso", pedidos_fields, [f"processo.pasta | igual a | {numero_processo}"])
        if pedidos_raw_data and pedidos_raw_data.get('rows'):
            df = pd.DataFrame(pedidos_raw_data['rows'])
            st.session_state.pedidos_df = df
            st.session_state.edited_pedidos_df = df.copy()
            st.info(f"Encontrados **{len(df)}** pedidos/objetos para este processo.")
        else:
            st.warning("Nenhum pedido/objeto encontrado para este processo.")
            st.session_state.pedidos_df = pd.DataFrame()
            st.session_state.edited_pedidos_df = pd.DataFrame()

    if st.session_state.processo_data:
        st.divider()
        st.subheader("Dados do Processo Carregado")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Pasta", st.session_state.processo_data.get('pasta', 'N/A'))
        col2.metric("Cliente", st.session_state.processo_data.get('cliente.nome', 'N/A'))
        col3.metric("Adverso", st.session_state.processo_data.get('adverso.nome', 'N/A'))
        col4.metric("Status", st.session_state.processo_data.get('status', 'N/A'))
        
        if st.session_state.pedidos_df is not None:
            st.subheader("Pedidos/Objetos do Processo")
            st.dataframe(st.session_state.pedidos_df, use_container_width=True)
        
        if st.button("✍️ Analisar Decisão deste Processo", use_container_width=True):
            st.session_state.page = "analise"
            st.rerun()

# ==============================================================================
# PÁGINA 2: ANÁLISE DE DECISÃO
# ==============================================================================
def render_analise_page():
    st.title("✍️ Formulário de Análise de Decisão")
    if st.button("⬅️ Voltar para a busca"):
        st.session_state.page = "consulta"
        st.rerun()

    st.info(f"Analisando o processo **{st.session_state.processo_data.get('pasta', '')}**.")
    st.divider()

    st.header("1. Contexto e Análise da Decisão")
    posicao_cliente_api = st.session_state.processo_data.get('posicaoCliente', '').lower()
    cliente_index = 1 if 'reclamado' in posicao_cliente_api else 0
    col_contexto1, col_contexto2, col_contexto3 = st.columns(3)
    with col_contexto1: data_ciencia = st.date_input("Data da Ciência/Publicação:", value=None, key="data_ciencia")
    with col_contexto2: cliente_role = st.selectbox("Cliente é:", options=CLIENTE_OPTIONS, index=cliente_index, key="cliente_role")
    with col_contexto3: tipo_decisao = st.selectbox("Tipo de Decisão Analisada:", options=DECISAO_OPTIONS, index=None, key="tipo_decisao")
    resultado_sentenca = st.selectbox("Resultado Geral para o Cliente:", options=RESULTADO_OPTIONS, index=None, key="resultado_sentenca")
    obs_sentenca = st.text_area("Observações sobre a Decisão (para o email):", help="Detalhe aqui nuances, especialmente se 'Parcialmente Favorável'.")

    st.header("2. Atualização dos Pedidos")
    if st.session_state.edited_pedidos_df is not None and not st.session_state.edited_pedidos_df.empty:
        st.info("Ajuste a 'situação' de cada pedido conforme a decisão. Isso será usado nos relatórios.")
        edited_df = st.data_editor(st.session_state.edited_pedidos_df, use_container_width=True, key="data_editor_pedidos")
    else:
        st.warning("Nenhum pedido foi carregado para este processo.")
        edited_df = pd.DataFrame()

    st.header("3. Próximos Passos (ED / Recurso)")
    ed_status = st.radio("Avaliação sobre Embargos de Declaração (ED):", options=ED_OPTIONS, index=None, key="ed_status", horizontal=True)
    justificativa_ed = ""
    if ed_status == "Cabe ED":
        justificativa_ed = st.text_area("Justificativa para ED (obrigatório):", height=100)

    recurso_selecionado, recurso_outro_especificar, recurso_justificativa = None, "", ""
    if ed_status == "Não cabe ED":
        with st.container(border=True):
            st.subheader("Análise de Recurso Cabível")
            suggested_recurso_index = MAPA_DECISAO_RECURSO.get(tipo_decisao, 0)
            recurso_selecionado = st.selectbox("Recurso a ser considerado:", options=RECURSO_OPTIONS, index=suggested_recurso_index, key="recurso_sel")
            if recurso_selecionado == "Outro":
                recurso_outro_especificar = st.text_input("Especifique qual outro recurso:", key="recurso_outro_txt")
            recurso_justificativa = st.text_area("Justificativa para a escolha do Recurso:", height=100)

    st.header("4. Custas e Depósito Recursal")
    with st.container(border=True):
        col_calc1, col_calc2 = st.columns(2)
        with col_calc1:
            valor_condenacao = st.number_input("Valor da Condenação (R$):", min_value=0.0, step=100.0, format="%.2f")
            deposito_recolhido = st.number_input("Valor de Depósito já Recolhido (R$):", min_value=0.0, step=100.0, format="%.2f")
        with col_calc2:
            percentual_custas = st.number_input("Percentual de Custas na Decisão (%):", min_value=0.0, max_value=100.0, value=2.0, step=0.5, format="%.1f")
        
        st.subheader("Depósito Recursal")
        isencao_deposito = st.selectbox("Isenção de Depósito Recursal:", options=ISENCAO_OPTIONS, key="isencao_deposito")
        outro_motivo_deposito = ""
        if isencao_deposito == "Outro motivo":
            outro_motivo_deposito = st.text_input("Especifique o outro motivo da isenção do depósito:", key="outro_motivo_deposito_input")
        
        pagamento_metade_deposito = st.checkbox("Redução de 50% no Depósito (MEI, EPP, etc.)", help="Marque se aplicável para o depósito recursal.")

        deposito_a_recolher = 0.0
        is_entidade_beneficente = (isencao_deposito == "Entidade Beneficente")
        
        if isencao_deposito == "Não se aplica" or is_entidade_beneficente:
            if recurso_selecionado and recurso_selecionado != "Não Interpor Recurso":
                teto_recurso = TETOS_DEPOSITO_RECURSAL.get(recurso_selecionado, max(TETOS_DEPOSITO_RECURSAL.values()))
                valor_base_deposito = min(teto_recurso, valor_condenacao) if valor_condenacao > 0 else teto_recurso
                deposito_a_recolher = valor_base_deposito - deposito_recolhido
                if is_entidade_beneficente or pagamento_metade_deposito:
                    deposito_a_recolher /= 2
                deposito_a_recolher = max(0, deposito_a_recolher)
                st.metric("Valor do Depósito a Recolher:", f"R$ {deposito_a_recolher:,.2f}")
        else:
            motivo_deposito_display = isencao_deposito if isencao_deposito != 'Outro motivo' else outro_motivo_deposito
            st.info(f"Depósito isento. Motivo: {motivo_deposito_display}")

        st.subheader("Custas Processuais")
        isencao_custas = st.selectbox("Isenção de Custas:", options=ISENCAO_OPTIONS, key="isencao_custas")
        outro_motivo_custas = ""
        if isencao_custas == "Outro motivo":
            outro_motivo_custas = st.text_input("Especifique o outro motivo da isenção das custas:", key="outro_motivo_custas_input")

        custas_a_recolher = 0.0
        if isencao_custas == "Não se aplica":
            custas_a_recolher = valor_condenacao * (percentual_custas / 100)
            st.metric("Valor das Custas a Recolher:", f"R$ {custas_a_recolher:,.2f}")
        else:
            motivo_custas_display = isencao_custas if isencao_custas != 'Outro motivo' else outro_motivo_custas
            st.info(f"Custas isentas. Motivo: {motivo_custas_display}")

    st.header("5. Prazos")
    with st.container(border=True):
        suggested_prazo = None
        if data_ciencia:
            data_base = data_ciencia
            prazo_dias = 8
            if ed_status == "Cabe ED":
                prazo_fatal = add_business_days(data_base, 5)
                if prazo_fatal:
                    suggested_prazo = {"descricao": "Prazo para Oposição de Embargos de Declaração", "data_fatal": prazo_fatal, "data_d": add_business_days(prazo_fatal, -2), "obs": ""}
            elif ed_status == "Não cabe ED" and recurso_selecionado:
                if "Extraordinário" in recurso_selecionado: prazo_dias = 15
                prazo_fatal = add_business_days(data_base, prazo_dias)
                if prazo_fatal:
                    if recurso_selecionado == "Não Interpor Recurso":
                        descricao = "Verificar interposição de recurso pela parte contrária"
                        data_d = prazo_fatal
                    else:
                        recurso_final = recurso_selecionado if recurso_selecionado != "Outro" else recurso_outro_especificar
                        descricao = f"Prazo para Interposição de {recurso_final}"
                        data_d = add_business_days(prazo_fatal, -2)
                    suggested_prazo = {"descricao": descricao, "data_fatal": prazo_fatal, "data_d": data_d, "obs": ""}
        
        if suggested_prazo:
            st.info(f"**Sugestão de Prazo:** {suggested_prazo['descricao']} (Fatal: {suggested_prazo['data_fatal'].strftime('%d/%m/%Y')})")
            if st.button("Adicionar Prazo Sugerido"):
                st.session_state.prazos.append(suggested_prazo)
                st.rerun()

        with st.expander("Adicionar Prazo Manualmente"):
            with st.form("form_prazos_manual", clear_on_submit=True):
                descricao_manual = st.text_input("Descrição do Prazo:")
                col_d1, col_d2 = st.columns(2)
                with col_d1: data_d_manual = st.date_input("Data D- (interna):", value=date.today())
                with col_d2: data_fatal_manual = st.date_input("Data Fatal (legal):", value=date.today())
                obs_manual = st.text_input("Observações do Prazo:")
                if st.form_submit_button("Adicionar Prazo Manual"):
                    if not descricao_manual.strip():
                        st.error("A descrição do prazo é obrigatória!")
                    else:
                        st.session_state.prazos.append({"descricao": descricao_manual, "data_d": data_d_manual, "data_fatal": data_fatal_manual, "obs": obs_manual})
                        st.rerun()

        if st.session_state.prazos:
            st.write("---")
            st.write("**Prazos Adicionados:**")
            indices_para_remover = []
            for i, prazo in enumerate(st.session_state.prazos):
                col1, col2 = st.columns([0.95, 0.05])
                with col1:
                    st.markdown(f"**{i+1}. {prazo.get('descricao', 'N/A')}** | D-: `{prazo.get('data_d').strftime('%d/%m/%Y')}` | Fatal: `{prazo.get('data_fatal').strftime('%d/%m/%Y')}`")
                    if obs := prazo.get('obs'): st.caption(f"Obs: {obs}")
                with col2:
                    if st.button("❌", key=f"del_{i}", help="Remover este prazo"):
                        indices_para_remover.append(i)
            if indices_para_remover:
                for index in sorted(indices_para_remover, reverse=True):
                    del st.session_state.prazos[index]
                st.rerun()

    st.header("6. Geração de Documentos")
    obs_finais = st.text_area("Observações Gerais Internas (opcional):", height=100)
    st.divider()

    if st.button("✔️ Gerar Relatórios e Arquivo de Atualização", type="primary", use_container_width=True):
        st.session_state.report_generated = True
        st.session_state.edited_pedidos_df = edited_df
        st.rerun()

    if st.session_state.report_generated:
        st.subheader("🤖 Arquivo de Atualização para o Robô")
        changes = st.session_state.pedidos_df.compare(st.session_state.edited_pedidos_df)
        if changes.empty:
            st.info("Nenhuma alteração nos pedidos detectada. Nenhum arquivo de atualização gerado.")
        else:
            update_tasks = []
            changed_cols = changes.columns.get_level_values(0).unique()
            for idx in changes.index:
                task = {'id': int(st.session_state.edited_pedidos_df.loc[idx, 'id'])}
                for col_name in changed_cols:
                    if not pd.isna(changes.loc[idx, (col_name, 'self')]):
                        task[col_name] = st.session_state.edited_pedidos_df.loc[idx, col_name]
                if len(task) > 1:
                    update_tasks.append(task)
            
            if update_tasks:
                os.makedirs(UPDATE_FOLDER, exist_ok=True)
                pasta_sanitizada = re.sub(r'[\\/*?:"<>|]',"", st.session_state.processo_data.get('pasta', 'unknown'))
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_name = f"update_{pasta_sanitizada}_{timestamp}.json"
                file_path = os.path.join(UPDATE_FOLDER, file_name)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(update_tasks, f, indent=2, ensure_ascii=False)
                st.success(f"Arquivo de atualização '{file_name}' salvo na pasta '{UPDATE_FOLDER}' no servidor para processamento pelo administrador.")
            else:
                 st.info("Nenhuma alteração nos pedidos detectada. Nenhum arquivo de atualização gerado.")

        st.subheader("📄 Relatório Interno Gerado")
        sections_data = []
        contexto_str = (f"- Processo: {st.session_state.processo_data.get('pasta', 'N/A')}\n"
                        f"- Cliente: {st.session_state.processo_data.get('cliente.nome', 'N/A')} ({cliente_role})\n"
                        f"- Adverso: {st.session_state.processo_data.get('adverso.nome', 'N/A')}\n"
                        f"- Tipo de Decisão Analisada: {tipo_decisao}\n"
                        f"- Data da Ciência: {data_ciencia.strftime('%d/%m/%Y') if data_ciencia else 'N/A'}")
        sections_data.append(("Contexto do Processo", contexto_str))
        
        resultado_str = (f"- Avaliação para o Cliente: {resultado_sentenca}\n"
                         f"- Observações: {obs_sentenca.strip() or 'Nenhuma'}")
        sections_data.append(("Resultado Geral da Decisão", resultado_str))
        
        pedidos_report_text = format_report_from_df(st.session_state.edited_pedidos_df, tipo_decisao)
        sections_data.append(("Tabela de Pedidos Processada", pedidos_report_text))
        
        ed_str = (f"- Avaliação: {ed_status}\n"
                  f"- Justificativa: {justificativa_ed.strip() or 'N/A'}")
        sections_data.append(("Embargos de Declaração (ED)", ed_str))

        if ed_status == "Não cabe ED":
            recurso_final = recurso_selecionado if recurso_selecionado != "Outro" else recurso_outro_especificar.strip()
            recurso_str = (f"- Decisão/Recomendação: {recurso_final}\n"
                           f"- Justificativa: {recurso_justificativa.strip()}")
            sections_data.append(("Recurso", recurso_str))
            
            motivo_deposito = isencao_deposito if isencao_deposito != 'Outro motivo' else outro_motivo_deposito
            motivo_custas = isencao_custas if isencao_custas != 'Outro motivo' else outro_motivo_custas
            custas_deposito_str = (f"- Depósito a Recolher: R$ {deposito_a_recolher:,.2f} (Isenção: {motivo_deposito})\n"
                                   f"- Custas a Recolher: R$ {custas_a_recolher:,.2f} (Isenção: {motivo_custas})")
            sections_data.append(("Custas e Depósito Recursal", custas_deposito_str))

        sections_data.append(("Prazos Adicionados", format_prazos(st.session_state.prazos)))
        sections_data.append(("Observações Finais Internas", obs_finais.strip() or "Nenhuma"))
        
        final_text = generate_final_text(sections_data)
        st.text_area("Copie o texto abaixo para seu workflow:", final_text, height=300)

        st.subheader("📧 Email para o Cliente")
        advogado_responsavel = st.text_input("Advogado(a) Responsável pela Comunicação:")

        if advogado_responsavel:
            mapa_assunto = {"Sentença (Vara do Trabalho)": "SENTENÇA", "Decisão de Embargos de Declaração": "SENTENÇA ED", "Acórdão (TRT)": "ACÓRDÃO TRT"}
            tipo_decisao_assunto = mapa_assunto.get(tipo_decisao, tipo_decisao.upper())
            email_subject = f"TRABALHISTA: {tipo_decisao_assunto} - {st.session_state.processo_data.get('adverso.nome', '')} X {st.session_state.processo_data.get('cliente.nome', '')}"
            local_processo = st.session_state.processo_data.get('faseAtual.vara') or st.session_state.processo_data.get('faseAtual.forum') or "Local não informado"

            pedidos_por_situacao = {}
            if not st.session_state.edited_pedidos_df.empty:
                pedidos_por_situacao = st.session_state.edited_pedidos_df.groupby('situacao')['nomeObjeto'].apply(list).to_dict()

            categorias_padrao = {
                'Procedentes': 'Procedência',
                'Parcialmente Procedentes': 'Parcialmente procedente',
                'Improcedentes': 'Improcedência'
            }
            
            resumo_pedidos_email = ""
            for nome_cat, chave_cat in categorias_padrao.items():
                pedidos = pedidos_por_situacao.get(chave_cat)
                if pedidos:
                    resumo_pedidos_email += f"{nome_cat}:\n" + "\n".join([f"- {p}" for p in pedidos]) + "\n\n"

            outras_ocorrencias = []
            for situacao, pedidos in pedidos_por_situacao.items():
                if situacao not in categorias_padrao.values():
                    for pedido in pedidos:
                        outras_ocorrencias.append(f"- {pedido} ({situacao})")
            
            if outras_ocorrencias:
                resumo_pedidos_email += "Outras Ocorrências:\n" + "\n".join(outras_ocorrencias) + "\n"

            motivo_deposito_final = isencao_deposito if isencao_deposito != 'Outro motivo' else outro_motivo_deposito
            motivo_custas_final = isencao_custas if isencao_custas != 'Outro motivo' else outro_motivo_custas

            info_deposito_str = ""
            if motivo_deposito_final != "Não se aplica":
                info_deposito_str = f"Quanto ao depósito recursal, foi deferida a isenção (motivo: {motivo_deposito_final})."
            elif deposito_a_recolher > 0:
                info_deposito_str = f"Para a interposição do recurso, será necessário o recolhimento de R$ {deposito_a_recolher:,.2f} a título de depósito recursal."
            else:
                 info_deposito_str = "Não há valor a ser recolhido a título de depósito recursal."

            info_custas_str = ""
            if motivo_custas_final != "Não se aplica":
                info_custas_str = f"Quanto às custas processuais, foi deferida a isenção (motivo: {motivo_custas_final})."
            elif custas_a_recolher > 0:
                info_custas_str = f"Será necessário, também, o pagamento de R$ {custas_a_recolher:,.2f} de custas processuais."
            else:
                info_custas_str = "Não há valor a ser recolhido a título de custas processuais."
            
            info_custas = f"{info_deposito_str} {info_custas_str}"

            recomendacao_final = ""
            if ed_status == "Não cabe ED" and recurso_selecionado != "Não Interpor Recurso":
                recurso_final_nome = recurso_selecionado if recurso_selecionado != "Outro" else recurso_outro_especificar
                recomendacao_final = f"Recomendamos a interposição de {recurso_final_nome} para {recurso_justificativa.lower() if recurso_justificativa else 'reverter a decisão desfavorável.'}"
            elif obs_sentenca:
                 recomendacao_final = obs_sentenca
            
            email_body = f"""Prezados, bom dia!

Local: {local_processo}
Processo nº. {st.session_state.processo_data.get('pasta', 'N/A')}
Cliente: {st.session_state.processo_data.get('cliente.nome', 'N/A')}
Adverso: {st.session_state.processo_data.get('adverso.nome', 'N/A')}

Pelo presente, informamos que a {tipo_decisao.lower() if tipo_decisao else 'decisão'} referente ao processo acima foi publicada.

Segue abaixo um resumo dos pedidos, com informações atualizadas sobre cada um deles:

{resumo_pedidos_email.strip()}

{recomendacao_final}
{info_custas}

Diante do exposto, para que possamos elaborar o recurso, solicitamos retorno quanto ao interesse em 48 horas.
Qualquer esclarecimento, favor entrar em contato com o escritório.

Atenciosamente,

{advogado_responsavel}
"""
            st.text_input("Assunto do Email:", value=email_subject)
            st.text_area("Corpo do Email:", value=email_body, height=400)
            st.success("Rascunho do email gerado com sucesso!")

# ==============================================================================
# ROTEADOR PRINCIPAL DO APP
# ==============================================================================
if st.session_state.page == "consulta":
    render_consulta_page()
elif st.session_state.page == "analise":
    if st.session_state.processo_data:
        render_analise_page()
    else:
        st.warning("Nenhum processo carregado. Redirecionando para a página de consulta.")
        st.session_state.page = "consulta"
        st.rerun()
