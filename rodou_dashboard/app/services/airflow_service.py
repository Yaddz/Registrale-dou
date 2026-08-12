import os
import requests
import subprocess
import json
from datetime import datetime, timezone

def trigger_airflow_dag(dag_id, logical_date=None, **kwargs):
    """Tenta disparar uma DAG no Airflow via API REST ou Docker CLI."""
    try:
        airflow_url = os.getenv('AIRFLOW_URL', 'http://localhost:8080')
        auth = ("airflow", "airflow")
        
        # 1. Unpause the DAG
        patch_url = f"{airflow_url}/api/v1/dags/{dag_id}"
        requests.patch(patch_url, json={"is_paused": False}, auth=auth, timeout=5)
        
        # 2. Trigger the DAG
        trigger_url = f"{airflow_url}/api/v1/dags/{dag_id}/dagRuns"
        payload = {}
        if logical_date:
            try:
                payload["conf"] = {"trigger_date": logical_date}
            except: pass
            
        response = requests.post(trigger_url, json=payload, auth=auth, timeout=5)
        
        if response.status_code in [200, 201]:
            return True, f"DAG {dag_id} disparada via API."
        else:
            return False, f"Erro Airflow API ({response.status_code}): {response.text}"
    except Exception as e:
        # Fallback para docker exec caso a API não esteja acessível
        try:
            subprocess.run(["docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "dags", "unpause", dag_id], capture_output=True, timeout=15)
            cmd = ["docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "dags", "trigger", dag_id]
            if logical_date:
                cmd.extend(["--conf", json.dumps({"trigger_date": logical_date})])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                return True, f"DAG {dag_id} disparada via Docker CLI."
            else:
                return False, f"Erro Docker/Airflow: {result.stderr or result.stdout}"
        except Exception as e2:
            return False, f"Falha API REST ({str(e)}) e falha Docker CLI ({str(e2)})"
