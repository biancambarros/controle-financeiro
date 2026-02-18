import datetime
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="💲 Dashboard Financeiro", layout="wide")

# --- AUTENTICAÇÃO ---
def check_password():
    """Retorna True se o usuário inserir a senha correta."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.text_input(
        "🔒 Digite a senha para acessar o Dashboard Financeiro:", 
        type="password", 
        key="password_input", 
        on_change=password_entered
    )
    return False

def password_entered():
    """Checa se a senha inserida bate com a dos Secrets."""
    if st.session_state["password_input"] == st.secrets["SENHA_ACESSO"]:
        st.session_state.password_correct = True
        del st.session_state["password_input"]  # Limpa a senha da memória
    else:
        st.error("😕 Senha incorreta.")
        

# --- CORE: BUSCA E LIMPEZA DE DADOS ---
def get_property_value(prop):
    if not prop: return "N/A"
    p_type = prop.get("type")
    if p_type == "select": return prop["select"]["name"] if prop["select"] else "N/A"
    elif p_type == "people": return prop["people"][0]["name"] if prop["people"] else "N/A"
    elif p_type == "rich_text": return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else "N/A"
    elif p_type == "formula": # Adicionado suporte para formulas de texto
        return prop["formula"]["string"] if prop["formula"]["type"] == "string" else "N/A"
    return "N/A"

@st.cache_data(ttl=600)
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
            # O Notion envia algo como: {'type': 'formula', 'formula': {'type': 'string', 'string': '15/02/2026'}}
            data_str = p["Data"]["formula"]["string"] if p["Data"]["formula"] else None

            rows.append({
                "Data": data_str, # Pegamos a string crua "DD/MM/YYYY"
                "Banco": get_property_value(p["Banco"]),
                "Transação": p["Transação"]["title"][0]["plain_text"] if p["Transação"]["title"] else "Sem Título",
                "Valor": (p["Valor"]["number"] or 0) * -1,
                "Tipo": get_property_value(p["Tipo de despesa"]),
                "Mes_Pagamento": get_property_value(p["Mês de pagamento"]),
                "Favorecido": get_property_value(p["Favorecido"]),
                "Parcela": get_property_value(p["Parcela"])
            })
        except Exception as e:
            # Dica: Se quiser debugar, descomente a linha abaixo para ver o erro no log
            # print(f"Erro ao processar linha: {e}") 
            continue
            
    df = pd.DataFrame(rows)
    if not df.empty:
        # 1. Conversão inteligente da data
        # Como sua fórmula já entrega "DD/MM/YYYY", usamos dayfirst=True
        # Isso converte a string para um objeto Timestamp limpo (sem horas quebradas)
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')

        # 2. Ordenação
        df = df.sort_values(by=['Data', 'Mes_Pagamento'], na_position='first')
    return df

# --- VISUALIZAÇÃO ---
def plot_macro_evolution(df):
    mapeamento = {
        "Remuneração": "Rendas", "Cashback": "Rendas", 
        "Rendimento": "Rendas", "Adicional": "Rendas",
        "Moradia": "Despesas essenciais", "Reforma": "Despesas essenciais",
        "Contas residenciais": "Despesas essenciais", "Supermercado": "Despesas essenciais",
        "Transporte": "Despesas essenciais", "TV / Internet / Telefone": "Despesas essenciais",
        "Pets": "Despesas essenciais", "Plano de Saúde": "Despesas essenciais", "Medicamentos": "Despesas essenciais",
        "Nutrição e atividade física": "Despesas essenciais", "Cuidados médicos ou psicológicos": "Despesas essenciais",
        "Trabalho": "Despesas essenciais", "Educação": "Despesas essenciais", "Móveis e eletrodomésticos": "Despesas não essenciais", 
        "Decoração e jardinagem": "Despesas não essenciais", "Vestuário": "Despesas não essenciais", "Bares / Restaurantes / Delivery": "Despesas não essenciais",
        "Estética": "Despesas não essenciais", "Lazer": "Despesas não essenciais", "Presentes": "Despesas não essenciais", "Doações": "Despesas não essenciais",
        "Eletrônicos": "Despesas não essenciais", "Investimentos": "Investimentos", "Impostos e taxas": "Impostos e taxas", "Previdência": "Impostos e taxas"
    }
    df['Macro_Grupo'] = df['Tipo'].apply(lambda x: mapeamento.get(x, 'Lifestyle'))
    # Filtro robusto para excluir investimentos (singular/plural)
    df_gastos = df[(df['Valor'] < 0) & (~df['Tipo'].astype(str).str.contains("Investiment", case=False)) & (df['Tipo'] != "Pagamento de cartão")].copy()
    df_gastos['Valor_Abs'] = df_gastos['Valor'].abs()
    
    ordem_meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 
                    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    df_evol = df_gastos.groupby(['Mes_Pagamento', 'Macro_Grupo'])['Valor_Abs'].sum().reset_index()
    df_evol['Mes_Pagamento'] = pd.Categorical(df_evol['Mes_Pagamento'], categories=ordem_meses, ordered=True)
    
    return px.bar(df_evol.sort_values('Mes_Pagamento'), x='Mes_Pagamento', y='Valor_Abs', color='Macro_Grupo', 
                  title="Evolução de Gastos: Essencial vs Lifestyle", barmode='stack')

def plot_relief_projection(df):
    df_parcelas = df[df['Parcela'].astype(str).str.contains('/')].copy()
    if df_parcelas.empty: return None

    projections = []
    ordem_meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 
                    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    
    mes_atual_nome = datetime.datetime.now().strftime('%B').capitalize()
    map_meses = {'February': 'Fevereiro', 'March': 'Março', 'April': 'Abril', 'May': 'Maio', 
                 'June': 'Junho', 'July': 'Julho', 'August': 'Agosto', 'September': 'Setembro', 
                 'October': 'Outubro', 'November': 'Novembro', 'December': 'Dezembro', 'January': 'Janeiro'}
    mes_atual_nome = map_meses.get(mes_atual_nome, 'Fevereiro')
    
    try: idx_atual = ordem_meses.index(mes_atual_nome)
    except: idx_atual = 0

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
    df_banco = df_mes[df_mes['Valor'] < 0].groupby('Banco')['Valor'].sum().abs().reset_index()
    return px.treemap(df_banco, path=['Banco'], values='Valor', 
                      title="Concentração de Gastos por Instituição",
                      color='Valor', color_continuous_scale='Blues')

# --- MONTANDO O DASHBOARD ---
def main():
    st.title("Controle Financeiro")
    
    with st.spinner("Sincronizando com Notion..."):
        df = process_financial_logic(fetch_notion_data())

    if df.empty:
        st.warning("Nenhum dado encontrado no Notion.")
        return

    # === [NOVA ESTRUTURA DE ABAS] ===
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Saúde financeira", "📈 Saldo Anual", "🏢 Raio-X de Consumo", "🔮 Projeções Futuras"])

    with tab1:
        st.caption(f"Há {len(df)} transações processadas.")
        meses = df['Mes_Pagamento'].unique().tolist()
        
        # 1. Descobrimos qual é o mês atual do sistema (Ex: 2 = Fevereiro)
        mes_atual_num = datetime.datetime.now().month
        
        # 2. Mapeamos para o nome exato que você usa no Notion
        map_meses_pt = {
            1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
            5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
            9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
        }
        mes_atual_nome = map_meses_pt[mes_atual_num]

        # 3. Tentamos selecionar o mês atual. 
        # Se ele ainda não existir nos dados (ex: virou o mês mas não tem gasto ainda), 
        # pegamos o último da lista (index 0 ou -1 dependendo da sua ordenação)
        try: 
            index_padrao = meses.index(mes_atual_nome)
        except ValueError: 
            index_padrao = 0 # Fallback de segurança
            
        mes_sel = st.selectbox("Escolha o mês:", meses, index=index_padrao)
                
        df_mes = df[df['Mes_Pagamento'] == mes_sel].copy() # .copy() evita warnings do Pandas
        
        c1, c2 = st.columns(2)
        with c1:
            # --- LÓGICA DE FILTRAGEM ---
            filtro_entradas = (
                (df_mes['Valor'] > 0) & 
                (df_mes['Tipo'] != "Pagamento de cartão")
            )
            
            filtro_saidas = (
                (df_mes['Valor'] < 0) & 
                (~df_mes['Tipo'].astype(str).str.contains("Investiment", case=False)) & 
                (df_mes['Tipo'] != "Pagamento de cartão")
            )
            
            entradas = df_mes[filtro_entradas]['Valor'].sum()
            saidas = df_mes[filtro_saidas]['Valor'].abs().sum()
            
            taxa = ((entradas - saidas) / entradas * 100) if entradas > 0 else 0
            
            fig = px.pie(names=['Poupado (Investido + Sobra)', 'Gasto (Consumo Real)'], 
                         values=[max(0, entradas-saidas), saidas], 
                         hole=0.6, title=f"Fluxo de Caixa Líquido")#: {mes_sel}
            fig.add_annotation(text=f"{taxa:.1f}%", x=0.5, y=0.5, showarrow=False, font_size=30)
            st.plotly_chart(fig, width='stretch')

            st.plotly_chart(plot_bank_treemap(df_mes), width='stretch')

        with c2:
            # --- AUDITORIA DE INVESTIMENTOS ---
            st.subheader(f"Carteira de Investimentos")#: {mes_sel}
            df_invest = df_mes[df_mes['Tipo'].astype(str).str.contains("Investiment", case=False, na=False)]
            
            if not df_invest.empty:
                saldo_liquido = df_invest['Valor'].sum()
                label_kpi = "Aplicação Líquida" if saldo_liquido < 0 else "Resgate Líquido"
                st.metric(label=label_kpi, value=f"R$ {abs(saldo_liquido):,.2f}")
                
                df_invest_display = df_invest[['Data', 'Transação', 'Valor', 'Tipo']].copy()
                
                # Ordenamos por Data ENQUANTO ainda é objeto de data (cronológico)
                df_invest_display = df_invest_display.sort_values(by=['Data', 'Valor'], na_position='first')
                
                # Convertemos para texto para exibição
                df_invest_display['Data'] = df_invest_display['Data'].dt.strftime('%d/%m/%Y')

                st.dataframe(
                    df_invest_display, 
                    hide_index=True,
                    column_config={
                        "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")
                    }
                )
            else:
                st.info("Sem movimentação de investimentos neste mês.")

            
            # --- AUDITORIA DE GASTOS ---
            st.subheader(f"Auditoria de gastos")
            label_kpi_2 = "Total calculado:"
            st.metric(label=label_kpi_2, value=f"R$ {saidas:,.2f}")
            #st.write(f"Total calculado: **R$ {saidas:,.2f}**")
            # 1. Filtramos
            df_auditoria = df_mes[filtro_saidas][['Data', 'Transação', 'Valor', 'Tipo']].copy()
            
            # CORREÇÃO: Ordenamos por Data cronológica PRIMEIRO
            df_auditoria = df_auditoria.sort_values(by=['Data', 'Valor'], na_position='first')
            
            # 2. Convertemos para string (Texto) DEPOIS da ordenação
            df_auditoria['Data'] = df_auditoria['Data'].dt.strftime('%d/%m/%Y')
            
            # 3. Exibimos
            st.dataframe(
                df_auditoria, 
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Valor": st.column_config.NumberColumn(
                        "Valor",
                        format="R$ %.2f"
                    )
                }
            )

    with tab2:
        st.header("Resultado Financeiro por Mês")
        
        # 1. Agrupamos tudo por Mês de Pagamento (somando todos os valores, positivos e negativos)
        # Atenção: Isso inclui salário, gastos, investimentos, tudo. É o "Saldo Final" da conta.
        df_anual = df.groupby('Mes_Pagamento')['Valor'].sum().reset_index()

        # 2. Ordenação Cronológica dos Meses
        ordem_meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 
                       'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        df_anual['Mes_Pagamento'] = pd.Categorical(df_anual['Mes_Pagamento'], categories=ordem_meses, ordered=True)
        df_anual = df_anual.sort_values('Mes_Pagamento')

        # 3. Gráfico de Barras com Cores Condicionais (Verde/Vermelho)
        fig_anual = px.bar(
            df_anual, 
            x='Mes_Pagamento', 
            y='Valor',
            title='Saldo Líquido (Receitas - Despesas)',
            color='Valor',
            color_continuous_scale='RdYlGn', # Gradiente Vermelho -> Amarelo -> Verde
            labels={'Valor': 'Saldo (R$)', 'Mes_Pagamento': 'Mês'}
        )
        
        # Ajuste Fino Visual
        fig_anual.update_layout(coloraxis_showscale=False) # Remove a barra de cores lateral
        st.plotly_chart(fig_anual, width='stretch')

    with tab3:
        c1, c2 = st.columns(2)
        
        # Sunburst com filtro correto de valores negativos
        df_sun = df[(df['Valor'] < 0) & (df['Tipo'] != "Pagamento de cartão")].copy()
        df_sun['Valor_Abs'] = df_sun['Valor'].abs()
        
        with c1: st.plotly_chart(plot_macro_evolution(df), width='stretch')
        with c2: st.plotly_chart(px.sunburst(df_sun, path=['Banco', 'Tipo'], values='Valor_Abs', title="Raio-X Banco > Categoria"), width='stretch')

    with tab4:
        st.header("🔮 Futuro das Parcelas")
        fig_proj = plot_relief_projection(df)
        if fig_proj:
            st.plotly_chart(fig_proj, width='stretch')
            st.info("Este gráfico mostra como seu custo fixo cai à medida que as parcelas terminam.")
        else:
            st.write("Nenhuma parcela detectada no Notion.")


if __name__ == "__main__":
    if check_password():
        main()
