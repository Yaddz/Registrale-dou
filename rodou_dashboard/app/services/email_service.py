import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import os
from ..models import Settings

class EmailSender:
    def __init__(self, config=None):
        self._smtp_config = config
        
    def _get_smtp_config(self):
        """Carrega config SMTP uma única vez por instância para evitar lookups no BD e lentidão."""
        if self._smtp_config is not None:
            return self._smtp_config
            
        settings_record = Settings.query.filter_by(key='global_settings').first()
        smtp_config = {}
        
        if settings_record:
            s_val = settings_record.get_value()
            smtp_config = s_val.get('smtp', {})
            
        self._smtp_config = smtp_config
        return smtp_config
        
    def send_custom_email(self, to_emails, subject, html_content):
        smtp_config = self._get_smtp_config()

        if isinstance(to_emails, str):
            to_emails = [e.strip() for e in to_emails.replace(';', ',').split(',') if e.strip()]
        elif isinstance(to_emails, (list, tuple, set)):
            to_emails = [str(e).strip() for e in to_emails if str(e).strip()]
        else:
            to_emails = []

        if not to_emails:
            raise ValueError("Nenhum destinatário de e-mail válido informado.")

        host = (smtp_config.get('server') or smtp_config.get('host') or os.getenv('AIRFLOW__SMTP__SMTP_HOST', 'smtp4dev')).strip()
        if host.lower().startswith('stmp.'):
            host = 'smtp.' + host[5:]
        elif host.lower().startswith('smpt.'):
            host = 'smtp.' + host[5:]
        port_raw = smtp_config.get('port') or os.getenv('AIRFLOW__SMTP__SMTP_PORT', 25)
        port = int(str(port_raw).strip())
        user = (smtp_config.get('user') or os.getenv('AIRFLOW__SMTP__SMTP_USER', '')).strip()
        raw_password = smtp_config.get('password') or os.getenv('AIRFLOW__SMTP__SMTP_PASSWORD', '')
        password = str(raw_password).strip()
        if 'gmail.com' in host.lower() or 'googlemail.com' in host.lower():
            password = password.replace(' ', '')
        sender_email = (smtp_config.get('from_email') or smtp_config.get('sender') or user or os.getenv('AIRFLOW__SMTP__SMTP_MAIL_FROM', 'rodou@gestao.gov.br')).strip()

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = ", ".join(to_emails)

        part = MIMEText(html_content, "html", "utf-8")
        msg.attach(part)

        server_conn = None
        try:
            if port == 465:
                server_conn = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server_conn = smtplib.SMTP(host, port, timeout=15)
                if port in (587, 25):
                    try:
                        server_conn.starttls()
                    except Exception as tls_err:
                        logging.warning(f"STARTTLS warning: {tls_err}")

            if user and password:
                server_conn.login(user, password)
            server_conn.sendmail(sender_email, to_emails, msg.as_string())
            logging.info(f"Email enviado com sucesso via {host} para {to_emails}")
            return True
        except Exception as e:
            logging.error(f"Falha ao enviar email via {host}:{port}: {str(e)}")
            raise
        finally:
            if server_conn:
                try:
                    server_conn.quit()
                except Exception:
                    pass

def apply_highlight_to_trecho(trecho: str, cnpj: str = '', cnpj_norm: str = '', terms: list = None, empresa: str = '') -> str:
    """Aplica o destaque amarelo em trechos para CNPJ, termos ou placeholders de busca com limites de palavra."""
    import re
    if not trecho:
        return ''
        
    t = re.sub(r'\s*-\s*PARTE\s*\d+', '', str(trecho), flags=re.IGNORECASE)
    
    # 1. Trata placeholders de destaque do motor de busca <%%>...</%%>
    if '<%%>' in t and '</%%>' in t:
        t = t.replace('<%%>', "<span class='highlight' style='background-color: #FFA; font-weight: bold; padding: 1px 4px; border-radius: 2px; color: #000;'>")
        t = t.replace('</%%>', "</span>")
        return t
        
    # 2. Converte tags <mark> ou <span class='highlight'> existentes garantindo estilo inline
    if '<mark' in t:
        t = re.sub(r'<mark[^>]*>', "<span class='highlight' style='background-color: #FFA; font-weight: bold; padding: 1px 4px; border-radius: 2px; color: #000;'>", t, flags=re.IGNORECASE)
        t = re.sub(r'</mark>', "</span>", t, flags=re.IGNORECASE)
        return t
        
    if "class='highlight'" in t or 'class="highlight"' in t:
        t = re.sub(r'<span class=[\'"]highlight[\'"][^>]*>', "<span class='highlight' style='background-color: #FFA; font-weight: bold; padding: 1px 4px; border-radius: 2px; color: #000;'>", t, flags=re.IGNORECASE)
        return t

    # 3. Destaque por correspondência segura com limite de palavras (\b)
    targets = []
    if cnpj and len(cnpj.strip()) >= 8:
        clean_cnpj = cnpj.strip()
        targets.append(re.escape(clean_cnpj))
        unmasked = re.sub(r'\D', '', clean_cnpj)
        if len(unmasked) == 14:
            targets.append(r'\b' + unmasked + r'\b')
    elif cnpj_norm and len(cnpj_norm.strip()) == 14:
        targets.append(r'\b' + cnpj_norm.strip() + r'\b')
        
    if empresa and len(empresa.strip()) >= 6:
        clean_emp = empresa.strip()
        stop_words = {'LTDA', 'EIRELI', 'S.A.', 'S/A', 'ME', 'EPP', 'BRASIL', 'SERVIÇOS', 'SERVICOS', 'COMÉRCIO', 'COMERCIO', 'GRUPO', 'EMPRESA', 'ADMINISTRAÇÃO', 'ADMINISTRACAO'}
        if clean_emp.upper() not in stop_words:
            targets.append(r'\b' + re.escape(clean_emp) + r'\b')
        
    if terms:
        if isinstance(terms, str):
            terms = [terms]
        for term in terms:
            t_str = str(term).strip()
            if t_str and len(t_str) >= 3 and t_str.upper() not in {'DE', 'DA', 'DO', 'EM', 'NO', 'NA', 'PARA', 'COM', 'POR', 'DOU', 'SECAO'}:
                targets.append(r'\b' + re.escape(t_str) + r'\b')
                
    if targets:
        # Ordena alvos pelo maior comprimento
        targets = sorted(list(set(targets)), key=len, reverse=True)
        try:
            pattern = re.compile(r'(' + '|'.join(targets) + r')', re.IGNORECASE)
            t = pattern.sub(r"<span class='highlight' style='background-color: #FFA; font-weight: bold; padding: 1px 4px; border-radius: 2px; color: #000;'>\1</span>", t)
        except Exception:
            pass
        
    return t

def build_mentions_email_html(mentions, template_name='Padrão Registrale', title=None, subtitle=None):
    """Renderiza a lista de menções no template HTML com formatação responsiva e suporte a templates sem {content}."""
    from ..models import EmailTemplate
    import re
    
    template = EmailTemplate.query.filter_by(name=template_name).first()
    if not template:
        template = EmailTemplate.query.filter_by(name='Padrão Registrale').first()
    
    if not mentions:
        empty_html = '<div style="padding: 30px; text-align: center; color: #64748b; font-size: 14px;">Nenhuma publicação encontrada para o período pesquisado.</div>'
        if template:
            base_html = template.body_html
            if title: base_html = re.sub(r'<h2[^>]*>.*?</h2>', f'<h2 style="color: #2563eb; margin:0;">{title}</h2>', base_html)
            if subtitle: base_html = re.sub(r'<p[^>]*>.*?</p>', f'<p style="color: #333; margin-top:10px;">{subtitle}</p>', base_html, count=1)
            if '{content}' in base_html:
                return base_html.replace('{content}', empty_html)
            return base_html
        return empty_html

    parts = []
    for m in mentions:
        cnpj = m.get('cnpj', '')
        cnpj_norm = m.get('cnpj_norm', '')
        empresa = m.get('empresa') or '—'
        trecho_raw = m.get('trecho', '')
        trecho = apply_highlight_to_trecho(trecho_raw, cnpj=cnpj, cnpj_norm=cnpj_norm, empresa=empresa)
        secao = m.get('secao') or 'DOU'
        data = m.get('data') or '—'
        link = m.get('link') or '#'
        
        cnpj_display = f"<span class='highlight' style='background-color: #FFA; font-weight: bold; padding: 1px 4px; border-radius: 2px; color: #000;'>{cnpj or cnpj_norm}</span>" if (cnpj or cnpj_norm) else "—"
        
        parts.append(f'''
        <div class="container" style="max-width: 1200px; margin: 0 auto 20px auto; background-color: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); overflow: hidden; border: 1px solid #e2e8f0;">
            <div class="content" style="padding: 5px;">
                <section>
                    <div class="results-section">
                        <div class="result-header" style="background-color: #06acff; color: white; padding: 12px 20px; font-weight: 600; font-size: 15px;">
                            {empresa}
                        </div>
                        <div class="result-body" style="padding: 15px 20px 10px;">
                            <h3 style="color: #545b61; font-size: 14px; margin: 0 0 8px 0;"><strong>Resultados para: </strong> {cnpj_display}</h3>
                            <div class="section-marker" style="color: #06acff; font-size: 12px; font-weight: bold; margin-bottom: 8px;">{secao}</div>
                            <div class="abstract" style="background-color: #f8f9fa; padding: 12px; border-radius: 6px; margin-top: 4px; text-align: justify; font-size: 14px; line-height: 1.5; color: #334155;">
                                <span class="tag recort" style="display: inline-block; padding: 2px 6px; font-size: 11px; font-weight: 600; color: #333; background-color: #ffebcc; border-radius: 4px; margin-right: 6px;">Recorte:</span> {trecho}
                            </div>
                            <div class="date" style="color: #64748b; font-size: 13px; font-weight: 500; text-align: right; margin-top: 10px;">{data}</div>
                            <div style="margin-top: 10px; margin-bottom: 10px;">
                                <a href="{link}" target="_blank" style="display: inline-block; font-size: 12px; padding: 6px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background-color: #f1f5f9; text-decoration: none; color: #0284c7; font-weight: 600;">
                                    &#8599; Ver Íntegra no DOU
                                </a>
                            </div>
                        </div>
                    </div>
                </section>
            </div>
        </div>''')

    mentions_html = ''.join(parts)
    if template:
        base_html = template.body_html
        if title: base_html = re.sub(r'<h2[^>]*>.*?</h2>', f'<h2 style="color: #2563eb; margin:0;">{title}</h2>', base_html)
        if subtitle: base_html = re.sub(r'<p[^>]*>.*?</p>', f'<p style="color: #333; margin-top:10px;">{subtitle}</p>', base_html, count=1)
        if '{content}' in base_html:
            return base_html.replace('{content}', mentions_html)
        else:
            if mentions:
                m0 = mentions[0]
                cnpj0 = m0.get('cnpj', '') or m0.get('cnpj_norm', '')
                empresa0 = m0.get('empresa') or '—'
                trecho0 = apply_highlight_to_trecho(m0.get('trecho', ''), cnpj=cnpj0, empresa=empresa0)
                secao0 = m0.get('secao') or 'DOU'
                data0 = m0.get('data') or '—'
                link0 = m0.get('link') or '#'
                base_html = base_html.replace('{empresa}', empresa0)
                base_html = base_html.replace('{cnpj}', f"<span class='highlight' style='background-color: #FFA; font-weight: bold; padding: 1px 4px; border-radius: 2px; color: #000;'>{cnpj0}</span>")
                base_html = base_html.replace('{secao}', secao0)
                base_html = base_html.replace('{data}', data0)
                base_html = base_html.replace('{trecho}', trecho0)
                base_html = base_html.replace('{link}', link0)
                
                if len(mentions) > 1:
                    extra_mentions_html = ''.join(parts[1:])
                    if '</body>' in base_html:
                        base_html = base_html.replace('</body>', f'{extra_mentions_html}</body>')
                    else:
                        base_html += extra_mentions_html
            return base_html
    return mentions_html
