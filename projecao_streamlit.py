import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
import re
import time

# Configuração da página
st.set_page_config(
    page_title="Projeção de Dividendos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def validar_codigo_acao(codigo):
    padrao = r'^[A-Za-z]{4}\d{1,2}$'
    return bool(re.match(padrao, codigo))

def processar_acao(acao, progress_bar, status_text):
    try:
        status_text.text(f"Processando {acao.upper()}...")
        url = f'https://playinvest.com.br/dividendos/{acao}'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            st.warning(f"⚠️ Não foi possível acessar a página para {acao.upper()}")
            return None

        soup = BeautifulSoup(response.content, 'html.parser')
        data = []
        tabela = soup.find('div', class_='card featured-card per-year-chart')

        if not tabela:
            st.warning(f"⚠️ Tabela não encontrada para {acao.upper()}")
            return None

        linhas = tabela.find_all('tr')
        for linha in linhas:
            colunas = linha.find_all(['th', 'td'])
            for coluna in colunas:
                row_data = coluna.get_text(strip=True)
                data.append(row_data)
        filtered_data = [item for item in data if item != '']

        if len(filtered_data) < 4:
            st.warning(f"⚠️ Dados insuficientes para {acao.upper()}")
            return None

        # Organizar a lista em pares (Ano, Proventos)
        organized_data = [(filtered_data[i], filtered_data[i + 1]) for i in range(2, len(filtered_data), 2)]
        # Criar o DataFrame
        df = pd.DataFrame(organized_data, columns=['Ano', 'Proventos'])
        # Converter Proventos para float
        df['Proventos'] = df['Proventos'].str.replace('R$', '').str.replace('.', '').str.replace(',', '.').astype(float)
        df['Proventos'] = round(df['Proventos'] / 100, 2)
        # Converter Ano para int
        df['Ano'] = df['Ano'].astype(int)

        # Criar df_final com todos os anos consecutivos
        ano_inicial = df['Ano'].min()
        ano_final = df['Ano'].max()
        anos_completos = list(range(ano_inicial, ano_final + 1))
        df_final = pd.DataFrame({'Ano': anos_completos})

        df_final = df_final.merge(df, on='Ano', how='left')
        df_final['Proventos'] = df_final['Proventos'].fillna(0)
        df_final['Variação'] = df_final['Proventos'] - df_final['Proventos'].shift(1)
        df_final['Variação'] = df_final['Variação'].fillna(0)

        # ✨ TRATAMENTO ESPECIAL PARA ISAE4 ✨
        if acao.upper() == 'ISAE4':
            if 2025 in df_final['Ano'].values:
                dividendo_2025 = df_final[df_final['Ano'] == 2025]['Proventos'].iloc[0]
                df_final.loc[df_final['Ano'] == 2024, 'Proventos'] = dividendo_2025
                st.info(f"🔄 ISAE4: Usando dividendo de 2025 (R$ {dividendo_2025:.2f}) como base para 2024")
            # Recalcular as variações após a alteração
            df_final['Variação'] = df_final['Proventos'] - df_final['Proventos'].shift(1)
            df_final['Variação'] = df_final['Variação'].fillna(0)

        # Criar df_final2 sem o ano de 2025 (se houver)
        df_final2 = df_final[df_final['Ano'] != 2025].copy()

        # Calcular médias
        variacao_avg = df_final2['Variação'].mean()
        variacao_avg5 = df_final2['Variação'].tail(5).mean()
        variacao_avg2 = df_final2['Variação'].tail(2).mean()

        # Obter o dividendo de 2024
        dividendo_2024 = df_final2[df_final2['Ano'] == 2024]['Proventos'].iloc[0] if 2024 in df_final2[
            'Ano'].values else df_final2['Proventos'].iloc[-1]

        # 🚀 CRIAR PROJEÇÕES CUMULATIVAS 🚀
        anos_projecao = [2025, 2026, 2027, 2028, 2029]
        # Cenário 1: Projeção cumulativa com média total
        projecao_cenario1 = []
        valor_atual = dividendo_2024
        for ano in anos_projecao:
            valor_atual = round(valor_atual + variacao_avg, 2)
            projecao_cenario1.append(valor_atual)
        # Cenário 2: Projeção cumulativa com média 5 anos
        projecao_cenario2 = []
        valor_atual = dividendo_2024
        for ano in anos_projecao:
            valor_atual = round(valor_atual + variacao_avg5, 2)
            projecao_cenario2.append(valor_atual)
        # Cenário 3: Projeção cumulativa com média 2 anos
        projecao_cenario3 = []
        valor_atual = dividendo_2024
        for ano in anos_projecao:
            valor_atual = round(valor_atual + variacao_avg2, 2)
            projecao_cenario3.append(valor_atual)

        # Dados históricos
        df_historico = df_final2[df_final2['Ano'] <= 2024].copy()

        resultado = {
            'acao': acao,
            'df_historico': df_historico,
            'projecao_cenario1': projecao_cenario1,
            'projecao_cenario2': projecao_cenario2,
            'projecao_cenario3': projecao_cenario3,
            'anos_projecao': anos_projecao,
            'dividendo_2024': dividendo_2024,
            'variacao_avg': variacao_avg,
            'variacao_avg5': variacao_avg5,
            'variacao_avg2': variacao_avg2,
            'df_completo': df_final2,
            'tratamento_especial': acao.upper() == 'ISAE4'
        }
        return resultado
    except Exception as e:
        st.error(f"❌ Erro ao processar {acao.upper()}: {str(e)}")
        return None

def criar_grafico(resultado):
    acao = resultado['acao']
    df_historico = resultado['df_historico']
    projecao_cenario1 = resultado['projecao_cenario1']
    projecao_cenario2 = resultado['projecao_cenario2']
    projecao_cenario3 = resultado['projecao_cenario3']
    anos_projecao = resultado['anos_projecao']
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_historico['Ano'],
        y=df_historico['Proventos'],
        mode='lines+markers',
        name='Dados Históricos',
        line=dict(color='#2E86C1', width=3),
        marker=dict(size=8, color='#2E86C1'),
        hovertemplate='<b>%{x}</b><br>Dividendo: R$ %{y:.2f}<extra></extra>'
    ))
    ultimo_ano = df_historico['Ano'].iloc[-1]
    ultimo_valor = df_historico['Proventos'].iloc[-1]
    anos_cenario1 = [ultimo_ano] + anos_projecao
    valores_cenario1 = [ultimo_valor] + projecao_cenario1
    fig.add_trace(go.Scatter(
        x=anos_cenario1,
        y=valores_cenario1,
        mode='lines+markers',
        name='Cenário 1: Média Total',
        line=dict(color='#E74C3C', width=2, dash='dash'),
        marker=dict(size=6, color='#E74C3C', symbol='square'),
        hovertemplate='<b>%{x}</b><br>Projeção: R$ %{y:.2f}<extra></extra>'
    ))
    anos_cenario2 = [ultimo_ano] + anos_projecao
    valores_cenario2 = [ultimo_valor] + projecao_cenario2
    fig.add_trace(go.Scatter(
        x=anos_cenario2,
        y=valores_cenario2,
        mode='lines+markers',
        name='Cenário 2: Média 5 Anos',
        line=dict(color='#28B463', width=2, dash='dash'),
        marker=dict(size=6, color='#28B463', symbol='triangle-up'),
        hovertemplate='<b>%{x}</b><br>Projeção: R$ %{y:.2f}<extra></extra>'
    ))
    anos_cenario3 = [ultimo_ano] + anos_projecao
    valores_cenario3 = [ultimo_valor] + projecao_cenario3
    fig.add_trace(go.Scatter(
        x=anos_cenario3,
        y=valores_cenario3,
        mode='lines+markers',
        name='Cenário 3: Média 2 Anos',
        line=dict(color='#F39C12', width=2, dash='dash'),
        marker=dict(size=6, color='#F39C12', symbol='diamond'),
        hovertemplate='<b>%{x}</b><br>Projeção: R$ %{y:.2f}<extra></extra>'
    ))
    fig.add_vline(
        x=ultimo_ano + 0.5,
        line_dash="dot",
        line_color="gray",
        opacity=0.7,
        annotation_text="Início das Projeções",
        annotation_position="top"
    )
    titulo_base = f'Evolução e Projeção de Dividendos - {acao.upper()}'
    if resultado.get('tratamento_especial', False):
        titulo_base += ' (Base 2024 = Dividendo 2025)'
    fig.update_layout(
        title={
            'text': titulo_base,
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18, 'family': 'Arial Black'}
        },
        xaxis_title='Ano',
        yaxis_title='Dividendos (R$)',
        font=dict(size=11),
        hovermode='x unified',
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="rgba(0,0,0,0.2)",
            borderwidth=1,
            font=dict(size=10)
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        height=500,
        margin=dict(l=60, r=150, t=80, b=60)
    )
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    return fig

def main():
    st.title("📊 Projeção de Dividendos")
    st.markdown("---")
    with st.sidebar:
        st.header("⚙️ Configurações")
        st.subheader("📈 Ações para Análise")
        acoes_input = st.text_area(
            "Digite os códigos das ações (separados por vírgula):",
            value="PINE4, BBAS3, ABCB4",
            help="Exemplo: PETR4, VALE3, ITUB4, ISAE4"
        )
        if acoes_input:
            acoes_lista = [acao.strip().lower() for acao in acoes_input.split(',') if acao.strip()]
            acoes_validas = []
            acoes_invalidas = []
            for acao in acoes_lista:
                if validar_codigo_acao(acao):
                    acoes_validas.append(acao)
                else:
                    acoes_invalidas.append(acao)
            if acoes_invalidas:
                st.warning(f"⚠️ Códigos inválidos: {', '.join(acoes_invalidas)}")
            if acoes_validas:
                st.success(f"✅ {len(acoes_validas)} ações válidas: {', '.join([a.upper() for a in acoes_validas])}")
                if any(acao.upper() == 'ISAE4' for acao in acoes_validas):
                    st.info("ℹ️ **ISAE4**: Será usado o dividendo de 2025 como base para 2024")
        processar = st.button("🚀 Processar Análise", type="primary", use_container_width=True)
        st.markdown("---")
        st.subheader("ℹ️ Sobre os Cenários")
        st.markdown("""
        **Cenário 1**: Média histórica total (cumulativa)

        **Cenário 2**: Média dos últimos 5 anos (cumulativa)

        **Cenário 3**: Média dos últimos 2 anos (cumulativa)

        📈 **Projeção Cumulativa:**
        - 2025 = Dividendo 2024 + Média
        - 2026 = Dividendo 2025 + Média
        - 2027 = Dividendo 2026 + Média

        ---

        **⚠️ Tratamento Especial:**
        **ISAE4**: Dividendo 2024 = Dividendo 2025
        """)

    if not processar:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("""
            ### 🎯 Como usar:

            1. **Digite os códigos das ações** na barra lateral
            2. **Clique em "Processar Análise"**
            3. **Visualize os gráficos e projeções**

            ### 📊 O que você verá:
            - Histórico de dividendos
            - 3 cenários de projeção **cumulativa** para 2025-2029
            - Tabelas com dados detalhados
            - Resumo comparativo

            ### ⚠️ Tratamentos Especiais:
            - **ISAE4**: O dividendo de 2024 será igual ao de 2025

            ### 📈 Nova Metodologia:
            - **Projeção Cumulativa**: Cada ano é baseado no anterior + média
            - **Crescimento Progressivo**: Reflete melhor a evolução temporal
            """)
    else:
        if not acoes_validas:
            st.error("❌ Nenhuma ação válida foi inserida!")
            return
        progress_bar = st.progress(0)
        status_text = st.empty()
        resultados = []
        total_acoes = len(acoes_validas)
        for i, acao in enumerate(acoes_validas):
            resultado = processar_acao(acao, progress_bar, status_text)
            if resultado:
                resultados.append(resultado)
            progress_bar.progress((i + 1) / total_acoes)
            time.sleep(1)
        status_text.empty()
        progress_bar.empty()
        if not resultados:
            st.error("❌ Nenhuma ação foi processada com sucesso!")
            return
        st.success(f"✅ {len(resultados)} ações processadas com sucesso!")
        tab1, tab2, tab3 = st.tabs(["📊 Gráficos", "📋 Dados Detalhados", "📈 Resumo Comparativo"])
        with tab1:
            st.header("📊 Gráficos de Projeção Cumulativa")
            for resultado in resultados:
                st.subheader(f"📈 {resultado['acao'].upper()}")
                if resultado.get('tratamento_especial', False):
                    st.info("🔄 **Tratamento Especial**: Dividendo 2024 baseado no valor de 2025")
                fig = criar_grafico(resultado)
                st.plotly_chart(fig, use_container_width=True)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    label_2024 = "💰 Dividendo 2024*" if resultado.get('tratamento_especial', False) else "💰 Dividendo 2024"
                    st.metric(label_2024, f"R$ {resultado['dividendo_2024']:.2f}")
                with col2:
                    st.metric("📊 Cenário 1 (2029)", f"R$ {resultado['projecao_cenario1'][-1]:.2f}")
                with col3:
                    st.metric("📊 Cenário 2 (2029)", f"R$ {resultado['projecao_cenario2'][-1]:.2f}")
                with col4:
                    st.metric("📊 Cenário 3 (2029)", f"R$ {resultado['projecao_cenario3'][-1]:.2f}")
                st.markdown("---")
        with tab2:
            st.header("📋 Dados Detalhados")
            for resultado in resultados:
                with st.expander(f"📊 Dados de {resultado['acao'].upper()}"):
                    if resultado.get('tratamento_especial', False):
                        st.warning("⚠️ **ISAE4**: Os dados de 2024 foram ajustados com base no dividendo de 2025")
                    st.subheader("📈 Histórico de Dividendos")
                    st.dataframe(resultado['df_historico'], use_container_width=True)
                    st.subheader("🔮 Projeções Cumulativas 2025-2029")
                    df_projecoes = pd.DataFrame({
                        'Ano': resultado['anos_projecao'],
                        'Cenário 1': resultado['projecao_cenario1'],
                        'Cenário 2': resultado['projecao_cenario2'],
                        'Cenário 3': resultado['projecao_cenario3']
                    })
                    st.dataframe(df_projecoes, use_container_width=True)
                    st.subheader("📊 Médias de Variação Utilizadas")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Média Total", f"{resultado['variacao_avg']:.2f}")
                    with col2:
                        st.metric("Média 5 Anos", f"{resultado['variacao_avg5']:.2f}")
                    with col3:
                        st.metric("Média 2 Anos", f"{resultado['variacao_avg2']:.2f}")
        with tab3:
            st.header("📈 Resumo Comparativo")
            dados_comparativos = []
            for resultado in resultados:
                acao_nome = resultado['acao'].upper()
                if resultado.get('tratamento_especial', False):
                    acao_nome += "*"
                dados_comparativos.append({
                    'Ação': acao_nome,
                    'Dividendo 2024': f"R$ {resultado['dividendo_2024']:.2f}",
                    'Var. Média Total': f"{resultado['variacao_avg']:.2f}",
                    'Var. Média 5 Anos': f"{resultado['variacao_avg5']:.2f}",
                    'Var. Média 2 Anos': f"{resultado['variacao_avg2']:.2f}",
                    'Cenário 1 (2029)': f"R$ {resultado['projecao_cenario1'][-1]:.2f}",
                    'Cenário 2 (2029)': f"R$ {resultado['projecao_cenario2'][-1]:.2f}",
                    'Cenário 3 (2029)': f"R$ {resultado['projecao_cenario3'][-1]:.2f}"
                })
            df_comparativo = pd.DataFrame(dados_comparativos)
            st.dataframe(df_comparativo, use_container_width=True)
            if any(resultado.get('tratamento_especial', False) for resultado in resultados):
                st.caption("* Ações com tratamento especial (ISAE4: Dividendo 2024 = Dividendo 2025)")
            csv = df_comparativo.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name="projecao_dividendos_cumulativa.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    main()
