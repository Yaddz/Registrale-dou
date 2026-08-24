from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
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
    origem = db.Column(db.String(50), default='GestãoClick')
    status = db.Column(db.Boolean, default=True) # Monitorado Sim/Não

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
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
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
    cnpj_norm = db.Column(db.String(20))
    secao = db.Column(db.String(50))
    data = db.Column(db.String(20))
    detected_at = db.Column(db.String(100))
    trecho = db.Column(db.Text)
    link = db.Column(db.Text)

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
            "link": self.link
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
