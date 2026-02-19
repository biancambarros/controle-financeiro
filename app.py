import datetime
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# --- CONSTANTES E CONFIGURAÇÕES ---
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
    "Viagens": "Gastos não essenciais", "Investimentos": "Investimentos",
    "Imposto de renda": "Impostos e taxas", "Impostos municipais": "Impostos e taxas",
    "Taxas bancárias": "Impostos e taxas"
}

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="💲 Dashboard Financeiro", layout="wide")


# --- CAMADA DE AUTENTICAÇÃO ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    def password_entered():
        if st.session_state["password_input"] == st.secrets["SENHA_ACESSO"]:
            st.session_state.password_correct = True
            del st.session_state["password_input"]
        else:
            st.error("😕 Senha incorreta.")

    st.text_input("🔒 Digite a senha:", type="password", key="password_input", on_change=password_entered)
    return False


# --- CAMADA DE DADOS (NOTION API) ---
class NotionClient:
    def __init__(self):
        self.token = st.secrets["NOTION_TOKEN"]
        self.db_id = st.secrets["DATABASE_ID"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    @st.cache_data(ttl=600)
    def fetch_all_pages(_self):
        url = f"https://api.notion.com/v1/databases/{_self.db_id}/query"
        all_pages, has_more, next_cursor = [], True, None

        while has_more:
            payload = {"start_cursor": next_cursor} if next_cursor else {}
            response = requests.post(url, json=payload, headers=_self.headers)
            if response.status_code != 200:
                raise Exception(f"Erro Notion: {response.text}")
            data = response.json()
            all_pages.extend(data.get("results", []))
            has_more, next_cursor = data.get("has_more", False), data.get("next_cursor")
        return all_pages


# --- CAMADA DE LÓGICA DE NEGÓCIO ---
def get_prop_safe(prop, p_type):
    """Extrai valores do Notion de forma segura."""
    if not prop: return "N/A"
    try:
        if p_type == "select": return prop["select"]["name"] if prop["select"] else "N/A"
        if p_type == "people": return prop["people"][0]["name"] if prop["people"] else "N/A"
        if p_type == "rich_text": return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else "N/A"
        if p_type == "formula": return prop["formula"].get("string", "N/A")
        if p_type == "title": return prop["title"][0]["plain_text"] if prop["title"] else "Sem Título"
    except (KeyError, IndexError):
        return "N/A"
    return "N/A"

def process_data(notion_results):
    rows = []
    for page in notion_results:
        p = page["properties"]
        rows.append({
            "Data": get_prop_safe(p.get("Data"), "formula"),
            "Banco": get_prop_safe(p.get("Banco"), "select"),
            "Transação": get_prop_safe(p.get("Transação"), "title"),
            "Valor": (p["Valor"].get("number", 0) or 0) * -1,
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

def get_projections(df):
    df_parcelas = df[df['Parcela'].astype(str).str.contains('/')].copy()
    if df_parcelas.empty: return None

    projections = []
    current_month_idx = datetime.datetime.now().month - 1
    
    for _, row in df_parcelas.iterrows():
        try:
            atual, total = map(int, row['Parcela'].split('/'))
            restantes = total - atual
            for i in range(restantes + 1):
                projections.append({
                    'Mes': MONTHS_ORDER[(current_month_idx + i) % 12],
                    'Valor': abs(row['Valor']),
                    'Transação': row['Transação'],
                    'Banco': row['Banco'],
                    'Parcela_Ref': f"{atual + i}/{total}"
                })
        except: continue

    df_proj = pd.DataFrame(projections)
    if not df_proj.empty:
        df_proj['Mes'] = pd.Categorical(df_proj['Mes'], categories=MONTHS_ORDER, ordered=True)
    return df_proj


# --- CAMADA DE UI (COMPONENTES VISUAIS) ---
def render_metrics_and_charts(df_mes):
    c1, c2 = st.columns(2)
    
    with c1:
        # Fluxo de Caixa
        entradas = df_mes[(df_mes['Valor'] > 0) & (df_mes['Tipo'] != "Pagamento de cartão")]['Valor'].sum()
        saidas = df_mes[(df_mes['Valor'] < 0) & (~df_mes['Tipo'].str.contains("Investiment", case=False)) & (df_mes['Tipo'] != "Pagamento de cartão")]['Valor'].abs().sum()
        taxa = ((entradas - saidas) / entradas * 100) if entradas > 0 else 0
        
        fig_pie = px.pie(names=['Poupado', 'Gasto'], values=[max(0, entradas-saidas), saidas], hole=0.6, title="Fluxo de Caixa Líquido")
        fig_pie.add_annotation(text=f"{taxa:.1f}%", x=0.5, y=0.5, showarrow=False, font_size=30)
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        st.subheader("Investimentos")
        df_inv = df_mes[df_mes['Tipo'].str.contains("Investiment", case=False, na=False)]
        if not df_inv.empty:
            st.metric("Saldo Líquido", f"R$ {df_inv['Valor'].sum():,.2f}")
            st.dataframe(df_inv[['Data', 'Transação', 'Valor']], hide_index=True)
        else:
            st.info("Sem investimentos.")


# --- MAIN APP ---
def main():
    st.title("Controle Financeiro")
    
    client = NotionClient()
    with st.spinner("Sincronizando..."):
        df = process_data(client.fetch_all_pages())

    if df.empty:
        st.warning("Dados não encontrados.")
        return

    tabs = st.tabs(["📊 Saúde", "📈 Histórico", "🏢 Raio-X", "🔮 Projeções"])

    with tabs[0]:
        mes_atual_nome = MONTHS_ORDER[datetime.datetime.now().month - 1]
        meses_disp = df['Mes_Pagamento'].unique().tolist()
        mes_sel = st.selectbox("Mês:", meses_disp, index=meses_disp.index(mes_atual_nome) if mes_atual_nome in meses_disp else 0)
        render_metrics_and_charts(df[df['Mes_Pagamento'] == mes_sel])

    # ... demais abas seguem a mesma lógica de chamar funções de renderização ...

if __name__ == "__main__":
    if check_password():
        main()
