import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import os
from ..models import Settings

class EmailSender:
    def __init__(self, config=None):
        self.config = config
        self._smtp_config = None
        
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

        host = smtp_config.get('server') or smtp_config.get('host') or os.getenv('AIRFLOW__SMTP__SMTP_HOST', 'smtp4dev')
        port = int(smtp_config.get('port') or os.getenv('AIRFLOW__SMTP__SMTP_PORT', 25))
        user = smtp_config.get('user') or os.getenv('AIRFLOW__SMTP__SMTP_USER', '')
        password = smtp_config.get('password') or os.getenv('AIRFLOW__SMTP__SMTP_PASSWORD', '')
        sender_email = smtp_config.get('from_email') or smtp_config.get('sender') or user or os.getenv('AIRFLOW__SMTP__SMTP_MAIL_FROM', 'rodou@gestao.gov.br')

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = ", ".join(to_emails)

        part = MIMEText(html_content, "html", "utf-8")
        msg.attach(part)

        try:
            if port == 465:
                server_conn = smtplib.SMTP_SSL(host, port, timeout=15)
            else:
                server_conn = smtplib.SMTP(host, port, timeout=15)
                if port in (587, 25):
                    try:
                        server_conn.starttls()
                    except:
                        pass

            if user and password:
                server_conn.login(user, password)
            server_conn.sendmail(sender_email, to_emails, msg.as_string())
            server_conn.quit()
            logging.info(f"Email enviado com sucesso via {host} para {to_emails}")
        except Exception as e:
            logging.error(f"Falha ao enviar email via {host}:{port}: {str(e)}")
            raise e
