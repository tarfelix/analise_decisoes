# -*- coding: utf-8 -*-
# Versão com Debugging Aprimorado no Parser + Debug Linha + Revisão Extração

import streamlit as st
from datetime import date, timedelta, datetime
import holidays # pip install holidays
import re # Importa regex para parsing flexível

# ========= INÍCIO: Funções Auxiliares =========

# --- Função para Cálculo de Dias Úteis ---
br_holidays = holidays.country_holidays('BR')
def add_business_days(from_date, num_days):
    if not isinstance(from_date, date): return None
    current_date = from_date; days_added = 0; increment = 1 if num_days >= 0 else -1
    absolute_days = abs(num_days)
    while days_added < absolute_days:
        current_date += timedelta(days=increment); weekday = current_date.weekday()
        if weekday >= 5 or current_date in br_holidays: continue
        days_added += 1
    return current_date

# --- Função de Parse da Tabela (VERSÃO ROBUSTA com DEBUG linha e Extração Revisada) ---
def parse_and_format_report_v2(texto: str, tipo_decisao_analisada: str) -> tuple:
    """
    Processa texto do DataJuri e formata relatório filtrando instâncias.
    Retorna: tuple: (dados_estruturados, texto_formatado_ou_erro)
    """
    print("-" * 10 + "[DEBUG] Iniciando parse_and_format_report_v2" + "-" * 10)
    lines = [l.strip() for l in texto.strip().splitlines() if l.strip()]
    if not lines:
        print("[DEBUG] Erro: Texto vazio.")
        return None, "Erro: Texto da tabela de pedidos está vazio."

    header_keywords = ['situação', 'resultado 1ª instância', 'resultado 2ª instância', 'resultado instância superior']
    header_row_index = -1; header_map = {}; header_line_parts = []

    # 1. Encontrar linha de cabeçalho
    print("[DEBUG] Procurando linha de cabeçalho por keywords...")
    for i, line in enumerate(lines):
        line_lower = line.lower(); keywords_found = [kw for kw in header_keywords if kw in line_lower]
        common_data_starts = ['adicional', 'horas', 'multa', 'diferenças', 'danos', 'justiça', 'honorários']
        is_likely_header = len(keywords_found) >= 2 and not any(line_lower.startswith(start) for start in common_data_starts)
        if is_likely_header:
            print(f"[DEBUG] Header provável encontrado na linha {i}: '{line}'")
            header_row_index = i; parts = line.split('\t')
            if len(parts) <= 1: parts = re.split(r'\s{2,}', line)
            header_line_parts = [p.strip() for p in parts]; break
    if header_row_index == -1:
        try: # Fallback Objetos
            objetos_index = -1
            for i, line in enumerate(lines):
                if line.strip().lower() == 'objetos': objetos_index = i; break
            if objetos_index != -1 and objetos_index + 1 < len(lines):
                 header_row_index = objetos_index + 1; line = lines[header_row_index]
                 print(f"[DEBUG] Usando linha após 'Objetos' (linha {header_row_index}): '{line}'")
                 parts = line.split('\t');
                 if len(parts) <= 1: parts = re.split(r'\s{2,}', line)
                 header_line_parts = [p.strip() for p in parts]; st.warning("Cabeçalho não encontrado por keywords, usando linha após 'Objetos'.")
            else: return None, "Erro: Não foi possível localizar a linha de cabeçalho. Verifique o texto colado."
        except Exception as e_fb: return None, f"Erro: Falha ao tentar localizar cabeçalho após 'Objetos': {e_fb}"

    print(f"[DEBUG] Cabeçalho detectado para mapeamento: {header_line_parts}")

    # 2. Mapear índices das colunas (Situação e Resultados apenas)
    header_map = {}
    try:
        header_map['situação'] = header_line_parts.index(next(h for h in header_line_parts if 'situação' in h.lower()))
        header_map['resultado 1ª instância'] = header_line_parts.index(next(h for h in header_line_parts if 'resultado 1ª instância' in h.lower()))
        header_map['resultado 2ª instância'] = header_line_parts.index(next(h for h in header_line_parts if 'resultado 2ª instância' in h.lower()))
        header_map['resultado instância superior'] = header_line_parts.index(next(h for h in header_line_parts if 'resultado instância superior' in h.lower()))
        print(f"[DEBUG] Mapeamento de cabeçalho (Situação/Resultados): {header_map}")
    except (ValueError, StopIteration) as e_map:
        error_detail = f"Cabeçalho Detectado: '{' | '.join(header_line_parts)}'. Erro específico: {e_map}"
        print(f"[DEBUG] Falha no mapeamento do cabeçalho. {error_detail}")
        return None, f"Erro: Não foi possível encontrar/mapear as colunas essenciais (Situação, Resultados...) no cabeçalho.\n{error_detail}\nVerifique o texto colado."

    # 3. Processar linhas de dados
    data_rows_start_index = header_row_index + 1; pedidos_data = []; processing_warnings = []
    print(f"[DEBUG] Iniciando processamento de dados da linha {data_rows_start_index}")
    for i in range(data_rows_start_index, len(lines)):
        line = lines[i]; line_lower_strip = line.strip().lower()
        if not line or line_lower_strip.startswith(("visualizar", "editar", "ação", "gerenciar")): continue
        parts = line.split('\t'); split_method = "TAB"
        if len(parts) <= 1 and len(line.split()) > 1: parts = re.split(r'\s{2,}', line); split_method = "REGEX"
        if len(parts) <= 1 and len(line.split()) > 1: parts = line.split(); split_method = "ESPAÇO SIMPLES"
        parts = [p.strip() for p in parts if p.strip()] # Remove partes vazias após split

        # <<< DEBUG DESCOMENTADO >>>
        print(f"[DEBUG]   Linha {i+1} Parts ({split_method}): {parts}") # DEBUG - VEJA ISSO NO TERMINAL

        if not parts or not parts[0]: continue # Pula se não sobrou nada ou o primeiro elemento é vazio

        # Lógica de extração revisada
        try:
            pedido_dict = {'Objetos': parts[0]} # Assume Objeto é sempre o primeiro

            # Calcula os índices esperados em 'parts' assumindo Objeto=parts[0]
            # Os índices do header_map (0, 1, 2, 3) correspondem a Situação, Res1, Res2, ResSup *no header_line_parts*
            # Se o header_line_parts começa com Situação (índice 0), então em 'parts' a situação deve estar no índice 1
            offset = 1 # Assume Objeto é parts[0]

            idx_situacao = header_map['situação'] + offset
            idx_res1 = header_map['resultado 1ª instância'] + offset
            idx_res2 = header_map['resultado 2ª instância'] + offset
            idx_resSup = header_map['resultado instância superior'] + offset

            # Pega os dados usando os índices calculados, com verificação de limites
            pedido_dict['Situação'] = parts[idx_situacao] if idx_situacao < len(parts) else 'N/A'
            pedido_dict['Res1'] = parts[idx_res1] if idx_res1 < len(parts) else 'N/A'
            pedido_dict['Res2'] = parts[idx_res2] if idx_res2 < len(parts) else 'N/A'
            pedido_dict['ResSup'] = parts[idx_resSup] if idx_resSup < len(parts) else 'N/A'

            pedidos_data.append(pedido_dict)

        except IndexError:
             # Se mesmo com a verificação de offset der erro, a estrutura da linha é inesperada
             processing_warnings.append(f"Falha ao processar linha {i+1} (Índice após offset): '{line[:70]}...' | Parts: {len(parts)}")
        except Exception as e:
             processing_warnings.append(f"Falha inesperada linha {i+1} '{line[:70]}...': {e}")


    print(f"[DEBUG] Processamento de dados concluído. {len(pedidos_data)} pedidos extraídos.")
    if not pedidos_data:
        error_msg = "Erro: Nenhum dado de pedido válido encontrado."
        if processing_warnings: error_msg += "\nPossíveis problemas:\n" + "\n".join([f"- {w}" for w in processing_warnings])
        error_msg += "\nVerifique o texto colado."; return None, error_msg

    # 4. Ordenar e Formatar para o Relatório Final (com filtro de instância)
    try: pedidos_data.sort(key=lambda x: x.get('Objetos', ''))
    except Exception as e: st.warning(f"Não foi possível ordenar os pedidos: {e}")
    pedidos_formatados_report = []
    if processing_warnings: pedidos_formatados_report.append("[AVISOS DURANTE PROCESSAMENTO]:"); pedidos_formatados_report.extend([f"- {w}" for w in processing_warnings]); pedidos_formatados_report.append("-" * 20)
    for index, item in enumerate(pedidos_data, start=1):
        pedidos_formatados_report.append(f"{index}) {item.get('Objetos', 'N/A')}")
        situacao = item.get('Situação', 'N/A').strip()
        if situacao: pedidos_formatados_report.append(f" - Situação: {situacao}")
        res1 = item.get('Res1', '').strip(); res2 = item.get('Res2', '').strip(); resSup = item.get('ResSup', '').strip()
        show_res1 = True; show_res2 = False; show_resSup = False
        if tipo_decisao_analisada:
            tipo_lower = tipo_decisao_analisada.lower()
            if tipo_lower.startswith("acórdão (trt)"): show_res2 = True
            elif tipo_lower.startswith("acórdão (tst"): show_res2 = True; show_resSup = True
            elif tipo_lower.startswith(("decisão monocrática", "despacho denegatório")): show_res2 = True; show_resSup = True
        def is_relevant(res_value): return res_value and res_value.lower() not in ["aguardando julgamento", "n/a", ""]
        if show_res1 and is_relevant(res1): pedidos_formatados_report.append(f" - Resultado 1ª Instância: {res1}")
        if show_res2 and is_relevant(res2): pedidos_formatados_report.append(f" - Resultado 2ª Instância: {res2}")
        if show_resSup and is_relevant(resSup): pedidos_formatados_report.append(f" - Resultado Instância Superior: {resSup}")
        pedidos_formatados_report.append("")
    print("[DEBUG] Formatação do relatório final concluída (com filtro de instância).")
    return pedidos_data, "\n".join(pedidos_formatados_report)

# --- Funções format_prazos, make_hyperlink, generate_final_text (mantidas) ---
def format_prazos(prazos_list):
    if not prazos_list: return "Nenhum prazo informado."
    lines = []
    for i, p in enumerate(prazos_list, start=1):
        lines.append(f"{i}) {p.get('descricao','N/A')}")
        try: data_d_obj = datetime.strptime(p['data_d'], '%Y-%m-%d').date(); lines.append(f"   - Data D-: {data_d_obj.strftime('%d/%m/%Y')}")
        except (ValueError, TypeError, KeyError): lines.append(f"   - Data D-: {p.get('data_d','Inválido')} (Formato inválido)")
        try: data_fatal_obj = datetime.strptime(p['data_fatal'], '%Y-%m-%d').date(); lines.append(f"   - Data Fatal: {data_fatal_obj.strftime('%d/%m/%Y')}")
        except (ValueError, TypeError, KeyError): lines.append(f"   - Data Fatal: {p.get('data_fatal','Inválido')} (Formato inválido)")
        obs = p.get('obs','').strip()
        if obs: lines.append(f"   - Observações: {obs}")
        lines.append("")
    return "\n".join(lines)

def make_hyperlink(path: str) -> str:
    path_cleaned = path.strip()
    if path_cleaned.lower().startswith("http://") or path_cleaned.lower().startswith("https://"): return f"[{path_cleaned}]({path_cleaned})"
    return path_cleaned

def generate_final_text(sections):
    final_lines = []; visible_idx = 1
    for title, content in sections:
        if content is not None:
            final_lines.append(f"{visible_idx}. {title}:"); final_lines.append(content if str(content).strip() else "N/A"); final_lines.append(""); visible_idx += 1
    return "\n".join(final_lines)
# ========= FIM: Funções Auxiliares =========


# ========= INÍCIO: Configuração da Página e Estado =========
st.set_page_config(page_title="Análise de Decisões de Mérito v2.6-debug", layout="wide") # Versão incrementada
st.title("Formulário de Análise de Decisões de Mérito")

# Inicializa estado da sessão
if "prazos" not in st.session_state: st.session_state["prazos"] = []
if "suggested_descricao" not in st.session_state: st.session_state.suggested_descricao = ""
if "suggested_data_fatal" not in st.session_state: st.session_state.suggested_data_fatal = date.today()
if "suggested_data_d" not in st.session_state: st.session_state.suggested_data_d = date.today()
if "data_ciencia_valida" not in st.session_state: st.session_state.data_ciencia_valida = False
if "recurso_sugerido_index" not in st.session_state: st.session_state.recurso_sugerido_index = 0
if "parsed_pedidos_data" not in st.session_state: st.session_state.parsed_pedidos_data = None
if "parsed_pedidos_error" not in st.session_state: st.session_state.parsed_pedidos_error = None
if "show_image_example" not in st.session_state: st.session_state.show_image_example = False

# ========= FIM: Configuração da Página e Estado =========

# ====== SIDEBAR DE AJUDA (Texto revisado) ======
with st.sidebar:
    st.header("Ajuda - Roteiro de Análise")
    st.info(
        """
        **Passos Principais:**

        1.  **Contexto:**
            * Informe a **Data da Ciência** (notificação).
            * Selecione o papel do **Cliente**.
            * Indique o **Tipo de Decisão** analisada.

        2.  **Análise da Decisão:**
            * Defina o **Resultado Geral** para seu cliente.
            * Adicione **Observações**, especialmente se
                o resultado for 'Parcialmente Favorável'.

        3.  **Tabela de Pedidos (DataJuri):**
            * Cole o texto da tabela do DataJuri.
            * *(Veja detalhes e exemplo na ajuda `?` do
                campo específico).*
            * Use **"Mostrar/Ocultar Imagem Exemplo"**
                (acima do campo) para ver a tela de origem.
            * **Importante:** Use **"Verificar Tabela Colada"**
                para validar o texto antes de prosseguir.

        4.  **Embargos de Declaração (ED):**
            * Avalie se cabem ED. Justifique se 'Sim'.
            * Se 'Cabe ED', o fluxo para aqui (foque no prazo ED).

        5.  **Recurso (Se Não Cabe ED):**
            * O sistema sugere um recurso; confirme ou altere.
            * Selecione o recurso específico ou 'Não Interpor'.
            * Justifique sua escolha.

        6.  **Custas / Depósito (Se Recurso Exigir):**
            * Informe isenções e valores devidos.

        7.  **Guias (Se Pagamento Necessário):**
            * Informe o status e o local/link das guias.

        8.  **Prazos:**
            * Use as sugestões automáticas (se aplicável)
                clicando em "Usar Prazo Sugerido".
            * Adicione outros prazos manualmente.
            * Remova prazos com o botão **"X"**.

        9.  **Observações Finais:**
            * Adicione notas gerais (opcional).

        10. **Gerar Texto:**
            * Clique no botão final após preencher tudo.
        """
    )

# ========= Seção Pré: Contexto Inicial (sem alterações) =========
st.header("Contexto do Processo")
col_contexto1, col_contexto2, col_contexto3 = st.columns(3)
with col_contexto1:
    data_ciencia = st.date_input("Data da Ciência/Publicação:", value=None, key="data_ciencia", help="Data da notificação formal da decisão.", max_value=date.today())
    st.session_state.data_ciencia_valida = data_ciencia is not None
with col_contexto2:
    cliente_options = ["Reclamante", "Reclamado", "Outro (Terceiro, MPT, etc.)"]
    cliente_role = st.selectbox("Cliente é:", options=cliente_options, index=1, key="cliente_role", help="Selecione o papel do cliente neste processo.")
with col_contexto3:
    decisao_options = ["Sentença (Vara do Trabalho)", "Acórdão (TRT)", "Acórdão (TST - Turma)", "Acórdão (TST - SDI)", "Decisão Monocrática (Relator TRT/TST)", "Despacho Denegatório de Recurso", "Decisão Interlocutória", "Outro"]
    tipo_decisao = st.selectbox("Tipo de Decisão Analisada:", options=decisao_options, index=None, key="tipo_decisao", help="Qual o tipo de pronunciamento judicial está sendo analisado?")

# ========= Seção Resultado =========
st.header("Análise da Decisão")
resultado_options = ["Favorável", "Desfavorável", "Parcialmente Favorável"]
resultado_sentenca = st.selectbox("Resultado Geral para o Cliente:", options=resultado_options, index=None, help="Avaliação geral da decisão PARA SEU CLIENTE.")
obs_sentenca = st.text_area("Observações sobre a Decisão:", help="Detalhe aqui nuances, especialmente se 'Parcialmente Favorável'.")

# ========= Seção Tabela de Pedidos (com Botão de Imagem e Preview) =========
st.header("Tabela de Pedidos (DataJuri)")

# Botão para mostrar/ocultar imagem
IMAGE_PATH = "image_545e9d.png"
if st.button("Mostrar/Ocultar Imagem Exemplo", key="toggle_image_btn"):
    st.session_state.show_image_example = not st.session_state.show_image_example
if st.session_state.show_image_example:
    try:
        st.image(IMAGE_PATH, caption="Exemplo Tela DataJuri - Tabela de Pedidos", use_column_width=True)
        st.caption(f"Certifique-se que o arquivo '{IMAGE_PATH}' está na mesma pasta do script .py")
    except FileNotFoundError: st.error(f"Erro: Imagem '{IMAGE_PATH}' não encontrada.")
    except Exception as img_e: st.error(f"Erro ao carregar imagem: {img_e}")

# Define o texto de ajuda V4 - SEM Bloco de Código Markdown no exemplo
help_text_tabela_v4 = """
Cole a tabela de pedidos completa copiada do sistema DataJuri.

**Colunas Essenciais Esperadas:**
O sistema tentará encontrar e processar dados das seguintes colunas após a linha de cabeçalho. Certifique-se de que elas estejam presentes no texto copiado:
* `Objetos` (ou Pedido)
* `Situação`
* `Resultado 1ª Instância`
* `Resultado 2ª Instância`
* `Resultado Instância Superior`

*(O sistema assume que as colunas são separadas por TAB (`\\t`). A ordem das colunas de Resultado é importante).*

**Exemplo da Estrutura de Texto (após colar):**

Objetos
Situação	Resultado 1ª Instância	Resultado 2ª Instância	Resultado Instância Superior
Adicional de Insalubridade e Reflexos	Procedência	Procedência	Procedência	Não Houve Recurso
Danos Morais	Improcedência	Improcedência	Não Houve Recurso	Não Houve Recurso
(mais linhas de dados separadas por TAB) ...


**Verificação:** Use o botão **"Verificar Tabela Colada"** abaixo para confirmar se o sistema processou corretamente o texto. Se houver erros, verifique o texto em um editor simples (Bloco de Notas).

*(Linhas com "Ação", "Visualizar | Editar" são geralmente ignoradas).*
"""

texto_tabela = st.text_area(
    "Cole aqui o texto da tabela de pedidos:",
    height=200,
    key="texto_tabela_pedidos",
    help=help_text_tabela_v4
)

# Botão de Verificação e Placeholder para Preview (mantido)
preview_placeholder = st.empty()
if st.button("Verificar Tabela Colada"):
    if not tipo_decisao:
         with preview_placeholder.container(): st.error("Selecione 'Tipo de Decisão Analisada' antes de verificar.")
    elif texto_tabela.strip():
        with st.spinner("Processando tabela..."):
            parsed_data, result_text = parse_and_format_report_v2(texto_tabela, tipo_decisao) # Passa tipo_decisao
            if parsed_data:
                st.session_state.parsed_pedidos_data = parsed_data; st.session_state.parsed_pedidos_error = None
                with preview_placeholder.container():
                    st.success("Tabela processada com sucesso para pré-visualização!"); st.dataframe(parsed_data, use_container_width=True)
            else:
                st.session_state.parsed_pedidos_data = None; st.session_state.parsed_pedidos_error = result_text
                with preview_placeholder.container():
                    st.error(f"Falha ao processar a tabela:"); st.code(result_text, language=None)
    else:
        with preview_placeholder.container(): st.warning("O campo da tabela de pedidos está vazio."); st.session_state.parsed_pedidos_data = None; st.session_state.parsed_pedidos_error = None

# ========= Seção Embargos de Declaração (ED) =========
st.header("Embargos de Declaração (ED)")
ed_status = st.radio("Avaliação sobre ED:", options=["Cabe ED", "Não cabe ED"], index=None, key="ed_status", help="Há omissão, contradição, obscuridade ou erro material?")
justificativa_ed = ""
if ed_status == "Cabe ED": justificativa_ed = st.text_area("Justificativa para ED (obrigatório se 'Cabe ED'):", height=100)

# ========= Seções Condicionais: Recurso, Custas, Guias =========
# (Inicialização de variáveis e lógica de exibição mantida)
recurso_selecionado = None; recurso_justificativa = ""; recurso_outro_especificar = ""
isenta_deposito = None; valor_deposito = 0.0; isenta_custas = None; valor_custas = 0.0
guias_status = None; local_guias = ""; mostrar_secao_recurso = False; mostrar_secao_custas_guias = False
lista_recursos = ["Não Interpor Recurso", "Recurso Ordinário (RO)", "Recurso de Revista (RR)", "Agravo de Instrumento em Recurso Ordinário (AIRO)", "Agravo de Instrumento em Recurso de Revista (AIRR)", "Agravo de Petição (AP)", "Agravo Regimental / Agravo Interno", "Embargos de Divergência ao TST (SDI)", "Recurso Extraordinário (RE)", "Outro"]
mapa_decisao_recurso = {"Sentença (Vara do Trabalho)": 1, "Acórdão (TRT)": 2, "Acórdão (TST - Turma)": 7, "Acórdão (TST - SDI)": 8, "Decisão Monocrática (Relator TRT/TST)": 6, "Despacho Denegatório de Recurso": 4, "Decisão Interlocutória": 0, "Outro": 0}

if ed_status == "Não cabe ED":
    mostrar_secao_recurso = True; st.header("Recurso Cabível"); suggested_recurso_index = 0
    if tipo_decisao:
        suggested_recurso_index = mapa_decisao_recurso.get(tipo_decisao, 0)
        if resultado_sentenca == "Favorável" and cliente_role == "Reclamado": suggested_recurso_index = 0
    recurso_selecionado = st.selectbox("Recurso a ser considerado/interposto:", options=lista_recursos, index=suggested_recurso_index, key="recurso_sel", help="Confirme ou altere a sugestão.")
    if recurso_selecionado == "Outro": recurso_outro_especificar = st.text_input("Especifique qual outro recurso:", key="recurso_outro_txt")
    recurso_justificativa = st.text_area("Justificativa para a escolha do Recurso:", height=100, help="Fundamente a decisão.")
    if recurso_selecionado and recurso_selecionado != "Não Interpor Recurso":
        mostrar_secao_custas_guias = True; st.header("Custas e Depósito Recursal"); col_custas1, col_custas2 = st.columns(2)
        with col_custas1:
            isenta_deposito = st.radio("Parte isenta de depósito recursal?", ["Sim", "Não"], index=None, key="isenta_deposito_v3")
            if isenta_deposito == "Não": valor_deposito = st.number_input("Valor do depósito (R$):", min_value=0.01, step=0.01, format="%.2f")
        with col_custas2:
            isenta_custas = st.radio("Parte isenta de custas processuais?", ["Sim", "Não"], index=None, key="isenta_custas_v3")
            if isenta_custas == "Não": valor_custas = st.number_input("Valor das custas (R$):", min_value=0.01, step=0.01, format="%.2f")
        if isenta_deposito == "Não" or isenta_custas == "Não":
            st.header("Guias de Pagamento")
            guias_status = st.radio("Status das Guias:", options=["Guias já elaboradas e salvas", "Guias pendentes de elaboração", "Não aplicável"], index=None, key="guias_status_v3")
            local_guias = st.text_input("Local/Observação sobre as Guias:", help="Link, pasta ou observação.")

# ========= Seção Prazos (com Bloco Corrigido) =========
st.header("Prazos")
suggested_prazo = None
if st.session_state.data_ciencia_valida:
    data_base = data_ciencia
    if ed_status == "Cabe ED": prazo_fatal_ed = add_business_days(data_base, 8); suggested_prazo = {"descricao": "Prazo para Oposição de Embargos de Declaração", "data_fatal": prazo_fatal_ed, "data_d": add_business_days(prazo_fatal_ed, -2)}
    elif ed_status == "Não cabe ED":
        if recurso_selecionado == "Não Interpor Recurso": prazo_fatal_verificacao = add_business_days(data_base, 8); suggested_prazo = {"descricao": "Verificar interposição de recurso pela parte contrária", "data_fatal": prazo_fatal_verificacao, "data_d": prazo_fatal_verificacao}
        elif recurso_selecionado and recurso_selecionado != "Não Interpor Recurso": prazo_fatal_recurso = add_business_days(data_base, 8); suggested_prazo = {"descricao": f"Prazo para Interposição de {recurso_selecionado}", "data_fatal": prazo_fatal_recurso, "data_d": add_business_days(prazo_fatal_recurso, -2)}
if suggested_prazo:
    st.info(f"**Sugestão de Prazo:**\n- **Descrição:** {suggested_prazo['descricao']}\n- **Data Fatal:** {suggested_prazo['data_fatal'].strftime('%d/%m/%Y')}\n- **Data D-:** {suggested_prazo['data_d'].strftime('%d/%m/%Y')}")
    if st.button("Usar Prazo Sugerido"): st.session_state.suggested_descricao = suggested_prazo['descricao']; st.session_state.suggested_data_fatal = suggested_prazo['data_fatal']; st.session_state.suggested_data_d = suggested_prazo['data_d']; st.rerun()
with st.form("form_prazos_v3", clear_on_submit=True):
    st.write("Adicione prazos relevantes:"); descricao = st.text_input("Descrição:", value=st.session_state.get('suggested_descricao', '')); col_datas1, col_datas2 = st.columns(2)
    with col_datas1: data_d = st.date_input("Data D- (interna):", value=st.session_state.get('suggested_data_d', date.today()), min_value=date(2000,1,1), max_value=date(2099,12,31))
    with col_datas2: data_fatal = st.date_input("Data Fatal (legal):", value=st.session_state.get('suggested_data_fatal', date.today()), min_value=date(2000,1,1), max_value=date(2099,12,31))
    obs_prazo = st.text_input("Observações:")
    submitted = st.form_submit_button("Adicionar Prazo")
    if submitted:
        if not descricao.strip(): st.error("A descrição do prazo é obrigatória!")
        elif data_d > data_fatal: st.error("Erro: A Data D- não pode ser posterior à Data Fatal!")
        else: st.session_state["prazos"].append({"descricao": descricao.strip(), "data_d": str(data_d), "data_fatal": str(data_fatal), "obs": obs_prazo.strip()}); st.success("Prazo adicionado!"); st.session_state.suggested_descricao = ""; st.session_state.suggested_data_fatal = date.today(); st.session_state.suggested_data_d = date.today(); st.rerun()

# --- Exibição e Remoção de Prazos Adicionados (Bloco Corrigido) ---
st.write("---")
if st.session_state["prazos"]:
    st.write("**Prazos Adicionados:**"); indices_para_remover = []
    for i, prazo in enumerate(st.session_state["prazos"]):
        col1, col2 = st.columns([0.95, 0.05])
        with col1:
            st.markdown(f"**{i+1}. {prazo.get('descricao', 'N/A')}**")
            try:
                if 'data_d' in prazo and prazo['data_d']: data_d_obj = datetime.strptime(prazo['data_d'], '%Y-%m-%d').date(); data_d_str = data_d_obj.strftime('%d/%m/%Y')
                else: data_d_str = "Não informada"
            except (ValueError, TypeError): data_d_str = f"{prazo.get('data_d', 'Inválido')} (formato inválido)"
            st.write(f"   - Data D-: {data_d_str}")
            try:
                if 'data_fatal' in prazo and prazo['data_fatal']: data_fatal_obj = datetime.strptime(prazo['data_fatal'], '%Y-%m-%d').date(); data_fatal_str = data_fatal_obj.strftime('%d/%m/%Y')
                else: data_fatal_str = "Não informada"
            except (ValueError, TypeError): data_fatal_str = f"{prazo.get('data_fatal', 'Inválido')} (formato inválido)"
            st.write(f"   - Data Fatal: {data_fatal_str}")
            obs = prazo.get('obs', '').strip();
            if obs: st.write(f"   - Observações: {obs}")
            st.write("---")
        with col2:
            if st.button("X", key=f"del_v3_{i}", help="Remover este prazo"): indices_para_remover.append(i)
    if indices_para_remover:
        for index in sorted(indices_para_remover, reverse=True):
            if index < len(st.session_state["prazos"]): del st.session_state["prazos"][index]
        st.rerun()

# ========= Seção Observações Finais (sem alterações) =========
st.header("Observações Finais")
obs_finais = st.text_area("Observações Gerais Finais (opcional):", height=100)

# ========= BOTÃO PARA GERAR O TEXTO FINAL =========
st.divider()
if st.button("✔️ Gerar Texto Final da Análise", type="primary"):
    # Validações
    valid = True; error_messages = []
    if not data_ciencia: error_messages.append("Data da Ciência/Publicação é obrigatória."); valid = False
    if not cliente_role: error_messages.append("Papel do Cliente é obrigatório."); valid = False
    if not tipo_decisao: error_messages.append("Tipo de Decisão Analisada é obrigatório."); valid = False
    if not resultado_sentenca: error_messages.append("Resultado Geral é obrigatório."); valid = False
    elif resultado_sentenca == "Parcialmente Favorável" and not obs_sentenca.strip(): error_messages.append("Observações são obrigatórias se Resultado 'Parcialmente Favorável'."); valid = False
    if not texto_tabela.strip(): error_messages.append("Tabela de Pedidos é obrigatória (campo de texto)."); valid = False
    # Verifica se o parse teve erro ou não foi verificado
    if st.session_state.get('parsed_pedidos_error'): error_messages.append(f"Erro ao processar Tabela de Pedidos: {st.session_state.parsed_pedidos_error}. Verifique/corrija o texto e clique em 'Verificar' novamente."); valid = False
    elif not st.session_state.get('parsed_pedidos_data') and texto_tabela.strip() and not st.session_state.get('parsed_pedidos_error'): error_messages.append("Clique em 'Verificar Tabela Colada' para validar os pedidos antes de gerar o texto final."); valid = False
    if ed_status is None: error_messages.append("Avaliação sobre ED é obrigatória."); valid = False
    elif ed_status == "Cabe ED" and not justificativa_ed.strip(): error_messages.append("Justificativa para ED é obrigatória."); valid = False
    if mostrar_secao_recurso:
        if not recurso_selecionado: error_messages.append("Seleção de Recurso é obrigatória."); valid = False
        elif recurso_selecionado == "Outro" and not recurso_outro_especificar.strip(): error_messages.append("Especifique o recurso 'Outro'."); valid = False
        if not recurso_justificativa.strip(): error_messages.append("Justificativa para Recurso é obrigatória."); valid = False
        if mostrar_secao_custas_guias:
            if isenta_deposito is None: error_messages.append("Informe isenção de depósito."); valid = False
            elif isenta_deposito == "Não" and valor_deposito <= 0.0: error_messages.append("Valor do depósito deve ser > 0."); valid = False
            if isenta_custas is None: error_messages.append("Informe isenção de custas."); valid = False
            elif isenta_custas == "Não" and valor_custas <= 0.0: error_messages.append("Valor das custas deve ser > 0."); valid = False
            if isenta_deposito == "Não" or isenta_custas == "Não":
                if guias_status is None: error_messages.append("Informe o status das Guias."); valid = False
                if not local_guias.strip(): error_messages.append("'Local/Obs.' das guias é obrigatório."); valid = False
    if not valid:
        for msg in error_messages: st.error(msg)
        st.stop()
    else:
        # Chama parse novamente para pegar o texto formatado/filtrado correto
        parsed_data_final, result_text_final = parse_and_format_report_v2(texto_tabela, tipo_decisao)
        if not parsed_data_final:
             st.error(f"Erro final ao processar tabela para o relatório: {result_text_final}")
             st.stop()

        pedidos_formatados_final = result_text_final
        prazos_text = format_prazos(st.session_state["prazos"])

        # Monta dados para texto final
        sections_data = []
        sections_data.append(("Contexto", f"- Cliente: {cliente_role}\n- Tipo de Decisão Analisada: {tipo_decisao}\n- Data da Ciência: {data_ciencia.strftime('%d/%m/%Y')}"))
        sections_data.append(("Resultado Geral da Decisão", f"- Avaliação para o Cliente: {resultado_sentenca}\n- Observações: {obs_sentenca if obs_sentenca.strip() else 'Nenhuma'}"))
        sections_data.append(("Tabela de Pedidos Processada", pedidos_formatados_final)) # Texto já filtrado e com Situação
        sections_data.append(("Embargos de Declaração (ED)", f"- Avaliação: {ed_status}\n- Justificativa: {justificativa_ed if ed_status == 'Cabe ED' else 'N/A'}"))
        if mostrar_secao_recurso:
            recurso_final = recurso_selecionado if recurso_selecionado != "Outro" else recurso_outro_especificar
            sections_data.append(("Recurso", f"- Decisão/Recomendação: {recurso_final}\n- Justificativa: {recurso_justificativa}"))
            if mostrar_secao_custas_guias:
                deposito_str = f"R$ {valor_deposito:.2f}" if isenta_deposito == "Não" else "Isento"; custas_str = f"R$ {valor_custas:.2f}" if isenta_custas == "Não" else "Isento"
                sections_data.append(("Custas e Depósito Recursal", f"- Depósito Recursal: {deposito_str} (Isenção: {isenta_deposito})\n- Custas Processuais: {custas_str} (Isenção: {isenta_custas})"))
                if isenta_deposito == "Não" or isenta_custas == "Não": sections_data.append(("Guias de Pagamento", f"- Status: {guias_status}\n- Local/Observação: {make_hyperlink(local_guias)}"))
        sections_data.append(("Prazos Adicionados", prazos_text))
        sections_data.append(("Observações Finais", obs_finais if obs_finais.strip() else "Nenhuma"))
        final_text = generate_final_text(sections_data) # Aplica numeração
        st.subheader("Texto Gerado para Workflow"); st.text_area("Copie o texto abaixo:", final_text, height=500); st.success("Texto gerado com sucesso!"); st.balloons()
