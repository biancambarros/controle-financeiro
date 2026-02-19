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
            "Favorecido": get_prop_safe(p.get("Favorecido"), "people"),
            "Parcela": get_prop_safe(p.get("Parcela"), "rich_text")
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')
        df['Macro_Grupo'] = df['Tipo'].map(lambda x: MACRO_CATEGORY_MAP.get(x, 'Outros'))
    return df

# --- COMPONENTES VISUAIS ---

def render_bank_treemap(df_mes):
    df_banco = df_mes[df_mes['Valor'] < 0].groupby('Banco')['Valor'].sum().abs().reset_index()
    fig = px.treemap(df_banco, path=['Banco'], values='Valor', title="Gastos por Instituição", color='Valor', height=275, color_continuous_scale='Blues')
    fig.update_traces(textinfo="label+text", texttemplate="<b>%{label}</b><br>R$ %{value:,.2f}")
    fig.update_traces(textfont_size=14)
    fig.update_layout(legend=dict(font=dict(size=16)))
    fig.update_layout(title={'font': {'size': 24}})
    fig.update_layout(coloraxis_showscale=False, margin=dict(t=50, l=10, r=10, b=10))
    return fig

def render_saude(df_mes):
    c1, c2 = st.columns(2)
    with c1:
        entradas = df_mes[(df_mes['Valor'] > 0) & (df_mes['Tipo'] != "Pagamento de cartão")]['Valor'].sum()
        saidas = df_mes[(df_mes['Valor'] < 0) & (~df_mes['Tipo'].str.contains("Investiment", case=False)) & (df_mes['Tipo'] != "Pagamento de cartão")]['Valor'].abs().sum()
        taxa = ((entradas - saidas) / entradas * 100) if entradas > 0 else 0
        fig = px.pie(names=['Poupado', 'Gasto'], values=[max(0, entradas-saidas), saidas], hole=0.6, height=325, title="Fluxo de Caixa Líquido")
        fig.add_annotation(text=f"{taxa:.1f}%", x=0.5, y=0.5, showarrow=False, font_size=30)
        fig.update_traces(textfont_size=16)
        fig.update_layout(legend=dict(font=dict(size=16), orientation="v", yanchor="middle", y=0.5, xanchor="left", x=-0.2))
        fig.update_layout(title={'font': {'size': 24}})
        st.plotly_chart(fig, use_container_width=True, key="pie_saude")
        st.plotly_chart(render_bank_treemap(df_mes), use_container_width=True, key="tree_banco")

    with c2:
        # Busca por "Imóveis" OU "Renda fixa" (ignora maiúsculas/minúsculas)
        df_inv = df_mes[df_mes['Tipo'].str.contains("Imóveis|Renda fixa", case=False, na=False)]
        st.subheader(f"Investimentos: R$ {df_inv['Valor'].sum():,.2f}")
        if not df_inv.empty:
            st.dataframe(df_inv[['Data', 'Transação', 'Valor']], hide_index=True)
        
        filtro_saidas = ((df_mes['Valor'] < 0) & (~df_mes['Tipo'].str.contains("Investiment", case=False)) & (df_mes['Tipo'] != "Pagamento de cartão"))
        st.subheader(f"Gastos: R$ {df_mes[filtro_saidas]['Valor'].abs().sum():,.2f}")
        df_audit = df_mes[filtro_saidas][['Data', 'Transação', 'Valor', 'Tipo']].sort_values('Data')
        df_audit['Data'] = df_audit['Data'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_audit, use_container_width=True, hide_index=True)

def render_historico(df):
    df_anual = df.groupby('Mes_Pagamento', observed=True)['Valor'].sum().reset_index()
    df_anual['Mes_Pagamento'] = pd.Categorical(df_anual['Mes_Pagamento'], categories=MONTHS_ORDER, ordered=True)
    fig = px.bar(df_anual.sort_values('Mes_Pagamento'), x='Mes_Pagamento', y='Valor', color='Valor', color_continuous_scale='RdYlGn')
    st.plotly_chart(fig, use_container_width=True, key="hist_anual")
    
    c1, c2 = st.columns(2)
    with c1:
        df_ent = df[(df['Valor'] > 0) & (df['Tipo'] != "Pagamento de cartão")]
        if not df_ent.empty:
            fig_ent = px.sunburst(df_ent, path=['Banco', 'Tipo'], values='Valor', title="Rendimentos (Anual)")
            st.plotly_chart(fig_ent, use_container_width=True, key="sun_ent")
    with c2:
        df_sai = df[(df['Valor'] < 0) & (df['Tipo'] != "Pagamento de cartão")].copy()
        df_sai['Valor_Abs'] = df_sai['Valor'].abs()
        if not df_sai.empty:
            fig_sai = px.sunburst(df_sai, path=['Banco', 'Tipo'], values='Valor_Abs', title="Gastos (Anual)")
            st.plotly_chart(fig_sai, use_container_width=True, key="sun_sai")

def render_raiox(df):
    df_gastos = df[(df['Valor'] < 0) & (~df['Tipo'].str.contains("Investiment", case=False)) & (df['Tipo'] != "Pagamento de cartão")].copy()
    df_gastos['Valor_Abs'] = df_gastos['Valor'].abs()
    
    col1, col2 = st.columns(2)
    with col1:
        df_evol = df_gastos.groupby(['Mes_Pagamento', 'Macro_Grupo'], observed=True)['Valor_Abs'].sum().reset_index()
        df_evol['Mes_Pagamento'] = pd.Categorical(df_evol['Mes_Pagamento'], categories=MONTHS_ORDER, ordered=True)
        fig = px.bar(df_evol.sort_values('Mes_Pagamento'), x='Mes_Pagamento', y='Valor_Abs', color='Macro_Grupo', barmode='stack')
        st.plotly_chart(fig, use_container_width=True, key="bar_raiox")
    
    with col2:
        sel_macro = st.selectbox("Grupo:", sorted(df_gastos['Macro_Grupo'].unique()), key="sel_macro")
        sel_mes = st.selectbox("Mês:", ["Todos"] + MONTHS_ORDER, key="sel_mes_raiox")
        df_d = df_gastos[df_gastos['Macro_Grupo'] == sel_macro]
        if sel_mes != "Todos": df_d = df_d[df_d['Mes_Pagamento'] == sel_mes]
        if not df_d.empty:
            st.plotly_chart(px.sunburst(df_d, path=['Tipo', 'Transação'], values='Valor_Abs', height=500), use_container_width=True, key="sun_raiox")

    st.divider()
    df_fav = df_gastos[df_gastos['Favorecido'] != "N/A"].groupby('Favorecido')['Valor_Abs'].sum().nlargest(10).reset_index()
    fig_fav = px.bar(df_fav.sort_values('Valor_Abs'), x='Valor_Abs', y='Favorecido', orientation='h', title="Top 10 Favorecidos")
    st.plotly_chart(fig_fav, use_container_width=True, key="top_fav")

def render_projeções_completo(df):
    st.header("🔮 Projeções Futuras")
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
                projections.append({
                    'Mes': MONTHS_ORDER[(current_month_idx + i) % 12],
                    'Valor': abs(row['Valor']), 'Transação': row['Transação'], 'Banco': row['Banco']
                })
        except: continue
    
    df_proj = pd.DataFrame(projections)
    df_proj['Mes'] = pd.Categorical(df_proj['Mes'], categories=MONTHS_ORDER, ordered=True)
    
    fig_line = px.line(df_proj.groupby('Mes', observed=True)['Valor'].sum().reset_index(), x='Mes', y='Valor', title="Custo Fixo Futuro", markers=True)
    st.plotly_chart(fig_line, use_container_width=True, key="line_proj")
    
    mes_sel = st.selectbox("Detalhar mês futuro:", df_proj['Mes'].unique(), key="sel_mes_proj")
    st.dataframe(df_proj[df_proj['Mes'] == mes_sel].sort_values('Valor', ascending=False), hide_index=True, use_container_width=True)

# --- MAIN ---
def main():
    st.title("Controle Financeiro")
    client = NotionClient()
    with st.spinner("Sincronizando..."):
        df = process_data(client.fetch_all_pages())

    if df.empty:
        st.warning("Sem dados.")
        return

    tabs = st.tabs(["📊 Saúde", "📈 Histórico", "🏢 Raio-X", "🔮 Projeções"])

    with tabs[0]:
        meses_disp = [m for m in MONTHS_ORDER if m in df['Mes_Pagamento'].unique()]
        mes_atual = MONTHS_ORDER[datetime.datetime.now().month - 1]
        idx = meses_disp.index(mes_atual) if mes_atual in meses_disp else 0
        mes_sel = st.selectbox("Mês:", meses_disp, index=idx, key="sel_mes_saude")
        render_saude(df[df['Mes_Pagamento'] == mes_sel])

    with tabs[1]: render_historico(df)
    with tabs[2]: render_raiox(df)
    with tabs[3]: render_projeções_completo(df)

if __name__ == "__main__":
    if check_password(): main()
