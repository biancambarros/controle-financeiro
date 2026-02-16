import datetime
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="💲 Dashboard Financeiro", layout="wide")

# --- CORE: BUSCA E LIMPEZA DE DADOS ---
def get_property_value(prop):
    """
    Função auxiliar para extrair o valor de texto de diferentes tipos de 
    propriedades do Notion (Select, People, Relation, Rich Text).
    """
    if not prop: return "N/A"
    p_type = prop.get("type")
    if p_type == "select": return prop["select"]["name"] if prop["select"] else "N/A"
    elif p_type == "people": return prop["people"][0]["name"] if prop["people"] else "N/A"
    elif p_type == "rich_text": return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else "N/A"
    return "N/A"

@st.cache_data(ttl=600) # Cache de 10 minutos
def fetch_notion_data():
    """
    Faz a comunicação direta com a API do Notion via protocolo HTTP (POST).
    Implementa a lógica de paginação para garantir que todas as transações sejam capturadas, mesmo que ultrapassem 100 itens.
    """
    token = st.secrets["NOTION_TOKEN"]
    db_id = st.secrets["DATABASE_ID"]
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
    
    all_pages = []
    has_more, next_cursor = True, None

    # Loop de paginação: o Notion envia no máximo 100 registros por vez
    while has_more:
        # Se existir um cursor, o payload pede a 'próxima página' de dados
        payload = {"start_cursor": next_cursor} if next_cursor else {}
        response = requests.post(url, json=payload, headers=headers)

        # Tratamento de erro: interrompe o código se a API falhar
        if response.status_code != 200: raise Exception(f"Erro Notion: {response.text}")

        # Converte a resposta bruta em um dicionário Python
        data = response.json()

        # Adiciona os resultados à lista principal
        all_pages.extend(data.get("results", []))

        # Verifica se ainda existem mais dados para buscar (paginação)
        has_more, next_cursor = data.get("has_more", False), data.get("next_cursor")
    return all_pages

def process_financial_logic(results):
    rows = []
    erros = 0
    sem_data = 0
    
    print(f"📡 API do Notion retornou {len(results)} registros brutos.")
    
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

def plot_relief_projection(df):
    # Filtramos transações com padrão '1/10'
    df_parcelas = df[df['Parcela'].astype(str).str.contains('/')].copy()
    if df_parcelas.empty: return None

    projections = []
    ordem_meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 
                    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    
    # Pegamos o mês atual para iniciar a projeção
    mes_atual_nome = datetime.datetime.now().strftime('%B').capitalize() # Pega o mês real do sistema
    # Ajuste manual caso o locale esteja em inglês
    map_meses = {'February': 'Fevereiro', 'March': 'Março'} # Adicione outros se necessário
    mes_atual_nome = map_meses.get(mes_atual_nome, 'Fevereiro')
    
    idx_atual = ordem_meses.index(mes_atual_nome)

    for _, row in df_parcelas.iterrows():
        try:
            atual, total = map(int, row['Parcela'].split('/'))
            restantes = total - atual
            for i in range(restantes + 1):
                idx_futuro = (idx_atual + i) % 12
                projections.append({'Mes': ordem_meses[idx_futuro], 'Valor': abs(row['Valor'])})
        except: continue

    df_proj = pd.DataFrame(projections).groupby('Mes')['Valor'].sum().reindex(ordem_meses).reset_index().dropna()
    
    fig = px.line(df_proj, x='Mes', y='Valor', title="Previsão de Gastos Parcelados (Escada de Alívio)",
                  markers=True, line_shape='hv', color_discrete_sequence=['#EF553B'])
    fig.update_layout(yaxis_title="R$ Comprometido")
    return fig


def plot_bank_treemap(df_mes):
    df_banco = df_mes[df_mes['Valor'] < 0].groupby('Banco')['Valor'].abs().sum().reset_index()
    return px.treemap(df_banco, path=['Banco'], values='Valor', 
                      title="Concentração de Gastos por Instituição",
                      color='Valor', color_continuous_scale='Reds')
# --- APP PRINCIPAL ---

def main():
    st.title("💲 Minhas finanças 💲")
    
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
