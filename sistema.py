import streamlit as st
import sqlite3
import pandas as pd
import datetime
import io # Necessário para o Excel na memória
import subprocess
import sys

# --- AUTOMATIZAÇÃO DE INSTALAÇÃO (HACK) ---
# Tenta importar openpyxl. Se falhar, instala automaticamente.
try:
    import openpyxl
except ImportError:
    st.warning("Instalando biblioteca 'openpyxl' necessária para o Excel... Aguarde um momento.")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    st.success("Instalação concluída! Por favor, recarregue a página (F5 ou Rerun).")
    st.stop() # Para o código para o usuário recarregar

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('clinica.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS pacientes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  nome TEXT NOT NULL, 
                  nascimento DATE)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS atendimentos 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  paciente_id INTEGER, 
                  data_consulta DATE, 
                  status TEXT, 
                  valor REAL,
                  prontuario TEXT,
                  nota_fiscal BOOLEAN, 
                  FOREIGN KEY(paciente_id) REFERENCES pacientes(id))''')
    conn.commit()
    return conn

conn = init_db()

# --- INTERFACE ---
st.set_page_config(page_title="Gestão Fonoaudiologia", layout="wide")
st.title("🧩 Sistema Fonoaudiologia")

menu = st.sidebar.radio("Navegação", 
    ["1. Cadastro de Pacientes", "2. Realizar Atendimento", "3. Histórico e Análise"])

# --- TELA 1: CADASTRO ---
if menu == "1. Cadastro de Pacientes":
    st.header("👤 Novo Paciente")
    with st.form("form_paciente"):
        nome = st.text_input("Nome Completo")
        dt_nasc = st.date_input("Data de Nascimento", format="DD/MM/YYYY", min_value=datetime.date(1920, 1, 1))
        submit = st.form_submit_button("Salvar Paciente")
        
        if submit and nome:
            c = conn.cursor()
            c.execute("INSERT INTO pacientes (nome, nascimento) VALUES (?, ?)", (nome, dt_nasc))
            conn.commit()
            st.success(f"Paciente '{nome}' cadastrado!")

# --- TELA 2: ATENDIMENTO ---
elif menu == "2. Realizar Atendimento":
    st.header("📝 Registro de Sessão")
    df_pacientes = pd.read_sql("SELECT id, nome FROM pacientes", conn)
    
    if not df_pacientes.empty:
        opcao_paciente = st.selectbox("Selecione o Paciente", df_pacientes['nome'])
        id_selecionado = df_pacientes[df_pacientes['nome'] == opcao_paciente]['id'].values[0]
        
        col1, col2, col3 = st.columns(3)
        with col1:
            data = st.date_input("Data da Sessão", format="DD/MM/YYYY")
        with col2:
            valor = st.number_input("Valor (R$)", min_value=0.0, value=100.0)
        with col3:
            status = st.selectbox("Status", ["Realizado", "Agendado", "Falta", "Cancelado"])
        
        nf_emitida = st.checkbox("Nota Fiscal Emitida?", value=False)

        st.subheader("Evolução Clínica (Prontuário)")
        prontuario_texto = st.text_area("Descreva os procedimentos:", height=150)
            
        if st.button("Salvar Sessão"):
            c = conn.cursor()
            c.execute("""INSERT INTO atendimentos (paciente_id, data_consulta, status, valor, prontuario, nota_fiscal) 
                         VALUES (?, ?, ?, ?, ?, ?)""", 
                         (int(id_selecionado), data, status, valor, prontuario_texto, nf_emitida))
            conn.commit()
            st.success("Salvo com sucesso!")
    else:
        st.warning("Cadastre pacientes antes.")

# --- TELA 3: HISTÓRICO ---
elif menu == "3. Histórico e Análise":
    st.header("📂 Histórico Clínico")
    
    query_analise = """
    SELECT a.id, p.nome, a.data_consulta, a.status, a.prontuario, a.nota_fiscal, a.valor
    FROM atendimentos a
    JOIN pacientes p ON a.paciente_id = p.id
    ORDER BY a.data_consulta DESC
    """
    df = pd.read_sql(query_analise, conn)
    
    if not df.empty:
        df_view = df.copy()
        df_view['data_consulta'] = pd.to_datetime(df_view['data_consulta']).dt.strftime('%d/%m/%Y')

    tab1, tab2 = st.tabs(["📜 Prontuários", "📊 Financeiro e NFs"])
    
    with tab1:
        if not df.empty:
            paciente_filtro = st.selectbox("Filtrar por Paciente", ["Todos"] + list(df_view['nome'].unique()))
            if paciente_filtro != "Todos":
                df_filtrado = df_view[df_view['nome'] == paciente_filtro]
            else:
                df_filtrado = df_view
            
            for index, row in df_filtrado.iterrows():
                nf_icon = "📄 NF OK" if row['nota_fiscal'] else "⚠️ Sem NF"
                with st.expander(f"{row['data_consulta']} - {row['nome']} ({row['status']}) | {nf_icon}"):
                    st.write(row['prontuario'] if row['prontuario'] else "Sem anotações.")
        else:
            st.info("Nenhum atendimento registrado.")

    with tab2:
        st.subheader("Controle Financeiro e Fiscal")
        
        if not df.empty:
            # Filtra apenas o que precisa de atenção
            df_pendentes = df[
                (df['status'] == 'Realizado') & 
                (df['nota_fiscal'] == 0)
            ]
            
            receita_total = df[df['status'] == 'Realizado']['valor'].sum()
            valor_pendente_nf = df_pendentes['valor'].sum()
            qtd_pendente = len(df_pendentes)

            # Métricas
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Faturamento Total", f"R$ {receita_total:.2f}")
            col_b.metric("Pendência de NF (Valor)", f"R$ {valor_pendente_nf:.2f}", delta_color="inverse")
            col_c.metric("Sessões s/ Nota", f"{qtd_pendente} sessões")

            st.divider()

            # --- LISTA DE PENDÊNCIAS COM BOTÃO DE AÇÃO ---
            if not df_pendentes.empty:
                st.write("### ⚠️ Pendências (Aguardando Emissão)")
                
                col_h1, col_h2, col_h3, col_h4 = st.columns([2, 2, 2, 2])
                col_h1.write("**Data**")
                col_h2.write("**Paciente**")
                col_h3.write("**Valor**")
                col_h4.write("**Ação**")
                
                for index, row in df_pendentes.iterrows():
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
                    
                    data_formatada = pd.to_datetime(row['data_consulta']).strftime('%d/%m/%Y')
                    c1.write(data_formatada)
                    c2.write(row['nome'])
                    c3.write(f"R$ {row['valor']:.2f}")
                    
                    # O Botão Mágico
                    if c4.button("✅ Já Emiti", key=f"btn_{row['id']}"):
                        cursor = conn.cursor()
                        cursor.execute("UPDATE atendimentos SET nota_fiscal = 1 WHERE id = ?", (row['id'],))
                        conn.commit()
                        st.success(f"Nota de {row['nome']} baixada!")
                        st.rerun()

                st.divider()

                # --- EXPORTAR EXCEL (Usando a biblioteca instalada automaticamente) ---
                st.write("📥 **Exportar Relatório (Excel)**")
                
                df_export = df_pendentes[['nome', 'data_consulta', 'valor']].copy()
                df_export.columns = ['Nome do Paciente', 'Data da Sessão', 'Valor (R$)']
                
                # Buffer para Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False, sheet_name='Pendencias_NF')
                    
                st.download_button(
                    label="Baixar Relatório Excel (.xlsx)",
                    data=buffer.getvalue(),
                    file_name="relatorio_pendencias.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            else:
                st.success("Tudo em dia! Todas as notas fiscais foram emitidas.")

        else:
            st.warning("Sem dados financeiros.")