import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard Financeiro - Bianca", layout="wide")

# --- CORE: BUSCA E LIMPEZA DE DADOS ---

def get_property_value(prop):
    if not prop: return "N/A"
    p_type = prop.get("type")
    if p_type == "select": return prop["select"]["name"] if prop["select"] else "N/A"
    elif p_type == "people": return prop["people"][0]["name"] if prop["people"] else "N/A"
    elif p_type == "rich_text": return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else "N/A"
    return "N/A"

@st.cache_data(ttl=600) # Cache de 10 minutos
def fetch_notion_data():
    token = st.secrets["NOTION_TOKEN"]
    db_id = st.secrets["DATABASE_ID"]
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
    
    all_pages = []
    has_more, next_cursor = True, None
    while has_more:
        payload = {"start_cursor": next_cursor} if next_cursor else {}
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200: raise Exception(f"Erro Notion: {response.text}")
        data = response.json()
        all_pages.extend(data.get("results", []))
        has_more, next_cursor = data.get("has_more", False), data.get("next_cursor")
    return all_pages

def process_financial_logic(results):
    rows = []
    for page in results:
        p = page["properties"]
        try:
            rows.append({
                "Data": p["Data"]["date"]["start"] if p["Data"]["date"] else None,
                "Banco": get_property_value(p["Banco"]),
                "Transação": p["Transação"]["title"][0]["plain_text"] if p["Transação"]["title"] else "Sem Título",
                "Valor": (p["Valor"]["number"] or 0) * -1,
                "Tipo": get_property_value(p["Tipo de despesa"]),
                "Mes_Pagamento": get_property_value(p["Mês de pagamento"]),
                "Favorecido": get_property_value(p["Favorecido"]),
                "Parcela": get_property_value(p["Parcela"]) # Captura essencial para projeção
            })
        except: continue
            
    df = pd.DataFrame(rows)
    if not df.empty:
        df['Data'] = pd.to_datetime(df['Data'], utc=True, errors='coerce').dt.tz_localize(None)
    return df

# --- FUNÇÕES DE VISUALIZAÇÃO ---

def plot_macro_evolution(df):
    mapeamento = {
        "Habitação": "Essencial", "Saúde": "Essencial", "Alimentação": "Essencial",
        "Transporte": "Essencial", "Educação": "Essencial", "TV / Internet / Telefone": "Essencial",
        "Assinaturas": "Lifestyle", "Lazer": "Lifestyle", "Cuidados Pessoais": "Lifestyle"
    }
    df['Macro_Grupo'] = df['Tipo'].apply(lambda x: mapeamento.get(x, 'Lifestyle'))
    df_gastos = df[(df['Valor'] < 0) & (~df['Tipo'].isin(["Pagamento de cartão", "Investimento"]))].copy()
    df_gastos['Valor_Abs'] = df_gastos['Valor'].abs()
    
    ordem_meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    df_evol = df_gastos.groupby(['Mes_Pagamento', 'Macro_Grupo'])['Valor_Abs'].sum().reset_index()
    df_evol['Mes_Pagamento'] = pd.Categorical(df_evol['Mes_Pagamento'], categories=ordem_meses, ordered=True)
    
    return px.bar(df_evol.sort_values('Mes_Pagamento'), x='Mes_Pagamento', y='Valor_Abs', color='Macro_Grupo', 
                  title="Evolução de Gastos: Essencial vs Lifestyle", barmode='stack')

# --- APP PRINCIPAL ---

def main():
    st.title("💰 Sistema de Gestão Financeira - Bianca")
    
    with st.spinner("Sincronizando com Notion..."):
        df = process_financial_logic(fetch_notion_data())

    if df.empty:
        st.warning("Nenhum dado encontrado no Notion.")
        return

    tab1, tab2, tab3 = st.tabs(["📊 Visão Mensal", "🏢 Raio-X de Consumo", "🔮 Projeções Futuras"])

    with tab1:
        meses = df['Mes_Pagamento'].unique().tolist()
        mes_sel = st.selectbox("Escolha o mês:", meses)
        df_mes = df[df['Mes_Pagamento'] == mes_sel]
        
        c1, c2 = st.columns(2)
        with c1:
            entradas = df_mes[(df_mes['Valor'] > 0) & (df_mes['Tipo'] != "Pagamento de cartão")]['Valor'].sum()
            saidas = df_mes[(df_mes['Valor'] < 0) & (~df_mes['Tipo'].isin(["Pagamento de cartão", "Investimento"]))]['Valor'].abs().sum()
            taxa = ( (entradas - saidas) / entradas * 100 ) if entradas > 0 else 0
            
            fig = px.pie(names=['Poupado', 'Gasto'], values=[max(0, entradas-saidas), saidas], hole=0.6, title=f"Saúde Financeira: {mes_sel}")
            fig.add_annotation(text=f"{taxa:.1f}%", x=0.5, y=0.5, showarrow=False, font_size=30)
            st.plotly_chart(fig, width='stretch')
        
        with c2:
            st.subheader("Investimentos do Mês")
            st.dataframe(df_mes[df_mes['Tipo'] == "Investimento"][['Transação', 'Valor', 'Banco']], hide_index=True)

    with tab2:
        st.plotly_chart(plot_macro_evolution(df), width='stretch')
        st.plotly_chart(px.sunburst(df[df['Valor']<0], path=['Banco', 'Tipo'], values='Valor', title="Distribuição por Banco"), width='stretch')

    with tab3:
        st.info("Aqui entrará o gráfico de Escada de Alívio que discutimos!")

if __name__ == "__main__":
    main()