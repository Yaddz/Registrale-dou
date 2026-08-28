import os
import requests
import subprocess
import json
import urllib.parse
from datetime import datetime, timezone, timedelta

def get_airflow_url():
    """Retorna a URL base do Airflow a partir das variáveis de ambiente."""
    return os.getenv('AIRFLOW_URL', 'http://localhost:8080')

def get_airflow_auth():
    """Retorna a tupla de autenticação básica para a API do Airflow."""
    user = os.getenv('AIRFLOW_USER', 'airflow')
    password = os.getenv('AIRFLOW_PASSWORD', 'airflow')
    return (user, password)

def trigger_airflow_dag(dag_id, logical_date=None, **kwargs):
    """Tenta disparar uma DAG no Airflow via API REST ou Docker CLI.
    Retorna (success: bool, message: str, run_info: dict).
    """
    trigger_time_dt = datetime.now(timezone(timedelta(hours=-3)))
    trigger_time_iso = trigger_time_dt.isoformat()
    trigger_time_str = trigger_time_dt.strftime('%Y-%m-%dT%H:%M:%S')
    
    run_info = {
        "dag_id": dag_id,
        "dag_run_id": None,
        "trigger_time": trigger_time_str,
        "trigger_time_iso": trigger_time_iso,
        "trigger_ts": trigger_time_dt.timestamp()
    }
    
    try:
        airflow_url = get_airflow_url()
        auth = get_airflow_auth()
        dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
        
        # 1. Unpause the DAG
        patch_url = f"{airflow_url}/api/v1/dags/{dag_id_quoted}"
        requests.patch(patch_url, json={"is_paused": False}, auth=auth, timeout=5)
        
        # 2. Trigger the DAG
        trigger_url = f"{airflow_url}/api/v1/dags/{dag_id_quoted}/dagRuns"
        payload = {}
        unique_suffix = int(datetime.now().timestamp() * 1000)
        if logical_date:
            if '/' in str(logical_date):
                parts = str(logical_date).split('/')
                if len(parts) == 3:
                    logical_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
            payload["dag_run_id"] = f"manual__{dag_id}_{logical_date}_{unique_suffix}"
        else:
            payload["dag_run_id"] = f"manual__{dag_id}_{unique_suffix}"
            
        payload["conf"] = {}
        if logical_date:
            payload["conf"]["trigger_date"] = logical_date
        for k, v in kwargs.items():
            payload["conf"][k] = v
            
        response = requests.post(trigger_url, json=payload, auth=auth, timeout=10)
        
        if response.status_code in [200, 201]:
            resp_data = response.json() if response.content else {}
            dag_run_id = resp_data.get("dag_run_id")
            run_info["dag_run_id"] = dag_run_id
            return True, f"DAG {dag_id} disparada via API.", run_info
        else:
            return False, f"Erro Airflow API ({response.status_code}): {response.text}", run_info
    except Exception as e:
        # Fallback para docker exec caso a API não esteja acessível
        try:
            subprocess.run(["docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "dags", "unpause", dag_id], capture_output=True, timeout=15)
            cmd = ["docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "dags", "trigger", dag_id]
            conf_payload = {}
            if logical_date:
                conf_payload["trigger_date"] = logical_date
            conf_payload.update(kwargs)
            if conf_payload:
                cmd.extend(["--conf", json.dumps(conf_payload)])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                return True, f"DAG {dag_id} disparada via Docker CLI.", run_info
            else:
                return False, f"Erro Docker/Airflow: {result.stderr or result.stdout}", run_info
        except Exception as e2:
            return False, f"Falha API REST ({str(e)}) e falha Docker CLI ({str(e2)})", run_info

def toggle_airflow_dag(dag_id, is_paused=True):
    """Pausa ou despausa uma DAG no Airflow via REST API com fallback para Docker CLI."""
    if not dag_id:
        return False, "ID da DAG não informado."
    
    try:
        airflow_url = get_airflow_url()
        auth = get_airflow_auth()
        dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
        patch_url = f"{airflow_url}/api/v1/dags/{dag_id_quoted}"
        res = requests.patch(patch_url, json={"is_paused": bool(is_paused)}, auth=auth, timeout=5)
        if res.status_code in (200, 201):
            action = "pausada" if is_paused else "ativada"
            return True, f"DAG {dag_id} {action} com sucesso no Airflow."
    except Exception:
        pass
    
    # Fallback Docker CLI
    try:
        cmd_action = "pause" if is_paused else "unpause"
        res_sub = subprocess.run(["docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "dags", cmd_action, dag_id], capture_output=True, timeout=10)
        if res_sub.returncode == 0:
            return True, f"DAG {dag_id} atualizada via Docker CLI."
    except Exception:
        pass

    return True, "Status da rotina atualizado localmente."

def wait_for_specific_dag_runs(dag_id, run_ids, max_wait=1800, poll_interval=4):
    """
    Aguarda especificamente até que todos os `run_ids` da DAG indicada atinjam
    um estado terminal ('success' ou 'failed') no Airflow.
    Retorna (all_finished: bool, states_dict: dict).
    """
    import time
    import logging
    
    if not run_ids:
        return True, {}
        
    airflow_url = get_airflow_url()
    auth = get_airflow_auth()
    
    start_time = time.time()
    pending_runs = set(run_ids)
    run_states = {}
    dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
    
    # Aguarda 3 segundos iniciais para o scheduler do Airflow enfileirar
    time.sleep(3)
    
    while pending_runs and (time.time() - start_time) < max_wait:
        for run_id in list(pending_runs):
            try:
                run_id_quoted = urllib.parse.quote(str(run_id), safe='')
                url = f"{airflow_url}/api/v1/dags/{dag_id_quoted}/dagRuns/{run_id_quoted}"
                r = requests.get(url, auth=auth, timeout=8)
                if r.status_code == 200:
                    state = r.json().get('state')
                    run_states[run_id] = state
                    if state in ('success', 'failed'):
                        pending_runs.remove(run_id)
                elif r.status_code == 404:
                    pass
            except Exception as e:
                logging.warning(f"Aviso transitório ao verificar DAG run {run_id}: {e}")
                
        if not pending_runs:
            break
            
        time.sleep(poll_interval)
        
    all_finished = (len(pending_runs) == 0)
    return all_finished, run_states

def wait_for_dag_discovery(dag_id, max_wait=120, poll_interval=3):
    """Aguarda até que o Airflow descubra e disponibilize uma DAG recém-gerada."""
    import time
    airflow_url = get_airflow_url()
    auth = get_airflow_auth()
    dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
    start = time.time()
    while (time.time() - start) < max_wait:
        try:
            url = f"{airflow_url}/api/v1/dags/{dag_id_quoted}"
            r = requests.get(url, auth=auth, timeout=5)
            r = requests.get(url, auth=auth, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(poll_interval)
    return False

def wait_for_dags(dags_list, max_wait=1800, poll_interval=4):
    """Aguarda até que todas as DAGs na lista terminem execuções ativas."""
    import time
    airflow_url = get_airflow_url()
    auth = get_airflow_auth()
    start = time.time()
    time.sleep(3)
    consecutive_errors = 0
    while (time.time() - start) < max_wait:
        all_done = True
        for did in set(dags_list):
            try:
                url = f"{airflow_url}/api/v1/dags/{did}/dagRuns?order_by=-execution_date&limit=30"
                r = requests.get(url, auth=auth, timeout=5)
                if r.status_code == 200:
                    consecutive_errors = 0
                    runs = r.json().get('dag_runs', [])
                    active = [run for run in runs if run.get('state') in ('running', 'queued')]
                    if active:
                        all_done = False
                        break
                else:
                    consecutive_errors += 1
                    if consecutive_errors > 8:
                        all_done = True
                        break
            except Exception:
                consecutive_errors += 1
                if consecutive_errors > 8:
                    all_done = True
                    break
        if all_done:
            break
        time.sleep(poll_interval)


