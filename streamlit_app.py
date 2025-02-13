import streamlit as st
from datetime import date

def parse_and_format_report(texto: str) -> str:
    """
    Processa o texto copiado do DataJuri, removendo linhas desnecessárias
    e gerando um relatório formatado com os pedidos ordenados alfabeticamente.
    """
    lines = [l.strip() for l in texto.splitlines() if l.strip()]
    pedidos = []
    header = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if "Ação" in line or "Visualizar | Editar" in line:
            i += 1
            continue
        if line == "Objetos":
            if i + 1 < len(lines):
                header = ["Objetos"] + lines[i+1].split("\t")
                i += 2
                continue
            else:
                i += 1
                continue
        pedidos.append(line.split("\t"))
        i += 1

    if not header or not pedidos:
        return "Erro: Não foi possível formatar os pedidos."

    pedidos.sort(key=lambda x: x[0])
    formatted_report = []
    for index, row in enumerate(pedidos, start=1):
        formatted_report.append(f"{index}) {row[0]}")
        if len(row) > 2 and row[2] and row[2] != "Aguardando Julgamento":
            formatted_report.append(f" - Resultado 1ª Instância: {row[2]}")
        if len(row) > 3 and row[3] and row[3] != "Aguardando Julgamento":
            formatted_report.append(f" - Resultado 2ª Instância: {row[3]}")
        if len(row) > 4 and row[4] and row[4] != "Aguardando Julgamento":
            formatted_report.append(f" - Resultado Instância Superior: {row[4]}")
        formatted_report.append("")
    return "\n".join(formatted_report)

def format_prazos(prazos_list):
    """Formata a lista de prazos para exibição no texto final."""
    if not prazos_list:
        return "Nenhum prazo informado."
    lines = []
    for i, p in enumerate(prazos_list, start=1):
        lines.append(f"{i}) {p['descricao']}")
        lines.append(f"   - Data D-: {p['data_d']}")
        lines.append(f"   - Data Fatal: {p['data_fatal']}")
        if p['obs']:
            lines.append(f"   - Observações: {p['obs']}")
        lines.append("")
    return "\n".join(lines)

def make_hyperlink(path: str) -> str:
    """
    Se o 'path' começar com http:// ou https://, gera um link clicável em Markdown.
    Caso contrário, retorna apenas o texto.
    """
    if path.lower().startswith("http://") or path.lower().startswith("https://"):
        return f"[{path}]({path})"
    return path

def generate_final_text(sections):
    """
    Recebe uma lista de tuplas (título, conteúdo) e gera o texto final
    com numeração dinâmica baseada nos tópicos visíveis.
    """
    final_lines = []
    for idx, (title, content) in enumerate(sections, start=1):
        final_lines.append(f"{idx}. {title}:")
        final_lines.append(content)
        final_lines.append("")
    return "\n".join(final_lines)

# Configuração da página
st.set_page_config(page_title="Análise de Decisões de Mérito", layout="wide")
st.title("Formulário de Análise de Decisões de Mérito")

# ====== SIDEBAR DE AJUDA ======
with st.sidebar:
    st.header("Ajuda - Roteiro de Análise")
    st.info(
        """
**1. Analisar a sentença e o processo**  
- Se a sentença for de improcedência e nosso cliente for reclamado, o resultado é **Favorável**.  
- Se o acórdão reverter a condenação (acolhendo nosso recurso), também é **Favorável**.

**2. Atualizar o DataJuri**  
- Verifique se todos os pedidos estão listados e atualizados.

**3. Embargos de Declaração (ED)**  
- Se houver omissões, contradições ou obscuridades, selecione **"Cabe ED"** e justifique.  
- Se **"Cabe ED"**, não serão avaliados Recurso, Custas e Guias.

**4. Recurso**  
- Se **"Não cabe ED"**, avalie o recurso: escolha entre interpor, não interpor, não conhecido, não admitido ou outro.

**5. Custas e Depósito Recursal**  
- Indique separadamente se há isenção de depósito recursal e de custas processuais.

**6. Guias**  
- Aparecem se **pelo menos um** dos itens (depósito ou custas) não for isento.

**7. Prazos**  
- Adicione prazos individualmente (descrição, data D- e data Fatal).  
  *Validação: A data D- não pode ser maior que a Data Fatal.*

**8. Observações Finais**  
- Campo opcional.
        """
    )

# ========= Seção 1: Resultado da Sentença/Acórdão =========
st.header("1. Resultado da Sentença/Acórdão")
resultado_sentenca = st.selectbox(
    "Resultado (obrigatório):",
    options=["Favorável", "Desfavorável"],
    help="Ex.: Sentença improcedente para reclamado = Favorável; acórdão que reverte condenação = Favorável."
)
obs_sentenca = st.text_area("Observações sobre a decisão (opcional):")

# ========= Seção 2: Tabela de Pedidos (obrigatória) =========
st.header("2. Tabela de Pedidos")
texto_tabela = st.text_area(
    "Cole aqui o texto copiado do DataJuri (obrigatório):",
    height=150
)

# ========= Seção 3: Embargos de Declaração (ED) =========
st.header("3. Embargos de Declaração (ED)")
ed_status = st.radio(
    "Selecione se cabem ED (obrigatório):",
    options=["Cabe ED", "Não cabe ED"],
    help="Se houver omissões, contradições ou obscuridades, selecione 'Cabe ED'."
)
justificativa_ed = ""
if ed_status == "Cabe ED":
    justificativa_ed = st.text_area(
        "Justificativa (obrigatório se 'Cabe ED'):",
        height=100
    )

# ========= Seções 4, 5, 6: Apenas se ED == "Não cabe ED" =========
if ed_status == "Não cabe ED":
    # --- Seção 4: Recurso ---
    st.header("4. Recurso")
    recurso_options = [
        "Recomenda interpor recurso (RO, RR etc.)",
        "Não recomenda interpor recurso",
        "Não foi conhecido",
        "Não foi admitido",
        "Outro",
        ""
    ]
    recurso_sel = st.selectbox(
        "Recurso (obrigatório):",
        options=recurso_options,
        help="Escolha a situação do recurso ou deixe em branco para especificar manualmente."
    )
    if recurso_sel in ["Outro", ""]:
        recurso_choice = st.text_input("Especifique outra opção de recurso (obrigatório se 'Outro'):")
    else:
        recurso_choice = recurso_sel

    justificativa_recurso = st.text_area("Justificativa para o recurso (obrigatório):", height=100)

    # --- Seção 5: Custas e Depósito Recursal ---
    st.header("5. Custas e Depósito Recursal")
    st.write("Informe separadamente se há isenção de depósito recursal e de custas processuais.")
    isenta_deposito = st.radio(
        "Parte é isenta de depósito recursal? (obrigatório)",
        ["Sim", "Não"]
    )
    valor_deposito = 0.0
    if isenta_deposito == "Não":
        valor_deposito = st.number_input(
            "Valor do depósito recursal (R$) (obrigatório se não isento):",
            min_value=0.0,
            step=0.01,
            format="%.2f"
        )

    isenta_custas = st.radio(
        "Parte é isenta de custas processuais? (obrigatório)",
        ["Sim", "Não"]
    )
    valor_custas = 0.0
    if isenta_custas == "Não":
        valor_custas = st.number_input(
            "Valor das custas processuais (R$) (obrigatório se não isento):",
            min_value=0.0,
            step=0.01,
            format="%.2f"
        )

    # --- Seção 6: Guias ---
    # Aparece se pelo menos um (depósito ou custas) não for isento.
    if isenta_deposito == "Não" or isenta_custas == "Não":
        st.header("6. Guias")
        st.write("Guias são necessárias se pelo menos um dos itens (depósito ou custas) não for isento.")
        guias_status = st.radio(
            "Guias (obrigatório):",
            options=["Guias já elaboradas e salvas no SharePoint", "Não aplicável (isenção ou sem recurso)"]
        )
        local_guias = st.text_input(
            "Local/pasta onde foram salvas (obrigatório se houver guias):",
            help="Se for um link (http:// ou https://), será convertido em hiperlink."
        )

# ========= Seção 7: Prazos e Observações =========
st.header("7. Prazos e Observações")
if "prazos" not in st.session_state:
    st.session_state["prazos"] = []

with st.form("form_prazos"):
    st.write("Adicione prazos individualmente. (Todos os campos são obrigatórios, exceto Observações)")
    descricao = st.text_input("Descrição do Prazo (obrigatório):")
    data_d = st.date_input("Data D- (data limite interna)", value=date.today())
    data_fatal = st.date_input("Data Fatal (último dia legal)", value=date.today())
    obs_prazo = st.text_input("Observações (opcional)")
    
    # Validação: data_d deve ser menor ou igual a data_fatal.
    if data_d > data_fatal:
        st.error("A data D- não pode ser maior que a Data Fatal!")
    
    if st.form_submit_button("Adicionar Prazo"):
        if not descricao.strip():
            st.error("A descrição do prazo é obrigatória!")
        elif data_d > data_fatal:
            st.error("Não é possível adicionar prazo: Data D- maior que Data Fatal!")
        else:
            st.session_state["prazos"].append({
                "descricao": descricao.strip(),
                "data_d": str(data_d),
                "data_fatal": str(data_fatal),
                "obs": obs_prazo.strip()
            })
            st.success("Prazo adicionado com sucesso!")

if st.session_state["prazos"]:
    st.write("Prazos adicionados:")
    for i, prazo in enumerate(st.session_state["prazos"], start=1):
        st.write(f"**{i}.** {prazo['descricao']}")
        st.write(f"   - Data D-: {prazo['data_d']}")
        st.write(f"   - Data Fatal: {prazo['data_fatal']}")
        if prazo['obs']:
            st.write(f"   - Observações: {prazo['obs']}")
        st.write("---")

# ========= Seção 8: Observações Finais (opcional) =========
st.header("8. Observações Finais")
obs_finais = st.text_area("Observações Finais (opcional):", height=100)

# ========= BOTÃO PARA GERAR O TEXTO FINAL =========
if st.button("Gerar Texto"):
    valid = True
    # Validação da Tabela de Pedidos
    if not texto_tabela.strip():
        st.error("A Tabela de Pedidos é obrigatória.")
        valid = False

    if ed_status == "Cabe ED" and not justificativa_ed.strip():
        st.error("A justificativa é obrigatória quando 'Cabe ED'.")
        valid = False

    if ed_status == "Não cabe ED":
        if not recurso_choice.strip():
            st.error("O campo Recurso é obrigatório (se 'Outro', especifique).")
            valid = False
        if not justificativa_recurso.strip():
            st.error("A justificativa para o recurso é obrigatória.")
            valid = False
        if isenta_deposito == "Não" and valor_deposito == 0.0:
            st.error("Valor do depósito recursal é obrigatório (se não isento).")
            valid = False
        if isenta_custas == "Não" and valor_custas == 0.0:
            st.error("Valor das custas processuais é obrigatório (se não isento).")
            valid = False
        if (isenta_deposito == "Não" or isenta_custas == "Não"):
            if not local_guias.strip():
                st.error("O campo 'Local/pasta onde foram salvas' é obrigatório quando há guias.")
                valid = False

    if not valid:
        st.stop()

    # Processamento da Tabela de Pedidos
    pedidos_formatados = parse_and_format_report(texto_tabela)
    prazos_text = format_prazos(st.session_state["prazos"])

    # Monta os tópicos visíveis de forma dinâmica
    sections = []
    sections.append(("Resultado da Sentença/Acórdão",
                     f"- Resultado: {resultado_sentenca}\n- Observações: {obs_sentenca}"))
    sections.append(("Tabela de Pedidos", pedidos_formatados))
    sections.append(("Embargos de Declaração (ED)",
                     f"- Opção: {ed_status}\n- Justificativa: {justificativa_ed}"))
    
    if ed_status == "Não cabe ED":
        sections.append(("Recurso",
                         f"- Recomendação: {recurso_choice}\n- Justificativa: {justificativa_recurso}"))
        deposito_str = f"R$ {valor_deposito:.2f}" if isenta_deposito == "Não" else "Isento"
        custas_str = f"R$ {valor_custas:.2f}" if isenta_custas == "Não" else "Isento"
        sections.append(("Custas e Depósito Recursal",
                         f"- Parte isenta de depósito recursal: {isenta_deposito}\n"
                         f"- Valor do depósito recursal: {deposito_str}\n"
                         f"- Parte isenta de custas processuais: {isenta_custas}\n"
                         f"- Valor das custas processuais: {custas_str}"))
        if isenta_deposito == "Não" or isenta_custas == "Não":
            sections.append(("Guias",
                             f"- Status: {guias_status}\n- Local/pasta: {make_hyperlink(local_guias.strip())}"))
    
    sections.append(("Prazos e Observações", prazos_text))
    sections.append(("Observações Finais", obs_finais))
    
    final_text = generate_final_text(sections)
    st.subheader("Texto Gerado")
    st.text_area("Copie o texto abaixo:", final_text, height=400)
    st.success("Texto gerado com sucesso! Agora é só copiar e enviar no workflow interno.")
