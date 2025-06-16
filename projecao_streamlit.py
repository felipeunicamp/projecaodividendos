import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
import re
import time
import warnings

warnings.filterwarnings('ignore')

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

        # Headers simples mas eficazes
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        url = f'https://playinvest.com.br/dividendos/{acao}'

        # Fazer requisição com encoding explícito
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.encoding = 'utf-8'  # Forçar encoding UTF-8

            if response.status_code != 200:
                st.warning(f"⚠️ Status {response.status_code} para {acao.upper()}")
                return None

        except Exception as e:
            st.error(f"❌ Erro na requisição para {acao.upper()}: {str(e)}")
            return None

        # Parse do HTML
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            st.error(f"❌ Erro no parse HTML para {acao.upper()}: {str(e)}")
            return None

        # Extrair dados da tabela
        data = []

        # Tentar encontrar a tabela principal
        tabela = soup.find('div', class_='card featured-card per-year-chart')

        if tabela:
            # Método 1: Procurar por tr/td
            linhas = tabela.find_all('tr')
            for linha in linhas:
                colunas = linha.find_all(['th', 'td'])
                for coluna in colunas:
                    texto = coluna.get_text(strip=True)
                    if texto:
                        data.append(texto)

        # Se não encontrou dados, tentar métodos alternativos
        if not data or len(data) < 4:
            # Método 2: Procurar por qualquer tabela
            tabelas = soup.find_all('table')
            for tabela in tabelas:
                linhas = tabela.find_all('tr')
                for linha in linhas:
                    colunas = linha.find_all(['th', 'td'])
                    for coluna in colunas:
                        texto = coluna.get_text(strip=True)
                        if texto:
                            data.append(texto)
                if len(data) >= 4:
                    break

        # Se ainda não encontrou, tentar busca por padrões
        if not data or len(data) < 4:
            # Método 3: Buscar por padrões no texto
            texto_completo = soup.get_text()

            # Procurar anos (2020, 2021, etc.)
            anos = re.findall(r'\b(20\d{2})\b', texto_completo)
            # Procurar valores monetários
            valores = re.findall(r'R\$\s*[\d.,]+', texto_completo)

            if len(anos) >= 2 and len(valores) >= 2:
                data = []
                min_len = min(len(anos), len(valores))
                for i in range(min_len):
                    data.extend([anos[i], valores[i]])

        # Filtrar dados vazios
        filtered_data = [item for item in data if item.strip() != '']

        if len(filtered_data) < 4:
            st.warning(f"⚠️ Dados insuficientes para {acao.upper()} - encontrados {len(filtered_data)} itens")
            if st.checkbox(f"Debug {acao.upper()}", key=f"debug_{acao}"):
                st.write("Dados encontrados:", filtered_data)
                st.write("Primeiros 500 chars do HTML:", str(soup)[:500])
            return None

        # Processar e organizar dados
        try:
            # Encontrar onde começam os dados (pular cabeçalhos)
            start_index = 0
            for i, item in enumerate(filtered_data):
                if re.match(r'^\d{4}$', item):  # Encontrou um ano
                    start_index = i
                    break

            # Se não encontrou ano, assumir que os primeiros 2 são cabeçalhos
            if start_index == 0 and len(filtered_data) > 2:
                if not re.match(r'^\d{4}$', filtered_data[0]):
                    start_index = 2

            # Organizar em pares (ano, valor)
            pares = []
            for i in range(start_index, len(filtered_data) - 1, 2):
                if i + 1 < len(filtered_data):
                    item1 = filtered_data[i].strip()
                    item2 = filtered_data[i + 1].strip()

                    # Verificar qual é o ano
                    if re.match(r'^\d{4}$', item1):
                        pares.append((item1, item2))
                    elif re.match(r'^\d{4}$', item2):
                        pares.append((item2, item1))

            if not pares:
                st.warning(f"⚠️ Não foi possível organizar dados para {acao.upper()}")
                return None

            # Criar DataFrame
            df = pd.DataFrame(pares, columns=['Ano', 'Proventos'])

            # Limpar valores monetários
            df['Proventos'] = df['Proventos'].astype(str)
            df['Proventos'] = df['Proventos'].str.replace('R$', '', regex=False)
            df['Proventos'] = df['Proventos'].str.replace('.', '', regex=False)  # Remove separador de milhares
            df['Proventos'] = df['Proventos'].str.replace(',', '.', regex=False)  # Troca vírgula por ponto
            df['Proventos'] = df['Proventos'].str.replace(' ', '', regex=False)  # Remove espaços

            # Converter para numérico
            df['Proventos'] = pd.to_numeric(df['Proventos'], errors='coerce')
            df['Ano'] = pd.to_numeric(df['Ano'], errors='coerce')

            # Remover linhas com erro de conversão
            df = df.dropna()

            if df.empty:
                st.warning(f"⚠️ Erro na conversão de dados para {acao.upper()}")
                return None

            # Ajustar escala se necessário
            if df['Proventos'].mean() > 100:
                df['Proventos'] = df['Proventos'] / 100

            df['Proventos'] = df['Proventos'].round(2)
            df['Ano'] = df['Ano'].astype(int)

            # Ordenar por ano
            df = df.sort_values('Ano').reset_index(drop=True)

            # Criar série completa de anos
            ano_min = df['Ano'].min()
            ano_max = df['Ano'].max()
            anos_completos = list(range(ano_min, ano_max + 1))

            df_final = pd.DataFrame({'Ano': anos_completos})
            df_final = df_final.merge(df, on='Ano', how='left')
            df_final['Proventos'] = df_final['Proventos'].fillna(0)

            # Calcular variações
            df_final['Variação'] = df_final['Proventos'].diff().fillna(0)

            # Tratamento especial ISAE4
            if acao.upper() == 'ISAE4':
                if 2025 in df_final['Ano'].values:
                    dividendo_2025 = df_final[df_final['Ano'] == 2025]['Proventos'].iloc[0]
                    df_final.loc[df_final['Ano'] == 2024, 'Proventos'] = dividendo_2025
                    st.info(f"🔄 ISAE4: Usando dividendo de 2025 (R$ {dividendo_2025:.2f}) como base para 2024")
                    # Recalcular variações
                    df_final['Variação'] = df_final['Proventos'].diff().fillna(0)

            # Remover 2025 se existir para cálculos
            df_calc = df_final[df_final['Ano'] != 2025].copy()

            # Calcular médias de variação
            variacao_avg = df_calc['Variação'].mean()
            variacao_avg5 = df_calc['Variação'].tail(5).mean()
            variacao_avg2 = df_calc['Variação'].tail(2).mean()

            # Dividendo base (2024)
            if 2024 in df_calc['Ano'].values:
                dividendo_2024 = df_calc[df_calc['Ano'] == 2024]['Proventos'].iloc[0]
            else:
                dividendo_2024 = df_calc['Proventos'].iloc[-1]

            # Projeções cumulativas
            anos_projecao = [2025, 2026, 2027, 2028, 2029]

            # Cenário 1
            projecao_1 = []
            valor = dividendo_2024
            for _ in anos_projecao:
                valor = round(valor + variacao_avg, 2)
                projecao_1.append(valor)

            # Cenário 2
            projecao_2 = []
            valor = dividendo_2024
            for _ in anos_projecao:
                valor = round(valor + variacao_avg5, 2)
                projecao_2.append(valor)

            # Cenário 3
            projecao_3 = []
            valor = dividendo_2024
            for _ in anos_projecao:
                valor = round(valor + variacao_avg2, 2)
                projecao_3.append(valor)

            # Dados históricos (sem 2025)
            df_historico = df_calc[df_calc['Ano'] <= 2024].copy()

            resultado = {
                'acao': acao,
                'df_historico': df_historico,
                'projecao_cenario1': projecao_1,
                'projecao_cenario2': projecao_2,
                'projecao_cenario3': projecao_3,
                'anos_projecao': anos_projecao,
                'dividendo_2024': dividendo_2024,
                'variacao_avg': variacao_avg,
                'variacao_avg5': variacao_avg5,
                'variacao_avg2': variacao_avg2,
                'df_completo': df_calc,
                'tratamento_especial': acao.upper() == 'ISAE4'
            }

            return resultado

        except Exception as e:
            st.error(f"❌ Erro no processamento para {acao.upper()}: {str(e)}")
            return None

    except Exception as e:
        st.error(f"❌ Erro geral para {acao.upper()}: {str(e)}")
        return None


def criar_grafico(resultado):
    acao = resultado['acao']
    df_historico = resultado['df_historico']
    projecao_cenario1 = resultado['projecao_cenario1']
    projecao_cenario2 = resultado['projecao_cenario2']
    projecao_cenario3 = resultado['projecao_cenario3']
    anos_projecao = resultado['anos_projecao']

    fig = go.Figure()

    # Dados históricos
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

    # Cenário 1
    anos_c1 = [ultimo_ano] + anos_projecao
    valores_c1 = [ultimo_valor] + projecao_cenario1
    fig.add_trace(go.Scatter(
        x=anos_c1,
        y=valores_c1,
        mode='lines+markers',
        name='Cenário 1: Média Total',
        line=dict(color='#E74C3C', width=2, dash='dash'),
        marker=dict(size=6, color='#E74C3C', symbol='square'),
        hovertemplate='<b>%{x}</b><br>Projeção: R$ %{y:.2f}<extra></extra>'
    ))

    # Cenário 2
    anos_c2 = [ultimo_ano] + anos_projecao
    valores_c2 = [ultimo_valor] + projecao_cenario2
    fig.add_trace(go.Scatter(
        x=anos_c2,
        y=valores_c2,
        mode='lines+markers',
        name='Cenário 2: Média 5 Anos',
        line=dict(color='#28B463', width=2, dash='dash'),
        marker=dict(size=6, color='#28B463', symbol='triangle-up'),
        hovertemplate='<b>%{x}</b><br>Projeção: R$ %{y:.2f}<extra></extra>'
    ))

    # Cenário 3
    anos_c3 = [ultimo_ano] + anos_projecao
    valores_c3 = [ultimo_valor] + projecao_cenario3
    fig.add_trace(go.Scatter(
        x=anos_c3,
        y=valores_c3,
        mode='lines+markers',
        name='Cenário 3: Média 2 Anos',
        line=dict(color='#F39C12', width=2, dash='dash'),
        marker=dict(size=6, color='#F39C12', symbol='diamond'),
        hovertemplate='<b>%{x}</b><br>Projeção: R$ %{y:.2f}<extra></extra>'
    ))

    # Linha divisória
    fig.add_vline(
        x=ultimo_ano + 0.5,
        line_dash="dot",
        line_color="gray",
        opacity=0.7,
        annotation_text="Início das Projeções",
        annotation_position="top"
    )

    # Título
    titulo = f'Evolução e Projeção de Dividendos - {acao.upper()}'
    if resultado.get('tratamento_especial', False):
        titulo += ' (Base 2024 = Dividendo 2025)'

    fig.update_layout(
        title={
            'text': titulo,
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

            ### 📈 Metodologia:
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
                    label_2024 = "💰 Dividendo 2024*" if resultado.get('tratamento_especial',
                                                                      False) else "💰 Dividendo 2024"
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
