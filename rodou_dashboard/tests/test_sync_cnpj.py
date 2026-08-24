import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add rodou_dashboard to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.sync_cnpj import get_monitored_data, formatar_cnpj

class TestSyncCnpj(unittest.TestCase):

    def test_formatar_cnpj(self):
        self.assertEqual(formatar_cnpj("12345678000195"), "12.345.678/0001-95")
        self.assertEqual(formatar_cnpj("12.345.678/0001-95"), "12.345.678/0001-95")
        self.assertIsNone(formatar_cnpj(None))

    @patch('app.services.sync_cnpj.time.sleep', return_value=None)
    @patch('requests.Session.get')
    def test_get_monitored_data_multi_page(self, mock_get, mock_sleep):
        # Setup 3 pages of mock data
        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.json.return_value = {
            "data": [
                {"razao_social": "Empresa 1", "cnpj": "11.111.111/0001-11", "ativo": "1"},
                {"razao_social": "Empresa 2", "cnpj": "22.222.222/0001-22", "ativo": "1"}
            ],
            "meta": {"total_paginas": 3, "proxima_pagina": 2}
        }

        page2_resp = MagicMock()
        page2_resp.status_code = 200
        page2_resp.json.return_value = {
            "data": [
                {"razao_social": "Empresa 3", "cnpj": "33.333.333/0001-33", "ativo": "1"}
            ],
            "meta": {"total_paginas": 3, "proxima_pagina": 3}
        }

        page3_resp = MagicMock()
        page3_resp.status_code = 200
        page3_resp.json.return_value = {
            "data": [
                {"razao_social": "Empresa 4", "cnpj": "44.444.444/0001-44", "ativo": "0"}
            ],
            "meta": {"total_paginas": 3, "proxima_pagina": None}
        }

        mock_get.side_effect = [page1_resp, page2_resp, page3_resp]

        headers = {"access-token": "abc", "secret-access-token": "xyz"}
        results = get_monitored_data("https://api.gestaoclick.com/franquias", "clientes", headers)

        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["nome"], "Empresa 1")
        self.assertEqual(results[0]["cnpj"], "11.111.111/0001-11")
        self.assertTrue(results[0]["status"])
        self.assertEqual(results[3]["nome"], "Empresa 4")
        self.assertFalse(results[3]["status"])
        self.assertEqual(mock_get.call_count, 3)

    @patch('app.services.sync_cnpj.time.sleep', return_value=None)
    @patch('requests.Session.get')
    def test_get_monitored_data_empty_page_termination(self, mock_get, mock_sleep):
        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.json.return_value = {
            "data": [
                {"razao_social": "Empresa A", "cnpj": "12345678000195", "ativo": "1"}
            ],
            "meta": {}
        }

        page2_resp = MagicMock()
        page2_resp.status_code = 200
        page2_resp.json.return_value = {
            "data": [],
            "meta": {}
        }

        mock_get.side_effect = [page1_resp, page2_resp]

        headers = {"access-token": "abc", "secret-access-token": "xyz"}
        results = get_monitored_data("https://api.gestaoclick.com/franquias", "clientes", headers)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["cnpj"], "12.345.678/0001-95")
    @patch('app.services.sync_cnpj.time.sleep', return_value=None)
    @patch('requests.Session.get')
    def test_get_monitored_data_url_next_page(self, mock_get, mock_sleep):
        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.json.return_value = {
            "data": [{"razao_social": "Empresa X", "cnpj": "12345678000195", "ativo": "1"}],
            "meta": {"proxima_pagina": "https://api.gestaoclick.com/franquias/clientes?pagina=2"}
        }

        page2_resp = MagicMock()
        page2_resp.status_code = 200
        page2_resp.json.return_value = {
            "data": [{"razao_social": "Empresa Y", "cnpj": "98765432000100", "ativo": "1"}],
            "meta": {"proxima_pagina": None}
        }

        page3_resp = MagicMock()
        page3_resp.status_code = 200
        page3_resp.json.return_value = {
            "data": [],
            "meta": {}
        }

        mock_get.side_effect = [page1_resp, page2_resp, page3_resp]

        headers = {"access-token": "abc", "secret-access-token": "xyz"}
        results = get_monitored_data("https://api.gestaoclick.com/franquias", "clientes", headers)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["nome"], "Empresa X")
        self.assertEqual(results[1]["nome"], "Empresa Y")

    @patch('app.services.sync_cnpj.time.sleep', return_value=None)
    @patch('requests.Session.get')
    def test_get_monitored_data_404_termination(self, mock_get, mock_sleep):
        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.json.return_value = {
            "data": [{"razao_social": "Empresa X", "cnpj": "12345678000195", "ativo": "1"}]
        }

        page2_resp = MagicMock()
        page2_resp.status_code = 404

        mock_get.side_effect = [page1_resp, page2_resp]

        headers = {"access-token": "abc", "secret-access-token": "xyz"}
        results = get_monitored_data("https://api.gestaoclick.com/franquias", "clientes", headers)

        self.assertEqual(len(results), 1)

if __name__ == '__main__':
    unittest.main()
