from flask import Blueprint, request, jsonify, session, send_file, after_this_request
import os
import json
from .auth import login_required
from .companies import get_companies_data
import logging

exports_bp = Blueprint('exports', __name__)
logger = logging.getLogger(__name__)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, "data")

def add_history_event(evento, detalhes):
    from ..models import db, SyncHistory
    try:
        from datetime import datetime, timezone, timedelta
        new_event = SyncHistory(
            data=datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m %H:%M'),
            evento=evento,
            detalhes=detalhes
        )
        db.session.add(new_event)
        if SyncHistory.query.count() >= 50:
            oldest = SyncHistory.query.order_by(SyncHistory.id.asc()).first()
            if oldest:
                db.session.delete(oldest)
        db.session.commit()
    except Exception as e:
        logger.error(f"Erro ao adicionar histórico: {e}")

@exports_bp.route('/export_report')
@login_required
def export_report():
    import pandas as pd
    import tempfile
    empresas = get_companies_data()
    
    df = pd.DataFrame(empresas)
    if not df.empty:
        df = df[['nome', 'cnpj', 'uf', 'cidade', 'email', 'telefone', 'situacao', 'status', 'origem']]
        df.columns = ['Empresa', 'CNPJ', 'UF', 'Cidade', 'Email', 'Telefone', 'Situação', 'Monitorado', 'Origem']
        df['Monitorado'] = df['Monitorado'].apply(lambda x: 'Sim' if x else 'Não')
    else:
        df = pd.DataFrame(columns=['Empresa', 'CNPJ', 'UF', 'Cidade', 'Email', 'Telefone', 'Situação', 'Monitorado', 'Origem'])
    
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False, dir=DATA_DIR)
    df.to_excel(tmp.name, index=False)
    tmp_path = tmp.name
    @after_this_request
    def cleanup(response):
        try:
            os.unlink(tmp_path)
        except:
            pass
        return response
    return send_file(tmp_path, as_attachment=True, download_name="relatorio_empresas.xlsx")

@exports_bp.route('/test_smtp', methods=['POST'])
@login_required
def test_smtp():
    if session['user']['role'] != 'master': return jsonify({"status": "error", "message": "Acesso negado."}), 403
    data = request.json
    smtp = data.get('smtp', {})
    test_email = data.get('test_email')
    
    server = smtp.get('server')
    port = smtp.get('port')
    user = smtp.get('user')
    password = smtp.get('password')
    from_email = smtp.get('from_email') or user
    
    if not all([server, port, test_email]):
        return jsonify({"status": "error", "message": "Servidor SMTP, porta e email de teste são obrigatórios."}), 400
        
    import smtplib
    from email.mime.text import MIMEText
    
    msg = MIMEText("Este é um email de teste enviado pelo Painel de Controle do Ro-DOU Registrale para validar as configurações de SMTP.")
    msg['Subject'] = "Ro-DOU - Teste de Conexão SMTP"
    msg['From'] = from_email
    msg['To'] = test_email
    
    try:
        port_num = int(port)
        if port_num == 465:
            server_conn = smtplib.SMTP_SSL(server, port_num, timeout=10)
        else:
            server_conn = smtplib.SMTP(server, port_num, timeout=10)
            if port_num == 587 or port_num == 25:
                try:
                    server_conn.starttls()
                except:
                    pass
                
        if user and password:
            server_conn.login(user, password)
        server_conn.send_message(msg)
        server_conn.quit()
        return jsonify({"status": "success", "message": f"Email de teste enviado com sucesso para {test_email}!"})
    except Exception as e:
        logger.error(f"Falha ao testar SMTP: {e}")
        return jsonify({"status": "error", "message": f"Erro de conexão: {str(e)}"}), 500

@exports_bp.route('/export_sheets', methods=['POST'])
@login_required
def export_sheets():
    from ..models import Settings
    settings_record = Settings.query.filter_by(key='global_settings').first()
    settings = settings_record.get_value() if settings_record else {}
    gs = settings.get('google_sheets', {})
    spreadsheet_id = gs.get('spreadsheet_id')
    sheet_name = gs.get('sheet_name', 'Deteções Ro-DOU')
    credentials_str = gs.get('credentials_json')
    
    if not all([spreadsheet_id, credentials_str]):
        return jsonify({"status": "error", "message": "Google Sheets não configurado nas Integrações."}), 400
        
    data = request.json
    mentions_to_export = data.get('mentions', [])
    if not mentions_to_export:
        return jsonify({"status": "error", "message": "Nenhuma menção selecionada para exportar."}), 400
        
    try:
        import googleapiclient.discovery
        from google.oauth2 import service_account
    except ImportError:
        return jsonify({"status": "error", "message": "Bibliotecas do Google Sheets não instaladas. Execute 'pip install google-api-python-client google-auth' no servidor."}), 500

    try:
        credentials_info = json.loads(credentials_str)
        creds = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = googleapiclient.discovery.build('sheets', 'v4', credentials=creds)
        
        values = []
        for m in mentions_to_export:
            values.append([
                m.get('data', ''),
                m.get('empresa', ''),
                m.get('cnpj', ''),
                m.get('secao', ''),
                m.get('trecho', ''),
                m.get('link', '')
            ])
            
        range_name = f"{sheet_name}!A:F"
        body = {
            'values': values
        }
        
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        
        return jsonify({"status": "success", "message": f"Exportado com sucesso! {result.get('updates', {}).get('updatedRows', 0)} linhas adicionadas no Google Sheets."})
    except Exception as e:
        logger.error(f"Erro ao exportar para Google Sheets: {e}")
        return jsonify({"status": "error", "message": f"Erro de integração: {str(e)}"}), 500

@exports_bp.route('/send_email', methods=['POST'])
@login_required
def send_email():
    from ..models import Settings
    data = request.json
    to_emails = data.get('to_emails', [])
    subject = data.get('subject', 'Notificação Registrale')
    body_html = data.get('body_html', '')
    
    settings_record = Settings.query.filter_by(key='global_settings').first()
    settings = settings_record.get_value() if settings_record else {}
    smtp = settings.get('smtp', {})
    
    server = smtp.get('server')
    port = smtp.get('port')
    user = smtp.get('user')
    password = smtp.get('password')
    from_email = smtp.get('from_email') or user
    
    if not all([server, port]):
        return jsonify({"status": "error", "message": "Configurações SMTP não definidas (servidor e porta são obrigatórios)."}), 400
        
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        port_num = int(port)
        if port_num == 465:
            server_conn = smtplib.SMTP_SSL(server, port_num, timeout=10)
        else:
            server_conn = smtplib.SMTP(server, port_num, timeout=10)
            if port_num == 587 or port_num == 25:
                server_conn.starttls()
                
        if user and password:
            server_conn.login(user, password)
        
        for recipient in to_emails:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_email
            msg['To'] = recipient
            msg.attach(MIMEText(body_html, 'html'))
            server_conn.send_message(msg)
            
        server_conn.quit()
        
        add_history_event("Email Enviado", f"Emails enviados para: {', '.join(to_emails)}")
        return jsonify({"status": "success", "message": "E-mails enviados com sucesso!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@exports_bp.route('/export_pdf', methods=['POST'])
@login_required
def export_pdf():
    data = request.json
    companies = data.get('companies', [])
    filters = data.get('filters', {})
    
    output_filename = os.path.join(DATA_DIR, 'relatorio_empresas.pdf')
    
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from datetime import datetime

    doc = SimpleDocTemplate(output_filename, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=1, fontSize=18, spaceAfter=20)
    meta_style = ParagraphStyle('MetaStyle', parent=styles['Normal'], fontSize=10, spaceAfter=10)
    
    elements.append(Paragraph("<b>REGISTRALE</b> - Relatório de Empresas Monitoradas", title_style))
    elements.append(Paragraph(f"Data de Geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}", meta_style))
    elements.append(Spacer(1, 20))
    
    table_data = [['Razão Social', 'CNPJ', 'UF', 'Cidade', 'Situação', 'Origem', 'Status']]
    for c in companies:
        table_data.append([
            c.get('nome', '')[:40] + ('...' if len(c.get('nome',''))>40 else ''), 
            c.get('cnpj', ''), 
            c.get('uf', ''), 
            c.get('cidade', ''), 
            c.get('situacao', ''), 
            c.get('origem', ''), 
            'Monitorado' if c.get('status') else 'Inativo'
        ])
    
    if len(table_data) > 1:
        t = Table(table_data, colWidths=[200, 100, 40, 100, 80, 80, 80])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
            ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#e2e8f0')),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Nenhuma empresa encontrada com os filtros atuais.", styles['Normal']))
        
    elements.append(PageBreak())
    
    elements.append(Paragraph("<b>Metadados e Filtros Aplicados</b>", title_style))
    elements.append(Spacer(1, 20))
    
    elements.append(Paragraph(f"<b>Usuário Solicitante:</b> {session['user']['username']} ({session['user']['role']})", meta_style))
    elements.append(Paragraph(f"<b>Data da Exportação:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", meta_style))
    elements.append(Paragraph(f"<b>Total de Registros:</b> {len(companies)}", meta_style))
    
    elements.append(Spacer(1, 10))
    elements.append(Paragraph("<b>Filtros Utilizados:</b>", meta_style))
    for k, v in filters.items():
        elements.append(Paragraph(f"- {k.capitalize()}: {v if v else 'Todos'}", meta_style))
        
    doc.build(elements)
    
    return send_file(output_filename, as_attachment=True, download_name="relatorio_empresas.pdf", mimetype='application/pdf')

@exports_bp.route('/export_mentions_pdf', methods=['POST'])
@login_required
def export_mentions_pdf():
    import tempfile
    data = request.json
    mentions = data.get('mentions', [])
    
    output_filename = os.path.join(DATA_DIR, 'relatorio_mencoes.pdf')
    
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from datetime import datetime

    doc = SimpleDocTemplate(output_filename, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=1, fontSize=18, spaceAfter=20)
    meta_style = ParagraphStyle('MetaStyle', parent=styles['Normal'], fontSize=10, spaceAfter=10)
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=8, leading=10)
    link_style = ParagraphStyle('LinkStyle', parent=styles['Normal'], fontSize=8, leading=10, textColor=colors.HexColor('#2563eb'))
    
    elements.append(Paragraph("<b>REGISTRALE</b> - Relatório de Menções Detectadas", title_style))
    elements.append(Paragraph(f"Data de Geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}", meta_style))
    elements.append(Spacer(1, 20))
    
    table_data = [['Data', 'Empresa', 'CNPJ', 'Seção', 'Trecho', 'Link']]
    for m in mentions:
        trecho = (m.get('trecho', '') or '')[:80] + ('...' if len(m.get('trecho', '') or '') > 80 else '')
        link = m.get('link', '')
        link_para = Paragraph(f'<a href="{link}">Abrir</a>', link_style) if link else ''
        table_data.append([
            m.get('data', ''),
            Paragraph(m.get('empresa', ''), cell_style),
            m.get('cnpj', ''),
            m.get('secao', ''),
            Paragraph(trecho, cell_style),
            link_para
        ])
    
    if len(table_data) > 1:
        t = Table(table_data, colWidths=[70, 140, 90, 70, 300, 50])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1c1917')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f4')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d6d3d1')),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f5f5f4'), colors.white]),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Nenhuma menção encontrada.", styles['Normal']))
    
    elements.append(PageBreak())
    
    elements.append(Paragraph("<b>Informações da Geração</b>", title_style))
    elements.append(Spacer(1, 20))
    
    meta_table_data = [
        ['Campo', 'Valor'],
        ['Data', datetime.now().strftime('%d/%m/%Y')],
        ['Hora', datetime.now().strftime('%H:%M:%S')],
        ['Usuário', session['user']['username']],
        ['Total de Menções', str(len(mentions))],
    ]
    
    meta_t = Table(meta_table_data, colWidths=[200, 300])
    meta_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1c1917')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f4')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d6d3d1')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(meta_t)
    
    doc.build(elements)
    
    return send_file(output_filename, as_attachment=True, download_name="relatorio_mencoes.pdf", mimetype='application/pdf')

@exports_bp.route('/export_mentions_excel', methods=['POST'])
@login_required
def export_mentions_excel():
    import pandas as pd
    import tempfile
    data = request.json
    mentions = data.get('mentions', [])
    
    df = pd.DataFrame(mentions)
    if not df.empty:
        df = df[['data', 'empresa', 'cnpj', 'secao', 'trecho', 'link']]
        df.columns = ['Data', 'Empresa', 'CNPJ', 'Seção', 'Trecho', 'Link']
    else:
        df = pd.DataFrame(columns=['Data', 'Empresa', 'CNPJ', 'Seção', 'Trecho', 'Link'])
    
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False, dir=DATA_DIR)
    df.to_excel(tmp.name, index=False)
    tmp_path = tmp.name
    @after_this_request
    def cleanup(response):
        try:
            os.unlink(tmp_path)
        except:
            pass
        return response
    return send_file(tmp_path, as_attachment=True, download_name="relatorio_mencoes.xlsx")
