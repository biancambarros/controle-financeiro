def render_raiox(df):
    df_gastos = df[(df['Valor'] < 0) & (~df['Tipo'].str.contains("Investiment", case=False)) & (df['Tipo'] != "Pagamento de cartão")].copy()
    df_gastos['Valor_Abs'] = df_gastos['Valor'].abs()
    
    col1, col2 = st.columns(2)
    with col1:
        df_evol = df_gastos.groupby(['Mes_Pagamento', 'Macro_Grupo'], observed=True)['Valor_Abs'].sum().reset_index()
        df_evol['Mes_Pagamento'] = pd.Categorical(df_evol['Mes_Pagamento'], categories=MONTHS_ORDER, ordered=True)
        
        # Gráfico Empilhado (Agora com a paleta de cores unificada)
        fig = px.bar(
            df_evol.sort_values('Mes_Pagamento'), 
            x='Mes_Pagamento', 
            y='Valor_Abs', 
            color='Macro_Grupo', 
            barmode='stack',
            color_discrete_map=MAPA_CORES_MACRO,       # <--- Paleta aplicada aqui!
            title="<b>Evolução dos Gastos por Grupo</b>" # <--- Título padronizado
        )
        fig.update_traces(hovertemplate="Grupo: %{fullData.name}<br>Valor: R$ %{y:,.2f}<extra></extra>")
        fig.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
        fig.update_layout(separators=",.", xaxis_title=None, yaxis_title="Valor (R$)")
        st.plotly_chart(fig, use_container_width=True, key="bar_raiox")
    
    with col2:
        sel_macro = st.selectbox("Grupo:", sorted(df_gastos['Macro_Grupo'].unique()), key="sel_macro")
        sel_mes = st.selectbox("Mês:", ["Todos"] + MONTHS_ORDER, key="sel_mes_raiox")
        
        df_d = df_gastos[df_gastos['Macro_Grupo'] == sel_macro]
        if sel_mes != "Todos": 
            df_d = df_d[df_d['Mes_Pagamento'] == sel_mes]
            
        if not df_d.empty:
            # Sunburst Dinâmico
            fig_sun = px.sunburst(
                df_d, 
                path=['Macro_Grupo', 'Tipo', 'Transação'],  # <--- Macro_Grupo no centro puxa a cor exata!
                values='Valor_Abs', 
                color='Macro_Grupo',
                color_discrete_map=MAPA_CORES_MACRO,        # <--- Paleta aplicada aqui!
                title=f"<b>Detalhes: {sel_macro}</b>",
                height=500
            )
            fig_sun.update_traces(hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>")
            fig_sun.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
            fig_sun.update_layout(separators=",.", margin=dict(t=60, l=10, r=10, b=10))
            st.plotly_chart(fig_sun, use_container_width=True, key="sun_raiox")

    st.divider()
    df_fav = df_gastos[df_gastos['Favorecido'] != "N/A"].groupby('Favorecido')['Valor_Abs'].sum().nlargest(10).reset_index()
    
    # Top 10 Favorecidos
    fig_fav = px.bar(
        df_fav.sort_values('Valor_Abs'), 
        x='Valor_Abs', 
        y='Favorecido', 
        orientation='h', 
        title="<b>Top 10 Maiores Favorecidos (Acumulado)</b>"
    )
    # Forçamos a cor quente (Rosa Sóbrio) para combinar com a ideia de saída de caixa
    fig_fav.update_traces(marker_color="#C06C84", hovertemplate="Favorecido: %{y}<br>Total: R$ %{x:,.2f}<extra></extra>")
    fig_fav.update_layout(title_font=dict(size=24, family="sans-serif"), title_x=0)
    fig_fav.update_layout(separators=",.", xaxis_title=None, yaxis_title=None) # Remove textos de eixo para ficar mais limpo
    
    st.plotly_chart(fig_fav, use_container_width=True, key="top_fav")
