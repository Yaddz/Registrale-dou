from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
import json

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False, default="N/A")
    cnpj = db.Column(db.String(20), unique=True, nullable=False)
    cnpj_norm = db.Column(db.String(20), unique=True, nullable=False, index=True)
    origem = db.Column(db.String(50), default='GestãoClick', index=True)
    status = db.Column(db.Boolean, default=True, index=True) # Monitorado Sim/Não

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "cnpj": self.cnpj,
            "cnpj_norm": self.cnpj_norm,
            "origem": self.origem,
            "status": self.status
        }

class SyncHistory(db.Model):
    __tablename__ = 'sync_history'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(50), nullable=False)
    evento = db.Column(db.String(255), nullable=False)
    detalhes = db.Column(db.Text, nullable=True)

    @classmethod
    def log_event(cls, evento, detalhes="", max_history=50):
        """Registra um evento de histórico mantendo no máximo max_history registros (FIFO)."""
        try:
            now_str = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M:%S")
            hist = cls(data=now_str, evento=evento, detalhes=detalhes)
            db.session.add(hist)
            db.session.commit()
            
            total = cls.query.count()
            if total > max_history:
                oldest_ids = [
                    h.id for h in cls.query.order_by(cls.id.asc()).limit(total - max_history).all()
                ]
                if oldest_ids:
                    cls.query.filter(cls.id.in_(oldest_ids)).delete(synchronize_session=False)
                    db.session.commit()
            return hist
        except Exception:
            db.session.rollback()
            return None

    def to_dict(self):
        return {
            "id": self.id,
            "data": self.data,
            "evento": self.evento,
            "detalhes": self.detalhes
        }

    @classmethod
    def get_last_sync_display(cls) -> str:
        """Retorna a data/hora da última sincronização no fuso de Brasília, ou 'Nunca'."""
        last_sync_record = cls.query.filter(
            (cls.evento.like('%GestãoClick%'))
            | (cls.evento.like('%Google Sheets%'))
            | (cls.evento.like('%Sincronização%'))
            | (cls.evento.like('%Sync%'))
        ).order_by(cls.id.desc()).first()

        if not last_sync_record or not last_sync_record.data:
            return "Nunca"

        raw = str(last_sync_record.data).strip()
        if len(raw) >= 10 and raw[2] == "/" and raw[5] == "/":
            return raw

        br_tz = timezone(timedelta(hours=-3))
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(br_tz).strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            return raw

class InlabsDownloadLog(db.Model):
    __tablename__ = 'inlabs_download_log'
    id = db.Column(db.Integer, primary_key=True)
    date_str = db.Column(db.String(10), unique=True, nullable=False)
    downloaded_at = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='success')

class Mention(db.Model):
    __tablename__ = 'mentions'
    id = db.Column(db.String(255), primary_key=True) # pub_id ou fallback_id
    empresa = db.Column(db.String(255))
    cnpj = db.Column(db.String(20))
    cnpj_norm = db.Column(db.String(20), index=True)
    secao = db.Column(db.String(50))
    data = db.Column(db.String(20), index=True)
    detected_at = db.Column(db.String(100))
    trecho = db.Column(db.Text)
    link = db.Column(db.Text)
    pdf_path = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "empresa": self.empresa,
            "cnpj": self.cnpj,
            "cnpj_norm": self.cnpj_norm,
            "secao": self.secao,
            "data": self.data,
            "detected_at": self.detected_at,
            "trecho": self.trecho,
            "link": self.link,
            "pdf_path": self.pdf_path,
        }

class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)

    def get_value(self):
        try:
            return json.loads(self.value)
        except:
            return self.value

    def set_value(self, val):
        self.value = json.dumps(val)

class EmailTemplate(db.Model):
    __tablename__ = 'email_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body_html = db.Column(db.Text, nullable=False)


class JobRun(db.Model):
    """Histórico de execuções locais de rotinas (substitui o XCom/dagRuns do Airflow)."""
    __tablename__ = 'job_runs'
    id = db.Column(db.String(128), primary_key=True)
    rotina = db.Column(db.String(255), nullable=False, index=True)
    data = db.Column(db.String(20), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='queued', index=True)
    inicio = db.Column(db.String(50), nullable=True)
    fim = db.Column(db.String(50), nullable=True)
    erro = db.Column(db.Text, nullable=True)
    resultado_json = db.Column(db.Text, nullable=True)

    def get_resultado(self):
        if not self.resultado_json:
            return []
        try:
            data = json.loads(self.resultado_json)
            return data if isinstance(data, list) else [data]
        except Exception:
            return []

    def set_resultado(self, val):
        self.resultado_json = json.dumps(val, ensure_ascii=False) if val is not None else None

    def to_dict(self):
        return {
            "id": self.id,
            "rotina": self.rotina,
            "data": self.data,
            "status": self.status,
            "inicio": self.inicio,
            "fim": self.fim,
            "erro": self.erro,
        }

