# -*- coding: utf-8 -*-
# Versão 3.0 - Refatorada para Eficiência e UX
# Implementa: Parser dinâmico, auto-verificação, fluxo de prazo otimizado e mais.

import streamlit as st
from datetime import date, timedelta, datetime
import holidays
import re
import pandas as pd

# ========= INÍCIO: Constantes e Configurações =========
# Centralizando opções e configurações para fácil manutenção
CLIENTE_OPTIONS = ["Reclamante", "Reclamado", "Outro (Terceiro, MPT, etc.)"]
DECISAO_OPTIONS = [
    "Sentença (Vara do Trabalho)", "Acórdão (TRT)", "Acórdão (TST - Turma)", 
    "Acórdão (TST - SDI)", "Decisão Monocrática (Relator TRT/TST)", 
    "Despacho Denegatório de Recurso", "Decisão Interlocutória", "Outro"
]
RESULTADO_OPTIONS = ["Favorável", "Desfavorável", "Parcialmente Favorável"]
ED_OPTIONS = ["Cabe ED", "Não cabe ED"]
RECURSO_OPTIONS = [
    "Não Interpor Recurso", "Recurso Ordinário (RO)", "Recurso de Revista (RR)", 
    "Agravo de Instrumento em Recurso Ordinário (AIRO)", 
    "Agravo de Instrumento em Recurso de Revista (AIRR)", "Agravo de Petição (AP)", 
    "Agravo Regimental / Agravo Interno", "Embargos de Divergência ao TST (SDI)", 
    "Recurso Extraordinário (RE)", "Outro"
]
GUIAS_STATUS_OPTIONS = ["Guias já elaboradas e salvas", "Guias pendentes de elaboração"]

MAPA_DECISAO_RECURSO = {
    "Sentença (Vara do Trabalho)": 1, "Acórdão (TRT)": 2, "Acórdão (TST - Turma)": 7, 
    "Acórdão (TST - SDI)": 8, "Decisão Monocrática (Relator TRT/TST)": 6, 
    "Despacho Denegatório de Recurso": 4, "Decisão Interlocutória": 0, "Outro": 0
}
IMAGE_PATH = "image_545e9d.png" # Certifique-se que este arquivo está na mesma pasta

# ========= FIM: Constantes e Configurações =========


# ========= INÍCIO: Funções Auxiliares =========

@st.cache_data
def get_holidays(year):
    """Cacheia feriados para evitar recálculos."""
    return holidays.country_holidays('BR', years=year)

def add_business_days(from_date, num_days):
    """Adiciona ou subtrai dias úteis de uma data, considerando feriados nacionais."""
    if not isinstance(from_date, date): return None
    
    br_holidays = get_holidays(from_date.year)
    if num_days != 0 and (from_date + timedelta(days=num_days)).year != from_date.year:
         br_holidays.update(get_holidays((from_date + timedelta(days=num_days)).year))

    current_date = from_date
    days_added = 0
    increment = 1 if num_days >= 0 else -1
    absolute_days = abs(num_days)
    
    while days_added < absolute_days:
        current_date += timedelta(days=increment)
        weekday = current_date.weekday()
        if weekday >= 5 or current_date in br_holidays:
            continue
        days_added += 1
    return current_date

def _find_header_and_map_columns(lines: list[str]) -> tuple[dict, int, list]:
    """Localiza a linha do cabeçalho e mapeia dinamicamente os índices das colunas."""
    HEADER_KEYWORDS = ['objetos', 'situação', 'resultado 1ª instância', 'resultado 2ª instância', 'resultado instância superior']
    header_map = {}
    header_row_index = -1

    for i, line in enumerate(lines):
        line_lower = line.lower()
        if sum(kw in line_lower for kw in HEADER_KEYWORDS) >= 3:
            header_row_index = i
            parts = re.split(r'\t|\s{2,}', line)
            header_parts = [p.strip().lower() for p in parts if p.strip()]
            
            for kw in HEADER_KEYWORDS:
                try:
                    found_col = next(col for col in header_parts if kw in col)
                    header_map[kw] = header_parts.index(found_col)
                except StopIteration:
                    return None, -1, [f"Coluna essencial '{kw}' não encontrada no cabeçalho: '{line}'"]
            return header_map, header_row_index, []
    
    return None, -1, ["Não foi possível localizar uma linha de cabeçalho válida. Verifique se colunas como 'Objetos', 'Situação' e 'Resultado...' estão presentes."]

def _parse_data_rows(lines: list[str], header_map: dict, start_index: int) -> tuple[list[dict], list[str]]:
    """Processa as linhas de dados com base no mapa de colunas dinâmico."""
    parsed_data = []
    warnings = []
    
    num_expected_parts = len(header_map)
    for i in range(start_index, len(lines)):
        line = lines[i].strip()
        if not line or line.lower().startswith(("visualizar", "editar", "ação", "gerenciar")):
            continue

        parts = re.split(r'\t|\s{2,}', line)
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) < num_expected_parts:
            warnings.append(f"Linha {i+1} parece incompleta (tem {len(parts)} partes, esperado ~{num_expected_parts}): '{line[:70]}...'")
            continue

        row_data = {}
        try:
            for key, col_index in header_map.items():
                # Renomeia chaves para serem mais amigáveis ao Python/Pandas
                clean_key = key.replace(' ', '_').replace('ª', 'a').capitalize()
                row_data[clean_key] = parts[col_index] if col_index < len(parts) else 'N/A'
            parsed_data.append(row_data)
        except IndexError:
            warnings.append(f"Falha ao acessar coluna na linha {i+1}. Verifique o alinhamento: '{line[:70]}...'")

    return parsed_data, warnings

def _format_report_text(data: list[dict], tipo_decisao: str, warnings: list[str]) -> str:
    """Formata os dados processados em um texto de relatório legível."""
    report_lines = []
    if warnings:
        report_lines.append("[AVISOS DURANTE PROCESSAMENTO]:")
        report_lines.extend([f"- {w}" for w in warnings])
        report_lines.append("-" * 20)

    try:
        data.sort(key=lambda x: x.get('Objetos', ''))
    except TypeError:
        st.warning("Não foi possível ordenar os pedidos (dados mistos).")

    for index, item in enumerate(data, start=1):
        report_lines.append(f"{index}) {item.get('Objetos', 'N/A')}")
        
        if situacao := item.get('Situação', 'N/A').strip():
             report_lines.append(f" - Situação: {situacao}")

        res1 = item.get('Resultado_1a_instância', 'N/A')
        res2 = item.get('Resultado_2a_instância', 'N/A')
        resSup = item.get('Resultado_instância_superior', 'N/A')

        tipo_decisao_lower = tipo_decisao.lower() if tipo_decisao else ""
        show_res2 = "acórdão" in tipo_decisao_lower or "monocrática" in tipo_decisao_lower or "denegatório" in tipo_decisao_lower
        show_resSup = "tst" in tipo_decisao_lower or "denegatório" in tipo_decisao_lower

        def is_relevant(res_value):
            return res_value and res_value.lower().strip() not in ["aguardando julgamento", "n/a", "", "não houve recurso"]

        if is_relevant(res1): report_lines.append(f" - Resultado 1ª Instância: {res1}")
        if show_res2 and is_relevant(res2): report_lines.append(f" - Resultado 2ª Instância: {res2}")
        if show_resSup and is_relevant(resSup): report_lines.append(f" - Resultado Instância Superior: {resSup}")
        
        report_lines.append("")

    return "\n".join(report_lines)

def process_datajuri_table(text: str, tipo_decisao: str) -> tuple[pd.DataFrame, str, str]:
    """Função principal que orquestra o pipeline de processamento da tabela."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None, None, "Erro: O texto da tabela está vazio."

    header_map, header_row_index, errors = _find_header_and_map_columns(lines)
    if errors:
        return None, None, "\n".join(errors)

    data_rows, warnings = _parse_data_rows(lines, header_map, header_row_index + 1)
    if not data_rows:
        return None, None, "Erro: Nenhum dado de pedido válido foi extraído. Verifique o conteúdo após o cabeçalho."

    df = pd.DataFrame(data_rows)
    report_text = _format_report_text(data_rows, tipo_decisao, warnings)

    return df, report_text, None

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

def make_hyperlink(path: str) -> str:
    path_cleaned = path.strip()
    if path_cleaned.lower().startswith(("http://", "https://")):
        return f"[{path_cleaned}]({path_cleaned})"
    return path_cleaned

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

# ========= FIM: Funções Auxiliares =========


# ========= INÍCIO: Configuração da Página e Estado =========
st.set_page_config(page_title="Análise de Decisões de Mérito v3.0", layout="wide", initial_sidebar_state="expanded")
st.title("Formulário de Análise de Decisões de Mérito")

# Inicializa estado da sessão
if "prazos" not in st.session_state: st.session_state.prazos = []
if "parsed_pedidos_df" not in st.session_state: st.session_state.parsed_pedidos_df = None
if "parsed_report_text" not in st.session_state: st.session_state.parsed_report_text = None
if "parser_error" not in st.session_state: st.session_state.parser_error = None
if "show_image_example" not in st.session_state: st.session_state.show_image_example = False

def callback_process_table():
    """Função chamada sempre que o texto da tabela ou o tipo de decisão mudam."""
    text = st.session_state.get("texto_tabela_pedidos", "")
    tipo_decisao = st.session_state.get("tipo_decisao", "")
    if not tipo_decisao:
        st.session_state.parser_error = "Selecione o 'Tipo de Decisão Analisada' antes de colar a tabela."
        st.session_state.parsed_pedidos_df = None
        st.session_state.parsed_report_text = None
        return
    if text:
        df, report_text, error = process_datajuri_table(text, tipo_decisao)
        st.session_state.parsed_pedidos_df = df
        st.session_state.parsed_report_text = report_text
        st.session_state.parser_error = error

# ====== SIDEBAR DE AJUDA ======
with st.sidebar:
    st.header("Ajuda - Roteiro de Análise")
    st.info(
        """
        **Passos Principais:**

        1.  **Contexto:** Informe a **Data da Ciência**, **Cliente** e **Tipo de Decisão**.
        2.  **Análise:** Defina o **Resultado Geral** e adicione observações.
        3.  **Tabela de Pedidos:** Cole o texto da tabela. A verificação é **automática**. Um preview (ou erro) aparecerá abaixo.
        4.  **Embargos (ED):** Avalie se cabem.
        5.  **Recurso:** Se não couber ED, escolha o recurso e justifique.
        6.  **Custas/Depósito:** Informe valores se o recurso exigir.
        7.  **Prazos:** Adicione o prazo sugerido com **um clique** ou insira prazos manualmente.
        8.  **Gerar Texto:** Clique no botão final para montar o relatório.
        """
    )
    st.warning("Lembre-se de salvar o texto gerado ao final do processo.")

# ========= INÍCIO DO LAYOUT DO FORMULÁRIO =========

st.header("1. Contexto e Análise da Decisão")
col_contexto1, col_contexto2, col_contexto3 = st.columns(3)
with col_contexto1:
    data_ciencia = st.date_input("Data da Ciência/Publicação:", value=None, key="data_ciencia")
with col_contexto2:
    cliente_role = st.selectbox("Cliente é:", options=CLIENTE_OPTIONS, index=1, key="cliente_role")
with col_contexto3:
    tipo_decisao = st.selectbox("Tipo de Decisão Analisada:", options=DECISAO_OPTIONS, index=None, key="tipo_decisao", on_change=callback_process_table)

resultado_sentenca = st.selectbox("Resultado Geral para o Cliente:", options=RESULTADO_OPTIONS, index=None, key="resultado_sentenca")
obs_sentenca = st.text_area("Observações sobre a Decisão:", help="Detalhe aqui nuances, especialmente se 'Parcialmente Favorável'.")

st.header("2. Tabela de Pedidos (DataJuri)")
if st.button("Mostrar/Ocultar Imagem Exemplo"):
    st.session_state.show_image_example = not st.session_state.show_image_example
if st.session_state.show_image_example:
    try:
        st.image(IMAGE_PATH, caption="Exemplo Tela DataJuri", use_column_width=True)
    except Exception:
        st.error(f"Erro: Imagem de exemplo ('{IMAGE_PATH}') não encontrada. Certifique-se que o arquivo está na mesma pasta do script.")

texto_tabela = st.text_area(
    "Cole aqui o texto da tabela de pedidos (a verificação é automática):",
    height=200,
    key="texto_tabela_pedidos",
    on_change=callback_process_table,
    help="Cole a tabela e o preview aparecerá abaixo. Certifique-se de ter selecionado o 'Tipo de Decisão' primeiro."
)

preview_placeholder = st.empty()
with preview_placeholder.container():
    if st.session_state.parser_error:
        st.error(f"Falha ao processar a tabela:\n\n{st.session_state.parser_error}")
    elif st.session_state.parsed_pedidos_df is not None:
        st.success("Tabela processada com sucesso! (Preview abaixo)")
        st.dataframe(st.session_state.parsed_pedidos_df, use_container_width=True)

st.header("3. Próximos Passos (ED, Recurso, Custas)")
ed_status = st.radio("Avaliação sobre Embargos de Declaração (ED):", options=ED_OPTIONS, index=None, key="ed_status", horizontal=True)
justificativa_ed = ""
if ed_status == "Cabe ED":
    justificativa_ed = st.text_area("Justificativa para ED (obrigatório):", height=100)

if ed_status == "Não cabe ED":
    with st.container(border=True):
        st.subheader("Análise de Recurso Cabível")
        suggested_recurso_index = MAPA_DECISAO_RECURSO.get(tipo_decisao, 0)
        recurso_selecionado = st.selectbox("Recurso a ser considerado:", options=RECURSO_OPTIONS, index=suggested_recurso_index, key="recurso_sel")
        recurso_outro_especificar = ""
        if recurso_selecionado == "Outro":
            recurso_outro_especificar = st.text_input("Especifique qual outro recurso:", key="recurso_outro_txt")
        recurso_justificativa = st.text_area("Justificativa para a escolha do Recurso:", height=100)

        if recurso_selecionado and recurso_selecionado != "Não Interpor Recurso":
            st.markdown("---")
            st.subheader("Custas e Depósito Recursal")
            col_custas1, col_custas2 = st.columns(2)
            with col_custas1:
                isenta_deposito = st.radio("Parte isenta de depósito?", ["Sim", "Não"], index=None, key="isenta_deposito")
                valor_deposito = st.number_input("Valor do depósito (R$):", min_value=0.0, step=0.01, format="%.2f", disabled=(isenta_deposito != "Não"))
            with col_custas2:
                isenta_custas = st.radio("Parte isenta de custas?", ["Sim", "Não"], index=None, key="isenta_custas")
                valor_custas = st.number_input("Valor das custas (R$):", min_value=0.0, step=0.01, format="%.2f", disabled=(isenta_custas != "Não"))
            
            if (isenta_deposito == "Não" and valor_deposito > 0) or (isenta_custas == "Não" and valor_custas > 0):
                st.markdown("---")
                st.subheader("Guias de Pagamento")
                guias_status = st.radio("Status das Guias:", options=GUIAS_STATUS_OPTIONS, index=None, key="guias_status")
                local_guias = st.text_input("Local/Link/Observação sobre as Guias:")

st.header("4. Prazos")
suggested_prazo = None
if data_ciencia:
    data_base = data_ciencia
    if ed_status == "Cabe ED":
        prazo_fatal = add_business_days(data_base, 5)
        if prazo_fatal:
            suggested_prazo = {"descricao": "Prazo para Oposição de Embargos de Declaração", "data_fatal": prazo_fatal, "data_d": add_business_days(prazo_fatal, -2), "obs": ""}
    elif ed_status == "Não cabe ED" and 'recurso_selecionado' in locals() and recurso_selecionado:
        prazo_dias = 15 if "Extraordinário" in recurso_selecionado else 8
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
    col_sugestao, col_botao = st.columns([0.75, 0.25])
    with col_sugestao:
        st.info(f"**Sugestão de Prazo:** {suggested_prazo['descricao']} (Fatal: {suggested_prazo['data_fatal'].strftime('%d/%m/%Y')})")
    with col_botao:
        if st.button("Adicionar Prazo Sugerido", use_container_width=True):
            st.session_state.prazos.append(suggested_prazo)
            st.rerun()

with st.expander("Adicionar outro prazo manualmente"):
    with st.form("form_prazos_manual", clear_on_submit=True):
        descricao = st.text_input("Descrição:")
        col_datas1, col_datas2 = st.columns(2)
        with col_datas1: data_d = st.date_input("Data D- (interna):", value=date.today())
        with col_datas2: data_fatal = st.date_input("Data Fatal (legal):", value=date.today())
        obs_prazo = st.text_input("Observações:")
        
        if st.form_submit_button("Adicionar Prazo Manual"):
            if not descricao.strip(): st.error("A descrição do prazo é obrigatória!")
            elif data_d > data_fatal: st.error("Erro: A Data D- não pode ser posterior à Data Fatal!")
            else:
                st.session_state.prazos.append({"descricao": descricao.strip(), "data_d": data_d, "data_fatal": data_fatal, "obs": obs_prazo.strip()})
                st.rerun()

if st.session_state.prazos:
    st.write("---")
    st.write("**Prazos Adicionados:**")
    indices_para_remover = []
    for i, prazo in enumerate(st.session_state.prazos):
        col1, col2 = st.columns([0.9, 0.1])
        with col1:
            data_d_str = prazo.get('data_d').strftime('%d/%m/%Y')
            data_fatal_str = prazo.get('data_fatal').strftime('%d/%m/%Y')
            st.markdown(f"**{i+1}. {prazo.get('descricao', 'N/A')}** | D-: `{data_d_str}` | Fatal: `{data_fatal_str}`")
            if obs := prazo.get('obs'): st.caption(f"Obs: {obs}")
        with col2:
            if st.button("❌", key=f"del_{i}", help="Remover este prazo"):
                indices_para_remover.append(i)
    if indices_para_remover:
        for index in sorted(indices_para_remover, reverse=True): del st.session_state.prazos[index]
        st.rerun()

st.header("5. Observações Finais")
obs_finais = st.text_area("Observações Gerais Finais (opcional):", height=100)

st.divider()
if st.button("✔️ Gerar Texto Final da Análise", type="primary", use_container_width=True):
    valid = True
    error_messages = []
    
    # Validações
    if not data_ciencia: error_messages.append("Data da Ciência/Publicação é obrigatória.")
    if not tipo_decisao: error_messages.append("Tipo de Decisão Analisada é obrigatório.")
    if not resultado_sentenca: error_messages.append("Resultado Geral é obrigatório.")
    if resultado_sentenca == "Parcialmente Favorável" and not obs_sentenca.strip(): error_messages.append("Observações são obrigatórias se o Resultado for 'Parcialmente Favorável'.")
    if not texto_tabela.strip(): error_messages.append("A Tabela de Pedidos é obrigatória.")
    if st.session_state.parser_error: error_messages.append(f"Há um erro no processamento da tabela: {st.session_state.parser_error}")
    if not st.session_state.parsed_report_text and texto_tabela.strip(): error_messages.append("A tabela foi preenchida, mas não pôde ser processada. Verifique os erros acima.")
    if not ed_status: error_messages.append("A avaliação sobre ED é obrigatória.")
    if ed_status == "Cabe ED" and not justificativa_ed.strip(): error_messages.append("A justificativa para ED é obrigatória.")
    
    if ed_status == "Não cabe ED":
        if not recurso_selecionado: error_messages.append("A seleção de Recurso é obrigatória.")
        elif recurso_selecionado == "Outro" and not recurso_outro_especificar.strip(): error_messages.append("Especifique o recurso 'Outro'.")
        if not recurso_justificativa.strip(): error_messages.append("A justificativa para o Recurso é obrigatória.")
        
        if recurso_selecionado and recurso_selecionado != "Não Interpor Recurso":
            if isenta_deposito is None: error_messages.append("Informe a isenção de depósito.")
            elif isenta_deposito == "Não" and valor_deposito <= 0: error_messages.append("O valor do depósito deve ser maior que zero.")
            if isenta_custas is None: error_messages.append("Informe a isenção de custas.")
            elif isenta_custas == "Não" and valor_custas <= 0: error_messages.append("O valor das custas deve ser maior que zero.")
            
            if (isenta_deposito == "Não" and valor_deposito > 0) or (isenta_custas == "Não" and valor_custas > 0):
                if not guias_status: error_messages.append("Informe o status das Guias.")
                if not local_guias.strip(): error_messages.append("O 'Local/Observação' das guias é obrigatório.")

    if error_messages:
        for msg in error_messages: st.error(msg)
    else:
        # Montagem dos dados para o texto final
        sections_data = []
        
        contexto_str = (f"- Cliente: {cliente_role}\n"
                        f"- Tipo de Decisão Analisada: {tipo_decisao}\n"
                        f"- Data da Ciência: {data_ciencia.strftime('%d/%m/%Y')}")
        sections_data.append(("Contexto", contexto_str))
        
        resultado_str = (f"- Avaliação para o Cliente: {resultado_sentenca}\n"
                         f"- Observações: {obs_sentenca.strip() or 'Nenhuma'}")
        sections_data.append(("Resultado Geral da Decisão", resultado_str))
        
        sections_data.append(("Tabela de Pedidos Processada", st.session_state.parsed_report_text))
        
        ed_str = (f"- Avaliação: {ed_status}\n"
                  f"- Justificativa: {justificativa_ed.strip() or 'N/A'}")
        sections_data.append(("Embargos de Declaração (ED)", ed_str))

        if ed_status == "Não cabe ED":
            recurso_final = recurso_selecionado if recurso_selecionado != "Outro" else recurso_outro_especificar.strip()
            recurso_str = (f"- Decisão/Recomendação: {recurso_final}\n"
                           f"- Justificativa: {recurso_justificativa.strip()}")
            sections_data.append(("Recurso", recurso_str))
            
            if recurso_final != "Não Interpor Recurso":
                deposito_str = f"R$ {valor_deposito:.2f}" if isenta_deposito == "Não" else "Isento"
                custas_str = f"R$ {valor_custas:.2f}" if isenta_custas == "Não" else "Isento"
                custas_deposito_str = (f"- Depósito Recursal: {deposito_str} (Isenção: {isenta_deposito})\n"
                                       f"- Custas Processuais: {custas_str} (Isenção: {isenta_custas})")
                sections_data.append(("Custas e Depósito Recursal", custas_deposito_str))

                if (isenta_deposito == "Não" and valor_deposito > 0) or (isenta_custas == "Não" and valor_custas > 0):
                    guias_str = (f"- Status: {guias_status}\n"
                                 f"- Local/Observação: {make_hyperlink(local_guias)}")
                    sections_data.append(("Guias de Pagamento", guias_str))

        sections_data.append(("Prazos Adicionados", format_prazos(st.session_state.prazos)))
        sections_data.append(("Observações Finais", obs_finais.strip() or "Nenhuma"))
        
        final_text = generate_final_text(sections_data)
        
        st.subheader("Texto Gerado para Workflow")
        st.text_area("Copie o texto abaixo:", final_text, height=600)
        st.success("Texto gerado com sucesso!")
        st.balloons()
