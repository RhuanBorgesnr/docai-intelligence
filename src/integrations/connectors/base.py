"""
Base ERP Connector — abstract interface for all ERP integrations.
Each ERP implements this interface (Omie, Bling, TOTVS, etc).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass
class ERPResponse:
    """Standardized response from any ERP operation."""

    success: bool
    entity_id: str = ""
    data: dict | None = None
    error_code: str = ""
    error_message: str = ""
    raw_response: dict | None = None

    @property
    def failed(self) -> bool:
        return not self.success


class BaseERPConnector(abc.ABC):
    """
    Abstract base for ERP connectors.
    
    Each connector must implement CRUD operations for the supported entities.
    All methods return ERPResponse for uniform handling.
    """

    def __init__(self, app_key: str, app_secret: str, **kwargs):
        self.app_key = app_key
        self.app_secret = app_secret

    @abc.abstractmethod
    def test_connection(self) -> ERPResponse:
        """Test if the connection credentials are valid."""
        ...

    # --- Contas a Pagar ---
    @abc.abstractmethod
    def criar_conta_pagar(self, data: dict[str, Any]) -> ERPResponse:
        """Create an accounts payable entry."""
        ...

    @abc.abstractmethod
    def consultar_conta_pagar(self, erp_id: str) -> ERPResponse:
        """Query an accounts payable entry by ERP ID."""
        ...

    @abc.abstractmethod
    def listar_contas_pagar(self, filters: dict | None = None) -> ERPResponse:
        """List accounts payable entries."""
        ...

    # --- Contas a Receber ---
    @abc.abstractmethod
    def criar_conta_receber(self, data: dict[str, Any]) -> ERPResponse:
        """Create an accounts receivable entry."""
        ...

    @abc.abstractmethod
    def consultar_conta_receber(self, erp_id: str) -> ERPResponse:
        """Query an accounts receivable entry by ERP ID."""
        ...

    @abc.abstractmethod
    def listar_contas_receber(self, filters: dict | None = None) -> ERPResponse:
        """List accounts receivable entries."""
        ...

    # --- Clientes/Fornecedores ---
    @abc.abstractmethod
    def criar_cliente(self, data: dict[str, Any]) -> ERPResponse:
        """Create a client/supplier."""
        ...

    @abc.abstractmethod
    def consultar_cliente(self, erp_id: str) -> ERPResponse:
        """Query a client by ERP ID."""
        ...

    @abc.abstractmethod
    def pesquisar_cliente_por_cnpj(self, cnpj: str) -> ERPResponse:
        """Search client by CNPJ/CPF."""
        ...

    # --- Notas Fiscais ---
    @abc.abstractmethod
    def consultar_nf(self, nf_id: str) -> ERPResponse:
        """Query a fiscal note."""
        ...

    @abc.abstractmethod
    def listar_nfs(self, filters: dict | None = None) -> ERPResponse:
        """List fiscal notes."""
        ...
