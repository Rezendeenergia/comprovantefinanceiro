import streamlit as st
import pdfplumber
import zipfile
import io
import os
import re
from datetime import datetime
from pathlib import Path
import tempfile


def extrair_info_comprovante(pdf_path):
    """
    Extrai data e nome do destinatário/beneficiário do comprovante PDF
    Suporta comprovantes de Boleto, PIX e TED
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extrair texto da primeira página
            primeira_pagina = pdf.pages[0]
            texto = primeira_pagina.extract_text()

            data = None
            destinatario = None
            tipo_comprovante = None

            # Detectar tipo de comprovante
            if 'Boleto' in texto or 'Data de débito:' in texto:
                tipo_comprovante = 'Boleto'

                # Extrair data de débito (Boleto)
                match_data = re.search(r'Data de débito:\s*(\d{2}/\d{2}/\d{4})', texto)
                if match_data:
                    data_str = match_data.group(1)
                    data = data_str.replace('/', '-')

                # Extrair nome do beneficiário (Boleto)
                match_beneficiario = re.search(r'Nome do beneficiário:\s*(.+?)(?:\n|$)', texto)
                if match_beneficiario:
                    destinatario = match_beneficiario.group(1).strip()

            elif 'TED' in texto and 'Transferência' in texto:
                tipo_comprovante = 'TED'

                # Extrair data/hora (TED) - pegar só a data
                match_data = re.search(r'Data/Hora:\s*(\d{2}/\d{2}/\d{4})', texto)
                if match_data:
                    data_str = match_data.group(1)
                    data = data_str.replace('/', '-')

                # Extrair nome do favorecido (TED)
                # Procurar após "Informações da Transferência"
                match_favorecido = re.search(r'Favorecido:\s*(.+?)(?:\n|$)', texto)
                if match_favorecido:
                    destinatario = match_favorecido.group(1).strip()

            elif 'PIX' in texto:
                tipo_comprovante = 'PIX'

                # Extrair data/hora (PIX) - pegar só a data
                match_data = re.search(r'Data/Hora:\s*(\d{2}/\d{2}/\d{4})', texto)
                if match_data:
                    data_str = match_data.group(1)
                    data = data_str.replace('/', '-')

                # Extrair nome do destinatário (PIX)
                # Procurar após "Informações do Destinatário"
                match_destinatario = re.search(r'Informações do Destinatário.*?Nome:\s*(.+?)(?:\n|CPF)', texto,
                                               re.DOTALL)
                if match_destinatario:
                    destinatario = match_destinatario.group(1).strip()

            return data, destinatario, tipo_comprovante

    except Exception as e:
        st.error(f"Erro ao processar PDF: {str(e)}")
        return None, None, None


def limpar_nome_arquivo(nome):
    """
    Remove caracteres inválidos do nome do arquivo
    """
    # Remove caracteres que não são permitidos em nomes de arquivo
    nome_limpo = re.sub(r'[<>:"/\\|?*]', '', nome)
    # Remove espaços extras
    nome_limpo = ' '.join(nome_limpo.split())
    return nome_limpo


def processar_zip(zip_file):
    """
    Processa o arquivo ZIP com comprovantes e retorna novo ZIP renomeado
    """
    resultados = []

    # Criar diretório temporário
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Extrair arquivos do ZIP
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall(temp_path)

        # Processar cada PDF
        pdf_files = list(temp_path.rglob('*.pdf'))

        if not pdf_files:
            st.warning("Nenhum arquivo PDF encontrado no ZIP.")
            return None, []

        progress_bar = st.progress(0)
        status_text = st.empty()

        arquivos_renomeados = []

        for idx, pdf_file in enumerate(pdf_files):
            status_text.text(f"Processando {pdf_file.name}...")

            # Extrair informações
            data, destinatario, tipo = extrair_info_comprovante(pdf_file)

            if data and destinatario:
                # Criar novo nome
                destinatario_limpo = limpar_nome_arquivo(destinatario)
                novo_nome = f"{data} - {destinatario_limpo}.pdf"

                # Caminho do arquivo renomeado
                novo_caminho = temp_path / novo_nome

                # Renomear arquivo
                try:
                    pdf_file.rename(novo_caminho)
                    arquivos_renomeados.append(novo_caminho)
                    resultados.append({
                        'original': pdf_file.name,
                        'novo_nome': novo_nome,
                        'status': '✅ Sucesso',
                        'tipo': tipo or 'Desconhecido',
                        'data': data,
                        'destinatario': destinatario_limpo
                    })
                except Exception as e:
                    resultados.append({
                        'original': pdf_file.name,
                        'novo_nome': '-',
                        'status': f'❌ Erro ao renomear: {str(e)}',
                        'tipo': tipo or 'Desconhecido',
                        'data': data,
                        'destinatario': destinatario_limpo
                    })
            else:
                resultados.append({
                    'original': pdf_file.name,
                    'novo_nome': '-',
                    'status': '⚠️ Informações não encontradas',
                    'tipo': tipo or 'Desconhecido',
                    'data': data or 'N/A',
                    'destinatario': destinatario or 'N/A'
                })

            progress_bar.progress((idx + 1) / len(pdf_files))

        status_text.text("Criando arquivo ZIP final...")

        # Criar novo ZIP com arquivos renomeados
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            for arquivo in arquivos_renomeados:
                zip_out.write(arquivo, arquivo.name)

        progress_bar.progress(1.0)
        status_text.text("Processamento concluído!")

        return zip_buffer.getvalue(), resultados


def main():
    st.set_page_config(
        page_title="Renomear Comprovantes",
        page_icon="📄",
        layout="wide"
    )

    st.title("📄 Renomeador de Comprovantes de Pagamento")
    st.markdown("""
    Esta aplicação processa comprovantes de pagamento em PDF e os renomeia automaticamente 
    no formato: **Data - Nome do Destinatário/Beneficiário/Favorecido**

    Suporta: **Boleto**, **PIX** e **TED**
    """)

    st.divider()

    # Upload do arquivo ZIP
    st.subheader("1️⃣ Upload do Arquivo")
    uploaded_file = st.file_uploader(
        "Envie um arquivo ZIP contendo os comprovantes em PDF",
        type=['zip'],
        help="O arquivo ZIP deve conter apenas arquivos PDF de comprovantes"
    )

    if uploaded_file is not None:
        st.success(f"Arquivo carregado: {uploaded_file.name}")

        # Botão para processar
        if st.button("🚀 Processar Comprovantes", type="primary", use_container_width=True):
            with st.spinner("Processando comprovantes..."):
                zip_output, resultados = processar_zip(uploaded_file)

            if zip_output and resultados:
                st.divider()
                st.subheader("2️⃣ Resultados do Processamento")

                # Estatísticas
                col1, col2, col3 = st.columns(3)

                total = len(resultados)
                sucesso = len([r for r in resultados if r['status'] == '✅ Sucesso'])
                erro = total - sucesso

                col1.metric("Total de Arquivos", total)
                col2.metric("Processados com Sucesso", sucesso)
                col3.metric("Erros/Avisos", erro)

                # Tabela de resultados
                st.dataframe(
                    resultados,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        'original': 'Nome Original',
                        'novo_nome': 'Novo Nome',
                        'status': 'Status',
                        'tipo': 'Tipo',
                        'data': 'Data',
                        'destinatario': 'Destinatário'
                    }
                )

                st.divider()
                st.subheader("3️⃣ Download dos Arquivos Renomeados")

                # Botão de download
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nome_arquivo = f"comprovantes_renomeados_{timestamp}.zip"

                st.download_button(
                    label="📥 Baixar ZIP com Comprovantes Renomeados",
                    data=zip_output,
                    file_name=nome_arquivo,
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )

                st.success("✅ Processamento concluído! Clique no botão acima para baixar os arquivos renomeados.")

    # Informações adicionais
    with st.expander("ℹ️ Informações e Formato"):
        st.markdown("""
        ### Formato do Nome
        Os arquivos serão renomeados seguindo o padrão:
        ```
        DD-MM-YYYY - NOME DO DESTINATÁRIO/BENEFICIÁRIO/FAVORECIDO.pdf
        ```

        ### Exemplos:

        **Boleto:**
        - **Antes:** `comprovante_123.pdf`
        - **Depois:** `22-12-2025 - A S DA CONCEICAO COMERCIO & SERVICOS LTDA.pdf`

        **PIX:**
        - **Antes:** `pix_001.pdf`
        - **Depois:** `19-12-2025 - Francivaldo de Sousa Figueira.pdf`

        **TED:**
        - **Antes:** `ted_456.pdf`
        - **Depois:** `12-06-2025 - MOVIDA PARTICIPACOES S.A..pdf`

        ### Tipos de Comprovante Suportados:

        ✅ **Boleto** - Extrai "Data de débito" e "Nome do beneficiário"

        ✅ **PIX** - Extrai "Data/Hora" (apenas data) e "Nome" do destinatário

        ✅ **TED** - Extrai "Data/Hora" (apenas data) e "Favorecido"

        ### Requisitos:
        - Os PDFs devem ser comprovantes do Omie Cash ou formato similar
        - **Boletos** devem conter os campos "Data de débito" e "Nome do beneficiário"
        - **PIX** devem conter os campos "Data/Hora" e "Nome" (em Informações do Destinatário)
        - **TED** devem conter os campos "Data/Hora" e "Favorecido"
        - Arquivos que não seguirem esses padrões não serão renomeados

        ### Observações:
        - O sistema detecta automaticamente se é Boleto, PIX ou TED
        - Caracteres especiais inválidos são removidos automaticamente
        - Espaços extras são normalizados
        - Para PIX e TED, apenas a data é usada (hora é descartada)
        - Arquivos duplicados (mesmo destinatário e data) sobrescreverão uns aos outros
        """)

    st.divider()
    st.caption("Desenvolvido para Rezende Energia | Processamento de Comprovantes")


if __name__ == "__main__":
    main()