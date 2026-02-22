import datetime
import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# --- CONSTANTES ---
MONTHS_ORDER = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

MACRO_CATEGORY_MAP = {
    "Remuneração": "Rendas", "Cashback": "Rendas", "Rendimento": "Rendas", "Adicional": "Rendas",
    "Moradia": "Despesas essenciais", "Contas residenciais": "Despesas essenciais",
    "Supermercado": "Despesas essenciais", "Transporte": "Despesas essenciais",
    "TV / Internet / Telefone": "Despesas essenciais", "Pets": "Despesas essenciais",
    "Filhos": "Despesas essenciais", "Medicamentos": "Despesas essenciais",
    "Plano de saúde": "Despesas essenciais", "Nutrição e atividade física": "Despesas essenciais",
    "Cuidados médicos ou psicológicos": "Despesas essenciais", "Trabalho": "Despesas essenciais",
    "Educação": "Despesas essenciais", "Previdência": "Despesas essenciais",
    "Reforma": "Gastos não essenciais", "Bares / Restaurantes / Delivery": "Gastos não essenciais",
    "Móveis e eletrodomésticos": "Gastos não essenciais", "Decoração e jardinagem": "Gastos não essenciais",
    "Eletrônicos": "Gastos não essenciais", "Vestuário": "Gastos não essenciais",
    "Estética": "Gastos não essenciais", "Lazer": "Gastos não essenciais",
    "Presentes": "Gastos não essenciais", "Doações": "Gastos não essenciais",
    "Viagens": "Gastos não essenciais", "Imóveis": "Investimentos", "Renda fixa": "Investimentos",
    "Imposto de renda": "Impostos e taxas", "Impostos municipais": "Impostos e taxas",
    "Taxas bancárias": "Impostos e taxas"
}

MAPA_CORES_MACRO = {
    "Despesas essenciais": "#F4A261",    # Laranja Areia Vivo (era o terracota apagado)
    "Gastos não essenciais": "#EF476F",  # Rosa/Melancia Vibrante (era o rosa sóbrio)
    "Investimentos": "#9D4EDD",          # Roxo Lavanda Brilhante (era o roxo ameixa fechado)
    "Impostos e taxas": "#8D99AE"        # Cinza Metálico/Azulado (mais limpo que o cinza puro)
}

MAPA_CORES_RENDAS = {
    "Remuneração": "#3A86FF",       
    "Adicional": "#3A86FF",         
    "Rendimento": "#9D4EDD",        
    "Cashback": "#9D4EDD",          
    "Renda fixa": "#9D4EDD",        
    "Plano de saúde": "#06D6A0",    
}

SALDO_INICIAL_RENDA_FIXA = float(st.secrets.get("SALDO_INICIAL_RENDA_FIXA", 0.00))
DIVIDA_ATUAL_CASA = float(st.secrets.get("DIVIDA_ATUAL_CASA", 0.00))
DIVIDA_ATUAL_TERRENO = float(st.secrets.get("DIVIDA_ATUAL_TERRENO", 0.00))

METAS_CUSTOS = {
    "Despesas essenciais": float(st.secrets.get("META_ESSENCIAIS", 0.00)),
    "Gastos não essenciais": float(st.secrets.get("META_NAO_ESSENCIAIS", 0.00)),
    "Impostos e taxas": float(st.secrets.get("META_IMPOSTOS", 0.00))
}

META_INVESTIMENTOS = float(st.secrets.get("META_INVESTIMENTOS", 0.00))

st.set_page_config(page_title="💲 Dashboard Financeiro", layout="wide")


# --- AUTENTICAÇÃO ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True
    def password_entered():
        if st.session_state["password_input"] == st.secrets["SENHA_ACESSO"]:
            st.session_state.password_correct = True
            del st.session_state["password_input"]
        else:
            st.error("😕 Senha incorreta.")
    st.text_input("🔒 Senha:", type="password", key="password_input", on_change=password_entered)
    return False


# --- DADOS ---
class NotionClient:
    def __init__(self):
        self.token = st.secrets["NOTION_TOKEN"]
        self.db_id = st.secrets["DATABASE_ID"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

    @st.cache_data(ttl=600)
    def fetch_all_pages(_self):
        url = f"https://api.notion.com/v1/databases/{_self.db_id}/query"
        all_pages, has_more, next_cursor = [], True, None
        while has_more:
            payload = {"start_cursor": next_cursor} if next_cursor else {}
            response = requests.post(url, json=payload, headers=_self.headers)
            if response.status_code != 200: raise Exception(f"Erro Notion: {response.text}")
            data = response.json()
            all_pages.extend(data.get("results", []))
            has_more, next_cursor = data.get("has_more", False), data.get("next_cursor")
        return all_pages

def get_prop_safe(prop, p_type):
    if not prop: return "N/A"
    try:
        if p_type == "select": return prop["select"]["name"] if prop["select"] else "N/A"
        if p_type == "people": return prop["people"][0]["name"] if prop["people"] else "N/A"
        if p_type == "rich_text": return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else "N/A"
        if p_type == "formula": return prop["formula"].get("string", "N/A")
        if p_type == "title": return prop["title"][0]["plain_text"] if prop["title"] else "Sem Título"
        if p_type == "number": return prop.get("number", 0) or 0
    except: return "N/A"
    return "N/A"

def process_data(results):
    rows = []
    for page in results:
        p = page["properties"]
        rows.append({
            "Data": get_prop_safe(p.get("Data"), "formula"),
            "Banco": get_prop_safe(p.get("Banco"), "select"),
            "Transação": get_prop_safe(p.get("Transação"), "title"),
            "Valor": get_prop_safe(p.get("Valor"), "number") * -1,
            "Tipo": get_prop_safe(p.get("Tipo de despesa"), "select"),
            "Mes_Pagamento": get_prop_safe(p.get("Mês de pagamento"), "select"),
            "Favorecido": get_prop_safe(p.get("Favorecido"), "rich_text"),
            "Descrição": get_prop_safe(p.get("Descrição"), "rich_text"),
            "Parcela": get_prop_safe(p.get("Parcela"), "rich_text")
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')
        df['Macro_Grupo'] = df['Tipo'].map(lambda x: MACRO_CATEGORY_MAP.get(x, 'Outros'))
    return df

def formata_br(valor):
    """Converte float americano para string no padrão PT-BR."""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- COMPONENTES VISUAIS ---
def render_bank_treemap(df_gastos_filtrado):
    df_banco = df_gastos_filtrado.groupby('Banco')['Valor'].sum().abs().reset_index()
    
    fig = px.treemap(df_banco, path=['Banco'], values='Valor', title="Custos por Instituição", color='Valor', height=275, color_continuous_scale='Reds')
    fig.update_traces(textinfo="label+text", texttemplate="<b>%{label}</b><br>R$ %{value:,.2f}", textfont_size=14)
    fig.update_layout(coloraxis_showscale=False, margin=dict(t=50, l=10, r=10, b=10))
    fig.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
    fig.update_layout(separators=",.")
    return fig

def render_saude(df_mes):
    c1, c2 = st.columns(2)
    
    # Calculamos os gastos reais apenas UMA vez para todo o painel
    filtro_saidas = (
        (df_mes['Valor'] < 0) & 
        (df_mes['Macro_Grupo'] != "Investimentos") & 
        (~df_mes['Tipo'].astype(str).str.contains("Pagamento de cartão", case=False, na=False))
    )
    df_gastos_reais = df_mes[filtro_saidas].copy()
    
    # O total matemático exato que deve bater em todos os lugares
    total_gastos = df_gastos_reais['Valor'].abs().sum()

    with c1:
        # 1. Entradas reais (agora EXCLUÍMOS os investimentos para não somar resgate como se fosse salário)
        entradas_comuns = df_mes[
            (df_mes['Valor'] > 0) & 
            (df_mes['Macro_Grupo'] != "Investimentos") & 
            (~df_mes['Tipo'].astype(str).str.contains("Pagamento de cartão", case=False, na=False))
        ]['Valor'].sum()
        
        # 2. O Saldo Líquido de Investimentos (Aportes negativos + Resgates positivos)
        saldo_investimentos = df_mes[df_mes['Macro_Grupo'] == "Investimentos"]['Valor'].sum()
        
        if saldo_investimentos < 0:
            # Aportou mais do que resgatou (dinheiro efetivamente virou patrimônio)
            total_investido = abs(saldo_investimentos)
            entradas_totais = entradas_comuns
        else:
            # Resgatou mais do que aportou (o saldo extra volta para compor o caixa do mês)
            total_investido = 0
            entradas_totais = entradas_comuns + saldo_investimentos
            
        # 3. Sobra Livre na Conta
        sobra_livre = entradas_totais - total_gastos - total_investido
        
        # 4. Taxa de Poupança real (Tudo que não virou fumaça / Total que entrou)
        valor_poupado = sobra_livre + total_investido
        taxa = (valor_poupado / entradas_totais * 100) if entradas_totais > 0 else 0
        
        # 5. Configuração do Gráfico com a paleta de tons sóbrios
        categorias_pizza = ['Sobra na Conta', 'Investimentos', 'Custos']
        valores_pizza = [max(0, sobra_livre), total_investido, total_gastos]
        
        mapa_de_cores = {
            'Sobra na Conta': '#06D6A0',  # O Verde vivo
            'Investimentos': '#9D4EDD',   # O Roxo brilhante
            'Custos': '#EF476F'           # O Rosa vibrante
        }


        fig = px.pie(
            names=categorias_pizza, 
            values=valores_pizza, 
            color=categorias_pizza,
            color_discrete_map=mapa_de_cores,
            hole=0.6, 
            height=325, 
            title="<b>Fluxo de Caixa Líquido</b>"
        )
        
        fig.add_annotation(text=f"{taxa:.1f}%", x=0.5, y=0.5, showarrow=False, font_size=30)
        
        fig.update_layout(
            legend=dict(
                orientation="v",
                yanchor="top", 
                y=1.0, 
                xanchor="left", 
                x=0.0,
                font=dict(size=16)
            ),
            title_font=dict(size=24, family="sans-serif"), 
            title_x=0,
            separators=",."
        )
        fig.update_traces(textfont_size=16)
        
        st.plotly_chart(fig, use_container_width=True, key="pie_saude")
        st.plotly_chart(render_bank_treemap(df_gastos_reais), use_container_width=True, key="tree_banco")

    with c2:
        # === INVESTIMENTOS (Corrigido) ===
        # Adicione o .copy() para evitar avisos do Pandas ao modificar a coluna
        df_inv = df_mes[df_mes['Macro_Grupo'] == "Investimentos"].copy() 
        
        saldo_inv = df_inv['Valor'].sum()
        saldo_inv = saldo_inv * -1
        st.subheader(f"Investimentos: R$ {formata_br(saldo_inv)}")
        
        if not df_inv.empty:
            # Formata a data igual à tabela de gastos
            df_inv['Data'] = df_inv['Data'].dt.strftime('%d/%m/%Y')
            df_inv['Valor'] = df_inv['Valor'].apply(formata_br)
            st.dataframe(df_inv[['Data', 'Transação', 'Valor', 'Tipo']].sort_values('Data'), hide_index=True)
        
        # === CUSTOS ===
        st.subheader(f"Custos: R$ {formata_br(total_gastos)}")
        df_audit = df_gastos_reais[['Data', 'Transação', 'Valor', 'Tipo']].sort_values('Data')
        df_audit['Data'] = df_audit['Data'].dt.strftime('%d/%m/%Y')
        df_audit['Valor'] = df_audit['Valor'].apply(formata_br)
        st.dataframe(df_audit, use_container_width=True, hide_index=True)

def render_historico(df):
    df_anual = df.groupby('Mes_Pagamento', observed=True)['Valor'].sum().reset_index()
    df_anual['Mes_Pagamento'] = pd.Categorical(df_anual['Mes_Pagamento'], categories=MONTHS_ORDER, ordered=True)
    fig = px.bar(df_anual.sort_values('Mes_Pagamento'), x='Mes_Pagamento', y='Valor', title='Saldos mensais', color='Valor', color_continuous_scale='RdYlGn')
    fig.update_traces(hovertemplate="Mês: %{x}<br>Saldo: R$ %{y:,.2f}<extra></extra>")
    fig.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
    fig.update_layout(separators=",.")
    st.plotly_chart(fig, use_container_width=True, key="hist_anual")
    
    c1, c2 = st.columns(2)
    with c1:
        df_ent = df[(df['Valor'] > 0) & (df['Tipo'] != "Pagamento de cartão")]
        if not df_ent.empty:
            # Adicionada a coluna 'Transação' ao path
            fig_ent = px.sunburst(
                df_ent, 
                path=['Tipo', 'Descrição'], 
                values='Valor', 
                color='Tipo',                        # O Plotly vai olhar para o Tipo para pintar
                color_discrete_map=MAPA_CORES_RENDAS,# Passamos a nossa paleta de rendas
                title="Rendimentos neste ano",
                height=800
            )
            # Formatação de 2 casas decimais para o Sunburst
            fig_ent.update_traces(hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>")
            fig_ent.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
            fig_ent.update_layout(separators=",.")
            st.plotly_chart(fig_ent, use_container_width=True, key="sun_ent")
    
    with c2:
        df_sai = df[(df['Valor'] < 0) & (df['Tipo'] != "Pagamento de cartão")].copy()
        df_sai['Valor_Abs'] = df_sai['Valor'].abs()
        if not df_sai.empty:
            # --- MUDANÇA AQUI: O path agora define o centro como Macro_Grupo e a borda como Tipo ---
            fig_sai = px.sunburst(
                df_sai, 
                path=['Macro_Grupo', 'Tipo'], 
                values='Valor_Abs', 
                color='Macro_Grupo',                  # Dizemos que a cor baseia-se no Macro_Grupo
                color_discrete_map=MAPA_CORES_MACRO,  # Passamos a nossa paleta
                title="<b>Custos neste ano</b>",
                height=800
            )
            # Formatação de 2 casas decimais para o Sunburst
            fig_sai.update_traces(hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>")
            fig_sai.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
            fig_sai.update_layout(separators=",.")
            st.plotly_chart(fig_sai, use_container_width=True, key="sun_sai")

def render_raiox(df):
    df_gastos = df[(df['Valor'] < 0) & (~df['Tipo'].str.contains("Investiment", case=False)) & (~df['Tipo'].astype(str).str.contains("Pagamento de cartão", case=False, na=False))].copy()
    df_gastos['Valor_Abs'] = df_gastos['Valor'].abs()
    
    col1, col2 = st.columns(2)
    with col1:
        df_evol = df_gastos.groupby(['Mes_Pagamento', 'Macro_Grupo'], observed=True)['Valor_Abs'].sum().reset_index()
        df_evol['Mes_Pagamento'] = pd.Categorical(df_evol['Mes_Pagamento'], categories=MONTHS_ORDER, ordered=True)
        
        # Gráfico Empilhado
        fig = px.bar(
            df_evol.sort_values('Mes_Pagamento'), 
            x='Mes_Pagamento', 
            y='Valor_Abs', 
            color='Macro_Grupo', 
            barmode='stack',
            color_discrete_map=MAPA_CORES_MACRO,
            title="<b>Evolução dos Custos por Grupo</b>"
        )
        fig.update_traces(hovertemplate="Grupo: %{fullData.name}<br>Valor: R$ %{y:,.2f}<extra></extra>")
        fig.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
        fig.update_layout(separators=",.", xaxis_title=None, yaxis_title="Valor (R$)")
        st.plotly_chart(fig, use_container_width=True, key="bar_raiox")
    
    with col2:
        sel_macro = st.selectbox("Grupo:", sorted(df_gastos['Macro_Grupo'].unique()), key="sel_macro")
        sel_mes = st.selectbox("Mês:", ["Todos os meses (soma anual)"] + MONTHS_ORDER, key="sel_mes_raiox")
        
        df_d = df_gastos[df_gastos['Macro_Grupo'] == sel_macro].copy()
        if sel_mes != "Todos os meses (soma anual)": 
            df_d = df_d[df_d['Mes_Pagamento'] == sel_mes]
            
        if not df_d.empty:
            # O TRUQUE DO DEGRADÊ: 
            # 1. O path começa no Macro_Grupo
            # 2. Usamos color_discrete_sequence para passar a cor exata do macro.
            # O Plotly automaticamente gera o degradê para as fatias filhas!
            fig_sun = px.sunburst(
                df_d, 
                path=['Macro_Grupo', 'Tipo', 'Transação'],
                values='Valor_Abs', 
                color_discrete_sequence=[MAPA_CORES_MACRO[sel_macro]],
                title=f"<b>{sel_macro} em {sel_mes}</b>",
                height=500
            )
            fig_sun.update_traces(
                hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>",
                root_color="white" # 3. Deixa SOMENTE a primeira camada (Macro_Grupo) com fundo branco
            )
            fig_sun.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
            fig_sun.update_layout(separators=",.", margin=dict(t=60, l=10, r=10, b=10))
            st.plotly_chart(fig_sun, use_container_width=True, key="sun_raiox")

    st.divider()
    
    # Filtros de Favorecido
    meu_nome = st.secrets.get("MEU_NOME", "Usuario") # Puxa do cofre seguro
    
    filtros_fav = (
        (df_gastos['Favorecido'] != "N/A") & 
        (~df_gastos['Favorecido'].str.contains(meu_nome, case=False, na=False)) &
        (~df_gastos['Favorecido'].str.contains("Cartão|Cartao", case=False, na=False)) &
        (~df_gastos['Tipo'].str.contains("Pagamento de cartão", case=False, na=False))
    )
    
    df_fav = df_gastos[filtros_fav].groupby('Favorecido')['Valor_Abs'].sum().nlargest(10).reset_index()
    
    if df_fav.empty:
        st.info("Nenhum 'Favorecido' preenchido nos registros para gerar o ranking após os filtros.")
    else:
        # Top 10 Favorecidos com Degradê
        fig_fav = px.bar(
            df_fav.sort_values('Valor_Abs'), 
            x='Valor_Abs', 
            y='Favorecido', 
            orientation='h', 
            color='Valor_Abs', # Ativa o degradê de intensidade
            color_continuous_scale=["#FFD6E0", "#EF476F", "#8A0A2A"], 
            text='Valor_Abs',  
            title="<b>Top 10 Maiores Favorecidos neste ano</b>",
            height=600         
        )
        
        fig_fav.update_traces(
            texttemplate="<b>R$ %{text:,.2f}</b>", 
            textposition="inside",
            textfont_size=16,                      
            hovertemplate="Favorecido: %{y}<br>Total: R$ %{x:,.2f}<extra></extra>"
        )
        
        fig_fav.update_layout(
            title_font=dict(size=24, family="sans-serif"), 
            title_x=0,
            coloraxis_showscale=False,              
            yaxis=dict(tickfont=dict(size=16)),     
            xaxis=dict(tickfont=dict(size=14))
        )
        fig_fav.update_layout(separators=",.", xaxis_title=None, yaxis_title=None)
        
        st.plotly_chart(fig_fav, use_container_width=True, key="top_fav")
        
def render_projeções_completo(df):
    #st.header("🔮 Projeções Futuras")
    df_parcelas = df[df['Parcela'].astype(str).str.contains('/')].copy()
    if df_parcelas.empty:
        st.info("Nenhuma parcela detectada.")
        return

    projections = []
    current_month_idx = datetime.datetime.now().month - 1
    for _, row in df_parcelas.iterrows():
        try:
            atual, total = map(int, row['Parcela'].split('/'))
            for i in range(total - atual + 1):
                # 1. Calcula a parcela exata do mês projetado
                parcela_calculada = f"{atual + i}/{total}"
                
                projections.append({
                    'Mes': MONTHS_ORDER[(current_month_idx + i) % 12],
                    'Valor': abs(row['Valor']), 
                    'Transação': row['Transação'], 
                    'Banco': row['Banco'],
                    'Parcela': parcela_calculada # <--- Adicionando à tabela
                })
        except: continue
    
    df_proj = pd.DataFrame(projections)
    df_proj['Mes'] = pd.Categorical(df_proj['Mes'], categories=MONTHS_ORDER, ordered=True)
    
    # 2. Gráfico de Linha na cor vermelha/vibrante da paleta
    fig_line = px.line(
        df_proj.groupby('Mes', observed=True)['Valor'].sum().reset_index(), 
        x='Mes', 
        y='Valor', 
        title="<b>Custo Fixo Futuro</b>", 
        markers=True,
        color_discrete_sequence=["#EF476F"] # <--- Forçando a cor aqui
    )
    fig_line.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
    fig_line.update_layout(separators=",.")
    st.plotly_chart(fig_line, use_container_width=True, key="line_proj")
    
    mes_sel = st.selectbox("Detalhar mês futuro:", df_proj['Mes'].unique(), key="sel_mes_proj")
    
    # 3. Filtrando o mês selecionado e aplicando formato brasileiro no valor
    df_show = df_proj[df_proj['Mes'] == mes_sel].sort_values('Valor', ascending=False).copy()
    df_show['Valor'] = df_show['Valor'].apply(formata_br)
    
    # Exibindo a tabela com a coluna 'Parcela' visível e na ordem mais lógica
    st.dataframe(df_show[['Transação', 'Banco', 'Parcela', 'Valor']], hide_index=True, use_container_width=True)

def render_metas(df):
    meses_disp = [m for m in MONTHS_ORDER if m in df['Mes_Pagamento'].unique()]
    mes_atual = MONTHS_ORDER[datetime.datetime.now().month - 1]
    idx = meses_disp.index(mes_atual) if mes_atual in meses_disp else 0
    idx = idx - 1
    mes_sel = st.selectbox("Mês de Avaliação:", meses_disp, index=idx, key="sel_mes_metas")
    
    df_mes = df[df['Mes_Pagamento'] == mes_sel].copy()

    # --- 1. INVESTIMENTOS ---
    st.subheader("📈 Meta de Investimentos")
    
    saldo_investimentos = df_mes[df_mes['Macro_Grupo'] == "Investimentos"]['Valor'].sum()
    total_investido = abs(saldo_investimentos) if saldo_investimentos < 0 else 0
    
    # Cálculo do delta de investimentos
    diff_inv = total_investido - META_INVESTIMENTOS 
    percent_inv = (total_investido / META_INVESTIMENTOS) * 100 if META_INVESTIMENTOS > 0 else 0
    
    # Correção: Forçando o sinal de menos no início absoluto da string para o Streamlit entender
    if diff_inv < 0:
        delta_inv_str = f"-R$ {formata_br(abs(diff_inv))} (Abaixo da meta)"
    else:
        delta_inv_str = f"R$ {formata_br(diff_inv)} (Acima da meta)"
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Alvo Mensal", f"R$ {formata_br(META_INVESTIMENTOS)}")
    
    # Agora o Streamlit vai ver o "-" na frente e pintar de vermelho com a seta para baixo!
    c2.metric("Realizado", f"R$ {formata_br(total_investido)}", delta=delta_inv_str, delta_color="normal")
    c3.metric("Atingimento", f"{percent_inv:.1f}%")
    
    st.progress(min(percent_inv / 100, 1.0))

    st.divider()
    
    # --- 2. CUSTOS ---
    st.subheader("🛑 Orçamento e Teto de Gastos")
    
    filtro_saidas = (
        (df_mes['Valor'] < 0) & 
        (df_mes['Macro_Grupo'] != "Investimentos") & 
        (~df_mes['Tipo'].astype(str).str.contains("Pagamento de cartão", case=False, na=False))
    )
    df_gastos = df_mes[filtro_saidas]
    
    col_list = st.columns(len(METAS_CUSTOS))
    dados_grafico = []
    
    for i, (cat, meta_valor) in enumerate(METAS_CUSTOS.items()):
        gasto_real = df_gastos[df_gastos['Macro_Grupo'] == cat]['Valor'].abs().sum()
        
        # Lógica rigorosa de Sobra e Estouro
        if gasto_real <= meta_valor:
            sobra_real = meta_valor - gasto_real
            delta_string = f"R$ {formata_br(sobra_real)} (Sobra)"
            
            # Para o gráfico empilhado
            dados_grafico.append({"Categoria": cat, "Tipo": "Gasto dentro da meta", "Valor": gasto_real})
            dados_grafico.append({"Categoria": cat, "Tipo": "Folga (Disponível)", "Valor": sobra_real})
            dados_grafico.append({"Categoria": cat, "Tipo": "Estouro", "Valor": 0})
        else:
            estouro = gasto_real - meta_valor
            delta_string = f"-R$ {formata_br(estouro)} (Estouro)" # Forçamos o sinal negativo na string
            
            # Para o gráfico empilhado
            dados_grafico.append({"Categoria": cat, "Tipo": "Gasto dentro da meta", "Valor": meta_valor})
            dados_grafico.append({"Categoria": cat, "Tipo": "Folga (Disponível)", "Valor": 0})
            dados_grafico.append({"Categoria": cat, "Tipo": "Estouro", "Valor": estouro})

        with col_list[i]:
            # delta_color="normal" aqui, junto com o sinal negativo na string que forçamos acima,
            # garante que um Estouro fique vermelho apontando para baixo. E a sobra fique verde!
            st.metric(
                label=f"Teto: {cat}", 
                value=f"R$ {formata_br(gasto_real)}", 
                delta=delta_string, 
                delta_color="normal" 
            )
    
    # Gráfico Comparativo Empilhado (Bullet Chart)
    df_plot = pd.DataFrame(dados_grafico)
    
    fig_metas = px.bar(
        df_plot, 
        x='Valor',            # Barras na horizontal costumam ser melhores para orçamentos
        y='Categoria', 
        color='Tipo', 
        barmode='stack',      # Empilhadas!
        orientation='h',
        color_discrete_map={
            "Gasto dentro da meta": "#8D99AE",   # Cinza Metálico (Ok)
            "Folga (Disponível)": "#E2E2E2",     # Cinza muito claro (O espaço vazio da barra)
            "Estouro": "#EF476F"                 # Vermelho Vibrante (O problema)
        },
        title="<b>Orçamento Mensal (Barras de Alerta)</b>",
        height=350
    )
    fig_metas.update_traces(hovertemplate="<b>%{y}</b><br>%{color}: R$ %{x:,.2f}<extra></extra>")
    fig_metas.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
    fig_metas.update_layout(separators=",.", xaxis_title=None, yaxis_title=None)
    fig_metas.update_layout(legend_title_text=None) # Remove o título da legenda pra ficar mais limpo
    
    st.plotly_chart(fig_metas, use_container_width=True, key="bar_metas")

def render_patrimonio(df):
    st.header("🏡 Evolução Patrimonial")
    
    # --- PREPARAÇÃO DE DADOS BASE ---
    # 1. Ativos (Renda Fixa + Rendimentos)
    df_rf = df[df['Tipo'].isin(['Renda fixa', 'Rendimento'])].copy()
    
    # Função blindada para garantir que Resgates diminuam o patrimônio e Aportes/Rendimentos aumentem
    def calcula_impacto_rf(row):
        if row['Tipo'] == 'Rendimento':
            return abs(row['Valor']) # Rendimento: Faz o bolo crescer
        elif row['Tipo'] == 'Renda fixa' and row['Valor'] < 0:
            return abs(row['Valor']) # Aporte: Faz o bolo crescer
        elif row['Tipo'] == 'Renda fixa' and row['Valor'] > 0:
            return -abs(row['Valor']) # Resgate: Tira do bolo
        return 0
        
    if not df_rf.empty:
        df_rf['Impacto'] = df_rf.apply(calcula_impacto_rf, axis=1)
        crescimento_rf_ano = df_rf['Impacto'].sum()
    else:
        df_rf['Impacto'] = 0
        crescimento_rf_ano = 0
        
    saldo_atual_rf = SALDO_INICIAL_RENDA_FIXA + crescimento_rf_ano
    
    # 2. Passivos (Casa)
    df_casa = df[(df['Tipo'] == 'Moradia') & (df['Valor'] < 0)].copy()
    df_casa['Valor_Abs'] = df_casa['Valor'].abs()
    pago_ano_casa = df_casa['Valor_Abs'].sum()
    
    # 3. Passivos (Terreno)
    df_terreno = df[(df['Tipo'] == 'Imóveis') & (df['Valor'] < 0)].copy()
    df_terreno['Valor_Abs'] = df_terreno['Valor'].abs()
    pago_ano_terreno = df_terreno['Valor_Abs'].sum()
    
    # --- GRANDE RESUMO: PATRIMÔNIO LÍQUIDO ---
    # Ativos totais menos a Dívida Real do banco
    patrimonio_liquido = saldo_atual_rf - DIVIDA_ATUAL_CASA - DIVIDA_ATUAL_TERRENO
    
    st.metric(
        label="Patrimônio Líquido Total (Ativos - Dívidas Reais)",
        value=f"R$ {formata_br(patrimonio_liquido)}",
        delta="Atualize os saldos devedores no código para a métrica ser exata",
        delta_color="off"
    )
    
    st.divider()

    # ==========================================
    # 1. ATIVOS (O que te gera dinheiro)
    # ==========================================
    st.subheader("📈 Ativos: Renda Fixa e Rendimentos")
    
    st.metric(
        label="Saldo Acumulado Estimado", 
        value=f"R$ {formata_br(saldo_atual_rf)}", 
        delta=f"R$ {formata_br(crescimento_rf_ano)} (Crescimento líquido no ano)", 
        delta_color="normal"
    )
    
    if not df_rf.empty:
        # Agrupa o impacto (já com os sinais corretos)
        df_evol_rf = df_rf.groupby('Mes_Pagamento', observed=True)['Impacto'].sum().reset_index()
        df_evol_rf['Mes_Pagamento'] = pd.Categorical(df_evol_rf['Mes_Pagamento'], categories=MONTHS_ORDER, ordered=True)
        df_evol_rf = df_evol_rf.sort_values('Mes_Pagamento')
        
        df_evol_rf['Acumulado_Ano'] = df_evol_rf['Impacto'].cumsum()
        df_evol_rf['Saldo_Evolucao'] = SALDO_INICIAL_RENDA_FIXA + df_evol_rf['Acumulado_Ano']
        
        fig_rf = px.area(
            df_evol_rf, 
            x='Mes_Pagamento', 
            y='Saldo_Evolucao', 
            title="<b>Evolução do Saldo (Renda Fixa)</b>", 
            color_discrete_sequence=["#3A86FF"], 
            markers=True
        )
        fig_rf.update_traces(hovertemplate="Mês: %{x}<br>Saldo Acumulado: R$ %{y:,.2f}<extra></extra>")
        fig_rf.update_layout(title_font=dict(size=18, family="sans-serif"), separators=",.", xaxis_title=None, yaxis_title=None)
        
        # Trava o fundo do gráfico para evidenciar o crescimento
        min_y = SALDO_INICIAL_RENDA_FIXA * 0.95 if SALDO_INICIAL_RENDA_FIXA > 0 else 0
        fig_rf.update_yaxes(range=[min_y, max(df_evol_rf['Saldo_Evolucao']) * 1.05])
        st.plotly_chart(fig_rf, use_container_width=True, key="area_rf")

    st.divider()

    # ==========================================
    # 2. PASSIVOS (O que você está pagando)
    # ==========================================
    st.subheader("🛑 Passivos: Esforço de Pagamento")
    st.caption("Como as parcelas incluem juros e taxas, a dívida real difere do valor gasto. O gráfico abaixo mostra o volume total de dinheiro que você já injetou no pagamento este ano (Esforço de Caixa).")
    
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### 🏠 Casa")
        # Cálculo da estimativa sem juros
        saldo_estimado_casa = DIVIDA_ATUAL_CASA - pago_ano_casa
        
        st.metric(
            label="Dívida em Janeiro/2026", 
            value=f"R$ {formata_br(DIVIDA_ATUAL_CASA)}", 
            delta=f"R$ {formata_br(pago_ano_casa)} (Esforço total no ano)", 
            delta_color="normal" # Fica verde porque pagar é um esforço positivo!
        )
        # Novo label com o saldo estimado
        st.caption(f"📉 **Saldo atual estimado (sem juros):** R$ {formata_br(saldo_estimado_casa)}")

        if not df_casa.empty:
            df_evol_casa = df_casa.groupby('Mes_Pagamento', observed=True)['Valor_Abs'].sum().reset_index()
            df_evol_casa['Mes_Pagamento'] = pd.Categorical(df_evol_casa['Mes_Pagamento'], categories=MONTHS_ORDER, ordered=True)
            df_evol_casa = df_evol_casa.sort_values('Mes_Pagamento')
            
            # Gráfico apontando para o Valor_Abs (pagamento mensal exato)
            fig_casa = px.area(
                df_evol_casa, 
                x='Mes_Pagamento', 
                y='Valor_Abs', 
                title="<b>Valor Pago por Mês (Casa)</b>", 
                color_discrete_sequence=["#F4A261"], 
                markers=True
            )
            fig_casa.update_traces(hovertemplate="Mês: %{x}<br>Pago no Mês: R$ %{y:,.2f}<extra></extra>")
            fig_casa.update_layout(title_font=dict(size=16, family="sans-serif"), separators=",.", xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig_casa, use_container_width=True, key="area_casa")

    with c2:
        st.markdown("#### ⛰️ Terreno")
        # Cálculo da estimativa sem juros
        saldo_estimado_terreno = DIVIDA_ATUAL_TERRENO - pago_ano_terreno
        
        st.metric(
            label="Dívida em Janeiro/2026", 
            value=f"R$ {formata_br(DIVIDA_ATUAL_TERRENO)}", 
            delta=f"R$ {formata_br(pago_ano_terreno)} (Esforço total no ano)", 
            delta_color="normal"
        )
        # Novo label com o saldo estimado
        st.caption(f"📉 **Saldo atual estimado (sem juros):** R$ {formata_br(saldo_estimado_terreno)}")

        if not df_terreno.empty:
            df_evol_terreno = df_terreno.groupby('Mes_Pagamento', observed=True)['Valor_Abs'].sum().reset_index()
            df_evol_terreno['Mes_Pagamento'] = pd.Categorical(df_evol_terreno['Mes_Pagamento'], categories=MONTHS_ORDER, ordered=True)
            df_evol_terreno = df_evol_terreno.sort_values('Mes_Pagamento')
            
            # Gráfico apontando para o Valor_Abs (pagamento mensal exato)
            fig_terreno = px.area(
                df_evol_terreno, 
                x='Mes_Pagamento', 
                y='Valor_Abs', 
                title="<b>Valor Pago por Mês (Terreno)</b>", 
                color_discrete_sequence=["#9D4EDD"], 
                markers=True
            )
            fig_terreno.update_traces(hovertemplate="Mês: %{x}<br>Pago no Mês: R$ %{y:,.2f}<extra></extra>")
            fig_terreno.update_layout(title_font=dict(size=16, family="sans-serif"), separators=",.", xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig_terreno, use_container_width=True, key="area_terreno")
    
# --- MAIN ---
def main():
    st.title("Controle Financeiro")
    client = NotionClient()
    with st.spinner("Sincronizando..."):
        df = process_data(client.fetch_all_pages())

    if df.empty:
        st.warning("Sem dados.")
        return

    opcoes_menu = ["🩺 Saúde financeira", "📊 Histórico", "🕵🏻‍♂️ Raio-X de custos", "🔮 Projeções", "🏡 Patrimônio", "🎯 Metas"]
    aba_ativa = st.radio("Navegação", opcoes_menu, horizontal=True, label_visibility="collapsed")
    st.divider()

    if aba_ativa == "🩺 Saúde financeira":
        meses_disp = [m for m in MONTHS_ORDER if m in df['Mes_Pagamento'].unique()]
        mes_atual = MONTHS_ORDER[datetime.datetime.now().month - 1]
        idx = meses_disp.index(mes_atual) if mes_atual in meses_disp else 0
        mes_sel = st.selectbox("Mês:", meses_disp, index=idx, key="sel_mes_saude")
        render_saude(df[df['Mes_Pagamento'] == mes_sel])

    elif aba_ativa == "📊 Histórico":
        render_historico(df)

    elif aba_ativa == "🕵🏻‍♂️ Raio-X de custos":
        render_raiox(df)

    elif aba_ativa == "🔮 Projeções":
        render_projeções_completo(df)
        
    elif aba_ativa == "🎯 Metas":
        render_metas(df)

    elif aba_ativa == "🏡 Patrimônio":
        render_patrimonio(df)
        
if __name__ == "__main__":
    if check_password(): main()
