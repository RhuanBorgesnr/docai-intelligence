"""
Omie ERP Connector.

Implements all API calls to Omie ERP using their JSON API.
Omie API docs: https://developer.omie.com.br/service-list/

All Omie endpoints use POST with JSON body containing:
- call: method name
- app_key: authentication key
- app_secret: authentication secret
- param: list of parameters
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import BaseERPConnector, ERPResponse

logger = logging.getLogger(__name__)

# Omie API base URL
OMIE_API_BASE = "https://app.omie.com.br/api/v1"

# Rate limiting: Omie allows ~3 requests/second
OMIE_MIN_INTERVAL_SECONDS = 0.34


class OmieConnector(BaseERPConnector):
    """
    Connector for Omie ERP API.
    
    Omie uses a unique API pattern where all endpoints are POST requests
    with a JSON body containing the method name and parameters.
    """

    def __init__(self, app_key: str, app_secret: str, **kwargs):
        super().__init__(app_key, app_secret, **kwargs)
        self._last_request_time = 0.0
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        """Build HTTP session with retry policy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.headers.update({"Content-Type": "application/json"})
        return session

    def _rate_limit(self):
        """Enforce Omie rate limit (~3 req/s)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < OMIE_MIN_INTERVAL_SECONDS:
            time.sleep(OMIE_MIN_INTERVAL_SECONDS - elapsed)
        self._last_request_time = time.time()

    def _call(self, endpoint: str, method: str, params: list[dict]) -> ERPResponse:
        """
        Execute a call to Omie API.
        
        Args:
            endpoint: API endpoint path (e.g., "financas/contapagar/")
            method: API method name (e.g., "IncluirContaPagar")
            params: List of parameter dicts
        """
        url = f"{OMIE_API_BASE}/{endpoint}"
        payload = {
            "call": method,
            "app_key": self.app_key,
            "app_secret": self.app_secret,
            "param": params,
        }

        self._rate_limit()

        try:
            response = self._session.post(url, json=payload, timeout=30)
            data = response.json()

            # Omie returns errors in faultstring/faultcode fields
            if "faultstring" in data or "faultcode" in data:
                error_msg = data.get("faultstring", "Unknown error")
                error_code = data.get("faultcode", "")
                logger.warning(
                    "Omie API error: %s (code: %s) - endpoint: %s/%s",
                    error_msg, error_code, endpoint, method,
                )
                return ERPResponse(
                    success=False,
                    error_code=str(error_code),
                    error_message=error_msg,
                    raw_response=data,
                )

            return ERPResponse(
                success=True,
                data=data,
                raw_response=data,
            )

        except requests.exceptions.Timeout:
            logger.error("Omie API timeout: %s/%s", endpoint, method)
            return ERPResponse(
                success=False,
                error_code="TIMEOUT",
                error_message=f"Timeout calling {endpoint}/{method}",
            )
        except requests.exceptions.ConnectionError as e:
            logger.error("Omie API connection error: %s", str(e))
            return ERPResponse(
                success=False,
                error_code="CONNECTION_ERROR",
                error_message=str(e),
            )
        except requests.exceptions.JSONDecodeError:
            logger.error("Omie API invalid JSON response: %s/%s", endpoint, method)
            return ERPResponse(
                success=False,
                error_code="INVALID_JSON",
                error_message="Response is not valid JSON",
            )

    # --- Connection Test ---

    def test_connection(self) -> ERPResponse:
        """Test connection by listing companies (lightweight call)."""
        result = self._call(
            "geral/empresas/",
            "ListarEmpresas",
            [{"pagina": 1, "registros_por_pagina": 1}],
        )
        if result.success:
            result.entity_id = "connection_ok"
        return result

    # --- Contas a Pagar ---

    def criar_conta_pagar(self, data: dict[str, Any]) -> ERPResponse:
        """
        Create accounts payable entry in Omie.
        
        Required fields in data:
            - codigo_lancamento_integracao: unique integration code
            - codigo_cliente_fornecedor: Omie client/supplier code
            - data_vencimento: due date (dd/mm/yyyy)
            - valor_documento: document value
            - codigo_categoria: category code
            - data_previsao: expected payment date (dd/mm/yyyy)
        """
        result = self._call(
            "financas/contapagar/",
            "IncluirContaPagar",
            [data],
        )
        if result.success and result.data:
            result.entity_id = str(result.data.get("codigo_lancamento_omie", ""))
        return result

    def consultar_conta_pagar(self, erp_id: str) -> ERPResponse:
        """Query accounts payable by Omie ID."""
        return self._call(
            "financas/contapagar/",
            "ConsultarContaPagar",
            [{"codigo_lancamento_omie": int(erp_id)}],
        )

    def listar_contas_pagar(self, filters: dict | None = None) -> ERPResponse:
        """List accounts payable with optional filters."""
        params = {"pagina": 1, "registros_por_pagina": 50}
        if filters:
            params.update(filters)
        return self._call(
            "financas/contapagar/",
            "ListarContasPagar",
            [params],
        )

    # --- Contas a Receber ---

    def criar_conta_receber(self, data: dict[str, Any]) -> ERPResponse:
        """
        Create accounts receivable entry in Omie.
        
        Required fields in data:
            - codigo_lancamento_integracao: unique integration code
            - codigo_cliente_fornecedor: Omie client code
            - data_vencimento: due date (dd/mm/yyyy)
            - valor_documento: document value
            - codigo_categoria: category code
            - data_previsao: expected receipt date (dd/mm/yyyy)
        """
        result = self._call(
            "financas/contareceber/",
            "IncluirContaReceber",
            [data],
        )
        if result.success and result.data:
            result.entity_id = str(result.data.get("codigo_lancamento_omie", ""))
        return result

    def consultar_conta_receber(self, erp_id: str) -> ERPResponse:
        """Query accounts receivable by Omie ID."""
        return self._call(
            "financas/contareceber/",
            "ConsultarContaReceber",
            [{"codigo_lancamento_omie": int(erp_id)}],
        )

    def listar_contas_receber(self, filters: dict | None = None) -> ERPResponse:
        """List accounts receivable with optional filters."""
        params = {"pagina": 1, "registros_por_pagina": 50}
        if filters:
            params.update(filters)
        return self._call(
            "financas/contareceber/",
            "ListarContasReceber",
            [params],
        )

    # --- Clientes/Fornecedores ---

    def criar_cliente(self, data: dict[str, Any]) -> ERPResponse:
        """
        Create client/supplier in Omie.
        
        Required fields in data:
            - codigo_cliente_integracao: unique integration code
            - razao_social: company name
            - cnpj_cpf: CNPJ or CPF
        """
        result = self._call(
            "geral/clientes/",
            "IncluirCliente",
            [data],
        )
        if result.success and result.data:
            result.entity_id = str(result.data.get("codigo_cliente_omie", ""))
        return result

    def consultar_cliente(self, erp_id: str) -> ERPResponse:
        """Query client by Omie ID."""
        return self._call(
            "geral/clientes/",
            "ConsultarCliente",
            [{"codigo_cliente_omie": int(erp_id)}],
        )

    def pesquisar_cliente_por_cnpj(self, cnpj: str) -> ERPResponse:
        """Search client by CNPJ/CPF."""
        # Omie uses ListarClientes with filter
        result = self._call(
            "geral/clientes/",
            "ListarClientes",
            [{"pagina": 1, "registros_por_pagina": 5, "clientesFiltro": {"cnpj_cpf": cnpj}}],
        )
        if result.success and result.data:
            clientes = result.data.get("clientes_cadastro", [])
            if clientes:
                result.entity_id = str(clientes[0].get("codigo_cliente_omie", ""))
        return result

    # --- Notas Fiscais ---

    def consultar_nf(self, nf_id: str) -> ERPResponse:
        """Query fiscal note by Omie ID."""
        return self._call(
            "produtos/nfconsultar/",
            "ConsultarNF",
            [{"nCodNF": int(nf_id)}],
        )

    def listar_nfs(self, filters: dict | None = None) -> ERPResponse:
        """List fiscal notes."""
        params = {"pagina": 1, "registros_por_pagina": 50}
        if filters:
            params.update(filters)
        return self._call(
            "produtos/nfconsultar/",
            "ListarNF",
            [params],
        )

    # --- Categorias (helper) ---

    def listar_categorias(self) -> ERPResponse:
        """List available categories (needed for conta_pagar/receber)."""
        return self._call(
            "geral/categorias/",
            "ListarCategorias",
            [{"pagina": 1, "registros_por_pagina": 500}],
        )

    # --- Contas Correntes (helper) ---

    def listar_contas_correntes(self) -> ERPResponse:
        """List bank accounts."""
        return self._call(
            "geral/contacorrente/",
            "ListarContasCorrentes",
            [{"pagina": 1, "registros_por_pagina": 50}],
        )

    # --- Idempotency helper ---

    @staticmethod
    def generate_integration_code(prefix: str, unique_data: str) -> str:
        """
        Generate a deterministic integration code for idempotency.
        Same input always produces same code — safe for retry.
        """
        hash_input = f"{prefix}:{unique_data}"
        return f"{prefix}_{hashlib.sha256(hash_input.encode()).hexdigest()[:16]}"
