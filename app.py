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
    elif p_type == "formula": 
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
            data_str = p["Data"]["formula"]["string"] if p["Data"]["formula"] else None

            rows.append({
                "Data": data_str,
                "Banco": get_property_value(p["Banco"]),
                "Transação": p["Transação"]["title"][0]["plain_text"] if p["Transação"]["title"] else "Sem Título",
                "Valor": (p["Valor"]["number"] or 0) * -1,
                "Tipo": get_property_value(p["Tipo de despesa"]),
                "Mes_Pagamento": get_property_value(p["Mês de pagamento"]),
                "Favorecido": get_property_value(p["Favorecido"]),
                "Parcela": get_property_value(p["Parcela"])
            })
        except Exception as e:
            continue
            
    df = pd.DataFrame(rows)
    if not df.empty:
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')
        df = df.sort_values(by=['Data', 'Mes_Pagamento'], na_position='first')
    return df


# --- FUNÇÕES AUXILIARES ---
def apply_macro_categories(df):
    """Aplica a lógica de Macro Grupos ao DataFrame inteiro."""
    mapeamento = {
        "Remuneração": "Rendas", 
        "Cashback": "Rendas", 
        "Rendimento": "Rendas", 
        "Adicional": "Rendas",
        "Moradia": "Despesas essenciais", 
        "Reforma": "Despesas essenciais",
        "Contas residenciais": "Despesas essenciais", 
        "Supermercado": "Despesas essenciais",
        "Transporte": "Despesas essenciais", 
        "TV / Internet / Telefone": "Despesas essenciais",
        "Pets": "Despesas essenciais", 
        "Plano de Saúde": 
        "Despesas essenciais", 
        "Medicamentos": "Despesas essenciais", 
        "Plano de saúde": "Despesas essenciais",
        "Nutrição e atividade física": "Despesas essenciais", 
        "Cuidados médicos ou psicológicos": "Despesas essenciais",
        "Trabalho": "Despesas essenciais", 
        "Educação": "Despesas essenciais", 
        "Móveis e eletrodomésticos": "Despesas não essenciais", 
        "Decoração e jardinagem": "Despesas não essenciais", "Vestuário": "Despesas não essenciais", "Bares / Restaurantes / Delivery": "Despesas não essenciais",
        "Estética": "Despesas não essenciais", "Lazer": "Despesas não essenciais", "Presentes": "Despesas não essenciais", "Doações": "Despesas não essenciais",
        "Eletrônicos": "Despesas não essenciais", "Investimentos": "Investimentos", "Impostos e taxas": "Impostos e taxas", "Previdência": "Impostos e taxas"
    }
    df['Macro_Grupo'] = df['Tipo'].apply(lambda x: mapeamento.get(x, 'Outros'))
    return df

def calculate_future_installments(df):
    """Gera um DataFrame com todas as parcelas futuras projetadas."""
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
            valor_parcela = abs(row['Valor'])
            
            # Projetamos o valor para os meses seguintes
            for i in range(restantes + 1):
                idx_futuro = (idx_atual + i) % 12
                mes_proj = ordem_meses[idx_futuro]
                
                # Adicionamos mais detalhes aqui para o Drill-Down
                projections.append({
                    'Mes': mes_proj,
                    'Valor': valor_parcela,
                    'Transação': row['Transação'],
                    'Banco': row['Banco'],
                    'Parcela_Ref': f"{atual + i}/{total}" # Ex: vira "2/10", "3/10" nas projeções
                })
        except: continue

    if not projections: return None
    
    df_proj = pd.DataFrame(projections)
    
    # Ordenação Categórica para garantir Jan -> Dez correto nos gráficos
    df_proj['Mes'] = pd.Categorical(df_proj['Mes'], categories=ordem_meses, ordered=True)
    return df_proj

def plot_bank_treemap(df_mes):
    df_banco = df_mes[df_mes['Valor'] < 0].groupby('Banco')['Valor'].sum().abs().reset_index()
    fig = px.treemap(df_banco, path=['Banco'], values='Valor', 
                      title="Concentração de Gastos por Instituição",
                      color='Valor', color_continuous_scale='Blues')
    fig.update_traces(hovertemplate="Banco: %{label}<br>Valor: R$ %{value:,.2f}<extra></extra>")
    return fig


# --- MONTANDO O DASHBOARD ---
def main():
    st.title("Controle Financeiro")
    
    with st.spinner("Sincronizando com Notion..."):
        df_raw = process_financial_logic(fetch_notion_data())
        df = apply_macro_categories(df_raw)

    if df.empty:
        st.warning("Nenhum dado encontrado no Notion.")
        return

    # === MENU DE NAVEGAÇÃO ===
    menu_options = ["📊 Saúde financeira", "📈 Histórico anual", "🏢 Raio-X de Consumo", "🔮 Projeções Futuras"]
    selected_tab = st.radio("Navegação", menu_options, horizontal=True, label_visibility="collapsed")
    st.divider()

    # 1. SAÚDE FINANCEIRA
    if selected_tab == "📊 Saúde financeira":
        st.caption(f"Há {len(df)} transações processadas.")
        meses = df['Mes_Pagamento'].unique().tolist()
        
        mes_atual_num = datetime.datetime.now().month
        map_meses_pt = {
            1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
            5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
            9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
        }
        mes_atual_nome = map_meses_pt[mes_atual_num]

        try: index_padrao = meses.index(mes_atual_nome)
        except ValueError: index_padrao = 0 
            
        mes_sel = st.selectbox("Escolha o mês:", meses, index=index_padrao)
                
        df_mes = df[df['Mes_Pagamento'] == mes_sel].copy()
        
        c1, c2 = st.columns(2)
        with c1:
            filtro_entradas = ((df_mes['Valor'] > 0) & (df_mes['Tipo'] != "Pagamento de cartão"))
            filtro_saidas = ((df_mes['Valor'] < 0) & (~df_mes['Tipo'].astype(str).str.contains("Investiment", case=False)) & (df_mes['Tipo'] != "Pagamento de cartão"))
            
            entradas = df_mes[filtro_entradas]['Valor'].sum()
            saidas = df_mes[filtro_saidas]['Valor'].abs().sum()
            taxa = ((entradas - saidas) / entradas * 100) if entradas > 0 else 0
            
            fig = px.pie(names=['Poupado (Investido + Sobra)', 'Gasto (Consumo Real)'], 
                         values=[max(0, entradas-saidas), saidas], 
                         hole=0.6, title=f"Fluxo de Caixa Líquido")
            fig.add_annotation(text=f"{taxa:.1f}%", x=0.5, y=0.5, showarrow=False, font_size=30)
            st.plotly_chart(fig, width='stretch')

            st.plotly_chart(plot_bank_treemap(df_mes), width='stretch')

        with c2:
            st.subheader(f"Carteira de Investimentos")
            df_invest = df_mes[df_mes['Tipo'].astype(str).str.contains("Investiment", case=False, na=False)]
            
            if not df_invest.empty:
                saldo_liquido = df_invest['Valor'].sum()
                label_kpi = "Aplicação Líquida" if saldo_liquido < 0 else "Resgate Líquido"
                st.metric(label=label_kpi, value=f"R$ {abs(saldo_liquido):,.2f}")
                
                df_invest_display = df_invest[['Data', 'Transação', 'Valor', 'Tipo']].copy()
                df_invest_display = df_invest_display.sort_values(by=['Data', 'Valor'], na_position='first')
                df_invest_display['Data'] = df_invest_display['Data'].dt.strftime('%d/%m/%Y')

                st.dataframe(df_invest_display, hide_index=True, column_config={"Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")})
            else:
                st.info("Sem movimentação de investimentos neste mês.")

            st.subheader(f"Auditoria de gastos")
            st.metric(label="Total calculado:", value=f"R$ {saidas:,.2f}")
            df_auditoria = df_mes[filtro_saidas][['Data', 'Transação', 'Valor', 'Tipo']].copy()
            df_auditoria = df_auditoria.sort_values(by=['Data', 'Valor'], na_position='first')
            df_auditoria['Data'] = df_auditoria['Data'].dt.strftime('%d/%m/%Y')
            
            st.dataframe(df_auditoria, hide_index=True, use_container_width=True, column_config={"Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f")})

    # 2. SALDO ANUAL
    elif selected_tab == "📈 Histórico anual":
        st.header("Saldos mensais")
        
        df_anual = df.groupby('Mes_Pagamento')['Valor'].sum().reset_index()
        ordem_meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        df_anual['Mes_Pagamento'] = pd.Categorical(df_anual['Mes_Pagamento'], categories=ordem_meses, ordered=True)
        df_anual = df_anual.sort_values('Mes_Pagamento')

        fig_anual = px.bar(
            df_anual, 
            x='Mes_Pagamento', y='Valor',
            #title='Evolução do saldo mensal',
            color='Valor', color_continuous_scale='RdYlGn', 
            labels={'Valor': 'Saldo (R$)', 'Mes_Pagamento': 'Mês'}
        )
        fig_anual.update_layout(coloraxis_showscale=False)
        fig_anual.update_traces(hovertemplate="Mês: %{x}<br>Saldo: R$ %{y:,.2f}<extra></extra>")
        
        st.plotly_chart(fig_anual, width='stretch')

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            df_entradas_geral = df[(df['Valor'] > 0) & (df['Tipo'] != "Pagamento de cartão")].copy()
            if not df_entradas_geral.empty:
                fig_sun_rend = px.sunburst(
                    df_entradas_geral, path=['Banco', 'Tipo'], values='Valor', 
                    title="Origem dos Rendimentos (Anual)",
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    height=650 
                )
                fig_sun_rend.update_traces(hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>")
                st.plotly_chart(fig_sun_rend, width='stretch')
            else: st.info("Sem dados de entradas.")

        with c2:
            df_saidas_geral = df[(df['Valor'] < 0) & (df['Tipo'] != "Pagamento de cartão")].copy()
            df_saidas_geral['Valor_Abs'] = df_saidas_geral['Valor'].abs()

            if not df_saidas_geral.empty:
                fig_sun_gastos = px.sunburst(
                    df_saidas_geral, path=['Banco', 'Tipo'], values='Valor_Abs', 
                    title="Destino dos Gastos (Anual)",
                    color_discrete_sequence=px.colors.qualitative.Set3,
                    height=650
                )
                fig_sun_gastos.update_traces(hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>")
                st.plotly_chart(fig_sun_gastos, width='stretch')
            else: st.info("Sem dados de saídas.")

        
    # 3. RAIO-X DE CONSUMO
    elif selected_tab == "🏢 Raio-X de Consumo":
        st.header("Análise por grupo de categorias")
        c1, c2 = st.columns([1, 1])
        
        df_gastos = df[(df['Valor'] < 0) & (~df['Tipo'].astype(str).str.contains("Investiment", case=False)) & (df['Tipo'] != "Pagamento de cartão")].copy()
        df_gastos['Valor_Abs'] = df_gastos['Valor'].abs()

        ordem_meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 
                        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        df_evol = df_gastos.groupby(['Mes_Pagamento', 'Macro_Grupo'])['Valor_Abs'].sum().reset_index()
        df_evol['Mes_Pagamento'] = pd.Categorical(df_evol['Mes_Pagamento'], categories=ordem_meses, ordered=True)
        
        cores_personalizadas = {
            "Despesas essenciais": "#87CEFA",    
            "Despesas não essenciais": "#0068C9", 
            "Impostos e taxas": "#FFB6C1",       
            "Outros": "#FF4B4B",              
            "Investimentos": "#81C784"           
        }

        with c1:
            fig_macro = px.bar(
                df_evol.sort_values('Mes_Pagamento'), 
                x='Mes_Pagamento', y='Valor_Abs', color='Macro_Grupo', 
                barmode='stack', color_discrete_map=cores_personalizadas
            )
            fig_macro.update_traces(hovertemplate="Mês: %{x}<br>%{fullData.name}: R$ %{y:,.2f}<extra></extra>")
            st.plotly_chart(fig_macro, width='stretch')

        with c2:
            st.subheader("🔎 Detalhar grupo de categorias")
            
            # 1. Seletor da Categoria Macro
            opcoes_macro = df_gastos['Macro_Grupo'].dropna().unique().tolist()
            opcoes_macro.sort()
            selecao_macro = st.selectbox("Selecione o grupo para ver detalhes:", opcoes_macro)
            
            # 2. NOVO: Seletor de Mês (com opção de ver o ano todo)
            meses_disponiveis = ["Todos (Ano inteiro)"] + df_gastos['Mes_Pagamento'].dropna().unique().tolist()
            selecao_mes = st.selectbox("Filtrar por mês:", meses_disponiveis)
            
            # 3. Lógica de filtro duplo
            if selecao_mes == "Todos (Ano inteiro)":
                df_detalhe = df_gastos[df_gastos['Macro_Grupo'] == selecao_macro].copy()
                titulo_grafico = f"Detalhamento: {selecao_macro} (Anual)"
            else:
                df_detalhe = df_gastos[(df_gastos['Macro_Grupo'] == selecao_macro) & (df_gastos['Mes_Pagamento'] == selecao_mes)].copy()
                titulo_grafico = f"Detalhamento: {selecao_macro} em {selecao_mes}"
            
            # 4. Plota o Sunburst
            if not df_detalhe.empty:
                fig_detalhe = px.sunburst(
                    df_detalhe, 
                    path=['Tipo', 'Transação'], 
                    values='Valor_Abs',
                    title=titulo_grafico, # Título dinâmico
                    color_discrete_sequence=px.colors.qualitative.Prism,
                    height=600
                )
                fig_detalhe.update_traces(hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>")
                st.plotly_chart(fig_detalhe, width='stretch')
            else:
                st.info(f"Sem gastos registrados em '{selecao_macro}' para o período selecionado.")

        st.divider()
        
        df_top_gastos = df[
            (df['Valor'] < 0) & 
            (df['Tipo'] != "Pagamento de cartão") & 
            (df['Favorecido'] != "Bianca Matos de Barros") & 
            (~df['Tipo'].astype(str).str.contains("Investiment", case=False))
        ].copy()
        
        df_top_gastos['Valor_Abs'] = df_top_gastos['Valor'].abs()

        if not df_top_gastos.empty:
            df_favorecidos = df_top_gastos.groupby('Favorecido')['Valor_Abs'].sum().reset_index()
            df_favorecidos = df_favorecidos.nlargest(10, 'Valor_Abs')
            df_favorecidos = df_favorecidos.sort_values('Valor_Abs', ascending=True)

            fig_top10 = px.bar(
                df_favorecidos,
                x='Valor_Abs', y='Favorecido', orientation='h',
                title='Maiores gastos: Top 10 Favorecidos (Exceto transferências próprias)',
                color='Valor_Abs', color_continuous_scale='Reds', text='Valor_Abs'
            )
            
            fig_top10.update_layout(coloraxis_showscale=True)
            fig_top10.update_traces(
                texttemplate='R$ %{x:,.2f}', textposition='outside',
                hovertemplate="Favorecido: %{y}<br>Total: R$ %{x:,.2f}<extra></extra>"
            )
            st.plotly_chart(fig_top10, width='stretch')
        else:
            st.info("Não há dados suficientes de despesas para gerar o Top 10.")


    # 4. PROJEÇÕES (ATUALIZADA)
    elif selected_tab == "🔮 Projeções Futuras":
        st.header("🔮 Futuro das Parcelas")
        
        # 1. Calculamos o DataFrame detalhado das projeções
        df_proj_detalhado = calculate_future_installments(df)
        
        if df_proj_detalhado is not None and not df_proj_detalhado.empty:
            # 2. Visão Macro: Gráfico de Linha (Agrupado por mês)
            df_agrupado = df_proj_detalhado.groupby('Mes')['Valor'].sum().reset_index()
            
            fig_proj = px.line(
                df_agrupado, x='Mes', y='Valor', 
                title="Tendência de Custo Fixo (Soma das parcelas)",
                markers=True, line_shape='hv', 
                color_discrete_sequence=['#EF553B']
            )
            fig_proj.update_traces(hovertemplate="Mês: %{x}<br>Total Parcelado: R$ %{y:,.2f}<extra></extra>")
            fig_proj.update_layout(yaxis_title="Total Comprometido (R$)")
            
            st.plotly_chart(fig_proj, width='stretch')
            st.info("O gráfico acima mostra o alívio no fluxo de caixa conforme suas dívidas parceladas terminam.")
            
            st.divider()
            
            # 3. Visão Micro: Detalhamento por Mês Selecionado
            st.subheader("🔎 Detalhar parcelas por mês")
            
            # Pega os meses disponíveis na projeção
            meses_proj = df_proj_detalhado['Mes'].unique().tolist()
            mes_foco = st.selectbox("Selecione um mês futuro para ver o que vai cair:", meses_proj)
            
            # Filtra os dados
            df_foco = df_proj_detalhado[df_proj_detalhado['Mes'] == mes_foco].copy()
            
            if not df_foco.empty:
                # Ordena do maior valor para o menor
                df_foco = df_foco.sort_values('Valor', ascending=True)
                
                # Gráfico de Barras Horizontais para ver quem são os vilões do mês
                fig_detalhe_mes = px.bar(
                    df_foco, 
                    x='Valor', y='Transação', 
                    orientation='h',
                    color='Banco', # Colore por banco para facilitar visualização
                    title=f"Composição das parcelas em {mes_foco}",
                    text='Valor'
                )
                fig_detalhe_mes.update_traces(
                    texttemplate='R$ %{x:,.2f}', textposition='outside',
                    hovertemplate="<b>%{y}</b><br>Banco: %{legendgroup}<br>Valor: R$ %{x:,.2f}<extra></extra>"
                )
                fig_detalhe_mes.update_layout(height=400 + (len(df_foco)*20)) # Ajusta altura dinâmica se tiver muitos itens
                
                st.plotly_chart(fig_detalhe_mes, width='stretch')
            else:
                st.write("Sem parcelas para este mês.")
                
        else:
            st.write("Nenhuma parcela futura detectada no Notion.")

if __name__ == "__main__":
    if check_password():
        main()
